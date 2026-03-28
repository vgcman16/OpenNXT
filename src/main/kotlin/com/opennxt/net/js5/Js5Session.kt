package com.opennxt.net.js5

import com.opennxt.Js5Thread
import com.opennxt.OpenNXT
import com.opennxt.filesystem.Container
import com.opennxt.net.js5.packet.Js5Packet
import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.Channel
import io.netty.util.AttributeKey
import mu.KotlinLogging
import java.nio.ByteBuffer
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.atomic.AtomicInteger

class Js5Session(val channel: Channel) : AutoCloseable {

    private val logger = KotlinLogging.logger { }

    private data class ArchiveKey(val index: Int, val archive: Int)
    private data class PendingResponse(
        val priority: Boolean,
        val index: Int,
        val archive: Int,
        val data: ByteBuf,
        var remaining: Int,
    )

    companion object {
        val ATTR_KEY = AttributeKey.valueOf<Js5Session>("js5-session")
        val XOR_KEY = AttributeKey.valueOf<Int>("js5-xor-key")
        val LOGGED_IN = AttributeKey.valueOf<Boolean>("js5-logged-in")
        private val NEXT_ID = AtomicInteger(0)
        private const val MAX_RESPONSE_BLOCK_PAYLOAD_BYTES = 102400 - 5
    }

    val id = NEXT_ID.incrementAndGet()
    val highPriorityRequests = ConcurrentLinkedQueue<Js5Packet.RequestFile>()
    val lowPriorityRequests = ConcurrentLinkedQueue<Js5Packet.RequestFile>()
    private val highPriorityResponses = ArrayDeque<PendingResponse>()
    private val lowPriorityResponses = ArrayDeque<PendingResponse>()
    private val highPriorityInFlight = ConcurrentHashMap.newKeySet<ArchiveKey>()
    private val lowPriorityInFlight = ConcurrentHashMap.newKeySet<ArchiveKey>()
    var initialized = false
    private var prefetchTableSent = false
    private var requestSequence = 0
    private var responseSequence = 0
    private var inboundTraceSequence = 0
    private val requestOccurrences = ConcurrentHashMap<ArchiveKey, AtomicInteger>()
    private val responseOccurrences = ConcurrentHashMap<ArchiveKey, AtomicInteger>()

    init {
        channel.attr(ATTR_KEY).set(this)
        channel.attr(XOR_KEY).set(0)
        channel.attr(LOGGED_IN).set(false)
    }

    private fun loadChecksumTableData(): ByteBuf {
        return Unpooled.wrappedBuffer(OpenNXT.checksumTable)
    }

    private fun Js5Packet.RequestFile.loadFileData(): ByteBuf? {
        try {
            return when {
                index == 255 && archive == 255 -> loadChecksumTableData()
                index == 255 -> {
                    val raw = OpenNXT.filesystem.readReferenceTable(archive) ?: return null
                    Unpooled.wrappedBuffer(stripVersionTrailer(raw))
                }
                else -> {
                    val raw = OpenNXT.filesystem.read(index, archive) ?: return null
                    Unpooled.wrappedBuffer(stripVersionTrailer(raw))
                }
            }
        } catch (e: Exception) {
            return null
        }
    }

    private fun stripVersionTrailer(raw: ByteBuffer): ByteArray {
        val bytes = ByteArray(raw.remaining())
        raw.duplicate().get(bytes)

        // Cache files are stored with a trailing 2-byte archive version. Live JS5 strips that trailer
        // when serving non-255 archives, so mirror that wire format for native clients.
        val version = Container.decode(ByteBuffer.wrap(bytes)).version
        if (version == -1 || bytes.size < 2) {
            return bytes
        }
        return bytes.copyOf(bytes.size - 2)
    }

    private fun describeRequest(request: Js5Packet.RequestFile): String = when {
        request.index == 255 && request.archive == 255 -> "master-reference-table(index=255, archive=255)"
        request.index == 255 -> "reference-table(index=255, archive=${request.archive})"
        else -> "archive(index=${request.index}, archive=${request.archive})"
    }

