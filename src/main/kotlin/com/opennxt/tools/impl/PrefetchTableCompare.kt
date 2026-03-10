package com.opennxt.tools.impl

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
import java.util.concurrent.TimeUnit

class PrefetchTableCompare : Tool(
    "prefetch-table-compare",
    "Fetches the live JS5 prefetch table and compares it with the locally generated table"
) {
    private val outputDir by option(help = "Directory where comparison artifacts should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("prefetch-table-compare").toString())
    private val ip by option(help = "JS5 host").default("content.runescape.com")
    private val port by option(help = "JS5 port").int().default(43594)
    private val timeoutSeconds by option(help = "Request timeout in seconds").int().default(30)

    override fun runTool() {
        val baseDir = Paths.get(outputDir)
        Files.createDirectories(baseDir)

        val local = PrefetchTable.of(filesystem).entries
        val remote = fetchRemotePrefetches()

        Files.writeString(baseDir.resolve("local-prefetches.txt"), renderPrefetches("local", local))
        Files.writeString(baseDir.resolve("remote-prefetches.txt"), renderPrefetches("remote", remote))
        Files.writeString(baseDir.resolve("compare-report.txt"), buildComparisonReport(local, remote))

        logger.info { "Wrote prefetch-table comparison artifacts to $baseDir" }
    }

    private fun fetchRemotePrefetches(): IntArray {
        val pool = Js5ClientPool(1, 1, ip, port)
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

    private fun buildComparisonReport(local: IntArray, remote: IntArray): String = buildString {
        appendLine("localCount=${local.size}")
        appendLine("remoteCount=${remote.size}")

        val mismatches = mutableListOf<String>()
        val maxEntries = minOf(local.size, remote.size)
        for (index in 0 until maxEntries) {
            if (local[index] != remote[index]) {
                mismatches += "slot=$index local=${local[index]} remote=${remote[index]}"
            }
        }

        appendLine("mismatchCount=${mismatches.size}")
        if (local.size != remote.size) {
            appendLine("countMismatch=true")
        }
        if (mismatches.isEmpty()) {
            appendLine("All prefetch entries match.")
        } else {
            appendLine("First mismatches:")
            mismatches.take(31).forEach(::appendLine)
        }
    }
}
