package com.opennxt.tools.impl.cachedownloader

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.google.common.util.concurrent.ThreadFactoryBuilder
import com.opennxt.Constants
import com.opennxt.ext.getCrc32
import com.opennxt.filesystem.ChecksumTable
import com.opennxt.filesystem.Container
import com.opennxt.filesystem.Filesystem
import com.opennxt.filesystem.ReferenceTable
import com.opennxt.filesystem.openFilesystem
import com.opennxt.tools.Tool
import java.lang.Thread.sleep
import java.nio.ByteBuffer
import java.util.concurrent.*
import kotlin.system.exitProcess

internal fun parseSelectionCsv(value: String?): Set<Int>? = value
    ?.split(",")
    ?.mapNotNull { token ->
        val trimmed = token.trim()
        if (trimmed.isEmpty()) null else trimmed.toInt()
    }
    ?.toSet()
    ?.takeIf { it.isNotEmpty() }

class CacheDownloader : Tool("cache-downloader", "Updates / downloads the cache from Jagex' JS5 servers") {
    private val ip by option(help = "Live js5 server ip").default("content.runescape.com")
    private val port by option(help = "Live js5 server port").int().default(43594)
    private val numJs5Clients by option(help = "The amount of concurrent js5 connections").int().default(1)
    private val numHttpClients by option(help = "The max amount of concurrent HTTP connections").int().default(3)
    private val ioThreads by option(help = "The number of I/O threads for cache-related operations").int().default(8)
    private val checkThreads by option(help = "The number of I/O threads for checking which files require updating").int()
        .default(4)
    private val configUrl by option(
        "--config-url",
        help = "Jagex jav_config.ws URL used to resolve the JS5 token and build"
    ).default(Js5Credentials.DEFAULT_CONFIG_URL)
    private val expectedBuild by option(
        "--expected-build",
        help = "Expected JS5 build; defaults to 947 for the 947 client, or 0 to disable the guard"
    ).int().default(947)
    private val httpTimeoutMillis by option(
        "--http-timeout-millis",
        help = "Connect/read timeout for index 40 HTTP archive downloads before retry/fallback"
    ).int().default(15_000)
    private val maxHttpAttempts by option(
        "--max-http-attempts",
        help = "HTTP attempts for index 40 archives before falling back to JS5; 0 disables HTTP for index 40"
    ).int().default(2)
    private val disableHttp by option(
        "--disable-http",
        help = "Download index 40 archives over JS5 immediately instead of the HTTP mirror"
    ).flag(default = false)
    private val indicesArg by option(help = "Comma-separated indices to refresh; defaults to all indices")
    private val archivesArg by option(help = "Comma-separated archive ids to refresh within the selected indices")

    private lateinit var cache: Filesystem

    private lateinit var checkerExecutor: ExecutorService

    private lateinit var clientPool: Js5ClientPool
    private lateinit var checksumTable: ChecksumTable

    private lateinit var requestHandler: Js5RequestHandler

    private fun shouldProcessIndex(index: Int, selectedIndices: Set<Int>?): Boolean =
        selectedIndices == null || index in selectedIndices

    fun request(priority: Boolean, index: Int, archive: Int): Js5RequestHandler.ArchiveRequest {
        if (index == 255) {
            val request = Js5RequestHandler.ArchiveRequest(index, archive, priority)

            return request
        } else {
            TODO("Non-255 requests")
        }
    }

    private fun downloadChecksumTable() {
        val request = clientPool.addRequest(true, 255, 255)
            ?: throw IllegalStateException("failed to request [255,255]")
        if (!request.awaitCompletion(30, TimeUnit.SECONDS)) {
            logger.error { "Took more than 30 seconds to download the checksum table. Exiting." }
            exitProcess(1)
        }

        logger.info { "Finished downloading checksum table!" }
        checksumTable = ChecksumTable.decode(ByteBuffer.wrap(Container.decode(request.buffer!!).data))
        checksumTable.entries.forEachIndexed { index, entry ->
            logger.info { "checksum for index $index = $entry" }
        }
    }

    private fun createNewIndices() {
        if (checksumTable.entries.size > cache.numIndices()) {
            logger.info { "Need to expand cache! Got ${cache.numIndices()} indices, need ${checksumTable.entries.size}" }
            for (i in cache.numIndices() until checksumTable.entries.size) {
                cache.createIndex(i)
                logger.info { "Creating index $i in the cache" }
            }
        } else {
            logger.info { "Cache is the correct size (${checksumTable.entries.size} indices)" }
        }
    }

