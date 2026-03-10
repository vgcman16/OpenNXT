package com.opennxt.net.handshake

import io.netty.buffer.ByteBuf
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging
import java.nio.charset.StandardCharsets

class HandshakeDecoder: ByteToMessageDecoder() {
    val logger = KotlinLogging.logger {  }

    init {
        isSingleDecode = true
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        val id = buf.readUnsignedByte().toInt()
        val type = HandshakeType.fromId(id)

        if (type == null) {
            val previewLength = minOf(buf.readableBytes(), 32)
            val preview = ByteArray(previewLength)
            buf.getBytes(buf.readerIndex(), preview)
            val previewHex = preview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
            val methodPrefix = buildString {
                append(id.toChar())
                append(preview.toString(StandardCharsets.ISO_8859_1))
            }
            logger.warn {
                "Client from ${ctx.channel().remoteAddress()} attempted to handshake with unknown id: $id " +
                    "(remaining=${buf.readableBytes()}, preview=$previewHex)"
            }

            if (methodPrefix.startsWith("POST ") || methodPrefix.startsWith("GET ") || methodPrefix.startsWith("HTTP/")) {
                val httpLength = minOf(buf.readableBytes() + 1, 4096)
                val httpBytes = ByteArray(httpLength)
                httpBytes[0] = id.toByte()
                buf.getBytes(buf.readerIndex(), httpBytes, 1, httpLength - 1)
                val httpText = httpBytes.toString(StandardCharsets.ISO_8859_1)
                logger.warn {
                    "Plaintext HTTP reached HandshakeDecoder from ${ctx.channel().remoteAddress()}:\n$httpText"
                }
            }

            ctx.close()
            buf.skipBytes(buf.readableBytes())
            return
        }

        logger.info { "Received handshake from ${ctx.channel().remoteAddress()} with type $type" }
        out.add(HandshakeRequest(type))
    }
}
