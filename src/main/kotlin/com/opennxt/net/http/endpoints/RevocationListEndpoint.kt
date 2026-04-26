package com.opennxt.net.http.endpoints

import com.opennxt.Constants
import com.opennxt.net.http.sendHttpBytes
import com.opennxt.net.http.sendHttpError
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpResponseStatus
import io.netty.handler.codec.http.QueryStringDecoder
import mu.KotlinLogging
import java.nio.file.Files

object RevocationListEndpoint {
    private val logger = KotlinLogging.logger { }
    private val crlPath = Constants.DATA_PATH.resolve("tls").resolve("opennxt-local-root.crl")

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {
        if (!Files.exists(crlPath)) {
            logger.warn { "Missing local CRL at $crlPath for uri=${msg.uri()}" }
            ctx.sendHttpError(HttpResponseStatus.NOT_FOUND)
            return
        }

        val bytes = Files.readAllBytes(crlPath)
        logger.info {
            "Serving local CRL to ${ctx.channel().remoteAddress()}: uri=${msg.uri()} bytes=${bytes.size}"
        }
        ctx.sendHttpBytes(bytes, "application/pkix-crl")
    }
}
