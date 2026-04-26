package com.opennxt.net.handshake

import com.opennxt.OpenNXT
import com.opennxt.net.ConnectedClient
import com.opennxt.net.PreLoginForensics
import com.opennxt.net.GenericResponse
import com.opennxt.net.RSChannelAttributes
import com.opennxt.net.Side
import com.opennxt.net.js5.Js5Decoder
import com.opennxt.net.js5.Js5Encoder
import com.opennxt.net.js5.Js5Handler
import com.opennxt.net.js5.Js5Session
import com.opennxt.net.login.LoginUniqueIdStore
import com.opennxt.net.login.LoginServerDecoder
import com.opennxt.net.login.LoginEncoder
import com.opennxt.net.login.LoginServerHandler
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.channel.SimpleChannelInboundHandler
import mu.KotlinLogging
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import java.util.concurrent.ThreadLocalRandom

class HandshakeHandler : SimpleChannelInboundHandler<HandshakeRequest>() {
    private val logger = KotlinLogging.logger {}

    companion object {
        internal fun buildSuccessfulLoginHandshakeBytes(uniqueId: Long): ByteArray =
            ByteBuffer.allocate(9)
                .put(GenericResponse.SUCCESSFUL_CONNECTION.id.toByte())
                .putLong(uniqueId)
                .array()
    }

    override fun channelRead0(ctx: ChannelHandlerContext, msg: HandshakeRequest) {
        ctx.channel().attr(RSChannelAttributes.SIDE).set(Side.CLIENT)
        ctx.channel().attr(RSChannelAttributes.CONNECTED_CLIENT)
            .set(ConnectedClient(Side.CLIENT, ctx.channel(), processUnidentifiedPackets = true))

        when (msg.type) {
            HandshakeType.JS_5 -> {
                val session = Js5Session(ctx.channel())

                // replace handler before decoder to avoid decoding packet before encoder is ready (yes this was a bug)
                ctx.pipeline().addLast("js5-encoder", Js5Encoder(session))

                ctx.pipeline().replace("handshake-handler", "js5-handler", Js5Handler(session))
                ctx.pipeline().replace("handshake-decoder", "js5-decoder", Js5Decoder(session))
            }
            HandshakeType.LOGIN, HandshakeType.LOGIN_ALT -> {
                val uniqueId = LoginUniqueIdStore.getOrCreate(ctx.channel().remoteAddress()) {
                    ThreadLocalRandom.current().nextLong()
                }

                ctx.channel().attr(RSChannelAttributes.LOGIN_UNIQUE_ID).set(uniqueId)

                ctx.pipeline().addLast("login-encoder", LoginEncoder())

                ctx.pipeline().replace("handshake-handler", "login-handler", LoginServerHandler())
                ctx.pipeline().replace("handshake-decoder", "login-decoder", LoginServerDecoder(OpenNXT.rsaConfig.login))

                val localPort = (ctx.channel().localAddress() as? InetSocketAddress)?.port ?: -1
                val remoteAddress = ctx.channel().remoteAddress().toString()
                val responseBytes = buildSuccessfulLoginHandshakeBytes(uniqueId)
                val responseHex = responseBytes.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }

                logger.info {
                    "Sending initial login handshake response to $remoteAddress " +
                        "(type=${msg.type}, uniqueId=$uniqueId, bytes=$responseHex)"
                }
                PreLoginForensics.recordTransportEvent(
                    localPort = localPort,
                    remoteAddress = remoteAddress,
                    event = "login-handshake-response",
                    details = mapOf(
                        "handshakeType" to msg.type.name,
                        "uniqueId" to uniqueId,
                        "responseHex" to responseHex,
                    ),
                )

                ctx.channel()
                    .writeAndFlush(Unpooled.wrappedBuffer(responseBytes))
                    .addListener { future ->
                        if (!future.isSuccess) {
                            logger.error(future.cause()) {
                                "Failed to send initial login handshake response to $remoteAddress"
                            }
                        } else {
                            logger.info {
                                "Initial login handshake response flushed to $remoteAddress"
                            }
                        }
                    }
            }
            else -> throw IllegalStateException("Cannot handle handshake message: $msg")
        }
    }

    override fun exceptionCaught(ctx: ChannelHandlerContext, cause: Throwable) {
        logger.error(cause) { "Handshake handler exception for ${ctx.channel().remoteAddress()}" }
        ctx.close()
    }
}
