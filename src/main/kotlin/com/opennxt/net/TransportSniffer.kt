package com.opennxt.net

import io.netty.buffer.ByteBuf
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import io.netty.handler.ssl.SslContext
import mu.KotlinLogging
import java.net.InetSocketAddress

class TransportSniffer(private val tlsContext: SslContext) : ByteToMessageDecoder() {
    private val logger = KotlinLogging.logger {}

    init {
        isSingleDecode = true
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        if (!buf.isReadable) {
            return
        }

        val readerIndex = buf.readerIndex()
        val contentType = buf.getUnsignedByte(readerIndex).toInt()
        val localPort = (ctx.channel().localAddress() as? InetSocketAddress)?.port ?: -1

        if (contentType == 0x16) {
            if (buf.readableBytes() < 3) {
                return
            }

            val major = buf.getUnsignedByte(readerIndex + 1).toInt()
            val minor = buf.getUnsignedByte(readerIndex + 2).toInt()
            val isTls = major == 0x03 && minor in 0x00..0x04
            if (!isTls) {
                logger.info {
                    "Detected plaintext transport from ${ctx.channel().remoteAddress()} " +
                        "to port $localPort (leading 0x16 was not TLS)"
                }
                ctx.pipeline().remove(this)
                out.add(buf.readRetainedSlice(buf.readableBytes()))
                return
            }

            logger.info {
                "Detected TLS ClientHello from ${ctx.channel().remoteAddress()} " +
                    "to port $localPort"
            }
            ctx.pipeline().addAfter(ctx.name(), "tls-server", tlsContext.newHandler(ctx.alloc()))
        } else {
            logger.info {
                "Detected plaintext transport from ${ctx.channel().remoteAddress()} " +
                    "to port $localPort"
            }
        }

        ctx.pipeline().remove(this)
        out.add(buf.readRetainedSlice(buf.readableBytes()))
    }
}
