package com.opennxt.net.js5

import com.opennxt.net.PreLoginForensics
import com.opennxt.net.js5.packet.Js5Packet
import com.opennxt.tools.impl.cachedownloader.Js5ClientPipeline
import io.netty.bootstrap.Bootstrap
import io.netty.buffer.ByteBuf
import io.netty.channel.Channel
import io.netty.channel.ChannelHandlerContext
import io.netty.channel.ChannelInitializer
import io.netty.channel.ChannelOption
import io.netty.channel.nio.NioEventLoopGroup
import io.netty.channel.socket.SocketChannel
import io.netty.channel.socket.nio.NioSocketChannel
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging
import java.net.InetSocketAddress
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * Mirrors the retail logged-out JS5 wire stream byte-for-byte after the initial client handshake.
 *
 * The 947 client appears to care about the exact ordering/chunking of the startup 255-slash-star burst.
 * Rebuilding those responses archive-by-archive is close, but not identical enough to reach login.
 */
class RetailLoggedOutJs5Proxy(
    private val localChannel: Channel,
    private val major: Int,
    private val minor: Int,
    private val token: String,
    private val language: Int,
) : AutoCloseable {
    private val logger = KotlinLogging.logger { }
    private data class RequestKey(val priority: Boolean, val index: Int, val archive: Int)
    private val lock = Any()
    private val pendingClientWrites = ArrayDeque<ByteBuf>()
    private val workerGroup = NioEventLoopGroup(1)
    private val bootstrap = Bootstrap()
    private val forwardedRequestCounts = ConcurrentHashMap<RequestKey, AtomicInteger>()

    @Volatile
    private var remoteChannel: Channel? = null

    @Volatile
    private var remoteReady = false

    @Volatile
    private var closed = false

    @Volatile
    private var queuedClientChunks = 0

    @Volatile
    private var queuedClientBytes = 0L

    @Volatile
    private var forwardedClientChunks = 0

    @Volatile
    private var forwardedClientBytes = 0L

    @Volatile
    private var forwardedRemoteChunks = 0

    @Volatile
    private var forwardedRemoteBytes = 0L

    init {
        bootstrap.group(workerGroup)
            .channel(NioSocketChannel::class.java)
            .option(ChannelOption.TCP_NODELAY, true)
            .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 10_000)
            .handler(object : ChannelInitializer<SocketChannel>() {
                override fun initChannel(ch: SocketChannel) {
                    ch.pipeline().addLast("encoder", Js5ClientPipeline.Js5ClientEncoder())
                    ch.pipeline().addLast("bridge-decoder", RemoteBridgeHandler())
                }
            })
    }

    private fun record(event: String, details: Map<String, Any?> = emptyMap()) {
        val localPort = (localChannel.localAddress() as? InetSocketAddress)?.port ?: -1
        PreLoginForensics.recordTransportEvent(
            localPort = localPort,
            remoteAddress = localChannel.remoteAddress().toString(),
            event = event,
            details = details,
        )
    }

    private fun ByteBuf.previewHex(limit: Int = 32): String {
        val length = minOf(readableBytes(), limit)
        if (length <= 0) {
            return "<empty>"
        }

        val bytes = ByteArray(length)
        getBytes(readerIndex(), bytes)
        return bytes.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun ByteBuf.decodeRequestSummary(limit: Int = 8): String? {
        if (!isReadable) {
            return null
        }

        val parts = mutableListOf<String>()
        var offset = readerIndex()
        val end = writerIndex()

        while (offset < end && parts.size < limit) {
            val remaining = end - offset
            val opcode = getUnsignedByte(offset).toInt()
            when (opcode) {
                0, 1, 17, 32, 33 -> {
                    if (remaining < 10) {
                        parts += "truncated-request(op=$opcode remaining=$remaining)"
                        break
                    }
                    val index = getUnsignedByte(offset + 1).toInt()
                    val archive = getInt(offset + 2)
                    val build = getUnsignedShort(offset + 6).toInt()
                    val priority = opcode == 1 || opcode == 17 || opcode == 33
                    val nxt = opcode == 17 || opcode == 32 || opcode == 33
                    forwardedRequestCounts.computeIfAbsent(RequestKey(priority, index, archive)) {
                        AtomicInteger(0)
                    }.incrementAndGet()
                    parts += "req(op=$opcode idx=$index arc=$archive build=$build pri=$priority nxt=$nxt)"
                    offset += 10
                }

                2, 3, 6, 7 -> {
                    if (remaining < 10) {
                        parts += "truncated-control(op=$opcode remaining=$remaining)"
                        break
                    }
                    parts += "ctrl(op=$opcode)"
                    offset += 10
                }

                4 -> {
                    if (remaining < 9) {
                        parts += "truncated-xor(remaining=$remaining)"
                        break
                    }
                    parts += "xor(${getUnsignedByte(offset + 1).toInt()})"
                    offset += 9
                }

                else -> {
                    parts += "unknown(op=$opcode remaining=$remaining)"
                    break
                }
            }
        }

        return if (parts.isEmpty()) null else parts.joinToString("; ")
    }

    private fun topForwardedRequests(limit: Int = 8): String {
        if (forwardedRequestCounts.isEmpty()) {
            return ""
        }

        val topEntries = ArrayList<Map.Entry<RequestKey, AtomicInteger>>(limit)
        for (entry in forwardedRequestCounts.entries) {
            topEntries += entry
        }
        topEntries.sortWith(object : Comparator<Map.Entry<RequestKey, AtomicInteger>> {
            override fun compare(
                left: Map.Entry<RequestKey, AtomicInteger>,
                right: Map.Entry<RequestKey, AtomicInteger>,
            ): Int {
                return right.value.get().compareTo(left.value.get())
            }
        })

        return topEntries
            .take(limit)
            .joinToString(", ") { entry ->
                val key = entry.key
                "idx=${key.index}/arc=${key.archive}/pri=${key.priority} x${entry.value.get()}"
            }
    }

    fun connect() {
        record(
            event = "js5-retail-proxy-activating",
            details = mapOf(
                "build" to "$major.$minor",
                "language" to language,
            ),
        )
        bootstrap.connect(RETAIL_HOST, RETAIL_PORT).addListener { future ->
            if (!future.isSuccess) {
                logger.warn(future.cause()) {
                    "Failed to connect retail logged-out JS5 proxy for ${localChannel.remoteAddress()}"
                }
                record(
                    event = "js5-retail-proxy-connect-failed",
                    details = mapOf("message" to future.cause()?.message),
                )
                closeLocalChannel()
                close()
            }
        }
    }

    fun forwardClientBytes(data: ByteBuf) {
        if (closed) {
            data.release()
            return
        }

        val bytes = data.readableBytes()
        val preview = data.previewHex()
        val requestSummary = data.decodeRequestSummary()

        synchronized(lock) {
            val remote = remoteChannel
            if (remoteReady && remote != null && remote.isActive) {
                forwardedClientChunks += 1
                forwardedClientBytes += bytes.toLong()
                if (forwardedClientChunks <= 8 || forwardedClientChunks % 16 == 0) {
                    record(
                        event = "js5-retail-proxy-client-forwarded",
                        details = mapOf(
                            "chunks" to forwardedClientChunks,
                            "bytes" to bytes,
                            "totalBytes" to forwardedClientBytes,
                            "previewHex" to preview,
                            "requestSummary" to requestSummary,
                        ),
                    )
                }
                remote.writeAndFlush(data)
                return
            }

            queuedClientChunks += 1
            queuedClientBytes += bytes.toLong()
            if (queuedClientChunks <= 8 || queuedClientChunks % 16 == 0) {
                record(
                    event = "js5-retail-proxy-client-queued",
                    details = mapOf(
                        "chunks" to queuedClientChunks,
                        "bytes" to bytes,
                        "totalBytes" to queuedClientBytes,
                        "previewHex" to preview,
                        "requestSummary" to requestSummary,
                    ),
                )
            }
            pendingClientWrites.addLast(data)
        }
    }

    override fun close() {
        if (closed) {
            return
        }
        closed = true

        synchronized(lock) {
            while (pendingClientWrites.isNotEmpty()) {
                pendingClientWrites.removeFirst().release()
            }
        }

        record(
            event = "js5-retail-proxy-close-summary",
            details = mapOf(
                "queuedClientChunks" to queuedClientChunks,
                "queuedClientBytes" to queuedClientBytes,
                "forwardedClientChunks" to forwardedClientChunks,
                "forwardedClientBytes" to forwardedClientBytes,
                "forwardedRemoteChunks" to forwardedRemoteChunks,
                "forwardedRemoteBytes" to forwardedRemoteBytes,
                "remoteReady" to remoteReady,
                "localActive" to localChannel.isActive,
                "topForwardedRequests" to topForwardedRequests(),
            ),
        )

        remoteChannel?.close()
        workerGroup.shutdownGracefully()
    }

    private fun flushPendingClientWrites() {
        synchronized(lock) {
            val remote = remoteChannel
            if (!remoteReady || remote == null || !remote.isActive) {
                return
            }

            var flushedChunks = 0
            var flushedBytes = 0L
            while (pendingClientWrites.isNotEmpty()) {
                val pending = pendingClientWrites.removeFirst()
                val bytes = pending.readableBytes()
                flushedChunks += 1
                flushedBytes += bytes.toLong()
                forwardedClientChunks += 1
                forwardedClientBytes += bytes.toLong()
                if (forwardedClientChunks <= 8 || forwardedClientChunks % 16 == 0) {
                    record(
                        event = "js5-retail-proxy-client-forwarded",
                        details = mapOf(
                            "chunks" to forwardedClientChunks,
                            "bytes" to bytes,
                            "totalBytes" to forwardedClientBytes,
                            "source" to "flush-pending",
                            "previewHex" to pending.previewHex(),
                            "requestSummary" to pending.decodeRequestSummary(),
                        ),
                    )
                }
                remote.write(pending)
            }
            remote.flush()
            if (flushedChunks > 0) {
                record(
                    event = "js5-retail-proxy-client-flush",
                    details = mapOf(
                        "chunks" to flushedChunks,
                        "bytes" to flushedBytes,
                        "totalForwardedBytes" to forwardedClientBytes,
                    ),
                )
            }
        }
    }

    private fun closeLocalChannel() {
        localChannel.eventLoop().execute {
            if (localChannel.isActive) {
                localChannel.close()
            }
        }
    }

    private inner class RemoteBridgeHandler : ByteToMessageDecoder() {
        private var awaitingHandshakeResponse = true

        override fun channelActive(ctx: ChannelHandlerContext) {
            remoteChannel = ctx.channel()
            record(event = "js5-retail-proxy-connected")
            ctx.writeAndFlush(Js5Packet.Handshake(major, minor, token, language))
        }

        override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
            if (awaitingHandshakeResponse) {
                if (!buf.isReadable) {
                    return
                }

                val code = buf.readUnsignedByte().toInt()
                if (code != 0) {
                    logger.warn {
                        "Retail logged-out JS5 proxy handshake was rejected with code=$code " +
                            "for ${localChannel.remoteAddress()}"
                    }
                    record(
                        event = "js5-retail-proxy-handshake-rejected",
                        details = mapOf("code" to code),
                    )
                    closeLocalChannel()
                    ctx.close()
                    return
                }

                awaitingHandshakeResponse = false
                remoteReady = true
                record(event = "js5-retail-proxy-ready")
                ctx.write(Js5Packet.ConnectionInitialized(5, major))
                ctx.write(Js5Packet.LoggedOut(major))
                ctx.flush()
                flushPendingClientWrites()
            }

            if (!buf.isReadable) {
                return
            }

            val bytes = buf.readableBytes()
            forwardedRemoteChunks += 1
            forwardedRemoteBytes += bytes.toLong()
            if (forwardedRemoteChunks <= 8 || forwardedRemoteChunks % 16 == 0) {
                record(
                    event = "js5-retail-proxy-remote-forwarded",
                    details = mapOf(
                        "chunks" to forwardedRemoteChunks,
                        "bytes" to bytes,
                        "totalBytes" to forwardedRemoteBytes,
                        "previewHex" to buf.previewHex(),
                    ),
                )
            }
            val payload = buf.readRetainedSlice(buf.readableBytes())
            if (!localChannel.isActive) {
                payload.release()
                return
            }
            localChannel.writeAndFlush(payload)
        }

        override fun channelInactive(ctx: ChannelHandlerContext) {
            record(event = "js5-retail-proxy-remote-inactive")
            closeLocalChannel()
            close()
        }

        override fun exceptionCaught(ctx: ChannelHandlerContext, cause: Throwable) {
            logger.warn(cause) { "Retail logged-out JS5 proxy crashed for ${localChannel.remoteAddress()}" }
            record(
                event = "js5-retail-proxy-exception",
                details = mapOf(
                    "errorType" to cause::class.java.name,
                    "message" to cause.message,
                ),
            )
            closeLocalChannel()
            ctx.close()
            close()
        }
    }

    companion object {
        private const val RETAIL_HOST = "content.runescape.com"
        private const val RETAIL_PORT = 43594
    }
}
