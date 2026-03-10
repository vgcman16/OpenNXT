package com.opennxt.net.js5

import com.opennxt.Js5Thread
import com.opennxt.OpenNXT
import com.opennxt.filesystem.Container
import com.opennxt.filesystem.Filesystem
import com.opennxt.net.js5.packet.Js5Packet
import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.Channel
import io.netty.util.AttributeKey
import mu.KotlinLogging
import java.nio.ByteBuffer
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger

class Js5Session(val channel: Channel) : AutoCloseable {

    private val logger = KotlinLogging.logger { }

    private data class ArchiveKey(val index: Int, val archive: Int)

    companion object {
        val ATTR_KEY = AttributeKey.valueOf<Js5Session>("js5-session")
        val XOR_KEY = AttributeKey.valueOf<Int>("js5-xor-key")
        val LOGGED_IN = AttributeKey.valueOf<Boolean>("js5-logged-in")
        private val NEXT_ID = AtomicInteger(0)
    }

    val id = NEXT_ID.incrementAndGet()
    val highPriorityRequests = ConcurrentLinkedQueue<Js5Packet.RequestFile>()
    val lowPriorityRequests = ConcurrentLinkedQueue<Js5Packet.RequestFile>()

    var initialized = false
    private var requestSequence = 0
    private var responseSequence = 0
    private var inboundTraceSequence = 0
    private val requestOccurrences = ConcurrentHashMap<ArchiveKey, AtomicInteger>()
    private val responseOccurrences = ConcurrentHashMap<ArchiveKey, AtomicInteger>()

    init {
        channel.attr(ATTR_KEY).set(this)
        channel.attr(XOR_KEY).set(0)
        channel.attr(LOGGED_IN).set(false)
    }

    private fun Js5Packet.RequestFile.loadFileData(): ByteBuf? {
        try {
            return when {
                index == 255 && archive == 255 -> Unpooled.wrappedBuffer(OpenNXT.checksumTable)
                index == 255 -> Unpooled.wrappedBuffer(OpenNXT.filesystem.readReferenceTable(archive) ?: return null)
                else -> {
                    val raw = OpenNXT.filesystem.read(index, archive) ?: return null
                    Unpooled.wrappedBuffer(stripVersionTrailer(raw))
                }
            }
        } catch (e: Exception) {
            return null
        }
    }

    private fun stripVersionTrailer(raw: ByteBuffer): ByteArray {
        val bytes = ByteArray(raw.remaining())
        raw.duplicate().get(bytes)

        // Cache files are stored with a trailing 2-byte archive version. Live JS5 strips that trailer
        // when serving non-255 archives, so mirror that wire format for native clients.
        val version = Container.decode(ByteBuffer.wrap(bytes)).version
        if (version == -1 || bytes.size < 2) {
            return bytes
        }
        return bytes.copyOf(bytes.size - 2)
    }

    private fun describeRequest(request: Js5Packet.RequestFile): String = when {
        request.index == 255 && request.archive == 255 -> "master-reference-table(index=255, archive=255)"
        request.index == 255 -> "reference-table(index=255, archive=${request.archive})"
        else -> "archive(index=${request.index}, archive=${request.archive})"
    }

    private fun shouldTraceOccurrence(occurrence: Int): Boolean {
        return occurrence <= 3 || occurrence == 5 || occurrence == 10 || occurrence == 25 || occurrence % 50 == 0
    }

    private fun shouldTraceRequest(request: Js5Packet.RequestFile, occurrence: Int): Boolean {
        return requestSequence <= 64 || request.index == 255 || request.archive == 255 || shouldTraceOccurrence(occurrence)
    }

    private fun shouldTraceResponse(request: Js5Packet.RequestFile, occurrence: Int): Boolean {
        return responseSequence <= 64 || request.index == 255 || request.archive == 255 || shouldTraceOccurrence(occurrence)
    }

    private fun Js5Packet.RequestFile.archiveKey(): ArchiveKey = ArchiveKey(index, archive)

    private fun describeAvailability(request: Js5Packet.RequestFile): String = when {
        request.index == 255 && request.archive == 255 -> "available=checksum-table"
        request.index == 255 -> "available=${OpenNXT.filesystem.readReferenceTable(request.archive) != null}"
        else -> "available=${OpenNXT.filesystem.exists(request.index, request.archive)}"
    }

    private fun topRequestSummary(
        occurrences: ConcurrentHashMap<ArchiveKey, AtomicInteger>,
        limit: Int = 8
    ): String {
        return occurrences.entries
            .sortedByDescending { it.value.get() }
            .take(limit)
            .joinToString(separator = ", ") { entry ->
                "index=${entry.key.index}/archive=${entry.key.archive} x${entry.value.get()}"
            }
    }

