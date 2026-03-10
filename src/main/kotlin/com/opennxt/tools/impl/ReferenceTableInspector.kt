package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.filesystem.Container
import com.opennxt.filesystem.ReferenceTable
import com.opennxt.tools.Tool
import com.opennxt.tools.impl.cachedownloader.Js5ClientPool
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.util.concurrent.TimeUnit

class ReferenceTableInspector : Tool(
    "reference-table-inspector",
    "Inspects local and live reference-table metadata for selected JS5 indices"
) {
    private val indicesArg by option(help = "Comma-separated index list")
        .default("32,33,34")
    private val outputDir by option(help = "Directory where inspection reports should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("reference-table-inspect").toString())
    private val live by option(help = "Also fetch and inspect live Jagex reference tables").flag(default = false)
    private val metadataOnly by option(help = "Only inspect table metadata; skip loading archive bodies").flag(default = false)
    private val ip by option(help = "Live js5 host").default("content.runescape.com")
    private val port by option(help = "Live js5 port").int().default(43594)
    private val timeoutSeconds by option(help = "Live fetch timeout in seconds").int().default(30)

    override fun runTool() {
        val indices = indicesArg.split(",")
            .map { it.trim() }
            .filter { it.isNotEmpty() }
            .map { it.toInt() }
        val baseDir = Paths.get(outputDir)
        Files.createDirectories(baseDir)

        val localReports = indices.map { inspectLocal(it) }
        Files.writeString(baseDir.resolve("local-report.txt"), localReports.joinToString("\n\n") { it.render() })

        if (live) {
            val liveReports = inspectLive(indices)
            Files.writeString(baseDir.resolve("live-report.txt"), liveReports.joinToString("\n\n") { it.render() })
        }

        logger.info { "Wrote reference-table inspection reports to $baseDir" }
    }

    private fun inspectLocal(index: Int): Inspection {
        val raw = filesystem.readReferenceTable(index)
            ?: throw IllegalStateException("Missing local reference table for index $index")
        return inspectBytes("local", index, raw)
    }

    private fun inspectLive(indices: List<Int>): List<Inspection> {
        val pool = Js5ClientPool(1, 1, ip, port)
        try {
            pool.openConnections(amount = 1)
            val client = pool.getClient()
            check(client.awaitConnected(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for live JS5 connection"
            }

            return indices.map { index ->
                val request = pool.addRequest(true, 255, index)
                    ?: throw IllegalStateException("Failed to queue live reference table request for index $index")
                check(request.awaitCompletion(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                    "Timed out waiting for live reference table index $index"
                }

                val buffer = request.buffer ?: throw IllegalStateException("Null live buffer for index $index")
                val bytes = ByteArray(buffer.remaining())
                buffer.get(bytes)
                buffer.rewind()
                inspectBytes("live", index, ByteBuffer.wrap(bytes))
            }
        } finally {
            pool.close()
        }
    }

    private fun inspectBytes(source: String, index: Int, raw: ByteBuffer): Inspection {
        val rawCopy = raw.duplicate()
        val rawBytes = ByteArray(rawCopy.remaining())
        rawCopy.get(rawBytes)

        val container = Container.decode(ByteBuffer.wrap(rawBytes))
        val payload = container.data
        val table = ReferenceTable(filesystem, index)
        table.decode(ByteBuffer.wrap(payload))

        val totalFileBytes: Long
        val firstArchiveFileBytes: List<Int>
        if (metadataOnly) {
            totalFileBytes = -1
            firstArchiveFileBytes = emptyList()
        } else {
            totalFileBytes = table.archives.keys.sumOf { archiveId ->
                val archive = table.loadArchive(archiveId)
                    ?: throw IllegalStateException("Failed to load archive [$index,$archiveId]")
                archive.files.values.sumOf { it.data.size.toLong() }
            }
            firstArchiveFileBytes = table.archives.keys.take(16).map { archiveId ->
                val archive = table.loadArchive(archiveId)
                    ?: throw IllegalStateException("Failed to load archive [$index,$archiveId]")
                archive.files.values.sumOf { it.data.size }
            }
        }

        return Inspection(
            source = source,
            index = index,
            rawContainerBytes = rawBytes.size,
            decodedPayloadBytes = payload.size,
            containerVersion = container.version,
            format = table.format,
            mask = table.mask,
            archiveCount = table.archives.size,
            highestEntry = table.highestEntry(),
            archiveSize = table.archiveSize(),
            totalCompressedSize = table.totalCompressedSize(),
            totalUncompressedSize = table.archives.values.sumOf { it.uncompressedSize.toLong() },
            totalFileBytes = totalFileBytes,
            firstArchiveIds = table.archives.keys.take(16),
            firstArchiveCompressedSizes = table.archives.values.take(16).map { it.compressedSize },
            firstArchiveUncompressedSizes = table.archives.values.take(16).map { it.uncompressedSize },
            firstArchiveFileBytes = firstArchiveFileBytes
        )
    }

    private data class Inspection(
        val source: String,
        val index: Int,
        val rawContainerBytes: Int,
        val decodedPayloadBytes: Int,
        val containerVersion: Int,
        val format: Int,
        val mask: Int,
        val archiveCount: Int,
        val highestEntry: Int,
        val archiveSize: Int,
        val totalCompressedSize: Long,
        val totalUncompressedSize: Long,
        val totalFileBytes: Long,
        val firstArchiveIds: List<Int>,
        val firstArchiveCompressedSizes: List<Int>,
        val firstArchiveUncompressedSizes: List<Int>,
        val firstArchiveFileBytes: List<Int>
    ) {
        fun render(): String = buildString {
            appendLine("source=$source index=$index")
            appendLine("rawContainerBytes=$rawContainerBytes")
            appendLine("decodedPayloadBytes=$decodedPayloadBytes")
            appendLine("containerVersion=$containerVersion")
            appendLine("format=$format")
            appendLine("mask=$mask")
            appendLine("archiveCount=$archiveCount")
            appendLine("highestEntry=$highestEntry")
            appendLine("archiveSize()=$archiveSize")
            appendLine("totalCompressedSize()=$totalCompressedSize")
            appendLine("sum(uncompressedSize)=$totalUncompressedSize")
            appendLine("sum(fileBytes)=$totalFileBytes")
            appendLine("firstArchiveIds=$firstArchiveIds")
            appendLine("firstArchiveCompressedSizes=$firstArchiveCompressedSizes")
            appendLine("firstArchiveUncompressedSizes=$firstArchiveUncompressedSizes")
            appendLine("firstArchiveFileBytes=$firstArchiveFileBytes")
        }
    }
}
