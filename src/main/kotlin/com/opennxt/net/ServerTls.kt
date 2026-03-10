package com.opennxt.net

import com.opennxt.Constants
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.ssl.SslContext
import io.netty.handler.ssl.SslContextBuilder
import io.netty.handler.ssl.SslHandler
import io.netty.handler.ssl.SslProvider
import mu.KotlinLogging
import java.nio.file.Files
import java.security.KeyStore
import javax.net.ssl.KeyManagerFactory

object ServerTls {
    private val logger = KotlinLogging.logger {}

    private const val PFX_PASSWORD = "opennxt-dev"
    private val pfxPath = Constants.DATA_PATH.resolve("tls").resolve("lobby46a.runescape.com.pfx")

    val context: SslContext by lazy {
        require(Files.exists(pfxPath)) {
            "Missing TLS certificate at $pfxPath"
        }

        logger.info { "Loading backend TLS certificate from $pfxPath" }

        val password = PFX_PASSWORD.toCharArray()
        val keyStore = KeyStore.getInstance("PKCS12")
        Files.newInputStream(pfxPath).use { input ->
            keyStore.load(input, password)
        }

        val keyManagerFactory = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        keyManagerFactory.init(keyStore, password)

        SslContextBuilder.forServer(keyManagerFactory)
            .sslProvider(SslProvider.JDK)
            .build()
    }

    fun newHandler(ctx: ChannelHandlerContext): SslHandler = context.newHandler(ctx.alloc())
}
