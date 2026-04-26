package com.opennxt.tools.impl

import java.time.Duration
import java.time.Instant

data class Js5SessionSummary(
    val sessionId: Int,
    val status: String,
    val startTimestamp: String,
    val endTimestamp: String,
    val durationSeconds: Long,
    val requestCount: Int,
    val masterReferenceRequests: Int,
    val referenceTableRequests: Int,
    val archiveRequests: Int,
    val responseHeaderCount: Int,
    val responseBytes: Long,
    val firstRequestAtMillis: Long?,
    val firstArchiveRequestAtMillis: Long?,
    val firstResponseHeaderAtMillis: Long?,
    val firstArchiveResponseAtMillis: Long?,
    val idleTimeoutTriggered: Boolean
)

data class Js5SessionResult(
    val lines: List<String>,
    val jsonLines: List<String>,
    val summary: Js5SessionSummary
)

class Js5SessionCapture(
    private val sessionId: Int,
    private val started: Instant
) {
    private val lines = mutableListOf<String>()
    private val jsonLines = mutableListOf<String>()

    private var requestCount = 0
    private var masterReferenceRequests = 0
    private var referenceTableRequests = 0
    private var archiveRequests = 0
    private var responseHeaderCount = 0
    private var responseBytes = 0L

    private var firstRequestAtMillis: Long? = null
    private var firstArchiveRequestAtMillis: Long? = null
    private var firstResponseHeaderAtMillis: Long? = null
    private var firstArchiveResponseAtMillis: Long? = null

    fun addLine(line: String) {
        lines += line
    }

    fun recordClientChunk(bytes: ByteArray, timestamp: Instant) {
        val at = millisSinceStart(timestamp)
        if (firstRequestAtMillis == null) {
            firstRequestAtMillis = at
        }
        requestCount++
        classifyClientChunk(bytes, at)
        val hex = headHex(bytes)
        lines += "session#$sessionId client t=${at}ms bytes=${bytes.size} hex=$hex"
        jsonLines += """{"sessionId":$sessionId,"direction":"client","atMillis":$at,"bytes":${bytes.size},"headHex":"$hex"}"""
    }

    fun recordRemoteChunk(bytes: ByteArray, timestamp: Instant) {
        val at = millisSinceStart(timestamp)
        responseBytes += bytes.size.toLong()
        responseHeaderCount++
        if (firstResponseHeaderAtMillis == null) {
            firstResponseHeaderAtMillis = at
        }
        if (firstArchiveResponseAtMillis == null && bytes.isNotEmpty()) {
            firstArchiveResponseAtMillis = at
        }
        val hex = headHex(bytes)
        lines += "session#$sessionId remote t=${at}ms bytes=${bytes.size} hex=$hex"
        jsonLines += """{"sessionId":$sessionId,"direction":"remote","atMillis":$at,"bytes":${bytes.size},"headHex":"$hex"}"""
    }

    fun finish(ended: Instant, idleTimeoutTriggered: Boolean): Js5SessionResult {
        val summary = Js5SessionSummary(
            sessionId = sessionId,
            status = if (idleTimeoutTriggered) "partial" else "ok",
            startTimestamp = started.toString(),
            endTimestamp = ended.toString(),
            durationSeconds = Duration.between(started, ended).seconds,
            requestCount = requestCount,
            masterReferenceRequests = masterReferenceRequests,
            referenceTableRequests = referenceTableRequests,
            archiveRequests = archiveRequests,
            responseHeaderCount = responseHeaderCount,
            responseBytes = responseBytes,
            firstRequestAtMillis = firstRequestAtMillis,
            firstArchiveRequestAtMillis = firstArchiveRequestAtMillis,
            firstResponseHeaderAtMillis = firstResponseHeaderAtMillis,
            firstArchiveResponseAtMillis = firstArchiveResponseAtMillis,
            idleTimeoutTriggered = idleTimeoutTriggered
        )
        return Js5SessionResult(
            lines = lines.toList(),
            jsonLines = jsonLines.toList(),
            summary = summary
        )
    }

    private fun classifyClientChunk(bytes: ByteArray, at: Long) {
        if (bytes.isEmpty()) {
            return
        }

        when (bytes[0].toInt() and 0xFF) {
            33 -> {
                archiveRequests++
                if (firstArchiveRequestAtMillis == null) {
                    firstArchiveRequestAtMillis = at
                }
            }
            3 -> referenceTableRequests++
            6 -> masterReferenceRequests++
        }
    }

    private fun millisSinceStart(timestamp: Instant): Long = Duration.between(started, timestamp).toMillis()

    private fun headHex(bytes: ByteArray, maxBytes: Int = 32): String {
        if (bytes.isEmpty()) {
            return ""
        }
        return bytes.copyOfRange(0, minOf(bytes.size, maxBytes))
            .joinToString(" ") { "%02x".format(it.toInt() and 0xFF) }
    }
}

class Js5ClientStreamParser(
    private val sessionId: Int,
    private val capture: Js5SessionCapture
) {
    fun feed(bytes: ByteArray, length: Int, timestamp: Instant) {
        if (length <= 0) {
            return
        }
        capture.recordClientChunk(bytes.copyOf(length), timestamp)
    }
}

class Js5RemoteStreamParser(
    private val sessionId: Int,
    private val capture: Js5SessionCapture
) {
    fun feed(bytes: ByteArray, length: Int, timestamp: Instant) {
        if (length <= 0) {
            return
        }
        capture.recordRemoteChunk(bytes.copyOf(length), timestamp)
    }

    fun finish(ended: Instant) {
        // The simplified recorder keeps streaming state in the capture itself.
    }
}
