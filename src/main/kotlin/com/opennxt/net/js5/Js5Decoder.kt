package com.opennxt.net.js5

import com.opennxt.OpenNXT
import com.opennxt.ext.readBuild
import com.opennxt.ext.readString
import com.opennxt.net.PreLoginForensics
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.js5.packet.Js5Packet
import com.opennxt.net.js5.packet.Js5PacketCodec
import io.netty.buffer.ByteBuf
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging
import java.net.InetSocketAddress

internal fun shouldSendLoggedOutPrefetchTable(
    build: Int,
    envValue: String? = System.getenv("OPENNXT_ENABLE_LOGGED_OUT_JS5_PREFETCH_TABLE"),
): Boolean = OpenNXT.loggedOutJs5PrefetchTableEnabled(build, envValue)

internal fun shouldActivateRetailLoggedOutProxy(
    build: Int,
    passthroughEnvValue: String? = System.getenv("OPENNXT_ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH"),
    prefetchEnvValue: String? = System.getenv("OPENNXT_ENABLE_LOGGED_OUT_JS5_PREFETCH_TABLE"),
): Boolean {
    return OpenNXT.retailLoggedOutJs5PassthroughEnabled(build, passthroughEnvValue) &&
        !shouldSendLoggedOutPrefetchTable(build, prefetchEnvValue)
}

class Js5Decoder(val session: Js5Session) : ByteToMessageDecoder() {
    private val logger = KotlinLogging.logger { }

    var handshakeDecoded = false

