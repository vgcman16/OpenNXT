package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.filesystem.Container
import com.opennxt.filesystem.ReferenceTable
import com.opennxt.tools.Tool
import com.opennxt.tools.impl.cachedownloader.Js5ClientPool
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Paths
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

class ArchiveContainerCompare : Tool(
    "archive-container-compare",
    "Compares local cache archive containers against live JS5 for selected indices"
) {
    private val indicesArg by option(help = "Comma-separated index list")
        .default("32,33,34")
    private val outputDir by option(help = "Directory where comparison reports should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("archive-container-compare").toString())
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

        val reports = compare(indices)
        Files.writeString(baseDir.resolve("report.txt"), reports.joinToString("\n\n") { it.render() })
        logger.info { "Wrote archive container comparison report to $baseDir" }
    }

    private fun compare(indices: List<Int>): List<IndexReport> {
        val pool = Js5ClientPool(1, 1, ip, port)
        try {
            pool.openConnections(amount = 1)
            val client = pool.getClient()
            check(client.awaitConnected(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for live JS5 connection"
            }

            return indices.map { index ->
                val table = filesystem.getReferenceTable(index)
                    ?: throw IllegalStateException("Missing local reference table for index $index")
                val archiveReports = table.archives.keys.sorted().map { archive ->
                    compareArchive(pool, index, archive)
                }
                IndexReport(index, archiveReports)
            }
        } finally {
            pool.close()
        }
    }

    private fun compareArchive(pool: Js5ClientPool, index: Int, archive: Int): ArchiveReport {
        val localRawBuffer = filesystem.read(index, archive)
            ?: throw IllegalStateException("Missing local archive [$index,$archive]")
        val localRaw = toByteArray(localRawBuffer)
        val liveRequest = pool.addRequest(true, index, archive)
            ?: throw IllegalStateException("Failed to queue live archive [$index,$archive]")
        check(liveRequest.awaitCompletion(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
            "Timed out waiting for live archive [$index,$archive]"
        }

        val liveBuffer = liveRequest.buffer ?: throw IllegalStateException("Null live buffer for [$index,$archive]")
        val liveRaw = toByteArray(liveBuffer)

        val localContainer = Container.decode(ByteBuffer.wrap(localRaw))
        val liveContainer = Container.decode(ByteBuffer.wrap(liveRaw))
        val firstMismatch = firstMismatch(localRaw, liveRaw)

        return ArchiveReport(
            archive = archive,
            rawMatch = localRaw.contentEquals(liveRaw),
            decodedMatch = localContainer.data.contentEquals(liveContainer.data),
            localRawBytes = localRaw.size,
            liveRawBytes = liveRaw.size,
            localCompression = localContainer.compression.name,
            liveCompression = liveContainer.compression.name,
            localVersion = localContainer.version,
            liveVersion = liveContainer.version,
            localPayloadBytes = localContainer.data.size,
            livePayloadBytes = liveContainer.data.size,
            localRawSha256 = sha256(localRaw),
            liveRawSha256 = sha256(liveRaw),
            localPayloadSha256 = sha256(localContainer.data),
            livePayloadSha256 = sha256(liveContainer.data),
            firstMismatch = firstMismatch
        )
    }

    private fun toByteArray(buffer: ByteBuffer): ByteArray {
        val copy = buffer.duplicate()
        val bytes = ByteArray(copy.remaining())
        copy.get(bytes)
        return bytes
    }

    private fun firstMismatch(left: ByteArray, right: ByteArray): String {
        val minSize = minOf(left.size, right.size)
        for (i in 0 until minSize) {
            if (left[i] != right[i]) {
                return "offset=$i local=${left[i].toInt() and 0xff} live=${right[i].toInt() and 0xff}"
            }
        }
        return if (left.size == right.size) "none" else "offset=$minSize local=${left.getOrNull(minSize)?.toInt()?.and(0xff) ?: "eof"} live=${right.getOrNull(minSize)?.toInt()?.and(0xff) ?: "eof"}"
    }

    private fun sha256(bytes: ByteArray): String {
        return MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private data class IndexReport(
        val index: Int,
        val archives: List<ArchiveReport>
    ) {
        fun render(): String = buildString {
            appendLine("index=$index")
            appendLine("archiveCount=${archives.size}")
            appendLine("rawMismatchCount=${archives.count { !it.rawMatch }}")
            appendLine("decodedMismatchCount=${archives.count { !it.decodedMatch }}")
            archives.forEach {
                appendLine()
                appendLine(it.render())
            }
        }
    }

    private data class ArchiveReport(
        val archive: Int,
        val rawMatch: Boolean,
        val decodedMatch: Boolean,
        val localRawBytes: Int,
        val liveRawBytes: Int,
        val localCompression: String,
        val liveCompression: String,
        val localVersion: Int,
        val liveVersion: Int,
        val localPayloadBytes: Int,
        val livePayloadBytes: Int,
        val localRawSha256: String,
        val liveRawSha256: String,
        val localPayloadSha256: String,
        val livePayloadSha256: String,
        val firstMismatch: String
    ) {
        fun render(): String = buildString {
            appendLine("archive=$archive")
            appendLine("rawMatch=$rawMatch decodedMatch=$decodedMatch")
            appendLine("localRawBytes=$localRawBytes liveRawBytes=$liveRawBytes")
            appendLine("localCompression=$localCompression liveCompression=$liveCompression")
            appendLine("localVersion=$localVersion liveVersion=$liveVersion")
            appendLine("localPayloadBytes=$localPayloadBytes livePayloadBytes=$livePayloadBytes")
            appendLine("firstMismatch=$firstMismatch")
            appendLine("localRawSha256=$localRawSha256")
            appendLine("liveRawSha256=$liveRawSha256")
            appendLine("localPayloadSha256=$localPayloadSha256")
            appendLine("livePayloadSha256=$livePayloadSha256")
        }
    }
}
