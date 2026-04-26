package com.opennxt.net.js5

import com.opennxt.Js5Thread
import com.opennxt.OpenNXT
import com.opennxt.net.PreLoginForensics
import com.opennxt.net.js5.packet.Js5Packet
import io.netty.channel.ChannelHandlerContext
import io.netty.channel.SimpleChannelInboundHandler
import mu.KotlinLogging
import java.net.InetSocketAddress

class Js5Handler(val session: Js5Session): SimpleChannelInboundHandler<Js5Packet>() {
    private val logger = KotlinLogging.logger {  }

    private fun record(ctx: ChannelHandlerContext, event: String, details: Map<String, Any?> = emptyMap()) {
        val localPort = (ctx.channel().localAddress() as? InetSocketAddress)?.port ?: -1
        PreLoginForensics.recordTransportEvent(
            localPort = localPort,
            remoteAddress = ctx.channel().remoteAddress().toString(),
            event = event,
            details = details,
        )
    }

    var handledHandshake = false

    override fun channelRead0(ctx: ChannelHandlerContext, msg: Js5Packet) {
        when(msg) {
            is Js5Packet.Handshake -> {
                if (handledHandshake)
                    throw IllegalStateException("Already handled handshake")
                handledHandshake = true
                session.recordClientHandshake(msg)

                val responseCode = 0
                logger.info {
                    "Accepting js5 handshake from ${ctx.channel().remoteAddress()} " +
                        "with build=${msg.major}.${msg.minor}, language=${msg.language}, " +
                        "tokenLength=${msg.token.length}, response=$responseCode, " +
                        "prefetches=${OpenNXT.prefetches.entries.size}"
                }
                record(
                    ctx,
                    event = "js5-handshake-accepted",
                    details = mapOf(
                        "sessionId" to session.id,
                        "build" to "${msg.major}.${msg.minor}",
                        "language" to msg.language,
                        "tokenLength" to msg.token.length,
                        "responseCode" to responseCode,
                    ),
                )

                ctx.channel().write(Js5Packet.HandshakeResponse(responseCode))
                ctx.channel().flush()
            }
            else -> TODO("Encode $msg")
        }
    }

    override fun exceptionCaught(ctx: ChannelHandlerContext, cause: Throwable) {
        logger.warn(cause) { "Caught exception" }
        record(
            ctx,
            event = "js5-handler-exception",
            details = mapOf(
                "sessionId" to session.id,
                "errorType" to cause::class.java.name,
                "message" to cause.message,
            ),
        )
    }

    override fun channelInactive(ctx: ChannelHandlerContext) {
        // remove session if the client connection drops and doesn't send the termination packet
        Js5Thread.removeSession(session)
        record(
            ctx,
            event = "js5-channel-inactive",
            details = mapOf(
                "sessionId" to session.id,
                "handledHandshake" to handledHandshake,
            ),
        )
    }
}
