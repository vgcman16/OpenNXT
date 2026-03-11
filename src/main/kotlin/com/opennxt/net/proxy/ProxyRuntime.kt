package com.opennxt.net.proxy

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.core.Context
import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.config.RsaConfig
import com.opennxt.config.ServerConfig
import com.opennxt.config.TomlConfig
import com.opennxt.login.LoginThread
import com.opennxt.login.ProxyLoginProcessor
import com.opennxt.model.tick.TickEngine
import com.opennxt.net.RSChannelInitializer
import com.opennxt.net.game.protocol.ProtocolInformation
import io.netty.bootstrap.ServerBootstrap
import io.netty.channel.Channel
import io.netty.channel.ChannelOption
import io.netty.channel.nio.NioEventLoopGroup
import io.netty.channel.socket.nio.NioServerSocketChannel
import mu.KotlinLogging
import java.io.FileNotFoundException
import java.nio.file.Files
import kotlin.system.exitProcess

object ProxyRuntime : CliktCommand(name = "run-proxy") {
    private val logger = KotlinLogging.logger { }

    private lateinit var config: ServerConfig
    private lateinit var rsaConfig: RsaConfig
    private lateinit var proxyConfig: ProxyConfig
    private lateinit var connectionFactory: ProxyConnectionFactory
    private lateinit var connectionHandler: ProxyConnectionHandler

    private val bootstrap = ServerBootstrap()
    private var networkGroup: NioEventLoopGroup? = null
    private var networkChannel: Channel? = null

    override fun help(context: Context): String = "Launches the standalone OpenNXT proxy runtime"

    override fun run() {
        logger.info { "Starting OpenNXT proxy runtime" }
        loadConfigurations()

        try {
            val protPath = Constants.PROT_PATH.resolve(config.build.toString())
            if (!Files.exists(protPath)) {
                throw IllegalStateException("Protocol information not found for build ${config.build} at $protPath")
            }

            OpenNXT.config = config
            OpenNXT.rsaConfig = rsaConfig
            OpenNXT.protocol = ProtocolInformation(protPath)
            OpenNXT.protocol.load()

            connectionFactory = ProxyConnectionFactory()
            connectionHandler = ProxyConnectionHandler()

            LoginThread.configure(
                ProxyLoginProcessor(
                    usernames = proxyConfig.usernames.map { it.lowercase() }.toSet(),
                    connectionFactory = connectionFactory,
                    connectionHandler = connectionHandler
                )
            )
            LoginThread.start()

            TickEngine().submitTickable(connectionHandler)

            networkGroup = NioEventLoopGroup()
            bootstrap.group(networkGroup)
                .channel(NioServerSocketChannel::class.java)
                .childHandler(RSChannelInitializer())
                .childOption(ChannelOption.SO_REUSEADDR, true)
                .childOption(ChannelOption.TCP_NODELAY, true)
                .childOption(ChannelOption.CONNECT_TIMEOUT_MILLIS, 30_000)

            logger.info { "Binding proxy runtime to 0.0.0.0:${config.ports.gameBackend}" }
            val result = bootstrap.bind("0.0.0.0", config.ports.gameBackend).sync()
            networkChannel = result.channel()
            if (!result.isSuccess) {
                throw IllegalStateException(
                    "Failed to bind proxy runtime to 0.0.0.0:${config.ports.gameBackend}",
                    result.cause()
                )
            }

            logger.info { "Proxy runtime bound to 0.0.0.0:${config.ports.gameBackend}" }
        } catch (e: Exception) {
            logger.error(e) { "Proxy runtime startup failed" }
            cleanupStartupFailure()
            exitProcess(1)
        }
    }

    private fun loadConfigurations() {
        logger.info { "Loading proxy runtime configuration files from ${Constants.CONFIG_PATH}" }
        config = TomlConfig.load(Constants.CONFIG_PATH.resolve("server.toml"))
        rsaConfig = try {
            TomlConfig.load(RsaConfig.DEFAULT_PATH, mustExist = true)
        } catch (e: FileNotFoundException) {
            logger.info { "Could not find RSA config: $e. Please run `run-tool rsa-key-generator`" }
            exitProcess(1)
        }
        proxyConfig = TomlConfig.load(Constants.CONFIG_PATH.resolve("proxy.toml"))
    }

    private fun cleanupStartupFailure() {
        networkChannel?.close()?.syncUninterruptibly()
        networkChannel = null

        networkGroup?.shutdownGracefully()?.syncUninterruptibly()
        networkGroup = null
    }
}
