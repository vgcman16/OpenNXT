package com.opennxt.net

import com.fasterxml.jackson.databind.JsonNode
import com.fasterxml.jackson.databind.ObjectMapper
import com.opennxt.Constants
import mu.KotlinLogging
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.StandardOpenOption
import java.time.Duration
import java.time.Instant
import kotlin.io.path.createDirectories

object PreLoginForensics {
    private val logger = KotlinLogging.logger { }
    private val objectMapper = ObjectMapper()
    private const val TRANSPORT_WINDOW_SECONDS = 10L
    private const val REPORT_TIMESTAMP_TRUST_WINDOW_MILLIS = 5_000L
    private val writeLock = Any()

    @Volatile
    internal var debugDirectoryOverride: Path? = null

    @Volatile
    internal var latestLiveHookPathOverride: Path? = null

    @Volatile
    internal var transportEventsPathOverride: Path? = null

    private fun debugDirectory(): Path =
        debugDirectoryOverride
            ?: Constants.DATA_PATH.resolve("debug")
                .toAbsolutePath()
                .normalize()

    private fun latestHookPaths(): List<Path> {
        latestLiveHookPathOverride?.let { return listOf(it.toAbsolutePath().normalize()) }

        val hookDirectory =
            debugDirectory()
                .resolve("direct-rs2client-patch")
                .toAbsolutePath()
                .normalize()
        return listOf(
            hookDirectory.resolve("latest-live-hook.jsonl"),
            hookDirectory.resolve("latest-client-only-hook.jsonl"),
        ).filter(Files::exists)
    }

    private fun transportEventsPath(): Path =
        transportEventsPathOverride
            ?: debugDirectory()
                .resolve("prelogin-transport-events.jsonl")
                .toAbsolutePath()
                .normalize()

    internal fun recordTransportEvent(
        localPort: Int,
        remoteAddress: String,
        event: String,
        details: Map<String, Any?> = emptyMap(),
        now: Instant = Instant.now(),
    ) {
        try {
            val payload = linkedMapOf<String, Any?>(
                "timestamp" to now.toString(),
                "localPort" to localPort,
                "remoteAddress" to remoteAddress,
                "event" to event,
            )
            payload.putAll(details.filterValues { it != null })

            val path = transportEventsPath()
            synchronized(writeLock) {
                path.parent?.createDirectories()
                Files.writeString(
                    path,
                    objectMapper.writeValueAsString(payload) + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND,
                )
            }
        } catch (error: Exception) {
            logger.warn(error) { "Failed to append pre-login transport event" }
        }
    }

    internal fun writeCorrelationSummary(
        outputPath: Path,
        reportInstant: Instant?,
        remoteAddress: String,
        requestTarget: String?,
        now: Instant = Instant.now(),
    ) {
        try {
            outputPath.parent?.createDirectories()
            val referenceInstant = chooseReferenceInstant(reportInstant, now)
            val hookFault = findNearestHookFault(referenceInstant)
            val transportEvents = findNearbyTransportEvents(referenceInstant)

            val lines = buildList {
                add("remote=$remoteAddress")
                add("requestTarget=${requestTarget ?: "<unknown>"}")
                add("analysisTimestamp=$now")
                add("clientReportedTimestamp=${reportInstant ?: "<none>"}")
                add("referenceTimestamp=$referenceInstant")
                if (hookFault == null) {
                    add("hookFaultMatched=false")
                } else {
                    add("hookFaultMatched=true")
                    add("hookFaultSource=${hookFault.source}")
                    add("hookFaultTimestamp=${hookFault.timestamp}")
                    add("hookFaultDeltaMs=${hookFault.deltaMillis}")
                    add("hookFaultExceptionType=${hookFault.exceptionType ?: "<unknown>"}")
                    add("hookFaultAddress=${hookFault.address ?: "<unknown>"}")
                }
                add("nearby43596EventCount=${transportEvents.size}")
                transportEvents.forEachIndexed { index, event ->
                    add(
                        "nearby43596Event[$index]=" +
                            "timestamp=${event.timestamp}," +
                            "deltaMs=${event.deltaMillis}," +
                            "event=${event.event}," +
                            "remote=${event.remoteAddress}," +
                            "previewHex=${event.previewHex ?: "<none>"}," +
                            "handshakeType=${event.handshakeType ?: "<none>"}"
                    )
                }
            }

            Files.writeString(
                outputPath,
                lines.joinToString(System.lineSeparator(), postfix = System.lineSeparator()),
                StandardCharsets.UTF_8,
            )
        } catch (error: Exception) {
            logger.warn(error) { "Failed to write pre-login correlation summary to $outputPath" }
        }
    }

