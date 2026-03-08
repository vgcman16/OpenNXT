package com.opennxt.net.http.endpoints

import com.opennxt.OpenNXT
import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.ClientConfig
import com.opennxt.model.files.FileChecker
import com.opennxt.net.http.sendHttpText
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.QueryStringDecoder

object JavConfigWsEndpoint {
    private val hostParamsToRewrite = setOf(3, 37, 49)

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {

        val type = BinaryType.values()[query.parameters().getOrElse("binaryType") { listOf("2") }.first().toInt()]
        val config = FileChecker.getConfig("compressed", type) ?: throw NullPointerException("Can't get config for type $type")
        if (!OpenNXT.enableProxySupport) {
            ctx.sendHttpText(config.toString().toByteArray(Charsets.ISO_8859_1))
            return
        }

        val liveConfig = ClientConfig.download("https://world5.runescape.com/jav_config.ws", type)

        var download = 0
        while (config.entries.containsKey("download_name_$download")) {
            liveConfig.entries["download_name_$download"] = config.entries.getValue("download_name_$download")
            liveConfig.entries["download_crc_$download"] = config.entries.getValue("download_crc_$download")
            liveConfig.entries["download_hash_$download"] = config.entries.getValue("download_hash_$download")
            download++
        }

        // Preserve live auth/account/web endpoints so the native CEF flow can render and authenticate.
        // Only redirect the JS5/game socket hosts that must terminate on OpenNXT.
        for (param in hostParamsToRewrite) {
            if (liveConfig.getParam(param) != null) {
                liveConfig["param=$param"] = OpenNXT.config.hostname
            }
        }

        for (param in listOf(41, 43, 45, 47)) {
            liveConfig["param=$param"] = OpenNXT.config.ports.game.toString()
        }

        for (param in listOf(42, 44, 46, 48)) {
            liveConfig["param=$param"] = OpenNXT.config.ports.https.toString()
        }

        ctx.sendHttpText(liveConfig.toString().toByteArray(Charsets.ISO_8859_1))
    }
}
