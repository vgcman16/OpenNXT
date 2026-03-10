package com.opennxt.net.http.endpoints

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.ClientConfig
import com.opennxt.model.files.FileChecker
import com.opennxt.net.http.sendHttpText
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.QueryStringDecoder

object JavConfigWsEndpoint {
    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {

        val type = BinaryType.values()[query.parameters().getOrElse("binaryType") { listOf("2") }.first().toInt()]
        val config = FileChecker.getConfig("compressed", type) ?: throw NullPointerException("Can't get config for type $type")
        val templatePath = Constants.CLIENTS_PATH
            .resolve(OpenNXT.config.build.toString())
            .resolve(type.name.lowercase())
            .resolve("original")
            .resolve("jav_config.ws")
        val liveConfig = runCatching { ClientConfig.load(templatePath) }.getOrElse {
            // If the original template is unavailable, fall back to the compressed config as-is.
            ctx.sendHttpText(config.toString().toByteArray(Charsets.ISO_8859_1))
            return
        }

        var download = 0
        while (config.entries.containsKey("download_name_$download")) {
            liveConfig.entries["download_name_$download"] = config.entries.getValue("download_name_$download")
            liveConfig.entries["download_crc_$download"] = config.entries.getValue("download_crc_$download")
            liveConfig.entries["download_hash_$download"] = config.entries.getValue("download_hash_$download")
            download++
        }

        // Preserve the live transport host/port layout from jav_config.ws. The local world handoff
        // is injected later by the lobby login response, and rewriting the pre-login transport
        // params here can strand the native client on the loading screen before it ever renders UI.

        ctx.sendHttpText(liveConfig.toString().toByteArray(Charsets.ISO_8859_1))
    }
}