    private fun chooseReferenceInstant(reportInstant: Instant?, now: Instant): Instant {
        if (reportInstant == null) {
            return now
        }
        val reportDeltaMillis = kotlin.math.abs(Duration.between(reportInstant, now).toMillis())
        return if (reportDeltaMillis <= REPORT_TIMESTAMP_TRUST_WINDOW_MILLIS) {
            now
        } else {
            reportInstant
        }
    }

    private data class HookFault(
        val timestamp: Instant,
        val deltaMillis: Long,
        val exceptionType: String?,
        val address: String?,
        val source: String,
    )

    private data class TransportEventSummary(
        val timestamp: Instant,
        val deltaMillis: Long,
        val remoteAddress: String?,
        val event: String?,
        val previewHex: String?,
        val handshakeType: String?,
    )

    private fun findNearestHookFault(referenceInstant: Instant): HookFault? {
        val paths = latestHookPaths()
        if (paths.isEmpty()) {
            return null
        }

        var bestMatch: HookFault? = null
        for (path in paths) {
            Files.lines(path, StandardCharsets.UTF_8).use { lines ->
                val iterator = lines.iterator()
                while (iterator.hasNext()) {
                    val line = iterator.next()
                    if (line.isBlank()) {
                        continue
                    }
                    val node = runCatching { objectMapper.readTree(line) }.getOrNull() ?: continue
                    val timestampValue = node.path("timestamp").asDouble(Double.NaN)
                    if (!timestampValue.isFinite()) {
                        continue
                    }
                    val timestamp = Instant.ofEpochMilli((timestampValue * 1000.0).toLong())
                    val isFault = node.path("action").asText() == "fault" || node.path("category").asText() == "client.exception"
                    if (!isFault) {
                        continue
                    }
                    val deltaMillis = kotlin.math.abs(Duration.between(referenceInstant, timestamp).toMillis())
                    val candidate = HookFault(
                        timestamp = timestamp,
                        deltaMillis = deltaMillis,
                        exceptionType = node.path("exceptionType").asText(null),
                        address = node.path("address").asText(null),
                        source = path.fileName.toString(),
                    )
                    if (bestMatch == null || candidate.deltaMillis < bestMatch.deltaMillis) {
                        bestMatch = candidate
                    }
                }
            }
        }
        return bestMatch
    }

    private fun findNearbyTransportEvents(referenceInstant: Instant): List<TransportEventSummary> {
        val path = transportEventsPath()
        if (!Files.exists(path)) {
            return emptyList()
        }

        val transportWindow = Duration.ofSeconds(TRANSPORT_WINDOW_SECONDS).toMillis()
        val matches = mutableListOf<TransportEventSummary>()
        Files.lines(path, StandardCharsets.UTF_8).use { lines ->
            val iterator = lines.iterator()
            while (iterator.hasNext()) {
                val line = iterator.next()
                if (line.isBlank()) {
                    continue
                }
                val node = runCatching { objectMapper.readTree(line) }.getOrNull() ?: continue
                val localPort = node.path("localPort").asInt(-1)
                if (localPort != 43596) {
                    continue
                }
                val timestamp = parseInstant(node.path("timestamp")) ?: continue
                val deltaMillis = kotlin.math.abs(Duration.between(referenceInstant, timestamp).toMillis())
                if (deltaMillis > transportWindow) {
                    continue
                }
                matches += TransportEventSummary(
                    timestamp = timestamp,
                    deltaMillis = deltaMillis,
                    remoteAddress = node.path("remoteAddress").asText(null),
                    event = node.path("event").asText(null),
                    previewHex = node.path("previewHex").asText(null),
                    handshakeType = node.path("handshakeType").asText(null),
                )
            }
        }
        return matches.sortedBy { it.deltaMillis }
    }

    private fun parseInstant(node: JsonNode): Instant? {
        val text = node.asText(null) ?: return null
        return runCatching { Instant.parse(text) }.getOrNull()
    }
}