    fun traceInboundBytes(stage: String, buf: ByteBuf, handshakeDecoded: Boolean) {
        inboundTraceSequence++

        if (inboundTraceSequence > 24) {
            return
        }

        val readable = buf.readableBytes()
        val previewLength = minOf(readable, 32)
        val preview = ByteArray(previewLength)
        if (previewLength > 0) {
            buf.getBytes(buf.readerIndex(), preview)
        }

        logger.info {
            "JS5 raw inbound session#$id read#$inboundTraceSequence from ${channel.remoteAddress()}: " +
                "stage=$stage, handshakeDecoded=$handshakeDecoded, readable=$readable, " +
                "preview=${preview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }}"
        }
    }

    fun enqueueRequest(request: Js5Packet.RequestFile, opcode: Int) {
        requestSequence++
        val occurrence = requestOccurrences.computeIfAbsent(request.archiveKey()) { AtomicInteger() }.incrementAndGet()

        if (shouldTraceRequest(request, occurrence)) {
            logger.info {
                "Queued js5 request #$requestSequence from ${channel.remoteAddress()}: " +
                    "opcode=$opcode, priority=${request.priority}, nxt=${request.nxt}, " +
                    "build=${request.build}, occurrence=$occurrence, ${describeRequest(request)}, ${describeAvailability(request)}"
            }
        }

        if (request.priority) highPriorityRequests.add(request)
        else lowPriorityRequests.add(request)

        Js5Thread.wake()
    }

    fun process(limit: Int): Int {
        var bytesSent = 0

        try {
            while (bytesSent < limit && highPriorityRequests.isNotEmpty()) {
                val request = highPriorityRequests.poll()
                val data = request.loadFileData()
                if (data == null) {
                    logger.warn {
                        "JS5 missing file for high-priority request from ${channel.remoteAddress()}: " +
                            "${describeRequest(request)}, ${describeAvailability(request)}"
                    }
                } else {
                    responseSequence++
                    val occurrence = responseOccurrences.computeIfAbsent(request.archiveKey()) { AtomicInteger() }
                        .incrementAndGet()
                    if (shouldTraceResponse(request, occurrence)) {
                        logger.info {
                            "Serving js5 response #$responseSequence to ${channel.remoteAddress()}: " +
                                "${describeRequest(request)}, priority=true, occurrence=$occurrence, bytes=${data.readableBytes()}"
                        }
                    }
                    channel.write(Js5Packet.RequestFileResponse(true, request.index, request.archive, data))
                    bytesSent += data.capacity()
                }
            }

            while (bytesSent < limit && lowPriorityRequests.isNotEmpty()) {
                val request = lowPriorityRequests.poll()
                val data = request.loadFileData()
                if (data == null) {
                    logger.warn {
                        "JS5 missing file for low-priority request from ${channel.remoteAddress()}: " +
                            "${describeRequest(request)}, ${describeAvailability(request)}"
                    }
                } else {
                    responseSequence++
                    val occurrence = responseOccurrences.computeIfAbsent(request.archiveKey()) { AtomicInteger() }
                        .incrementAndGet()
                    if (shouldTraceResponse(request, occurrence)) {
                        logger.info {
                            "Serving js5 response #$responseSequence to ${channel.remoteAddress()}: " +
                                "${describeRequest(request)}, priority=false, occurrence=$occurrence, bytes=${data.readableBytes()}"
                        }
                    }
                    channel.write(Js5Packet.RequestFileResponse(false, request.index, request.archive, data))
                    bytesSent += data.capacity()
                }
            }
        } finally {
            if (bytesSent != 0) {
                channel.flush()
            }
        }

        return bytesSent
    }

    fun initialize() {
        if (initialized) {
            logger.warn("Tried initializing js5 session twice from ${channel.remoteAddress()}. Terminating connection.")
            close()
            return
        }

        initialized = true
        Js5Thread.addSession(this)
    }

    override fun close() {
        initialized = false

        logger.info {
            "Closing js5 session#$id from ${channel.remoteAddress()}: " +
                "initialized=$initialized, requests=$requestSequence, responses=$responseSequence, " +
                "rawReads=$inboundTraceSequence, " +
                "topRequests=[${topRequestSummary(requestOccurrences)}], " +
                "topResponses=[${topRequestSummary(responseOccurrences)}]"
        }

        Js5Thread.removeSession(this)

        channel.close()
        highPriorityRequests.clear()
        lowPriorityRequests.clear()
    }
}
