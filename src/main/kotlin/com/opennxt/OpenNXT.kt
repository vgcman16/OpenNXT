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
import com.opennxt.tools.impl.cachedownloader.Js5ClientPool
import com.opennxt.tools.impl.cachedownloader.Js5Credentials
import io.netty.bootstrap.ServerBootstrap
import io.netty.channel.Channel
import io.netty.channel.ChannelOption
import io.netty.channel.nio.NioEventLoopGroup
import io.netty.channel.socket.nio.NioServerSocketChannel
import mu.KotlinLogging
import java.io.FileNotFoundException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.file.Files
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
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
    private val startupProbeEnabled by lazy {
        System.getenv("OPENNXT_STARTUP_PROBE")
            ?.trim()
            ?.lowercase()
            ?.let { it == "1" || it == "true" || it == "yes" || it == "on" }
            ?: false
    }

    internal data class RawChecksumTableSelection(
        val bytes: ByteArray,
        val source: String,
        val warning: String? = null
    )

    private const val RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD = 947
    private const val RAW_CHECKSUM_INDEX = 255
    private const val RAW_CHECKSUM_ARCHIVE = 255
    private const val RAW_CHECKSUM_ENTRY_SIZE = 4 + 4 + 4 + 4 + 64
    private const val LIVE_JS5_HOST = "content.runescape.com"
    private const val LIVE_JS5_PORT = 43594
    private const val LIVE_JS5_FETCH_TIMEOUT_SECONDS = 30L
    private const val ENABLE_RETAIL_RAW_CHECKSUM_PASSTHROUGH_ENV =
        "OPENNXT_ENABLE_RETAIL_RAW_CHECKSUM_PASSTHROUGH"
    private const val ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH_ENV =
        "OPENNXT_ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH"
    private const val ENABLE_LOGGED_OUT_JS5_PREFETCH_TABLE_ENV =
        "OPENNXT_ENABLE_LOGGED_OUT_JS5_PREFETCH_TABLE"

    private data class RetailJs5ArchiveKey(val index: Int, val archive: Int)

    private val retailLoggedOutJs5ResponseCache = ConcurrentHashMap<RetailJs5ArchiveKey, ByteArray>()
    private val retailLoggedOutJs5PoolLock = Any()
    @Volatile
    private var retailLoggedOutJs5Pool: Js5ClientPool? = null

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

    internal fun retailRawChecksumPassthroughEnabled(
        build: Int,
        envValue: String? = System.getenv(ENABLE_RETAIL_RAW_CHECKSUM_PASSTHROUGH_ENV)
    ): Boolean {
        if (build != RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD) {
            return false
        }

        return envValue
            ?.trim()
            ?.lowercase()
            ?.let { it == "1" || it == "true" || it == "yes" || it == "on" }
            ?: false
    }

    internal fun retailLoggedOutJs5PassthroughEnabled(
        build: Int,
        envValue: String? = System.getenv(ENABLE_RETAIL_LOGGED_OUT_JS5_PASSTHROUGH_ENV)
    ): Boolean {
        if (build != RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD) {
            return false
        }

        return when (envValue?.trim()?.lowercase()) {
            null, "" -> true
            "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
        }
    }

    internal fun loggedOutJs5PrefetchTableEnabled(
        build: Int,
        envValue: String? = System.getenv(ENABLE_LOGGED_OUT_JS5_PREFETCH_TABLE_ENV)
    ): Boolean {
        when (envValue?.trim()?.lowercase()) {
            "1", "true", "yes", "on" -> return true
            "0", "false", "no", "off" -> return false
        }

        return build < RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD
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

    private fun startupProbe(stage: String) {
        if (!startupProbeEnabled) {
            return
        }

        System.err.println("OPENNXT_STARTUP_PROBE $stage")
        System.err.flush()
    }

    internal fun decodeRawChecksumTableEntries(containerBytes: ByteArray): ChecksumTable {
        val payload = Container.decode(ByteBuffer.wrap(containerBytes)).data
        val entryCount = payload.firstOrNull()?.toInt()?.and(0xff)
            ?: throw IllegalStateException("Empty raw checksum-table payload")
        val entriesSize = 1 + entryCount * RAW_CHECKSUM_ENTRY_SIZE
        require(payload.size >= entriesSize) {
            "Raw checksum-table payload is too short: ${payload.size} < $entriesSize"
        }
        return ChecksumTable.decode(ByteBuffer.wrap(payload.copyOfRange(0, entriesSize)))
    }

    private fun fetchLiveRawChecksumTable(build: Int): ByteArray? {
        val credentials = try {
            Js5Credentials.download()
        } catch (e: Exception) {
            logger.warn(e) { "Failed to download retail JS5 credentials for build=$build" }
            return null
        }

        if (credentials.version != build) {
            logger.warn {
                "Skipping live raw JS5 checksum-table fetch because retail jav_config " +
                    "reported server_version=${credentials.version} while local build=$build"
            }
            return null
        }

        val pool = Js5ClientPool(1, 1, LIVE_JS5_HOST, LIVE_JS5_PORT)
        try {
            pool.openConnections(amount = 1)
            val client = pool.getClient()
            check(client.awaitConnected(LIVE_JS5_FETCH_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                "Timed out waiting for retail JS5 connection to $LIVE_JS5_HOST:$LIVE_JS5_PORT"
            }

            val request = pool.addRequest(true, RAW_CHECKSUM_INDEX, RAW_CHECKSUM_ARCHIVE)
                ?: throw IllegalStateException("Failed to enqueue retail raw checksum-table request [255,255]")
            check(request.awaitCompletion(LIVE_JS5_FETCH_TIMEOUT_SECONDS, TimeUnit.SECONDS)) {
                "Timed out waiting for retail raw checksum table [255,255]"
            }

            val buffer = request.buffer ?: throw IllegalStateException("Retail raw checksum-table buffer was null")
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            buffer.rewind()
            logger.info { "Fetched live raw JS5 checksum table for build=$build (${bytes.size} bytes)" }
            return bytes
        } catch (e: Exception) {
            logger.warn(e) { "Failed to fetch live raw JS5 checksum table for build=$build" }
            return null
        } finally {
            pool.close()
        }
    }

    private fun getRetailLoggedOutJs5Pool(): Js5ClientPool {
        retailLoggedOutJs5Pool?.let { return it }

        synchronized(retailLoggedOutJs5PoolLock) {
            retailLoggedOutJs5Pool?.let { return it }

            val pool = Js5ClientPool(1, 1, LIVE_JS5_HOST, LIVE_JS5_PORT)
            pool.openConnections(amount = 1)
            retailLoggedOutJs5Pool = pool
            return pool
        }
    }

    internal fun fetchRetailLoggedOutJs5Archive(
        build: Int,
        index: Int,
        archive: Int,
        priority: Boolean,
        timeoutSeconds: Long = LIVE_JS5_FETCH_TIMEOUT_SECONDS,
    ): ByteArray? {
        if (!retailLoggedOutJs5PassthroughEnabled(build)) {
            return null
        }

        val key = RetailJs5ArchiveKey(index, archive)
        retailLoggedOutJs5ResponseCache[key]?.let { return it.copyOf() }

        synchronized(retailLoggedOutJs5PoolLock) {
            retailLoggedOutJs5ResponseCache[key]?.let { return it.copyOf() }

            val pool = try {
                getRetailLoggedOutJs5Pool()
            } catch (e: Exception) {
                logger.warn(e) {
                    "Failed to prepare retail logged-out JS5 passthrough pool for build=$build index=$index archive=$archive"
                }
                return null
            }

            return try {
                pool.healthCheck()
                val request = pool.addRequest(priority, index, archive)
                    ?: throw IllegalStateException(
                        "Failed to enqueue retail logged-out JS5 request index=$index archive=$archive"
                    )
                check(request.awaitCompletion(timeoutSeconds, TimeUnit.SECONDS)) {
                    "Timed out waiting for retail logged-out JS5 response index=$index archive=$archive"
                }
                val buffer = request.buffer ?: throw IllegalStateException(
                    "Retail logged-out JS5 response buffer was null for index=$index archive=$archive"
                )
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                buffer.rewind()
                retailLoggedOutJs5ResponseCache[key] = bytes.copyOf()
                logger.info {
                    "Using retail logged-out JS5 passthrough for build=$build index=$index archive=$archive (${bytes.size} bytes)"
                }
                bytes
            } catch (e: Exception) {
                logger.warn(e) {
                    "Failed retail logged-out JS5 passthrough for build=$build index=$index archive=$archive"
                }
                null
            }
        }
    }

    internal fun selectRawChecksumTableSource(
        build: Int,
        overrideBytes: ByteArray?,
        generatedLocalBytes: ByteArray,
        fetchLiveRawBytes: (Int) -> ByteArray?
    ): RawChecksumTableSelection {
        if (overrideBytes != null && build != RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD) {
            return RawChecksumTableSelection(overrideBytes, "override")
        }

        if (build != RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD) {
            return RawChecksumTableSelection(generatedLocalBytes, "generated-local")
        }

        val generatedLocalTable = try {
            decodeRawChecksumTableEntries(generatedLocalBytes)
        } catch (e: Exception) {
            return RawChecksumTableSelection(
                generatedLocalBytes,
                "generated-local",
                "Failed to decode generated raw JS5 checksum table for build=$build: ${e.message}"
            )
        }

        val liveRawBytes = try {
            fetchLiveRawBytes(build)
        } catch (e: Exception) {
            return RawChecksumTableSelection(
                generatedLocalBytes,
                "generated-local",
                "Failed to fetch live retail raw JS5 checksum table for build=$build: ${e.message}"
            )
        }

        if (liveRawBytes == null) {
            return RawChecksumTableSelection(
                generatedLocalBytes,
                "generated-local",
                "Live retail raw JS5 checksum table unavailable for build=$build; using generated local table"
            )
        }

        val liveRawTable = try {
            decodeRawChecksumTableEntries(liveRawBytes)
        } catch (e: Exception) {
            return RawChecksumTableSelection(
                generatedLocalBytes,
                "generated-local",
                "Failed to decode live retail raw JS5 checksum table for build=$build: ${e.message}"
            )
        }

        if (generatedLocalTable != liveRawTable) {
            return RawChecksumTableSelection(
                liveRawBytes,
                "live-retail-raw",
                "Live retail raw JS5 checksum table entries differ from generated local entries for build=$build; " +
                    "using live retail raw table because retail raw checksum passthrough is enabled"
            )
        }

        return RawChecksumTableSelection(liveRawBytes, "live-retail-raw")
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
        startupProbe("run-enter")
        logger.info { "Starting OpenNXT (vgcman16 fork)" }
        startupProbe("before-load-configurations")
        loadConfigurations()
        startupProbe("after-load-configurations")

        try {
            val protPath = Constants.PROT_PATH.resolve(config.build.toString())
            if (!Files.exists(protPath)) {
                logger.error { "Protocol information not found for build ${config.build}." }
                logger.error { " Looked in: $protPath" }
                logger.error { " Please look check out the following wiki page for help: <TO-DO>" }
                exitProcess(1)
            }

            startupProbe("before-protocol-load")
            protocol = ProtocolInformation(protPath)
            protocol.load()
            startupProbe("after-protocol-load")

            logger.info { "Setting up HTTP server" }
            startupProbe("before-http-init")
            http = HttpServer(config)
            http.init(skipHttpFileVerification)
            startupProbe("after-http-init")
            http.bind()
            startupProbe("after-http-bind")

            logger.info { "Opening filesystem from ${Constants.CACHE_PATH}" }
            startupProbe("before-filesystem-open")
            filesystem = SqliteFilesystem(Constants.CACHE_PATH)
            startupProbe("after-filesystem-open")

            logger.info { "Generating prefetch table" }
            startupProbe("before-prefetch-table")
            prefetches = PrefetchTable.of(filesystem, config.build)
            startupProbe("after-prefetch-table")

            logger.info { "Generating & encoding checksum tables" }
            startupProbe("before-checksum-table")
            val generatedChecksumTable = Container.wrap(
                ChecksumTable.create(filesystem, false)
                    .encode(rsaConfig.js5.modulus, rsaConfig.js5.exponent)
            ).array()
            val generatedHttpChecksumTable = Container.wrap(
                ChecksumTable.create(filesystem, true)
                    .encode(rsaConfig.js5.modulus, rsaConfig.js5.exponent)
            ).array()
            startupProbe("after-checksum-table")
            val rawChecksumOverride = loadJs5ChecksumOverride()
            val rawChecksumSelection = if (
                rawChecksumOverride == null &&
                !retailRawChecksumPassthroughEnabled(config.build)
            ) {
                RawChecksumTableSelection(
                    bytes = generatedChecksumTable,
                    source = "generated-local",
                    warning = if (config.build == RETAIL_RAW_CHECKSUM_PASSTHROUGH_BUILD) {
                        "Retail raw JS5 checksum passthrough is disabled by default because patched clients " +
                            "expect the local JS5 RSA modulus; set $ENABLE_RETAIL_RAW_CHECKSUM_PASSTHROUGH_ENV=1 " +
                            "to re-enable retail raw passthrough for diagnostics."
                    } else {
                        null
                    }
                )
            } else {
                selectRawChecksumTableSource(
                    build = config.build,
                    overrideBytes = rawChecksumOverride,
                    generatedLocalBytes = generatedChecksumTable,
                    fetchLiveRawBytes = ::fetchLiveRawChecksumTable
                )
            }
            rawChecksumSelection.warning?.let { warning ->
                logger.warn { warning }
            }
            if (retailLoggedOutJs5PassthroughEnabled(config.build)) {
                logger.warn {
                    "Retail logged-out JS5 passthrough is enabled for build=${config.build}; " +
                        "logged-out JS5 archive/reference requests will be served from live retail when available."
                }
            }
            checksumTable = rawChecksumSelection.bytes
            logger.info {
                "Using raw JS5 checksum table source=${rawChecksumSelection.source} " +
                    "for build=${config.build} (${checksumTable.size} bytes)"
            }
            httpChecksumTable = loadHttpChecksumOverride()
                ?: fetchLiveHttpChecksumTable(config.build)
                ?: generatedHttpChecksumTable
            startupProbe("after-http-checksum-table")

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
            startupProbe("before-game-bind")
            val result = bootstrap.bind("0.0.0.0", config.ports.gameBackend).sync()
            networkChannel = result.channel()
            if (!result.isSuccess) {
                throw IllegalStateException("Failed to bind to 0.0.0.0:${config.ports.gameBackend}", result.cause())
            }

            startupProbe("after-game-bind")
            logger.info { "Game server bound to 0.0.0.0:${config.ports.gameBackend}" }
        } catch (e: Exception) {
            startupProbe("startup-exception:${e::class.simpleName}")
            logger.error(e) { "Server startup failed" }
            cleanupStartupFailure()
            exitProcess(1)
        }
    }
}
