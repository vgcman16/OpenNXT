package com.opennxt.net.game.pipeline

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.ext.isBigOpcode
import com.opennxt.ext.readOpcode
import com.opennxt.util.ISAACCipher
import com.opennxt.net.RSChannelAttributes
import com.opennxt.net.Side
import com.opennxt.net.game.PacketRegistry
import io.netty.buffer.ByteBuf
import io.netty.buffer.ByteBufUtil
import io.netty.channel.Channel
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import it.unimi.dsi.fastutil.ints.Int2IntMap
import mu.KotlinLogging
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.StandardOpenOption
import java.time.Instant

class GamePacketFraming : ByteToMessageDecoder() {
    companion object {
        private val framingDoctorLock = Any()

        private fun framingDoctorPath(): Path =
            Paths.get(
                System.getProperty(
                    "opennxt.lobby.framing.doctor.path",
                    Constants.DATA_PATH.resolve("debug").resolve("lobby-framing-doctor.jsonl").toString()
                )
            )
    }

    private val logger = KotlinLogging.logger { }

    private val protocol = OpenNXT.protocol

    private var inited = false
    private lateinit var isaac: ISAACCipher
    private lateinit var mapping: Int2IntMap
    private lateinit var side: Side

    private var state = State.READ_OPCODE
    private var opcode = -1
    private var size = -1
    private var droppingLobbySocialClientTraffic = false

    private fun bootstrapStage(channel: Channel): String {
        val client = channel.attr(RSChannelAttributes.CONNECTED_CLIENT).get()
        return client?.currentBootstrapStage ?: client?.lastCompletedBootstrapStage ?: "none"
    }

    private fun preview(buf: ByteBuf, limit: Int = 32): String {
        val length = minOf(limit, buf.readableBytes())
        if (length <= 0) {
            return "<empty>"
        }
        return ByteBufUtil.hexDump(buf, buf.readerIndex(), length)
    }

    private fun rawPeek(buf: ByteBuf, limit: Int = 32): String {
        val length = minOf(limit, buf.readableBytes())
        if (length <= 0) {
            return "<empty>"
        }
        return ByteBufUtil.hexDump(buf, buf.readerIndex(), length)
    }

    private fun shouldTraceLobbyDoctor(channel: Channel): Boolean {
        if (side != Side.CLIENT) {
            return false
        }

        return when (bootstrapStage(channel)) {
            "social-state",
            "late-default-varps" -> true
            else -> false
        }
    }

    private fun shouldUseLobbyCompatVarByteFallback(
        channel: Channel,
        opcode: Int,
        encodedSize: Int,
    ): Boolean {
        if (side != Side.CLIENT || bootstrapStage(channel) != "social-state") {
            return false
        }

        // The contained 947 social-state branch has surfaced a real client opcode 0 that the
        // extracted size map reports as var-short, but the observed wire bytes on the local compat
        // path occasionally turn into absurd lengths like 18355 and stall the stream forever.
        // Historical handled-report captures for this family stay well below this threshold, so
        // treat obviously bogus var-short lengths as a compat var-byte form instead.
        return opcode == 0 && encodedSize > 4096
    }

    private fun lobbyCompatClientSizeOverride(channel: Channel, opcode: Int): Int? {
        if (side != Side.CLIENT || bootstrapStage(channel) != "social-state") {
            return null
        }

        return when (opcode) {
            // The contained social-state stream stays aligned only if this compat packet keeps its
            // extra trailing bytes. The generic 947 client map says 12, but the observed lobby form
            // is longer on the contained post-login branch.
            27 -> 14
            // Observed immediately after the contained 27 -> 206 -> 62 -> 109 post-social path.
            // Treat this as a one-byte-length compat packet so we can keep framing instead of
            // dropping the entire lobby stream at the first unresolved big opcode.
            22481,
            30625,
            // Newer contained social-state branch: 27 -> 206 -> 96 -> 30398.
            // This also arrives as an unresolved big opcode and needs the same variable-size
            // treatment so we can observe its body instead of dropping the remainder of the stream.
            30398 -> -1
            else -> null
        }
    }

    private fun lateWorldCompatClientSizeOverride(channel: Channel, opcode: Int): Int? {
        if (side != Side.CLIENT || bootstrapStage(channel) != "late-default-varps") {
            return null
        }

        return when (opcode) {
            // On the contained post-lobby 947 path the late-default-varps branch surfaces client
            // opcode 30 as a four-byte payload (for example 00 00 00 01). The extracted 947 map
            // still reports OPPLAYER10 as size 3, but the local compat path repeatedly stalls if we
            // wait for more than the four payload bytes that actually arrive. Keep this scoped to
            // late-default-varps so we don't globally rewrite the extracted interaction packet size.
            30 -> 4
            else -> null
        }
    }

