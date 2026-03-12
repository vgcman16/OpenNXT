package com.opennxt.net.game.pipeline

import com.opennxt.net.RSChannelAttributes
import com.opennxt.net.Side
import io.netty.channel.ChannelHandlerContext
import io.netty.channel.SimpleChannelInboundHandler
import mu.KotlinLogging
import java.util.*

class DynamicPacketHandler : SimpleChannelInboundHandler<OpcodeWithBuffer>() {
    private val logger = KotlinLogging.logger { }

    override fun channelRead0(ctx: ChannelHandlerContext, msg: OpcodeWithBuffer) {
        try {
            ctx.channel().attr(RSChannelAttributes.CONNECTED_CLIENT).get().receive(msg)
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    override fun exceptionCaught(ctx: ChannelHandlerContext, cause: Throwable) {
        logger.error(cause) { "Exception caught in packet handler" }
    }

    override fun channelInactive(ctx: ChannelHandlerContext) {
        logger.info { "Channel on side ${ctx.channel().attr(RSChannelAttributes.SIDE).get()} went inactive" }
        ctx.channel().attr(RSChannelAttributes.CONNECTED_CLIENT).get()?.let { client ->
            val currentStage = client.currentBootstrapStage
            val stage = currentStage ?: client.lastCompletedBootstrapStage
            if (stage != null) {
                logger.info {
                    "Channel ${ctx.channel().remoteAddress()} closed after bootstrap stage $stage " +
                        "(current=${currentStage ?: "none"}, completed=${client.completedBootstrapStages.joinToString()})"
                }
            }
        }

        val passthrough = ctx.channel().attr(RSChannelAttributes.PASSTHROUGH_CHANNEL).get()
        if (passthrough != null && passthrough.isOpen) {
            passthrough.close()
        }
    }
}