    private fun updateReferenceTables(selectedIndices: Set<Int>?) {
        val pending = HashSet<Js5RequestHandler.ArchiveRequest>()

        checksumTable.entries.forEachIndexed { index, entry ->
            if (!shouldProcessIndex(index, selectedIndices)) {
                return@forEachIndexed
            }
            if (entry.crc == 0 && entry.version == 0) return@forEachIndexed

            val existingRaw = cache.readReferenceTable(index)
            if (existingRaw == null) {
                logger.info { "Reference table for index $index missing, adding to downloads..." }
                pending += clientPool.addRequest(true, 255, index)
                    ?: throw IllegalStateException("Failed to add reference table request $index")
                return@forEachIndexed
            }

            val crc = existingRaw.getCrc32()
            if (entry.crc != crc) {
                logger.info { "CRC mismatch in reference table for index $index, adding to downloads..." }
                pending += clientPool.addRequest(true, 255, index)
                    ?: throw IllegalStateException("Failed to add reference table request $index")
                return@forEachIndexed
            }

            val existing = ReferenceTable(cache, index)
            existing.decode(ByteBuffer.wrap(Container.decode(existingRaw).data))

            if (existing.version != entry.version) {
                logger.info { "Version mismatch in reference table for index $index, adding to downloads..." }
                pending += clientPool.addRequest(true, 255, index)
                    ?: throw IllegalStateException("Failed to add reference table request $index")
                return@forEachIndexed
            }

            logger.info { "Reference table for index $index is up-to-date." }
        }

        pending.forEach { request ->
            if (!request.awaitCompletion(30, TimeUnit.SECONDS)) {
                logger.error { "Took more than 30 seconds to download reference table for index ${request.archive}. Exiting." }
                exitProcess(1)
            }

            val buffer = request.buffer ?: throw NullPointerException("Buffer for completed archive request is null")
            val referenceTable = ReferenceTable(cache, request.archive)

            val crc = buffer.getCrc32()
            val entry = checksumTable.entries[request.archive]
            if (crc != entry.crc) {
                logger.error { "CRC mismatch in downloaded reference table for index ${request.archive}. Exiting." }
                exitProcess(1)
            }

            val container = Container.decode(buffer)
            referenceTable.decode(ByteBuffer.wrap(container.data))
            if (referenceTable.version != entry.version) {
                logger.error { "Version mismatch in downloaded reference table for index ${request.archive}. Exiting." }
                exitProcess(1)
            }

            cache.writeReferenceTable(request.archive, buffer.array(), container.version, crc)
            logger.info { "Finished downloading & saving reference table for index ${request.archive}." }
        }
    }

    private fun downloadTargetedArchives(selectedIndices: Set<Int>, selectedArchives: Set<Int>) {
        logger.info {
            "Starting targeted archive sync for indices=${
                selectedIndices.sorted().joinToString(",")
            } archives=${selectedArchives.sorted().joinToString(",")}"
        }

        val pending = ArrayList<Js5RequestHandler.ArchiveRequest>()

        selectedIndices.sorted().forEach { index ->
            val table = cache.getReferenceTable(index)
                ?: throw NullPointerException("Couldn't get reference table for index $index")

            selectedArchives.sorted().forEach { archiveId ->
                val archive = table.archives[archiveId]
                if (archive == null) {
                    logger.info { "Skipping [$index,$archiveId] because it is not present in the reference table" }
                    return@forEach
                }

                val existing = cache.read(index, archiveId)
                val reason = when {
                    existing == null -> "missing"
                    existing.getCrc32(existing.capacity() - 2) != archive.crc -> "crc-mismatch"
                    else -> {
                        existing.position(existing.capacity() - 2)
                        val version = existing.short.toInt() and 0xffff
                        if (version != (archive.version and 0xffff)) "version-mismatch" else null
                    }
                }

                if (reason == null) {
                    logger.info { "Archive [$index,$archiveId] is already up-to-date" }
                    return@forEach
                }

                logger.info { "Queueing [$index,$archiveId] because $reason" }
                val request = clientPool.addRequest(false, index, archiveId)
                    ?: throw IllegalStateException("Failed to add archive request [$index,$archiveId]")
                pending += request
            }
        }

        if (pending.isEmpty()) {
            logger.info { "No targeted archives required updates" }
            return
        }