    private fun lateWorldCompatUnmappedSizeOverride(channel: Channel, opcode: Int): Int? {
        if (side != Side.CLIENT || bootstrapStage(channel) != "late-default-varps") {
            return null
        }

        // Once the contained 947 client survives into late-default-varps it starts surfacing big
        // bootstrap/control opcodes that the extracted map does not know about yet. Treat these as
        // variable-byte packets so we can keep the stream aligned long enough to observe their
        // payloads instead of immediately closing the world socket on first contact.
        return if (opcode >= 128) -1 else null
    }

    private fun lobbyCompatUnmappedSizeOverride(channel: Channel, opcode: Int): Int? {
        if (side != Side.CLIENT || bootstrapStage(channel) != "social-state") {
            return null
        }

        // The contained lobby branch has repeatedly surfaced unresolved big opcodes whose wire form
        // is "big opcode + 1-byte length + payload". Keeping these framed as variable-length
        // packets gives us a stable compat stream instead of dropping the whole post-login lobby
        // session at the first unmapped branch-specific packet.
        if (opcode >= 128) {
            return -1
        }

        return null
    }

    private fun traceLobbyDoctor(
        channel: Channel,
        event: String,
        values: Map<String, Any?>
    ) {
        if (!shouldTraceLobbyDoctor(channel)) {
            return
        }

        val payload = buildString {
            append("{")
            append("\"timestamp\":\"").append(Instant.now()).append('"')
            append(",\"event\":\"").append(event).append('"')
            values.entries.forEachIndexed { index, entry ->
                append(",\"").append(entry.key).append("\":")
                when (val value = entry.value) {
                    null -> append("null")
                    is Number, is Boolean -> append(value.toString())
                    else -> append("\"").append(value.toString().replace("\\", "\\\\").replace("\"", "\\\"")).append("\"")
                }
            }
            append("}")
        }

        synchronized(framingDoctorLock) {
            val path = framingDoctorPath()
            Files.createDirectories(path.parent)
            Files.writeString(
                path,
                payload + "\n",
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            )
        }
    }

