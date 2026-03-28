package com.opennxt

import com.github.ajalt.clikt.core.CliktCommand
import com.github.ajalt.clikt.core.Context
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.options.option
import com.opennxt.api.stat.Stat
import com.opennxt.config.RsaConfig
import com.opennxt.config.ServerConfig
import com.opennxt.config.TomlConfig
import com.opennxt.filesystem.ChecksumTable
import com.opennxt.filesystem.Container
import com.opennxt.filesystem.Filesystem
import com.opennxt.filesystem.prefetches.PrefetchTable
import com.opennxt.filesystem.sqlite.SqliteFilesystem
import com.opennxt.login.AuthoritativeLoginProcessor
import com.opennxt.login.LoginThread
import com.opennxt.model.commands.CommandRepository
import com.opennxt.model.lobby.Lobby
import com.opennxt.model.tick.TickEngine
import com.opennxt.model.world.World
import com.opennxt.net.RSChannelInitializer
import com.opennxt.net.game.protocol.ProtocolInformation
import com.opennxt.net.http.HttpServer
import com.opennxt.resources.FilesystemResources
import io.netty.bootstrap.ServerBootstrap
import io.netty.channel.Channel
import io.netty.channel.ChannelOption
import io.netty.channel.nio.NioEventLoopGroup
import io.netty.channel.socket.nio.NioServerSocketChannel
import mu.KotlinLogging
import java.io.FileNotFoundException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import kotlin.system.exitProcess

object OpenNXT : CliktCommand(name = "run-server") {
    val skipHttpFileVerification by option(help = "Skips file verification when http server starts").flag(default = false)

    private val logger = KotlinLogging.logger {}

    lateinit var config: ServerConfig
    lateinit var rsaConfig: RsaConfig

    lateinit var http: HttpServer

    lateinit var filesystem: Filesystem
    lateinit var resources: FilesystemResources
    lateinit var prefetches: PrefetchTable
    lateinit var checksumTable: ByteArray
    lateinit var httpChecksumTable: ByteArray

    lateinit var protocol: ProtocolInformation
    lateinit var tickEngine: TickEngine

    lateinit var world: World
    lateinit var lobby: Lobby

    lateinit var commands: CommandRepository

    private val bootstrap = ServerBootstrap()
    private var networkGroup: NioEventLoopGroup? = null
    private var networkChannel: Channel? = null

    override fun help(context: Context): String = "Launches the vgcman16 OpenNXT server"

    private fun loadConfigurations() {
        logger.info { "Loading configuration files from ${Constants.CONFIG_PATH}" }
        config = TomlConfig.load(Constants.CONFIG_PATH.resolve("server.toml"))
        rsaConfig = try {
            TomlConfig.load(RsaConfig.DEFAULT_PATH, mustExist = true)
        } catch (e: FileNotFoundException) {
            logger.info { "Could not find RSA config: $e. Please run `run-tool rsa-key-generator`" }
            exitProcess(1)
        }
    }

    fun reloadContent() {
        Stat.reload()
    }

    private fun loadJs5ChecksumOverride(): ByteArray? {
        val disableOverride = System.getenv("OPENNXT_DISABLE_CHECKSUM_OVERRIDE")
            ?.trim()
            ?.lowercase()
            ?.let { it == "1" || it == "true" || it == "yes" }
            ?: false
        if (disableOverride) {
            logger.warn { "Skipping JS5 checksum table override because OPENNXT_DISABLE_CHECKSUM_OVERRIDE is enabled" }
            return null
        }

        val overridePath = Constants.DATA_PATH.resolve("debug").resolve("checksum-table-override.bin")
        if (!Files.exists(overridePath)) {
            return null
        }

        val bytes = Files.readAllBytes(overridePath)
        logger.warn { "Using JS5 checksum table override from $overridePath (${bytes.size} bytes)" }
        return bytes
    }

    private fun loadHttpChecksumOverride(): ByteArray? {
        val disableOverride = System.getenv("OPENNXT_DISABLE_HTTP_CHECKSUM_OVERRIDE")
            ?.trim()
            ?.lowercase()
            ?.let { it == "1" || it == "true" || it == "yes" }
            ?: false
        if (disableOverride) {
            logger.warn { "Skipping HTTP checksum table override because OPENNXT_DISABLE_HTTP_CHECKSUM_OVERRIDE is enabled" }
            return null
        }

        val overridePath = Constants.DATA_PATH.resolve("debug").resolve("http-checksum-table-override.bin")
        if (!Files.exists(overridePath)) {
            return null
        }

        val bytes = Files.readAllBytes(overridePath)
        logger.warn { "Using HTTP checksum table override from $overridePath (${bytes.size} bytes)" }
        return bytes
    }

