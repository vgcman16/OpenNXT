package com.opennxt.net.js5

import com.opennxt.Js5Thread
import com.opennxt.OpenNXT
import com.opennxt.filesystem.Container
import com.opennxt.net.PreLoginForensics
import com.opennxt.net.js5.packet.Js5Packet
import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.Channel
import io.netty.util.AttributeKey
import mu.KotlinLogging
import java.nio.ByteBuffer
import java.net.InetSocketAddress
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
        val totalLength: Int,
        var blocksSent: Int = 0,
    )
    private data class ClientHandshake(
        val major: Int,
        val minor: Int,
        val token: String,
        val language: Int,
    )

    companion object {
        val ATTR_KEY = AttributeKey.valueOf<Js5Session>("js5-session")
        val XOR_KEY = AttributeKey.valueOf<Int>("js5-xor-key")
        val LOGGED_IN = AttributeKey.valueOf<Boolean>("js5-logged-in")
        private val NEXT_ID = AtomicInteger(0)
        private const val MAX_RESPONSE_BLOCK_PAYLOAD_BYTES = 102400 - 5
        private const val QUEUED_TRACE_INDEX = 255
        private const val QUEUED_TRACE_ARCHIVE = 2
        private const val QUEUED_TRACE_PREVIEW_BYTES = 16
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
    @Volatile
    private var clientHandshake: ClientHandshake? = null
    @Volatile
    private var retailLoggedOutProxy: RetailLoggedOutJs5Proxy? = null

    init {
        channel.attr(ATTR_KEY).set(this)
        channel.attr(XOR_KEY).set(0)
        channel.attr(LOGGED_IN).set(false)
    }

    private fun record(event: String, details: Map<String, Any?> = emptyMap()) {
        val localPort = (channel.localAddress() as? InetSocketAddress)?.port ?: -1
        PreLoginForensics.recordTransportEvent(
            localPort = localPort,
            remoteAddress = channel.remoteAddress().toString(),
            event = event,
            details = details + mapOf("sessionId" to id),
        )
    }

    private fun loadChecksumTableData(): ByteBuf {
        return Unpooled.wrappedBuffer(OpenNXT.checksumTable)
    }

    internal fun formatArchivePayload(index: Int, raw: ByteBuffer): ByteArray {
        return if (index == 255) {
            val bytes = ByteArray(raw.remaining())
            raw.duplicate().get(bytes)
            bytes
        } else {
            stripVersionTrailer(raw)
        }
    }

    internal fun loadFileData(
        request: Js5Packet.RequestFile,
        fetchRetailLoggedOutArchive: (build: Int, index: Int, archive: Int, priority: Boolean) -> ByteArray? =
            OpenNXT::fetchRetailLoggedOutJs5Archive,
        preferRetailLoggedOutArchives: (build: Int) -> Boolean =
            OpenNXT::retailLoggedOutJs5PassthroughEnabled,
    ): ByteBuf? {
        val retailFirstLoggedOutRequest = !isLoggedIn() &&
            preferRetailLoggedOutArchives(request.build) &&
            !(request.index == 255 && request.archive == 255)

        if (retailFirstLoggedOutRequest) {
            try {
                val retailBytes = fetchRetailLoggedOutArchive(
                    OpenNXT.config.build,
                    request.index,
                    request.archive,
                    request.priority,
                )
                if (retailBytes != null) {
                    logger.info {
                        "Using retail logged-out JS5 passthrough for ${describeRequest(request)} " +
                            "from ${channel.remoteAddress()}"
                    }
                    return Unpooled.wrappedBuffer(retailBytes)
                }
            } catch (e: Exception) {
            }
        }

        try {
            val localData = when {
                request.index == 255 && request.archive == 255 -> loadChecksumTableData()
                request.index == 255 -> {
                    OpenNXT.filesystem.readReferenceTable(request.archive)?.let { raw ->
                        Unpooled.wrappedBuffer(formatArchivePayload(request.index, raw))
                    }
                }
                else -> {
                    OpenNXT.filesystem.read(request.index, request.archive)?.let { raw ->
                        Unpooled.wrappedBuffer(formatArchivePayload(request.index, raw))
                    }
                }
            }
            if (localData != null) {
                if (retailFirstLoggedOutRequest) {
                    logger.info {
                        "Using local logged-out JS5 fallback for ${describeRequest(request)} " +
                            "after retail passthrough miss from ${channel.remoteAddress()}"
                    }
                }
                return localData
            }
        } catch (e: Exception) {
            if (isLoggedIn()) {
                return null
            }
        }

        if (isLoggedIn()) {
            return null
        }

        if (retailFirstLoggedOutRequest) {
            return null
        }

        return try {
            val retailBytes = fetchRetailLoggedOutArchive(
                OpenNXT.config.build,
                request.index,
                request.archive,
                request.priority,
            ) ?: return null
            logger.info {
                "Using retail logged-out JS5 fallback for ${describeRequest(request)} " +
                    "from ${channel.remoteAddress()}"
            }
            Unpooled.wrappedBuffer(retailBytes)
        } catch (e: Exception) {
            null
        }
    }

    private fun Js5Packet.RequestFile.loadFileData(): ByteBuf? = loadFileData(this)

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
        return requestSequence <= 64 || request.archive == 255 || shouldTraceOccurrence(occurrence)
    }

    private fun shouldTraceResponse(request: Js5Packet.RequestFile, occurrence: Int): Boolean {
        return responseSequence <= 64 || request.archive == 255 || shouldTraceOccurrence(occurrence)
    }

    private fun Js5Packet.RequestFile.archiveKey(): ArchiveKey = ArchiveKey(index, archive)

    private fun Js5Packet.RequestFile.isInlineCriticalRequest(): Boolean {
        return priority && index == 255 && archive == 255
    }

    private fun Js5Packet.RequestFile.shouldAllowDuplicateWhileLoggedOut(): Boolean {
        return !isLoggedIn() && index == 255 && archive != 255
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

    private fun ByteBuf.previewHex(limit: Int = QUEUED_TRACE_PREVIEW_BYTES): String {
        val length = minOf(readableBytes(), limit)
        if (length <= 0) {
            return "<empty>"
        }

        val bytes = ByteArray(length)
        getBytes(readerIndex(), bytes)
        return bytes.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
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

    private fun isLoggedIn(): Boolean = channel.attr(LOGGED_IN).get() ?: false

    fun recordClientHandshake(packet: Js5Packet.Handshake) {
        clientHandshake = ClientHandshake(
            major = packet.major,
            minor = packet.minor,
            token = packet.token,
            language = packet.language,
        )
    }

    fun hasRetailLoggedOutProxy(): Boolean = retailLoggedOutProxy != null

    fun activateRetailLoggedOutProxyIfEligible(build: Int): Boolean {
        if (!OpenNXT.retailLoggedOutJs5PassthroughEnabled(build)) {
            return false
        }

        if (retailLoggedOutProxy != null) {
            return true
        }

        val handshake = clientHandshake ?: return false
        val proxy = RetailLoggedOutJs5Proxy(
            localChannel = channel,
            major = handshake.major,
            minor = handshake.minor,
            token = handshake.token,
            language = handshake.language,
        )
        retailLoggedOutProxy = proxy
        proxy.connect()
        return true
    }

    fun forwardRetailLoggedOutProxyBytes(data: ByteBuf) {
        retailLoggedOutProxy?.forwardClientBytes(data) ?: data.release()
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

        val totalLength = data.js5ResponseLength()
        return PendingResponse(
            priority = request.priority,
            index = request.index,
            archive = request.archive,
            data = data,
            remaining = totalLength,
            totalLength = totalLength,
        )
    }

    private fun nextPendingResponse(priority: Boolean): PendingResponse? {
        val requests = queueFor(priority)
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

        val isQueuedTraceTarget = response.index == QUEUED_TRACE_INDEX && response.archive == QUEUED_TRACE_ARCHIVE
        val firstBlock = response.blocksSent == 0
        if (isQueuedTraceTarget && shouldTraceOccurrence(responseOccurrences[ArchiveKey(response.index, response.archive)]?.get() ?: 1)) {
            logger.info {
                "JS5 queued wire trace session#$id: index=${response.index}, archive=${response.archive}, " +
                    "priority=${response.priority}, firstBlock=$firstBlock, remainingBefore=${response.remaining}, " +
                    "payloadBytes=$payloadBytes, totalLength=${response.totalLength}, preview=${out.previewHex()}"
            }
        }

        response.remaining -= payloadBytes
        response.blocksSent++
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
            if (request.shouldAllowDuplicateWhileLoggedOut()) {
                logger.info {
                    "Allowing duplicate logged-out js5 request from ${channel.remoteAddress()}: " +
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

        if (request.shouldAllowDuplicateWhileLoggedOut()) {
            val occurrence = requestOccurrences[archiveKey]?.get() ?: 0
            if (occurrence > 0 && shouldTraceOccurrence(occurrence + 1)) {
                logger.info {
                    "Queued duplicate logged-out reference-table request from ${channel.remoteAddress()}: " +
                        "opcode=$opcode, priority=${request.priority}, nxt=${request.nxt}, " +
                        "build=${request.build}, ${describeRequest(request)}, priorOccurrences=$occurrence"
                }
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
                record(
                    event = "js5-inline-response",
                    details = mapOf(
                        "index" to request.index,
                        "archive" to request.archive,
                        "bytes" to data.readableBytes(),
                        "occurrence" to responseOccurrence,
                    ),
                )
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
        record(
            event = "js5-prefetch-table",
            details = mapOf(
                "reason" to reason,
                "entries" to prefetchTable.size,
            ),
        )
        channel.writeAndFlush(Js5Packet.Prefetches(prefetchTable))
        prefetchTableSent = true
    }

    override fun close() {
        initialized = false
        retailLoggedOutProxy?.close()
        retailLoggedOutProxy = null

        logger.info {
            "Closing js5 session#$id from ${channel.remoteAddress()}: " +
                "initialized=$initialized, requests=$requestSequence, responses=$responseSequence, " +
                "rawReads=$inboundTraceSequence, " +
                "topRequests=[${topRequestSummary(requestOccurrences)}], " +
                "topResponses=[${topRequestSummary(responseOccurrences)}]"
        }
        record(
            event = "js5-session-close",
            details = mapOf(
                "initialized" to initialized,
                "requests" to requestSequence,
                "responses" to responseSequence,
                "rawReads" to inboundTraceSequence,
                "loggedIn" to isLoggedIn(),
                "channelActive" to channel.isActive,
                "channelOpen" to channel.isOpen,
            ),
        )

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