    private fun shouldTraceOccurrence(occurrence: Int): Boolean {
        return occurrence <= 3 || occurrence == 5 || occurrence == 10 || occurrence == 25 || occurrence % 50 == 0
    }

    private fun shouldTraceRequest(request: Js5Packet.RequestFile, occurrence: Int): Boolean {
        return requestSequence <= 64 || request.index == 255 || request.archive == 255 || shouldTraceOccurrence(occurrence)
    }

    private fun shouldTraceResponse(request: Js5Packet.RequestFile, occurrence: Int): Boolean {
        return responseSequence <= 64 || request.index == 255 || request.archive == 255 || shouldTraceOccurrence(occurrence)
    }

    private fun Js5Packet.RequestFile.archiveKey(): ArchiveKey = ArchiveKey(index, archive)

    private fun Js5Packet.RequestFile.isInlineCriticalRequest(): Boolean {
        return priority && index == 255 && archive == 255
    }

    private fun ByteBuf.js5ResponseLength(): Int {
        var length = ((getByte(1).toInt() and 0xff) shl 24) +
            ((getByte(2).toInt() and 0xff) shl 16) +
            ((getByte(3).toInt() and 0xff) shl 8) +
            (getByte(4).toInt() and 0xff) + 5
        if (getByte(0).toInt() != 0) {
            length += 4
        }
        return length
    }

    private fun describeAvailability(request: Js5Packet.RequestFile): String = when {
        request.index == 255 && request.archive == 255 -> "available=checksum-table"
        request.index == 255 -> "available=${OpenNXT.filesystem.readReferenceTable(request.archive) != null}"
        else -> "available=${OpenNXT.filesystem.exists(request.index, request.archive)}"
    }

    private fun queueFor(priority: Boolean): ConcurrentLinkedQueue<Js5Packet.RequestFile> {
        return if (priority) highPriorityRequests else lowPriorityRequests
    }

    private fun pendingQueueFor(priority: Boolean): ArrayDeque<PendingResponse> {
        return if (priority) highPriorityResponses else lowPriorityResponses
    }

    private fun inflightSetFor(priority: Boolean): MutableSet<ArchiveKey> {
        return if (priority) highPriorityInFlight else lowPriorityInFlight
    }

    private fun shouldPreferQueuedRequest(priority: Boolean, request: Js5Packet.RequestFile?): Boolean {
        if (!priority || request == null) {
            return false
        }

        val loggedIn = isLoggedIn()
        return !loggedIn && request.index == 255 && request.archive != 255
    }

    private fun isLoggedIn(): Boolean = channel.attr(LOGGED_IN).get() ?: false

    private fun Js5Packet.RequestFile.isLoggedOutReferenceTableRequest(): Boolean {
        return !isLoggedIn() && index == 255 && archive != 255
    }

    private fun loadPendingResponse(request: Js5Packet.RequestFile): PendingResponse? {
        val data = request.loadFileData()
        if (data == null) {
            inflightSetFor(request.priority).remove(request.archiveKey())
            logger.warn {
                "JS5 missing file for ${if (request.priority) "high" else "low"}-priority request from ${channel.remoteAddress()}: " +
                    "${describeRequest(request)}, ${describeAvailability(request)}"
            }
            return null
        }

        responseSequence++
        val occurrence = responseOccurrences.computeIfAbsent(request.archiveKey()) { AtomicInteger() }
            .incrementAndGet()
        if (shouldTraceResponse(request, occurrence)) {
            logger.info {
                "Serving js5 response #$responseSequence to ${channel.remoteAddress()}: " +
                    "${describeRequest(request)}, priority=${request.priority}, occurrence=$occurrence, bytes=${data.readableBytes()}"
            }
        }

        return PendingResponse(
            priority = request.priority,
            index = request.index,
            archive = request.archive,
            data = data,
            remaining = data.js5ResponseLength(),
        )
    }