    private fun fetchLiveHttpChecksumTable(build: Int): ByteArray? {
        val url = URL("https://content.runescape.com/ms?m=0&a=255&k=$build&g=255&c=0&v=0")
        val connection = (url.openConnection() as? HttpURLConnection) ?: return null
        connection.requestMethod = "GET"
        connection.connectTimeout = 10_000
        connection.readTimeout = 10_000
        connection.setRequestProperty("Accept", "*/*")
        connection.setRequestProperty("Connection", "close")
        return try {
            val status = connection.responseCode
            if (status != HttpURLConnection.HTTP_OK) {
                logger.warn { "Live HTTP checksum fetch returned status=$status for build=$build" }
                null
            } else {
                connection.inputStream.use { input ->
                    val bytes = input.readBytes()
                    logger.info { "Fetched live HTTP checksum table for build=$build (${bytes.size} bytes)" }
                    bytes
                }
            }
        } catch (e: Exception) {
            logger.warn(e) { "Failed to fetch live HTTP checksum table for build=$build" }
            null
        } finally {
            connection.disconnect()
        }
    }

    private fun cleanupStartupFailure() {
        networkChannel?.close()?.syncUninterruptibly()
        networkChannel = null

        networkGroup?.shutdownGracefully()?.syncUninterruptibly()
        networkGroup = null

        if (this::http.isInitialized) {
            try {
                http.close()
            } catch (e: Exception) {
                logger.warn(e) { "Failed to close HTTP server during startup cleanup" }
            }
        }
    }

    override fun run() {
        logger.info { "Starting OpenNXT (vgcman16 fork)" }
        loadConfigurations()

        try {
            val protPath = Constants.PROT_PATH.resolve(config.build.toString())
            if (!Files.exists(protPath)) {
                logger.error { "Protocol information not found for build ${config.build}." }
                logger.error { " Looked in: $protPath" }
                logger.error { " Please look check out the following wiki page for help: <TO-DO>" }
                exitProcess(1)
            }

            protocol = ProtocolInformation(protPath)
            protocol.load()

            logger.info { "Setting up HTTP server" }
            http = HttpServer(config)
            http.init(skipHttpFileVerification)
            http.bind()

            logger.info { "Opening filesystem from ${Constants.CACHE_PATH}" }
            filesystem = SqliteFilesystem(Constants.CACHE_PATH)

            logger.info { "Generating prefetch table" }
            prefetches = PrefetchTable.of(filesystem, config.build)

            logger.info { "Generating & encoding checksum tables" }
            val generatedChecksumTable = Container.wrap(
                ChecksumTable.create(filesystem, false)
                    .encode(rsaConfig.js5.modulus, rsaConfig.js5.exponent)
            ).array()
            val generatedHttpChecksumTable = Container.wrap(
                ChecksumTable.create(filesystem, true)
                    .encode(rsaConfig.js5.modulus, rsaConfig.js5.exponent)
            ).array()
            checksumTable = loadJs5ChecksumOverride() ?: generatedChecksumTable
            httpChecksumTable = loadHttpChecksumOverride()
                ?: fetchLiveHttpChecksumTable(config.build)
                ?: generatedHttpChecksumTable

            logger.info { "Setting up filesystem resource manager" }
            resources = FilesystemResources(filesystem, Constants.RESOURCE_PATH)

            logger.info { "Setting up command repository" }
            commands = CommandRepository()

            logger.info { "Starting js5 thread" }
            Js5Thread.start()

            logger.info { "Starting login thread" }
            LoginThread.configure(AuthoritativeLoginProcessor)
            LoginThread.start()

            logger.info { "Starting tick engine" }
            tickEngine = TickEngine()

            logger.info { "Instantiating game world" }
            world = World()
            tickEngine.submitTickable(world)

            logger.info { "Instantiating lobby" }
            lobby = Lobby()
            tickEngine.submitTickable(lobby)

            logger.info { "Reloading content-related things" }
            reloadContent()

            logger.info { "Starting network" }
            networkGroup = NioEventLoopGroup()
            bootstrap.group(networkGroup)
                .channel(NioServerSocketChannel::class.java)
                .childHandler(RSChannelInitializer())
                .childOption(ChannelOption.SO_REUSEADDR, true)
                .childOption(ChannelOption.TCP_NODELAY, true)
                .childOption(ChannelOption.CONNECT_TIMEOUT_MILLIS, 30_000)

            logger.info { "Binding game server to 0.0.0.0:${config.ports.gameBackend}" }
            val result = bootstrap.bind("0.0.0.0", config.ports.gameBackend).sync()
            networkChannel = result.channel()
            if (!result.isSuccess) {
                throw IllegalStateException("Failed to bind to 0.0.0.0:${config.ports.gameBackend}", result.cause())
            }

            logger.info { "Game server bound to 0.0.0.0:${config.ports.gameBackend}" }
        } catch (e: Exception) {
            logger.error(e) { "Server startup failed" }
            cleanupStartupFailure()
            exitProcess(1)
        }
    }
}