    private fun init(channel: Channel) {
        inited = true

        isaac = channel.attr(RSChannelAttributes.INCOMING_ISAAC).get()
        side = channel.attr(RSChannelAttributes.SIDE).get()
        mapping = if (side == Side.CLIENT) protocol.clientProtSizes.values else protocol.serverProtSizes.values
        if (side == Side.CLIENT) {
            val opcode27Size = mapping.getOrDefault(27, Int.MIN_VALUE)
            val opcode92Size = mapping.getOrDefault(92, Int.MIN_VALUE)
            logger.info {
                "Initialized client framing map for ${channel.remoteAddress()} " +
                    "[protocolPath=${protocol.path.toAbsolutePath().normalize()}, opcode27=$opcode27Size, opcode92=$opcode92Size]"
            }
            traceLobbyDoctor(
                channel,
                "init-mapping",
                mapOf(
                    "side" to side.name,
                    "remote" to channel.remoteAddress().toString(),
                    "opcode27" to opcode27Size,
                    "opcode92" to opcode92Size,
                    "protocolPath" to protocol.path.toAbsolutePath().normalize().toString(),
                )
            )
        }
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        try {
            if (!inited) init(ctx.channel())

            if (droppingLobbySocialClientTraffic && side == Side.CLIENT) {
                if (buf.isReadable) {
                    traceLobbyDoctor(
                        ctx.channel(),
                        "compat-drop-bytes",
                        mapOf(
                            "side" to side.name,
                            "remote" to ctx.channel().remoteAddress().toString(),
                            "readableBefore" to buf.readableBytes(),
                            "rawPeekBefore" to rawPeek(buf),
                            "bootstrapStage" to bootstrapStage(ctx.channel()),
                        )
                    )
                    buf.skipBytes(buf.readableBytes())
                }
                return
            }

            while (buf.isReadable) {
                if (state == State.READ_OPCODE) {
                    if (!buf.isReadable) return

                    val readableBeforeOpcode = buf.readableBytes()
                    val rawPeekBeforeOpcode = rawPeek(buf)
                    val isaacCurrentValue = isaac.currentValue
                    if (buf.readableBytes() < 2 && buf.isBigOpcode(isaac)) {
                        traceLobbyDoctor(
                            ctx.channel(),
                            "big-opcode-wait",
                            mapOf(
                                "side" to side.name,
                                "remote" to ctx.channel().remoteAddress().toString(),
                                "readable" to readableBeforeOpcode,
                                "rawPeek" to rawPeekBeforeOpcode,
                                "isaacCurrent" to isaacCurrentValue,
                            )
                        )
                        logger.info { "is big opcode:  true, readable is 1, need to wait!" }
                        return
                    }

                    opcode = buf.readOpcode(isaac)
                    traceLobbyDoctor(
                        ctx.channel(),
                        "read-opcode",
                        mapOf(
                            "side" to side.name,
                            "remote" to ctx.channel().remoteAddress().toString(),
                            "opcode" to opcode,
                            "readableBefore" to readableBeforeOpcode,
                            "rawPeekBefore" to rawPeekBeforeOpcode,
                            "isaacCurrent" to isaacCurrentValue,
                            "readableAfter" to buf.readableBytes(),
                        )
                    )
                    val compatSizeOverride =
                        lobbyCompatClientSizeOverride(ctx.channel(), opcode)
                            ?: lateWorldCompatClientSizeOverride(ctx.channel(), opcode)
                    val compatUnmappedSizeOverride =
                        if (compatSizeOverride == null && !mapping.containsKey(opcode))
                            lobbyCompatUnmappedSizeOverride(ctx.channel(), opcode)
                                ?: lateWorldCompatUnmappedSizeOverride(ctx.channel(), opcode)
                        else null

                    if (compatSizeOverride == null && compatUnmappedSizeOverride == null && !mapping.containsKey(opcode)) {
                        if (side == Side.CLIENT && bootstrapStage(ctx.channel()) == "social-state") {
                            droppingLobbySocialClientTraffic = true
                            traceLobbyDoctor(
                                ctx.channel(),
                                "compat-drop-enter",
                                mapOf(
                                    "side" to side.name,
                                    "remote" to ctx.channel().remoteAddress().toString(),
                                    "opcode" to opcode,
                                    "readableAfter" to buf.readableBytes(),
                                    "rawPeekAfter" to rawPeek(buf),
                                    "isaacCurrent" to isaac.currentValue,
                                    "bootstrapStage" to bootstrapStage(ctx.channel()),
                                )
                            )
                            logger.warn {
                                "Entering compatible drop mode for unresolved client opcode $opcode " +
                                    "during lobby social-state from ${ctx.channel().remoteAddress()} " +
                                    "(readable=${buf.readableBytes()}, preview=${preview(buf)})"
                            }
                            buf.skipBytes(buf.readableBytes())
                            return
                        }

                        traceLobbyDoctor(
                            ctx.channel(),
                            "missing-opcode-mapping",
                            mapOf(
                                "side" to side.name,
                                "remote" to ctx.channel().remoteAddress().toString(),
                                "opcode" to opcode,
                                "readableAfter" to buf.readableBytes(),
                                "rawPeekAfter" to rawPeek(buf),
                                "isaacCurrent" to isaac.currentValue,
                                "bootstrapStage" to bootstrapStage(ctx.channel()),
                            )
                        )
                        logger.error {
                            "No opcode->size mapping for opcode $opcode (side=$side, remote=${ctx.channel().remoteAddress()}, " +
                                "bootstrapStage=${bootstrapStage(ctx.channel())}, readable=${buf.readableBytes()}, " +
                                "preview=${preview(buf)})"
                        }
                        ctx.channel().attr(RSChannelAttributes.CONNECTED_CLIENT).get()?.traceBootstrap(
                            "world-framing-close remote=${ctx.channel().remoteAddress()} " +
                                "stage=${bootstrapStage(ctx.channel())} reason=missing-opcode-mapping " +
                                "opcode=$opcode side=$side readable=${buf.readableBytes()} preview=${preview(buf)}"
                        )
                        buf.skipBytes(buf.readableBytes())
                        ctx.channel().close()
                        return
                    }

                    size = compatSizeOverride ?: compatUnmappedSizeOverride ?: mapping[opcode]
                    if (compatSizeOverride != null || compatUnmappedSizeOverride != null) {
                        traceLobbyDoctor(
                            ctx.channel(),
                            "compat-size-override",
                            mapOf(
                                "side" to side.name,
                                "remote" to ctx.channel().remoteAddress().toString(),
                                "opcode" to opcode,
                                "size" to size,
                                "bootstrapStage" to bootstrapStage(ctx.channel()),
                            )
                        )
                        logger.info {
                            "Using compatibility size override for opcode $opcode " +
                                "(size=$size, remote=${ctx.channel().remoteAddress()}, " +
                                "bootstrapStage=${bootstrapStage(ctx.channel())})"
                        }
                    }
                    traceLobbyDoctor(
                        ctx.channel(),
                        "resolved-size",
                        mapOf(
                            "side" to side.name,
                            "remote" to ctx.channel().remoteAddress().toString(),
                            "opcode" to opcode,
                            "size" to size,
                            "readableAfter" to buf.readableBytes(),
                        )
                    )
                    state = if (size >= 0) State.READ_BODY else State.READ_SIZE
                }

                if (state == State.READ_SIZE && size < 0) {
                    if (buf.readableBytes() < -size) {
                        traceLobbyDoctor(
                            ctx.channel(),
                            "wait-size-byte",
                            mapOf(
                                "side" to side.name,
                                "remote" to ctx.channel().remoteAddress().toString(),
                                "opcode" to opcode,
                                "sizeEncodingBytes" to -size,
                                "readable" to buf.readableBytes(),
                                "rawPeek" to rawPeek(buf),
                            )
                        )
                        return
                    }

                    size =
                        if (size == -1) {
                            buf.readUnsignedByte().toInt()
                        } else {
                            val encodedSize = buf.getUnsignedShort(buf.readerIndex())
                            if (shouldUseLobbyCompatVarByteFallback(ctx.channel(), opcode, encodedSize)) {
                                val compatSize = buf.readUnsignedByte().toInt()
                                traceLobbyDoctor(
                                    ctx.channel(),
                                    "compat-varbyte-fallback",
                                    mapOf(
                                        "side" to side.name,
                                        "remote" to ctx.channel().remoteAddress().toString(),
                                        "opcode" to opcode,
                                        "encodedVarShort" to encodedSize,
                                        "compatSize" to compatSize,
                                        "rawPeekAfter" to rawPeek(buf),
                                    )
                                )
                                logger.info {
                                    "Using lobby social-state variable-byte fallback for opcode $opcode " +
                                        "(encodedVarShort=$encodedSize, compatSize=$compatSize, remote=${ctx.channel().remoteAddress()})"
                                }
                                compatSize
                            } else {
                                buf.readUnsignedShort()
                            }
                        }
                    traceLobbyDoctor(
                        ctx.channel(),
                        "read-variable-size",
                        mapOf(
                            "side" to side.name,
                            "remote" to ctx.channel().remoteAddress().toString(),
                            "opcode" to opcode,
                            "size" to size,
                            "readableAfter" to buf.readableBytes(),
                            "rawPeekAfter" to rawPeek(buf),
                        )
                    )

                    state = State.READ_BODY
                }

                if (state == State.READ_BODY) {
                    if (buf.readableBytes() < size) {
                        traceLobbyDoctor(
                            ctx.channel(),
                            "wait-body",
                            mapOf(
                                "side" to side.name,
                                "remote" to ctx.channel().remoteAddress().toString(),
                                "opcode" to opcode,
                                "size" to size,
                                "readable" to buf.readableBytes(),
                                "rawPeek" to rawPeek(buf),
                            )
                        )
                        return
                    }

                    val payload = buf.readBytes(size)
                    traceLobbyDoctor(
                        ctx.channel(),
                        "framed-packet",
                        mapOf(
                            "side" to side.name,
                            "remote" to ctx.channel().remoteAddress().toString(),
                            "opcode" to opcode,
                            "size" to size,
                            "payloadPreview" to preview(payload),
                            "readableAfter" to buf.readableBytes(),
                        )
                    )
                    if (side == Side.CLIENT) {
                        val registration = PacketRegistry.getRegistration(side, opcode)
                        logger.info {
                            "Framed client packet opcode=$opcode size=$size name=${registration?.name ?: "unregistered"} " +
                                "from ${ctx.channel().remoteAddress()} [bootstrapStage=${bootstrapStage(ctx.channel())}]"
                        }
                    }

                    out.add(OpcodeWithBuffer(opcode, payload))

                    state = State.READ_OPCODE
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
            ctx.channel().attr(RSChannelAttributes.CONNECTED_CLIENT).get()?.traceBootstrap(
                "world-framing-close remote=${ctx.channel().remoteAddress()} " +
                    "stage=${bootstrapStage(ctx.channel())} reason=decode-exception side=$side " +
                    "type=${e::class.qualifiedName ?: e::class.simpleName ?: "unknown"} " +
                    "message=${e.message ?: "<none>"}"
            )
        }
    }

    private enum class State {
        READ_OPCODE,
        READ_SIZE,
        READ_BODY
    }
}
