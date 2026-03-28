package com.opennxt.tools.impl

import com.google.gson.GsonBuilder
import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.tools.Tool
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.IOException
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.time.Duration
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

class Js5ProxyRecorder : Tool(
    "js5-proxy-recorder",
    "Proxies a local JS5 port to live Jagex and records the client's request sequence"
) {
    private val bindHost by option(help = "Local host to bind to").default("127.0.0.1")
    private val bindPort by option(help = "Local port to bind to").int().default(43595)
    private val remoteHost by option(help = "Remote JS5 host").default("content.runescape.com")
    private val remotePort by option(help = "Remote JS5 port").int().default(43594)
    private val maxSessions by option(help = "Maximum number of client sessions to record").int().default(6)
    private val idleTimeoutSeconds by option(help = "Stop after this many idle seconds without a new client").int().default(20)
    private val sessionIdleTimeoutSeconds by option(help = "Close a proxied session after this many idle seconds").int().default(10)
    private val socketTimeoutMillis by option(help = "Socket read timeout in milliseconds").int().default(1000)
    private val outputDir by option(help = "Directory where request traces should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("js5-proxy-recorder").toString())

    override fun runTool() {
        val outputPath = Paths.get(outputDir)
        Files.createDirectories(outputPath)

        val sessionRecords = mutableListOf<Map<String, Any?>>()
        val summaryLines = mutableListOf<String>()
        val timestamp = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneOffset.UTC).format(Instant.now())
        val summaryLogPath = outputPath.resolve("summary-$timestamp.log")
        val summaryJsonPath = outputPath.resolve("summary-$timestamp.json")
        val summaryMarkdownPath = outputPath.resolve("summary-$timestamp.md")

        logger.info { "Binding JS5 proxy on $bindHost:$bindPort -> $remoteHost:$remotePort" }

        ServerSocket(bindPort, 50).use { server ->
            server.reuseAddress = true
            server.soTimeout = 1000

            var sessionCount = 0
            var lastAccept = System.nanoTime()

            while (sessionCount < maxSessions) {
                val idleElapsed = Duration.ofNanos(System.nanoTime() - lastAccept)
                if (idleElapsed.seconds >= idleTimeoutSeconds && sessionCount > 0) {
                    logger.info { "Stopping proxy after ${idleElapsed.seconds}s of idle time" }
                    break
                }

                val client = try {
                    server.accept()
                } catch (_: SocketTimeoutException) {
                    continue
                }

                lastAccept = System.nanoTime()
                sessionCount += 1

                val baseName = "session-${sessionCount.toString().padStart(2, '0')}-$timestamp"
                val result = handleSession(sessionCount, client)
                val sessionLogPath = outputPath.resolve("$baseName.log")
                val sessionJsonlPath = outputPath.resolve("$baseName.jsonl")
                Files.write(sessionLogPath, result.lines)
                Files.write(sessionJsonlPath, result.jsonLines)
                summaryLines += result.lines
                summaryLines += ""
                sessionRecords += buildSessionRecord(result, sessionLogPath, sessionJsonlPath)
            }
        }

        Files.write(summaryLogPath, summaryLines)
        val artifact = buildSummaryArtifact(
            timestamp = timestamp,
            outputPath = outputPath,
            summaryLogPath = summaryLogPath,
            summaryJsonPath = summaryJsonPath,
            summaryMarkdownPath = summaryMarkdownPath,
            sessions = sessionRecords
        )
        Files.writeString(summaryJsonPath, gson.toJson(artifact))
        Files.writeString(summaryMarkdownPath, renderSummaryMarkdown(artifact))
        logger.info { "Wrote JS5 proxy traces to $outputPath" }
    }

    private fun handleSession(sessionId: Int, client: Socket): Js5SessionResult {
        val started = Instant.now()
        val capture = Js5SessionCapture(sessionId, started)
        val clientParser = Js5ClientStreamParser(sessionId, capture)
        val remoteParser = Js5RemoteStreamParser(sessionId, capture)
        val lastActivity = AtomicLong(System.nanoTime())
        var idleTimeoutTriggered = false

        client.soTimeout = socketTimeoutMillis
        client.tcpNoDelay = true

        capture.addLine("session#$sessionId start=$started")
        capture.addLine("session#$sessionId client=${client.remoteSocketAddress}")

        Socket().use { remote ->
            remote.soTimeout = socketTimeoutMillis
            remote.tcpNoDelay = true
            remote.connect(java.net.InetSocketAddress(remoteHost, remotePort), socketTimeoutMillis)
            capture.addLine("session#$sessionId remote=$remoteHost:$remotePort")

            val done = CountDownLatch(2)
            val clientToRemote = Thread {
                try {
                    pump(
                        source = client,
                        destination = remote,
                        lastActivity = lastActivity,
                        inspect = { bytes, length, timestamp -> clientParser.feed(bytes, length, timestamp) }
                    )
                } finally {
                    done.countDown()
                }
            }
            val remoteToClient = Thread {
                try {
                    pump(
                        source = remote,
                        destination = client,
                        lastActivity = lastActivity,
                        inspect = { bytes, length, timestamp -> remoteParser.feed(bytes, length, timestamp) }
                    )
                } finally {
                    done.countDown()
                }
            }

            clientToRemote.name = "js5-proxy-client-$sessionId"
            remoteToClient.name = "js5-proxy-remote-$sessionId"
            clientToRemote.start()
            remoteToClient.start()

            while (!done.await(1, TimeUnit.SECONDS)) {
                val idle = Duration.ofNanos(System.nanoTime() - lastActivity.get()).seconds
                if (idle >= sessionIdleTimeoutSeconds) {
                    idleTimeoutTriggered = true
                    capture.addLine("session#$sessionId idle-timeout=${idle}s")
                    break
                }
            }

            closeQuietly(client)
            closeQuietly(remote)
            clientToRemote.join(2000)
            remoteToClient.join(2000)
        }

        val ended = Instant.now()
        remoteParser.finish(ended)
        capture.addLine("session#$sessionId end=$ended")
        return capture.finish(ended, idleTimeoutTriggered)
    }

    private fun pump(
        source: Socket,
        destination: Socket,
        lastActivity: AtomicLong,
        inspect: ((ByteArray, Int, Instant) -> Unit)? = null
    ) {
        val input = BufferedInputStream(source.getInputStream())
        val output = BufferedOutputStream(destination.getOutputStream())
        val buffer = ByteArray(8192)

        while (!source.isClosed && !destination.isClosed) {
            val read = try {
                input.read(buffer)
            } catch (_: SocketTimeoutException) {
                continue
            } catch (_: IOException) {
                break
            }

            if (read < 0) {
                break
            }

            val timestamp = Instant.now()
            lastActivity.set(System.nanoTime())
            inspect?.invoke(buffer, read, timestamp)
            output.write(buffer, 0, read)
            output.flush()
        }
    }

    private fun closeQuietly(socket: Socket) {
        try {
            socket.close()
        } catch (_: IOException) {
        }
    }

    private fun buildSessionRecord(result: Js5SessionResult, sessionLogPath: Path, sessionJsonlPath: Path): Map<String, Any?> {
        val summary = result.summary
        return linkedMapOf<String, Any?>(
            "sessionId" to summary.sessionId,
            "status" to summary.status,
            "startTimestamp" to summary.startTimestamp,
            "endTimestamp" to summary.endTimestamp,
            "durationSeconds" to summary.durationSeconds,
            "requestCount" to summary.requestCount,
            "masterReferenceRequests" to summary.masterReferenceRequests,
            "referenceTableRequests" to summary.referenceTableRequests,
            "archiveRequests" to summary.archiveRequests,
            "responseHeaderCount" to summary.responseHeaderCount,
            "responseBytes" to summary.responseBytes,
            "firstRequestAtMillis" to summary.firstRequestAtMillis,
            "firstArchiveRequestAtMillis" to summary.firstArchiveRequestAtMillis,
            "firstResponseHeaderAtMillis" to summary.firstResponseHeaderAtMillis,
            "firstArchiveResponseAtMillis" to summary.firstArchiveResponseAtMillis,
            "idleTimeoutTriggered" to summary.idleTimeoutTriggered,
            "sessionLog" to sessionLogPath.toString(),
            "sessionJsonl" to sessionJsonlPath.toString()
        )
    }

    private fun buildSummaryArtifact(
        timestamp: String,
        outputPath: Path,
        summaryLogPath: Path,
        summaryJsonPath: Path,
        summaryMarkdownPath: Path,
        sessions: List<Map<String, Any?>>
    ): Map<String, Any?> {
        val partialSessions = sessions.count { it["status"] == "partial" }
        val requestCount = sessions.sumOf { (it["requestCount"] as? Number)?.toInt() ?: 0 }
        val referenceTableRequests = sessions.sumOf { (it["referenceTableRequests"] as? Number)?.toInt() ?: 0 }
        val archiveRequests = sessions.sumOf { (it["archiveRequests"] as? Number)?.toInt() ?: 0 }
        val responseHeaderCount = sessions.sumOf { (it["responseHeaderCount"] as? Number)?.toInt() ?: 0 }
        val responseBytes = sessions.sumOf { (it["responseBytes"] as? Number)?.toLong() ?: 0L }
        val status = if (sessions.isNotEmpty() && partialSessions == 0) "ok" else "partial"
        return linkedMapOf(
            "tool" to "js5-proxy-recorder",
            "schemaVersion" to 1,
            "generatedAt" to Instant.now().toString(),
            "status" to status,
            "inputs" to linkedMapOf(
                "bindHost" to bindHost,
                "bindPort" to bindPort,
                "remoteHost" to remoteHost,
                "remotePort" to remotePort,
                "maxSessions" to maxSessions,
                "idleTimeoutSeconds" to idleTimeoutSeconds,
                "sessionIdleTimeoutSeconds" to sessionIdleTimeoutSeconds,
                "socketTimeoutMillis" to socketTimeoutMillis,
                "outputDir" to outputPath.toString(),
                "runTimestamp" to timestamp
            ),
            "summary" to linkedMapOf(
                "sessionCount" to sessions.size,
                "partialSessionCount" to partialSessions,
                "requestCount" to requestCount,
                "referenceTableRequests" to referenceTableRequests,
                "archiveRequests" to archiveRequests,
                "responseHeaderCount" to responseHeaderCount,
                "responseBytes" to responseBytes
            ),
            "sessions" to sessions,
            "artifacts" to linkedMapOf(
                "summaryLog" to summaryLogPath.toString(),
                "summaryJson" to summaryJsonPath.toString(),
                "summaryMarkdown" to summaryMarkdownPath.toString()
            )
        )
    }

    private fun renderSummaryMarkdown(artifact: Map<String, Any?>): String {
        val summary = artifact["summary"] as Map<*, *>
        val sessions = artifact["sessions"] as List<Map<String, Any?>>
        return buildString {
            appendLine("# JS5 Proxy Recorder")
            appendLine()
            appendLine("- Status: `${artifact["status"]}`")
            appendLine("- Sessions: `${summary["sessionCount"]}`")
            appendLine("- Requests: `${summary["requestCount"]}`")
            appendLine("- Archive requests: `${summary["archiveRequests"]}`")
            appendLine("- Response headers: `${summary["responseHeaderCount"]}`")
            appendLine("- Response bytes: `${summary["responseBytes"]}`")
            appendLine()
            appendLine("## Sessions")
            appendLine()
            if (sessions.isEmpty()) {
                appendLine("- No client sessions were recorded.")
            } else {
                for (session in sessions) {
                    appendLine(
                        "- `session#${session["sessionId"]}` status=`${session["status"]}` " +
                            "requests=`${session["requestCount"]}` archiveRequests=`${session["archiveRequests"]}` " +
                            "responseHeaders=`${session["responseHeaderCount"]}` idleTimeout=`${session["idleTimeoutTriggered"]}`"
                    )
                }
            }
        }
    }

    companion object {
        private val gson = GsonBuilder().disableHtmlEscaping().setPrettyPrinting().create()
    }
}