        pending.forEach { request ->
            if (!request.awaitCompletion(60, TimeUnit.SECONDS)) {
                logger.error { "Took more than 60 seconds to download targeted archive [${request.index},${request.archive}]. Exiting." }
                exitProcess(1)
            }

            writeCompletedRequest(cache, request)
            logger.info { "Finished downloading & saving targeted archive [${request.index},${request.archive}]." }
        }
    }

    override fun runTool() {
        check(numJs5Clients > 0) { "num-js5-clients must be greater than 0" }
        check(numHttpClients > 0) { "num-http-clients must be greater than 0" }
        check(ioThreads > 0) { "io-threads must be greater than 0" }
        check(httpTimeoutMillis > 0) { "http-timeout-millis must be greater than 0" }
        check(maxHttpAttempts >= 0) { "max-http-attempts must be greater than or equal to 0" }

        val selectedIndices = parseSelectionCsv(indicesArg)
        val selectedArchives = parseSelectionCsv(archivesArg)
        require(selectedArchives == null || selectedIndices != null) {
            "--archives-arg requires --indices-arg"
        }

        logger.info { "Starting download from $ip:$port" }

        logger.info { "Opening filesystem from ${Constants.CACHE_PATH}" }
        cache = openFilesystem(Constants.CACHE_PATH)

        logger.info { "Setting up client pool with $numJs5Clients js5 clients and $numHttpClients http clients" }
        clientPool = Js5ClientPool(numJs5Clients, numHttpClients, ip, port, configUrl = configUrl, httpTimeoutMillis = httpTimeoutMillis)
        val credentials = clientPool.resolveCredentials()
        if (expectedBuild > 0 && credentials.version != expectedBuild) {
            logger.error {
                "Refusing to download cache for JS5 build ${credentials.version}; expected $expectedBuild for the 947 client. " +
                    "Use --expected-build=0 only when intentionally syncing a different build."
            }
            exitProcess(1)
        }
        logger.info {
            "Using JS5 build ${credentials.version} from $configUrl; " +
                "index 40 HTTP ${if (disableHttp || maxHttpAttempts == 0) "disabled" else "enabled with $maxHttpAttempts attempts and ${httpTimeoutMillis}ms timeout"}"
        }

        logger.info { "Grabbing checksum and reference tables..." }
        clientPool.openConnections(amount = 1)
        val client = clientPool.getClient()

        try {
            if (!client.awaitConnected(30, TimeUnit.SECONDS)) {
                logger.error { "Took more than 30 seconds to successfully connect to js5 servers. Exiting." }
                exitProcess(1)
            }
        } catch (e: InterruptedException) {
            logger.error { "Lock on connection got interrupted. Exiting." }
            exitProcess(1)
        }

        logger.info { "Connected! Requesting checksum table now..." }
        downloadChecksumTable()
        createNewIndices()

        logger.info { "Checking tables" }
        updateReferenceTables(selectedIndices)

        if (selectedIndices != null && selectedArchives != null) {
            downloadTargetedArchives(selectedIndices, selectedArchives)
            clientPool.close()
            return
        }

        logger.info { "Setting up request handler" }
        requestHandler = Js5RequestHandler(
            clientPool,
            cache,
            ioThreads,
            useHttpForIndex40 = !disableHttp,
            maxHttpAttempts = maxHttpAttempts
        )

        logger.info { "Starting table checks" }
        checkerExecutor = Executors.newFixedThreadPool(checkThreads, ThreadFactoryBuilder()
            .setNameFormat("table-checker-%d")
            .setUncaughtExceptionHandler { t, e ->
                logger.error { "Uncaught exception in thread ${t.name}: $e" }
                e.printStackTrace()
            }
            .build())

        // start music first, big archive over http we can download first for faster overall downloads
        val includeMusic = shouldProcessIndex(40, selectedIndices)
        val musicChecker = if (includeMusic) {
            IndexCompletionChecker(cache, 40, requestHandler).also(checkerExecutor::submit)
        } else {
            null
        }

        val completionCheckers = HashSet<IndexCompletionChecker>()
        checksumTable.entries.forEachIndexed { index, entry ->
            if (!shouldProcessIndex(index, selectedIndices) || index == 40 || (entry.crc == 0 && entry.version == 0)) {
                return@forEachIndexed
            }

            val checker = IndexCompletionChecker(cache, index, requestHandler)
            completionCheckers.add(checker)
            checkerExecutor.submit(checker)
        }

        // Other clients in the pool will automatically be opened in the request handler
        Thread(requestHandler, "js5-request-handler").start()

        var doneJs5 = false
        var doneHttp = false
        while (true) {
            val snapshot = requestHandler.createSnapshot()

            if (!clientPool.closed && completionCheckers.all { it.completed } && snapshot.pendingCount == 0 && snapshot.processingCount == 0) {
                logger.info { "All js5 operations are done, closing js5 client pool" }
                clientPool.close()
                doneJs5 = true
            }

            if (clientPool.closed && (musicChecker?.completed ?: true) && snapshot.pendingHttpCount == 0) {
                logger.info { "All http operations are done, preparing to shutdown" }
                doneHttp = true
            }

            if (doneJs5 && doneHttp && snapshot.pendingIOOPerations == 0) {
                logger.info { "No more pending IO operations, shutting down remaining things" }
                logger.error { "We can't close the cache yet. Should probably support that." }
                exitProcess(0)
            }

            logger.info {
                "Unassigned: ${snapshot.pendingCount} (~${snapshot.pendingSize / 1024L / 1024L}MB). Assigned: ${snapshot.processingCount} (~${snapshot.processingSize / 1024L / 1024L}MB). Http pending: ${snapshot.pendingHttpCount} (~${snapshot.pendingHttpSize / 1024L / 1024L}MB). Js5 Bandwidth: ${
                    "%.2f".format(
                        Js5ClientPipeline.getReadThroughput().toDouble() / 1024.0 / 1024.0
                    )
                }MB/s (excludes http). Pending IO ops: ${snapshot.pendingIOOPerations}. Last worker tick: ${System.currentTimeMillis()-snapshot.lastTick}ms ago"
            }
            sleep(1000)
        }
    }
}
