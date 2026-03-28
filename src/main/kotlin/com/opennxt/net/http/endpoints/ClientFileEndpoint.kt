package com.opennxt.net.http.endpoints

import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.FileChecker
import com.opennxt.net.http.sendHttpError
import com.opennxt.net.http.sendHttpFile
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpResponseStatus
import io.netty.handler.codec.http.QueryStringDecoder
import mu.KotlinLogging

object ClientFileEndpoint {
    private val logger = KotlinLogging.logger { }
    private val clientFolders = listOf("original", "patched", "compressed")

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {
        if (!query.parameters().containsKey("binaryType") ||
            !query.parameters().containsKey("fileName") ||
            !query.parameters().containsKey("crc")
        ) {
            logger.warn { "Rejecting /client request with missing parameters: uri=${msg.uri()}" }
            ctx.sendHttpError(HttpResponseStatus.NOT_FOUND)
            return
        }

        val binaryType = BinaryType.values()[query.parameters().getValue("binaryType").first().toInt()]
        val filename = query.parameters().getValue("fileName").first()
        val crc = query.parameters().getValue("crc").first().toLong()

        var data: ByteArray? = null
        var sourceFolder: String? = null
        for (folder in clientFolders) {
            val candidate = FileChecker.getFile(folder, binaryType, file = filename, crc = crc)
            if (candidate != null) {
                data = candidate
                sourceFolder = folder
                break
            }
        }

        if (data == null || sourceFolder == null) {
            logger.warn {
                "Missing /client payload for ${ctx.channel().remoteAddress()}: " +
                    "binaryType=$binaryType file=$filename crc=$crc folders=${clientFolders.joinToString(",")}"
            }
            ctx.sendHttpError(HttpResponseStatus.NOT_FOUND)
            return
        }

        logger.info {
            "Serving /client payload to ${ctx.channel().remoteAddress()}: " +
                "binaryType=$binaryType file=$filename crc=$crc bytes=${data.size} source=$sourceFolder"
        }
        ctx.sendHttpFile(data, filename)
    }
}
