package com.opennxt.net.js5

import com.opennxt.ext.readBuild
import com.opennxt.ext.readString
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.js5.packet.Js5Packet
import com.opennxt.net.js5.packet.Js5PacketCodec
import io.netty.buffer.ByteBuf
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging

class Js5Decoder(val session: Js5Session) : ByteToMessageDecoder() {
    private val logger = KotlinLogging.logger { }

    var handshakeDecoded = false

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        session.traceInboundBytes("decode-entry", buf, handshakeDecoded)

        if (!handshakeDecoded) {
            buf.markReaderIndex()
            val size = buf.readUnsignedByte().toInt()

            if (size <= 10) {
                logger.warn { "Invalid js5 handshake sent from ${ctx.channel().remoteAddress()}" }
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

            check(!buf.isReadable) { "buffer is readable after reading js5 handshake" }

            logger.info {
                "Decoded js5 handshake for session#${session.id} from ${ctx.channel().remoteAddress()} " +
                    "with build=${build.major}.${build.minor}, language=$language, tokenLength=${token.length}"
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
                ctx.channel().attr(Js5Session.ATTR_KEY).get().initialize()
            }

            Js5PacketCodec.RequestTermination.opcode -> {
                logger.info { "Request termination" }
                Js5PacketCodec.RequestTermination.decode(GamePacketReader(buf))
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
                ctx.channel().attr(Js5Session.LOGGED_IN).set(true)
            }

            Js5PacketCodec.LoggedOut.opcode -> {
                val packet = Js5PacketCodec.LoggedOut.decode(GamePacketReader(buf))
                logger.info { "JS5 logged out state from ${ctx.channel().remoteAddress()} for build=${packet.build}" }
                ctx.channel().attr(Js5Session.LOGGED_IN).set(false)
            }

            else -> {
                logger.warn {
                    "Unknown js5 opcode $opcode on session#${session.id} from ${ctx.channel().remoteAddress()}. " +
                        "Skipping 9 bytes"
                }
                buf.skipBytes(minOf(9, buf.readableBytes()))
            }
        }
    }
}
