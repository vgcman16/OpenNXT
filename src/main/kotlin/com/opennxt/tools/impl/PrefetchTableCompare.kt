package com.opennxt.tools.impl

import com.google.gson.GsonBuilder
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.filesystem.prefetches.PrefetchTable
import com.opennxt.tools.Tool
import com.opennxt.tools.impl.cachedownloader.Js5ClientPool
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.time.Instant
import java.util.concurrent.TimeUnit

class PrefetchTableCompare : Tool(
    "prefetch-table-compare",
    "Fetches the live JS5 prefetch table and compares it with the locally generated table"
) {
    private val outputDir by option(help = "Directory where comparison artifacts should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("prefetch-table-compare").toString())
    private val ip by option(help = "JS5 host").default("content.runescape.com")
    private val port by option(help = "JS5 port").int().default(43594)
    private val build by option(help = "Build number used to choose the local prefetch spec").int().default(946)
    private val timeoutSeconds by option(help = "Request timeout in seconds").int().default(30)

    override fun runTool() {
        val baseDir = Paths.get(outputDir)
        Files.createDirectories(baseDir)

        val local = PrefetchTable.of(filesystem, build).entries
        val remote = fetchRemotePrefetches()
        val summary = analyzeComparison(local, remote)

        Files.writeString(baseDir.resolve("local-prefetches.txt"), renderPrefetches("local", local))
        Files.writeString(baseDir.resolve("remote-prefetches.txt"), renderPrefetches("remote", remote))
        Files.writeString(baseDir.resolve("compare-report.txt"), renderTextReport(summary))
        Files.writeString(baseDir.resolve("compare-report.md"), renderMarkdownReport(summary))
        Files.writeString(baseDir.resolve("compare-report.json"), gson.toJson(buildArtifact(summary, baseDir, build)))

        logger.info {
            "Wrote prefetch-table comparison artifacts to $baseDir " +
                "(status=${summary.status}, state=${summary.comparisonState})"
        }
    }

    private fun fetchRemotePrefetches(): IntArray {
        val pool = Js5ClientPool(1, 1, ip, port, bootstrapLoggedIn = true)
        try {
            pool.openConnections(amount = 1)
            val client = pool.getClient()
            check(client.awaitConnected(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for JS5 connection to $ip:$port"
            }
            if (!client.awaitPrefetches(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                logger.info { "No JS5 prefetch table received from $ip:$port within $timeoutSeconds seconds" }
                return IntArray(0)
            }
            return client.prefetches?.copyOf()
                ?: throw IllegalStateException("Client connected to $ip:$port without recording a prefetch table")
        } finally {
            pool.close()
        }
    }

    private fun renderPrefetches(label: String, entries: IntArray): String = buildString {
        appendLine("label=$label")
        appendLine("count=${entries.size}")
        appendLine()
        appendLine("slot value")
        entries.forEachIndexed { index, value ->
            appendLine("%02d %d".format(index, value))
        }
    }

    data class ComparisonSummary(
        val localCount: Int,
        val remoteCount: Int,
        val mismatchCount: Int,
        val countMismatch: Boolean,
        val comparisonState: String,
        val status: String,
        val mismatches: List<String>,
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
        private val gson = GsonBuilder().disableHtmlEscaping().setPrettyPrinting().create()

        internal fun analyzeComparison(local: IntArray, remote: IntArray): ComparisonSummary {
            val mismatches = mutableListOf<String>()
            val maxEntries = minOf(local.size, remote.size)
            for (index in 0 until maxEntries) {
                if (local[index] != remote[index]) {
                    mismatches += "slot=$index local=${local[index]} remote=${remote[index]}"
                }
            }
            val countMismatch = local.size != remote.size
            val comparisonState = when {
                remote.isEmpty() -> "inconclusive-no-remote-table"
                countMismatch || mismatches.isNotEmpty() -> "mismatch"
                else -> "match"
            }
            val status = when (comparisonState) {
                "match" -> "ok"
                else -> "partial"
            }
            val recommendation = when (comparisonState) {
                "match" -> "Local prefetch table matches the live JS5 response."
                "inconclusive-no-remote-table" ->
                    "Live JS5 did not provide a prefetch table. Treat this result as advisory-only and verify with wire captures if prefetch behavior matters."
                else ->
                    "Local prefetch table differs from live JS5. Refresh the cache and verify whether the client still receives or expects these prefetch entries."
            }
            return ComparisonSummary(
                localCount = local.size,
                remoteCount = remote.size,
                mismatchCount = mismatches.size,
                countMismatch = countMismatch,
                comparisonState = comparisonState,
                status = status,
                mismatches = mismatches,
                recommendation = recommendation
            )
        }

        internal fun renderTextReport(summary: ComparisonSummary): String = buildString {
            appendLine("status=${summary.status}")
            appendLine("comparisonState=${summary.comparisonState}")
            appendLine("localCount=${summary.localCount}")
            appendLine("remoteCount=${summary.remoteCount}")
            appendLine("mismatchCount=${summary.mismatchCount}")
            appendLine("countMismatch=${summary.countMismatch}")
            appendLine("recommendation=${summary.recommendation}")
            if (summary.mismatches.isEmpty()) {
                appendLine(
                    when (summary.comparisonState) {
                        "match" -> "All prefetch entries match."
                        "inconclusive-no-remote-table" -> "Remote JS5 did not provide a prefetch table; comparison is inconclusive."
                        else -> "No slot mismatches recorded."
                    }
                )
            } else {
                appendLine("First mismatches:")
                summary.mismatches.take(31).forEach(::appendLine)
            }
        }

        internal fun renderMarkdownReport(summary: ComparisonSummary): String = buildString {
            appendLine("# Prefetch Table Compare")
            appendLine()
            appendLine("- Status: `${summary.status}`")
            appendLine("- Comparison state: `${summary.comparisonState}`")
            appendLine("- Local count: `${summary.localCount}`")
            appendLine("- Remote count: `${summary.remoteCount}`")
            appendLine("- Mismatch count: `${summary.mismatchCount}`")
            appendLine("- Count mismatch: `${summary.countMismatch}`")
            appendLine("- Recommendation: ${summary.recommendation}")
            appendLine()
            appendLine("## Top Mismatches")
            appendLine()
            if (summary.mismatches.isEmpty()) {
                appendLine(
                    when (summary.comparisonState) {
                        "match" -> "- No mismatches detected."
                        "inconclusive-no-remote-table" -> "- Remote JS5 did not provide a prefetch table."
                        else -> "- No slot mismatches recorded."
                    }
                )
            } else {
                summary.mismatches.take(31).forEach { appendLine("- `${it}`") }
            }
        }

        private fun buildArtifact(summary: ComparisonSummary, baseDir: Path, build: Int): ComparisonArtifact =
            ComparisonArtifact(
                tool = "prefetch-table-compare",
                schemaVersion = 1,
                generatedAt = Instant.now().toString(),
                status = summary.status,
                inputs = mapOf(
                    "outputDir" to baseDir.toString(),
                    "build" to build
                ),
                summary = summary,
                artifacts = mapOf(
                    "text" to baseDir.resolve("compare-report.txt").toString(),
                    "markdown" to baseDir.resolve("compare-report.md").toString(),
                    "json" to baseDir.resolve("compare-report.json").toString(),
                    "localPrefetches" to baseDir.resolve("local-prefetches.txt").toString(),
                    "remotePrefetches" to baseDir.resolve("remote-prefetches.txt").toString()
                )
            )
    }

    private fun buildComparisonReport(local: IntArray, remote: IntArray): String = buildString {
        val summary = analyzeComparison(local, remote)
        append(renderTextReport(summary))
    }
}
