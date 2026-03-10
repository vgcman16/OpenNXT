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
    private val hostParamsToRewrite = setOf(37, 49)

    private fun applyLocalSocketRewrite(config: ClientConfig) {
        for (param in hostParamsToRewrite) {
            if (config.getParam(param) != null) {
                config["param=$param"] = OpenNXT.config.hostname
            }
        }

        for (param in listOf(41, 43, 45, 47)) {
            config["param=$param"] = OpenNXT.config.ports.game.toString()
        }
    }

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {

        val type = BinaryType.values()[query.parameters().getOrElse("binaryType") { listOf("2") }.first().toInt()]
        val config = FileChecker.getConfig("compressed", type) ?: throw NullPointerException("Can't get config for type $type")
        val templatePath = Constants.CLIENTS_PATH
            .resolve(OpenNXT.config.build.toString())
            .resolve(type.name.lowercase())
            .resolve("original")
            .resolve("jav_config.ws")
        val liveConfig = runCatching { ClientConfig.load(templatePath) }.getOrElse {
            // If the original template is unavailable, fall back to the compressed config and at least
            // normalize the direct OpenNXT socket endpoints.
            applyLocalSocketRewrite(config)
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

        // Preserve live lobby/auth/account/web endpoints so the native flow can render and
        // authenticate. Only redirect the content/game socket hosts that must terminate on OpenNXT.
        applyLocalSocketRewrite(liveConfig)

        ctx.sendHttpText(liveConfig.toString().toByteArray(Charsets.ISO_8859_1))
    }
}
