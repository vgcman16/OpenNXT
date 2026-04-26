package com.opennxt.net.http

import com.opennxt.net.http.endpoints.ClientFileEndpoint
import com.opennxt.net.http.endpoints.ClientErrorWsEndpoint
import com.opennxt.net.http.endpoints.JavConfigWsEndpoint
import com.opennxt.net.http.endpoints.Js5MsEndpoint
import com.opennxt.net.http.endpoints.RevocationListEndpoint
import io.netty.channel.ChannelHandler
import io.netty.channel.ChannelHandlerContext
import io.netty.channel.SimpleChannelInboundHandler
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpMethod
import io.netty.handler.codec.http.HttpResponseStatus
import io.netty.handler.codec.http.QueryStringDecoder
import mu.KotlinLogging

@ChannelHandler.Sharable
class HttpRequestHandler : SimpleChannelInboundHandler<FullHttpRequest>() {
    private val logger = KotlinLogging.logger { }

    internal fun canonicalizePath(path: String): String {
        var normalized = path
        while (true) {
            val next = when {
                normalized.matches(Regex("^/(k|l)=[^/]+/.*$")) -> normalized.replaceFirst(Regex("^/(k|l)=[^/]+"), "")
                normalized.matches(Regex("^/(k|l)=[^/]+$")) -> "/"
                else -> null
            }
            normalized = next ?: break
        }
        return normalized
    }

    override fun channelRead0(ctx: ChannelHandlerContext, msg: FullHttpRequest) {
        if (!msg.decoderResult().isSuccess) {
            logger.warn { "HTTP bad request from ${ctx.channel().remoteAddress()}: uri=${msg.uri()}" }
            ctx.sendHttpError(HttpResponseStatus.BAD_REQUEST)
            return
        }

        val uri = msg.uri()
        val query = QueryStringDecoder(uri)
        val path = canonicalizePath(query.path())

        if (msg.method() == HttpMethod.POST && path == "/nxtclienterror.ws") {
            logger.info { "HTTP POST $path from ${ctx.channel().remoteAddress()}: uri=$uri" }
            ClientErrorWsEndpoint.handle(ctx, msg, query)
            return
        }

        if (msg.method() != HttpMethod.GET) {
            logger.warn {
                "HTTP unsupported method from ${ctx.channel().remoteAddress()}: method=${msg.method()} uri=${msg.uri()}"
            }
            ctx.sendHttpError(HttpResponseStatus.METHOD_NOT_ALLOWED)
            return
        }

        logger.info { "HTTP GET $path from ${ctx.channel().remoteAddress()}: uri=$uri" }

        when {
            path == "/jav_config.ws" -> JavConfigWsEndpoint.handle(ctx, msg, query)
            path == "/client" -> ClientFileEndpoint.handle(ctx, msg, query)
            path == "/ms" -> Js5MsEndpoint.handle(ctx, msg, query)
            path == "/opennxt-local-root.crl" -> RevocationListEndpoint.handle(ctx, msg, query)
            else -> {
                logger.warn { "HTTP 404 for ${ctx.channel().remoteAddress()}: uri=$uri" }
                ctx.sendHttpError(HttpResponseStatus.NOT_FOUND)
            }
        }
    }

    override fun exceptionCaught(ctx: ChannelHandlerContext, cause: Throwable) {
        logger.error(cause) { "HTTP handler exception from ${ctx.channel().remoteAddress()}" }
        if (ctx.channel().isActive) {
            ctx.sendHttpError(HttpResponseStatus.INTERNAL_SERVER_ERROR)
        }
    }
}