    private fun nextPendingResponse(priority: Boolean): PendingResponse? {
        val requests = queueFor(priority)
        if (shouldPreferQueuedRequest(priority, requests.peek())) {
            while (true) {
                val request = requests.poll() ?: break
                val pending = loadPendingResponse(request)
                if (pending != null) {
                    return pending
                }
            }
        }

        while (true) {
            val request = requests.poll()
            if (request == null) {
                val pendingQueue = pendingQueueFor(priority)
                return if (pendingQueue.isNotEmpty()) pendingQueue.removeFirst() else null
            }
            val pending = loadPendingResponse(request)
            if (pending != null) {
                return pending
            }
        }
    }

    private fun recyclePendingResponse(response: PendingResponse) {
        if (response.remaining > 0) {
            pendingQueueFor(response.priority).addLast(response)
            return
        }

        val archiveKey = ArchiveKey(response.index, response.archive)
        inflightSetFor(response.priority).remove(archiveKey)

        if (response.data.refCnt() > 0) {
            response.data.release()
        }
    }

    private fun writeResponseBlock(response: PendingResponse, budget: Int): Int {
        val payloadBudget = budget - 5
        val payloadBytes = minOf(MAX_RESPONSE_BLOCK_PAYLOAD_BYTES, response.remaining, payloadBudget)
        if (payloadBytes <= 0) {
            return 0
        }

        val xor = channel.attr(XOR_KEY).get() ?: 0
        val size = if (response.priority) response.archive else (response.archive or Int.MIN_VALUE)
        val out = channel.alloc().buffer(5 + payloadBytes)
        out.writeByte(response.index xor xor)
        out.writeByte((size shr 24) xor xor)
        out.writeByte((size shr 16) xor xor)
        out.writeByte((size shr 8) xor xor)
        out.writeByte(size xor xor)

        repeat(payloadBytes) {
            out.writeByte(response.data.readByte().toInt() xor xor)
        }
        response.remaining -= payloadBytes
        channel.write(out)
        return payloadBytes + 5
    }

    private fun topRequestSummary(
        occurrences: ConcurrentHashMap<ArchiveKey, AtomicInteger>,
        limit: Int = 8
    ): String {
        return occurrences.entries
            .sortedByDescending { it.value.get() }
            .take(limit)
            .joinToString(separator = ", ") { entry ->
                "index=${entry.key.index}/archive=${entry.key.archive} x${entry.value.get()}"
            }
    }

    fun traceInboundBytes(stage: String, buf: ByteBuf, handshakeDecoded: Boolean) {
        inboundTraceSequence++

        if (inboundTraceSequence > 24) {
            return
        }

        val readable = buf.readableBytes()
        val previewLength = minOf(readable, 32)
        val preview = ByteArray(previewLength)
        if (previewLength > 0) {
            buf.getBytes(buf.readerIndex(), preview)
        }

        logger.info {
            "JS5 raw inbound session#$id read#$inboundTraceSequence from ${channel.remoteAddress()}: " +
                "stage=$stage, handshakeDecoded=$handshakeDecoded, readable=$readable, " +
                "preview=${preview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }}"
        }
    }

