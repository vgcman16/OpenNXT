package com.opennxt.net.http

import com.opennxt.config.ServerConfig
import com.opennxt.model.files.FileChecker
import io.netty.bootstrap.ServerBootstrap
import io.netty.channel.Channel
import io.netty.channel.ChannelInitializer
import io.netty.channel.ChannelOption
import io.netty.channel.nio.NioEventLoopGroup
import io.netty.channel.socket.SocketChannel
import io.netty.channel.socket.nio.NioServerSocketChannel
import io.netty.handler.codec.http.HttpObjectAggregator
import io.netty.handler.codec.http.HttpServerCodec
import mu.KotlinLogging

class HttpServer(val config: ServerConfig) : AutoCloseable {
    private val logger = KotlinLogging.logger {}
    private var initialized = false

    private val handler = HttpRequestHandler()
    private val eventLoopGroup = NioEventLoopGroup()
    private val channels = ArrayList<Channel>()
    private val httpBootstrap = ServerBootstrap()
        .group(eventLoopGroup)
        .channel(NioServerSocketChannel::class.java)
        .childHandler(HttpChannelInitializer(handler))
        .childOption(ChannelOption.SO_REUSEADDR, true)
        .childOption(ChannelOption.TCP_NODELAY, true)
        .childOption(ChannelOption.CONNECT_TIMEOUT_MILLIS, 30_000)

    fun init(skipFileChecks: Boolean) {
        if (skipFileChecks) {
            logger.info { "Skipping http file verification" }
        } else {
            FileChecker.checkFiles("compressed")
        }
        // TODO Checksum table?

        initialized = true
    }

    fun bind(httpPort: Int = config.ports.http) {
        check(initialized) { "Attempted to bind http server before initializing" }

        val ports = LinkedHashSet<Int>().apply {
            add(httpPort)
            addAll(config.ports.httpAliases)
        }
        ports.forEach { port ->
            logger.info { "Binding http server to 0.0.0.0:$port" }

            val result = httpBootstrap.bind("0.0.0.0", port).sync()
            check(result.isSuccess) { "Failed to bind to 0.0.0.0:$port" }

            channels += result.channel()
            logger.info { "Http server bound to 0.0.0.0:$port" }
        }
    }

    override fun close() {
        channels.forEach { channel ->
            channel.close()?.syncUninterruptibly()
        }
        channels.clear()
        eventLoopGroup.shutdownGracefully().syncUninterruptibly()
    }

    private class HttpChannelInitializer(val handler: HttpRequestHandler) : ChannelInitializer<SocketChannel>() {
        override fun initChannel(ch: SocketChannel) {
            ch.pipeline().addLast("codec", HttpServerCodec())
            ch.pipeline().addLast("aggregator", HttpObjectAggregator(2048))
            ch.pipeline().addLast("handler", handler)
        }
    }
}