    private fun record(ctx: ChannelHandlerContext, event: String, details: Map<String, Any?> = emptyMap()) {
        val localPort = (ctx.channel().localAddress() as? InetSocketAddress)?.port ?: -1
        PreLoginForensics.recordTransportEvent(
            localPort = localPort,
            remoteAddress = ctx.channel().remoteAddress().toString(),
            event = event,
            details = details + mapOf("sessionId" to session.id),
        )
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        if (session.hasRetailLoggedOutProxy()) {
            if (buf.isReadable) {
                session.forwardRetailLoggedOutProxyBytes(buf.readRetainedSlice(buf.readableBytes()))
            }
            return
        }

        session.traceInboundBytes("decode-entry", buf, handshakeDecoded)

        if (!handshakeDecoded) {
            buf.markReaderIndex()
            val size = buf.readUnsignedByte().toInt()

            if (size <= 10) {
                logger.warn { "Invalid js5 handshake sent from ${ctx.channel().remoteAddress()}" }
                record(
                    ctx,
                    event = "js5-invalid-handshake",
                    details = mapOf(
                        "size" to size,
                        "readableBytes" to buf.readableBytes(),
                    ),
                )
                buf.skipBytes(buf.readableBytes())
                ctx.channel().close()
                return
            }

            if (buf.readableBytes() < size) {
                buf.resetReaderIndex()
                return
            }

            val build = buf.readBuild()
            val token = buf.readString()
            val language = buf.readUnsignedByte().toInt()
            val remaining = buf.readableBytes()

            logger.info {
                "Decoded js5 handshake for session#${session.id} from ${ctx.channel().remoteAddress()} " +
                    "with build=${build.major}.${build.minor}, language=$language, tokenLength=${token.length}, " +
                    "remaining=$remaining"
            }
            out.add(Js5Packet.Handshake(build.major, build.minor, token, language))

            handshakeDecoded = true
            return
        }

        if (buf.readableBytes() < 10) {
            logger.info {
                "Session#${session.id} waiting for more js5 bytes from ${ctx.channel().remoteAddress()}: " +
                    "readable=${buf.readableBytes()}"
            }
            return
        }
        when (val opcode = buf.readUnsignedByte().toInt()) {
            Js5PacketCodec.RequestFile.opcodeLow,
            Js5PacketCodec.RequestFile.opcodeHigh,
            Js5PacketCodec.RequestFile.opcodeNxtLow,
            Js5PacketCodec.RequestFile.opcodeNxtHigh1,
            Js5PacketCodec.RequestFile.opcodeNxtHigh2 -> {
                val request = Js5PacketCodec.RequestFile.decode(GamePacketReader(buf))
                request.priority = opcode == Js5PacketCodec.RequestFile.opcodeHigh ||
                    opcode == Js5PacketCodec.RequestFile.opcodeNxtHigh1 ||
                    opcode == Js5PacketCodec.RequestFile.opcodeNxtHigh2
                request.nxt = opcode == Js5PacketCodec.RequestFile.opcodeNxtLow ||
                    opcode == Js5PacketCodec.RequestFile.opcodeNxtHigh1 ||
                    opcode == Js5PacketCodec.RequestFile.opcodeNxtHigh2

                session.enqueueRequest(request, opcode)
            }

            Js5PacketCodec.ConnectionInitialized.opcode -> {
                val packet = Js5PacketCodec.ConnectionInitialized.decode(GamePacketReader(buf))
                logger.info {
                    "JS5 connection initialized from ${ctx.channel().remoteAddress()} " +
                        "with value=${packet.value}, build=${packet.build}"
                }
                record(
                    ctx,
                    event = "js5-connection-initialized",
                    details = mapOf(
                        "value" to packet.value,
                        "build" to packet.build,
                    ),
                )
                ctx.channel().attr(Js5Session.ATTR_KEY).get().apply {
                    initialize()
                }
            }

            Js5PacketCodec.RequestTermination.opcode -> {
                logger.info { "Request termination" }
                Js5PacketCodec.RequestTermination.decode(GamePacketReader(buf))
                record(ctx, event = "js5-request-termination")
                ctx.channel().attr(Js5Session.ATTR_KEY).get().close()
            }

            Js5PacketCodec.XorRequest.opcode -> {
                val packet = Js5PacketCodec.XorRequest.decode(GamePacketReader(buf))
                logger.info { "Set XOR: ${packet.xor}" }
                ctx.channel().attr(Js5Session.XOR_KEY).set(packet.xor)
            }

            Js5PacketCodec.LoggedIn.opcode -> {
                val packet = Js5PacketCodec.LoggedIn.decode(GamePacketReader(buf))
                logger.info { "JS5 logged in state from ${ctx.channel().remoteAddress()} for build=${packet.build}" }
                record(
                    ctx,
                    event = "js5-login-state",
                    details = mapOf(
                        "loggedIn" to true,
                        "build" to packet.build,
                    ),
                )
                ctx.channel().attr(Js5Session.ATTR_KEY).get().apply {
                    updateLoggedInState(true)
                    sendPrefetchTableIfNeeded("logged-in")
                }
            }

            Js5PacketCodec.LoggedOut.opcode -> {
                val packet = Js5PacketCodec.LoggedOut.decode(GamePacketReader(buf))
                logger.info { "JS5 logged out state from ${ctx.channel().remoteAddress()} for build=${packet.build}" }
                record(
                    ctx,
                    event = "js5-login-state",
                    details = mapOf(
                        "loggedIn" to false,
                        "build" to packet.build,
                    ),
                )
                ctx.channel().attr(Js5Session.ATTR_KEY).get().apply {
                    updateLoggedInState(false)
                    val sendLoggedOutPrefetchTable = shouldSendLoggedOutPrefetchTable(packet.build)
                    val proxyActivated = if (shouldActivateRetailLoggedOutProxy(packet.build)) {
                        activateRetailLoggedOutProxyIfEligible(packet.build)
                    } else {
                        logger.info {
                            "Keeping logged-out js5 session#${session.id} on the local decoder for build=${packet.build} " +
                                "so the first master-table request can be served inline before any retail proxy takeover"
                        }
                        record(
                            ctx,
                            event = "js5-retail-proxy-skipped",
                            details = mapOf(
                                "build" to packet.build,
                                "reason" to if (sendLoggedOutPrefetchTable) {
                                    "logged-out-prefetch-local-inline"
                                } else {
                                    "retail-passthrough-disabled"
                                },
                            ),
                        )
                        false
                    }
                    if (sendLoggedOutPrefetchTable) {
                        sendPrefetchTableIfNeeded("logged-out")
                    } else {
                        logger.info {
                            "Suppressing logged-out js5 prefetch table for build=${packet.build} " +
                                "from ${ctx.channel().remoteAddress()} to mirror retail wire order"
                        }
                        record(
                            ctx,
                            event = "js5-prefetch-table-suppressed",
                            details = mapOf(
                                "reason" to "logged-out",
                                "build" to packet.build,
                            ),
                        )
                    }
                    if (proxyActivated && buf.isReadable) {
                        forwardRetailLoggedOutProxyBytes(buf.readRetainedSlice(buf.readableBytes()))
                    }
                }
            }

            else -> {
                logger.warn {
                    "Unknown js5 opcode $opcode on session#${session.id} from ${ctx.channel().remoteAddress()}. " +
                        "Skipping 9 bytes"
                }
                record(
                    ctx,
                    event = "js5-unknown-opcode",
                    details = mapOf(
                        "opcode" to opcode,
                        "readableBytes" to buf.readableBytes(),
                    ),
                )
                buf.skipBytes(minOf(9, buf.readableBytes()))
            }
        }
    }
}