    fun enqueueRequest(request: Js5Packet.RequestFile, opcode: Int) {
        val archiveKey = request.archiveKey()
        val inflight = inflightSetFor(request.priority)
        if (!inflight.add(archiveKey)) {
            if (request.isLoggedOutReferenceTableRequest()) {
                logger.info {
                    "Allowing duplicate logged-out js5 bootstrap request from ${channel.remoteAddress()}: " +
                        "opcode=$opcode, priority=${request.priority}, nxt=${request.nxt}, " +
                        "build=${request.build}, ${describeRequest(request)}"
                }
            } else {
            if (request.index == 255 || request.archive == 255) {
                logger.info {
                    "Suppressing duplicate js5 request from ${channel.remoteAddress()}: " +
                        "opcode=$opcode, priority=${request.priority}, nxt=${request.nxt}, " +
                        "build=${request.build}, ${describeRequest(request)}"
                }
            }
            return
            }
        }

        requestSequence++
        val occurrence = requestOccurrences.computeIfAbsent(archiveKey) { AtomicInteger() }.incrementAndGet()

        if (shouldTraceRequest(request, occurrence)) {
            logger.info {
                "Queued js5 request #$requestSequence from ${channel.remoteAddress()}: " +
                    "opcode=$opcode, priority=${request.priority}, nxt=${request.nxt}, " +
                    "build=${request.build}, occurrence=$occurrence, ${describeRequest(request)}, ${describeAvailability(request)}"
            }
        }

        if (request.isInlineCriticalRequest()) {
            val data = request.loadFileData()
            if (data != null) {
                responseSequence++
                val responseOccurrence = responseOccurrences.computeIfAbsent(request.archiveKey()) { AtomicInteger() }
                    .incrementAndGet()
                logger.info {
                    "Serving js5 response inline #$responseSequence to ${channel.remoteAddress()}: " +
                        "${describeRequest(request)}, priority=true, occurrence=$responseOccurrence, " +
                        "bytes=${data.readableBytes()}"
                }
                channel.write(Js5Packet.RequestFileResponse(true, request.index, request.archive, data))
                channel.flush()
                inflight.remove(archiveKey)
                return
            }
            inflight.remove(archiveKey)
        }

        if (request.priority) highPriorityRequests.add(request)
        else lowPriorityRequests.add(request)

        Js5Thread.wake()
    }

    fun process(limit: Int): Int {
        var bytesSent = 0

        try {
            while (bytesSent < limit) {
                val response = nextPendingResponse(priority = true) ?: break
                val sent = writeResponseBlock(response, limit - bytesSent)
                bytesSent += sent
                recyclePendingResponse(response)
            }

            while (bytesSent < limit) {
                val response = nextPendingResponse(priority = false) ?: break
                val sent = writeResponseBlock(response, limit - bytesSent)
                bytesSent += sent
                recyclePendingResponse(response)
            }
        } finally {
        if (bytesSent != 0) {
            channel.flush()
        }
    }

    return bytesSent
    }

    fun updateLoggedInState(loggedIn: Boolean) {
        channel.attr(LOGGED_IN).set(loggedIn)
    }

    fun initialize() {
        if (initialized) {
            logger.warn("Tried initializing js5 session twice from ${channel.remoteAddress()}. Terminating connection.")
            close()
            return
        }

        initialized = true
        Js5Thread.addSession(this)
    }

    fun sendPrefetchTableIfNeeded(reason: String) {
        if (prefetchTableSent) {
            logger.info {
                "Skipping duplicate js5 prefetch table for session#$id from ${channel.remoteAddress()} because it was already sent " +
                    "(reason=$reason)"
            }
            return
        }

        val prefetchTable = OpenNXT.prefetches.entries.copyOf()
        logger.info {
            "Sending js5 prefetch table to ${channel.remoteAddress()} on session#$id " +
                "(reason=$reason, entries=${prefetchTable.size})"
        }
        channel.writeAndFlush(Js5Packet.Prefetches(prefetchTable))
        prefetchTableSent = true
    }

    override fun close() {
        initialized = false

        logger.info {
            "Closing js5 session#$id from ${channel.remoteAddress()}: " +
                "initialized=$initialized, requests=$requestSequence, responses=$responseSequence, " +
                "rawReads=$inboundTraceSequence, " +
                "topRequests=[${topRequestSummary(requestOccurrences)}], " +
                "topResponses=[${topRequestSummary(responseOccurrences)}]"
        }

        Js5Thread.removeSession(this)

        channel.close()
        highPriorityRequests.clear()
        lowPriorityRequests.clear()
        highPriorityResponses.forEach { response ->
            if (response.data.refCnt() > 0) {
                response.data.release()
            }
        }
        lowPriorityResponses.forEach { response ->
            if (response.data.refCnt() > 0) {
                response.data.release()
            }
        }
        highPriorityResponses.clear()
        lowPriorityResponses.clear()
        highPriorityInFlight.clear()
        lowPriorityInFlight.clear()
    }
}
