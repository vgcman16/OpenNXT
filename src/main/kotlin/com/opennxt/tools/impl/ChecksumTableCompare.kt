package com.opennxt.tools.impl

import com.google.gson.GsonBuilder
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.config.RsaConfig
import com.opennxt.config.TomlConfig
import com.opennxt.filesystem.ChecksumTable
import com.opennxt.filesystem.Container
import com.opennxt.tools.Tool
import com.opennxt.tools.impl.cachedownloader.Js5ClientPool
import com.opennxt.tools.impl.cachedownloader.Js5Credentials
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.security.MessageDigest
import java.time.Instant
import java.util.concurrent.TimeUnit

class ChecksumTableCompare : Tool(
    "checksum-table-compare",
    "Fetches live 255/255, dumps both sides, and compares the generated JS5 checksum table against Jagex"
) {
    private val outputDir by option(help = "Directory where comparison artifacts should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("checksum-table-compare").toString())
    private val ip by option(help = "Live js5 host").default("content.runescape.com")
    private val port by option(help = "Live js5 port").int().default(43594)
    private val timeoutSeconds by option(help = "Request timeout in seconds").int().default(30)

    override fun runTool() {
        val baseDir = Paths.get(outputDir)
        Files.createDirectories(baseDir)

        val rsaConfig = TomlConfig.load<RsaConfig>(RsaConfig.DEFAULT_PATH, mustExist = true)
        val local = createLocalDump(rsaConfig.js5)
        writeDump(baseDir, "local-js5", local)

        val liveCredentials = Js5Credentials.download()
        val live = fetchLiveDump()
        writeDump(baseDir, "live-js5", live)

        val summary = analyzeComparison(local, live, liveCredentials.version)
        val artifact = buildArtifact(summary, baseDir)
        Files.writeString(baseDir.resolve("compare-report.txt"), renderTextReport(summary))
        Files.writeString(baseDir.resolve("compare-report.md"), renderMarkdownReport(summary))
        Files.writeString(baseDir.resolve("compare-report.json"), gson.toJson(artifact))
        logger.info {
            "Wrote checksum-table comparison artifacts to $baseDir " +
                "(status=${summary.status}, mismatches=${summary.entryMismatchCount})"
        }
    }

    private fun createLocalDump(keyPair: RsaConfig.RsaKeyPair): DumpedChecksumTable {
        val table = ChecksumTable.create(filesystem, false)
        val payload = table.encode(keyPair.modulus, keyPair.exponent)
        val container = Container.wrap(payload)
        val containerBytes = ByteArray(container.remaining())
        container.get(containerBytes)
        return decodeDump("local-js5", containerBytes)
    }

    private fun fetchLiveDump(): DumpedChecksumTable {
        val pool = Js5ClientPool(1, 1, ip, port)
        try {
            pool.openConnections(amount = 1)
            val client = pool.getClient()
            check(client.awaitConnected(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for live JS5 connection to $ip:$port"
            }

            val request = pool.addRequest(true, 255, 255)
                ?: throw IllegalStateException("Failed to enqueue live request for [255,255]")
            check(request.awaitCompletion(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for live checksum table from $ip:$port"
            }

            val buffer = request.buffer ?: throw IllegalStateException("Live checksum table buffer was null")
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            buffer.rewind()
            return decodeDump("live-js5", bytes)
        } finally {
            pool.close()
        }
    }

    private fun decodeDump(label: String, containerBytes: ByteArray): DumpedChecksumTable {
        val payload = Container.decode(ByteBuffer.wrap(containerBytes)).data
        val entryCount = payload.firstOrNull()?.toInt()?.and(0xff)
            ?: throw IllegalStateException("Empty checksum payload for $label")
        val entriesSize = 1 + entryCount * ENTRY_SIZE
        require(payload.size >= entriesSize) {
            "Checksum payload for $label is too short: ${payload.size} < $entriesSize"
        }

        val entriesBytes = payload.copyOfRange(0, entriesSize)
        val signatureBytes = payload.copyOfRange(entriesSize, payload.size)
        val table = ChecksumTable.decode(ByteBuffer.wrap(entriesBytes))
        return DumpedChecksumTable(containerBytes, payload, entriesBytes, signatureBytes, table)
    }

    private fun writeDump(baseDir: Path, prefix: String, dump: DumpedChecksumTable) {
        Files.write(baseDir.resolve("$prefix.container.bin"), dump.containerBytes)
        Files.write(baseDir.resolve("$prefix.payload.bin"), dump.payloadBytes)
        Files.write(baseDir.resolve("$prefix.entries.bin"), dump.entriesBytes)
        Files.write(baseDir.resolve("$prefix.signature.bin"), dump.signatureBytes)
        Files.writeString(baseDir.resolve("$prefix.manifest.txt"), buildManifest(prefix, dump))
    }

    private fun buildManifest(prefix: String, dump: DumpedChecksumTable): String {
        val out = StringBuilder()
        out.appendLine("label=$prefix")
        out.appendLine("entries=${dump.table.entries.size}")
        out.appendLine("nonEmptyEntries=${dump.table.entries.count { it != ChecksumTable.TableEntry.EMPTY }}")
        out.appendLine("containerBytes=${dump.containerBytes.size}")
        out.appendLine("payloadBytes=${dump.payloadBytes.size}")
        out.appendLine("entriesBytes=${dump.entriesBytes.size}")
        out.appendLine("signatureBytes=${dump.signatureBytes.size}")
        out.appendLine("containerSha256=${dump.containerBytes.sha256Hex()}")
        out.appendLine("payloadSha256=${dump.payloadBytes.sha256Hex()}")
        out.appendLine("entriesSha256=${dump.entriesBytes.sha256Hex()}")
        out.appendLine("signatureSha256=${dump.signatureBytes.sha256Hex()}")
        out.appendLine()
        out.appendLine("index crc version files size whirlpool")

        dump.table.entries.forEachIndexed { index, entry ->
            out.appendLine(
                "%03d %s %s %d %d %s".format(
                    index,
                    entry.crc.toUInt().toString(16).padStart(8, '0'),
                    entry.version.toUInt().toString(16).padStart(8, '0'),
                    entry.files,
                    entry.size,
                    entry.whirlpool.toHex()
                )
            )
        }

        return out.toString()
    }

    private fun ByteArray.sha256Hex(): String = MessageDigest.getInstance("SHA-256").digest(this).toHex()

    private fun ByteArray.toHex(): String = joinToString("") { byte ->
        "%02x".format(byte.toInt() and 0xff)
    }

    private data class DumpedChecksumTable(
        val containerBytes: ByteArray,
        val payloadBytes: ByteArray,
        val entriesBytes: ByteArray,
        val signatureBytes: ByteArray,
        val table: ChecksumTable
    )

    data class MismatchRow(
        val index: Int,
        val detail: String
    )

    data class ComparisonSummary(
        val liveVersion: Int,
        val localEntries: Int,
        val liveEntries: Int,
        val entriesBytesMatch: Boolean,
        val signatureBytesMatch: Boolean,
        val containerBytesMatch: Boolean,
        val localEntriesSha256: String,
        val liveEntriesSha256: String,
        val localSignatureSha256: String,
        val liveSignatureSha256: String,
        val entryMismatchCount: Int,
        val mismatchRows: List<MismatchRow>,
        val status: String,
        val severity: String,
        val recommendation: String
    )

    private data class ComparisonArtifact(
        val tool: String,
        val schemaVersion: Int,
        val generatedAt: String,
        val status: String,
        val inputs: Map<String, Any>,
        val summary: ComparisonSummary,
        val artifacts: Map<String, String>
    )

    companion object {
        private const val ENTRY_SIZE = 4 + 4 + 4 + 4 + 64
        private val gson = GsonBuilder().disableHtmlEscaping().setPrettyPrinting().create()

        private fun analyzeComparison(
            local: DumpedChecksumTable,
            live: DumpedChecksumTable,
            liveVersion: Int
        ): ComparisonSummary = analyzeComparison(
            liveVersion = liveVersion,
            localEntries = local.table.entries.size,
            liveEntries = live.table.entries.size,
            entriesBytesMatch = local.entriesBytes.contentEquals(live.entriesBytes),
            signatureBytesMatch = local.signatureBytes.contentEquals(live.signatureBytes),
            containerBytesMatch = local.containerBytes.contentEquals(live.containerBytes),
            localEntriesSha256 = sha256Hex(local.entriesBytes),
            liveEntriesSha256 = sha256Hex(live.entriesBytes),
            localSignatureSha256 = sha256Hex(local.signatureBytes),
            liveSignatureSha256 = sha256Hex(live.signatureBytes),
            mismatches = buildMismatchRows(local, live)
        )

        internal fun analyzeComparison(
            liveVersion: Int,
            localEntries: Int,
            liveEntries: Int,
            entriesBytesMatch: Boolean,
            signatureBytesMatch: Boolean,
            containerBytesMatch: Boolean,
            localEntriesSha256: String,
            liveEntriesSha256: String,
            localSignatureSha256: String,
            liveSignatureSha256: String,
            mismatches: List<MismatchRow>
        ): ComparisonSummary {
            val hasMismatch = mismatches.isNotEmpty() || !entriesBytesMatch || !signatureBytesMatch || !containerBytesMatch
            val severity = when {
                mismatches.size >= 10 || !entriesBytesMatch -> "high"
                hasMismatch -> "medium"
                else -> "none"
            }
            val recommendation = if (!hasMismatch) {
                "Local cache checksum table matches live JS5 for this build."
            } else {
                "Local cache diverges from live JS5. Refresh the cache with `run-tool cache-downloader`, then rerun `run-tool checksum-table-compare`."
            }
            return ComparisonSummary(
                liveVersion = liveVersion,
                localEntries = localEntries,
                liveEntries = liveEntries,
                entriesBytesMatch = entriesBytesMatch,
                signatureBytesMatch = signatureBytesMatch,
                containerBytesMatch = containerBytesMatch,
                localEntriesSha256 = localEntriesSha256,
                liveEntriesSha256 = liveEntriesSha256,
                localSignatureSha256 = localSignatureSha256,
                liveSignatureSha256 = liveSignatureSha256,
                entryMismatchCount = mismatches.size,
                mismatchRows = mismatches,
                status = if (hasMismatch) "partial" else "ok",
                severity = severity,
                recommendation = recommendation
            )
        }

        internal fun renderTextReport(summary: ComparisonSummary): String = buildString {
            appendLine("status=${summary.status}")
            appendLine("severity=${summary.severity}")
            appendLine("liveVersion=${summary.liveVersion}")
            appendLine("localEntries=${summary.localEntries}")
            appendLine("liveEntries=${summary.liveEntries}")
            appendLine("entriesBytesMatch=${summary.entriesBytesMatch}")
            appendLine("signatureBytesMatch=${summary.signatureBytesMatch}")
            appendLine("containerBytesMatch=${summary.containerBytesMatch}")
            appendLine("localEntriesSha256=${summary.localEntriesSha256}")
            appendLine("liveEntriesSha256=${summary.liveEntriesSha256}")
            appendLine("localSignatureSha256=${summary.localSignatureSha256}")
            appendLine("liveSignatureSha256=${summary.liveSignatureSha256}")
            appendLine("entryMismatchCount=${summary.entryMismatchCount}")
            appendLine("recommendation=${summary.recommendation}")
            appendLine()
            if (summary.mismatchRows.isEmpty()) {
                appendLine("All checksum rows match.")
            } else {
                appendLine("First mismatches:")
                summary.mismatchRows.take(25).forEach { appendLine(it.detail) }
            }
        }

        internal fun renderMarkdownReport(summary: ComparisonSummary): String = buildString {
            appendLine("# Checksum Table Compare")
            appendLine()
            appendLine("- Status: `${summary.status}`")
            appendLine("- Severity: `${summary.severity}`")
            appendLine("- Live version: `${summary.liveVersion}`")
            appendLine("- Entry mismatch count: `${summary.entryMismatchCount}`")
            appendLine("- Entries bytes match: `${summary.entriesBytesMatch}`")
            appendLine("- Signature bytes match: `${summary.signatureBytesMatch}`")
            appendLine("- Container bytes match: `${summary.containerBytesMatch}`")
            appendLine("- Recommendation: ${summary.recommendation}")
            appendLine()
            appendLine("## Hashes")
            appendLine()
            appendLine("- Local entries SHA-256: `${summary.localEntriesSha256}`")
            appendLine("- Live entries SHA-256: `${summary.liveEntriesSha256}`")
            appendLine("- Local signature SHA-256: `${summary.localSignatureSha256}`")
            appendLine("- Live signature SHA-256: `${summary.liveSignatureSha256}`")
            appendLine()
            appendLine("## Top Mismatches")
            appendLine()
            if (summary.mismatchRows.isEmpty()) {
                appendLine("- No entry mismatches detected.")
            } else {
                summary.mismatchRows.take(25).forEach { appendLine("- `${it.detail}`") }
            }
        }

        private fun buildArtifact(summary: ComparisonSummary, baseDir: Path): ComparisonArtifact =
            ComparisonArtifact(
                tool = "checksum-table-compare",
                schemaVersion = 1,
                generatedAt = Instant.now().toString(),
                status = summary.status,
                inputs = mapOf(
                    "outputDir" to baseDir.toString()
                ),
                summary = summary,
                artifacts = mapOf(
                    "text" to baseDir.resolve("compare-report.txt").toString(),
                    "markdown" to baseDir.resolve("compare-report.md").toString(),
                    "json" to baseDir.resolve("compare-report.json").toString(),
                    "localManifest" to baseDir.resolve("local-js5.manifest.txt").toString(),
                    "liveManifest" to baseDir.resolve("live-js5.manifest.txt").toString()
                )
            )

        private fun buildMismatchRows(
            local: DumpedChecksumTable,
            live: DumpedChecksumTable
        ): List<MismatchRow> {
            val maxEntries = minOf(local.table.entries.size, live.table.entries.size)
            val mismatches = ArrayList<MismatchRow>()
            for (index in 0 until maxEntries) {
                val localEntry = local.table.entries[index]
                val liveEntry = live.table.entries[index]
                if (localEntry == liveEntry) continue

                val detail = buildString {
                    append("index=$index")
                    if (localEntry.crc != liveEntry.crc) {
                        append(" crc=${localEntry.crc.toUInt().toString(16).padStart(8, '0')}!=${liveEntry.crc.toUInt().toString(16).padStart(8, '0')}")
                    }
                    if (localEntry.version != liveEntry.version) {
                        append(" version=${localEntry.version.toUInt().toString(16).padStart(8, '0')}!=${liveEntry.version.toUInt().toString(16).padStart(8, '0')}")
                    }
                    if (localEntry.files != liveEntry.files) {
                        append(" files=${localEntry.files}!=${liveEntry.files}")
                    }
                    if (localEntry.size != liveEntry.size) {
                        append(" size=${localEntry.size}!=${liveEntry.size}")
                    }
                    if (!localEntry.whirlpool.contentEquals(liveEntry.whirlpool)) {
                        append(" whirlpool=${toHex(localEntry.whirlpool)}!=${toHex(liveEntry.whirlpool)}")
                    }
                }
                mismatches += MismatchRow(index = index, detail = detail)
            }
            return mismatches
        }

        private fun sha256Hex(bytes: ByteArray): String = toHex(MessageDigest.getInstance("SHA-256").digest(bytes))

        private fun toHex(bytes: ByteArray): String = bytes.joinToString("") { byte ->
            "%02x".format(byte.toInt() and 0xff)
        }
    }
}
