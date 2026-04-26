package com.opennxt.net

import com.google.gson.GsonBuilder
import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.model.proxy.PacketDumper
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.golden.GoldenPacketSupport
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.pipeline.GamePacketCodec
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.game.serverprot.NoTimeout
import com.opennxt.net.game.serverprot.variables.VarpLarge
import com.opennxt.net.game.serverprot.variables.VarpSmall
import com.opennxt.net.proxy.ProxyChannelAttributes
import com.opennxt.net.proxy.UnidentifiedPacket
import io.netty.buffer.ByteBufUtil
import io.netty.buffer.Unpooled
import io.netty.channel.Channel
import mu.KotlinLogging
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.file.StandardOpenOption
import java.time.Instant
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Handles incoming packets on the lowest possible level. This is usually called directly from the Netty pipeline, and
 *   the [incomingQueue] is polled from the main thread. This way packets are received and decoded async, and handled
 *   sync.
 *
 * This also handles sending packets to the other side of the channel.
 *
 * This class can be used for both the server (Where clients connect to) and the client (Which connects to a server).
 *   It is, for example, used in the proxy as well.
 *
 * [side] represents the side of the remote. This means the server uses side "Client".
 */
class ConnectedClient(
    val side: Side,
    val channel: Channel,
    var processUnidentifiedPackets: Boolean = false,
    var dumper: PacketDumper? = null
) {
    companion object {
        private val bootstrapTraceLock = Any()
        private val bootstrapPacketCaptureLock = Any()
        private val bootstrapPacketCaptureJson = GsonBuilder().disableHtmlEscaping().create()
        private val bootstrapEvidencePackets = setOf(
            "CLIENT_BOOTSTRAP_BLOB_28",
            "CLIENT_BOOTSTRAP_CONTROL_50",
            "CLIENT_BOOTSTRAP_CONTROL_82"
        )
        // The 946 client needs some early default-varp progression, but the old 64-packet burst
        // disconnects it before it reaches the late scene-ready phases.
        private const val LATE_BOOTSTRAP_VARP_BATCH_SIZE = 8
        private const val LATE_BOOTSTRAP_VARP_BATCH_INTERVAL_NANOS = 0L

        private fun bootstrapTracePath(): Path =
            Paths.get(
                System.getProperty(
                    "opennxt.bootstrap.trace.path",
                    Constants.DATA_PATH.resolve("debug").resolve("world-bootstrap-raw.log").toString()
                )
            )

        private fun bootstrapPacketCapturePath(): Path =
            Paths.get(
                System.getProperty(
                    "opennxt.bootstrap.packet.capture.path",
                    Constants.DATA_PATH.resolve("debug").resolve("world-bootstrap-packets.jsonl").toString()
                )
            )
    }

    private data class VarpFilterDecision(
        val allowed: Boolean,
        val id: Int? = null
    )

    private data class DeferredServerPacket(
        val registration: PacketRegistry.Registration,
        val packet: GamePacket
    )

    private data class BootstrapPacketCaptureRecord(
        val timestamp: String,
        val timestampEpochMillis: Long,
        val packet: String,
        val opcode: Int,
        val payloadSize: Int,
        val payloadHex: String,
        val previewHex: String,
        val bootstrapStage: String,
        val lastCompletedBootstrapStage: String?,
        val remoteAddress: String,
        val localAddress: String,
        val channelId: String,
        val username: String?,
        val loginUsername: String?,
        val playerIndex: Int?,
        val decodeSummary: Map<String, Any?>,
        val expectation: Map<String, Any?>,
        val mismatchFlags: List<String>
    )

    val logger = KotlinLogging.logger { }

    val incomingQueue = ConcurrentLinkedQueue<GamePacket>()
    private val deferredBootstrapVarpQueue = ArrayDeque<DeferredServerPacket>()
    private val lateDefaultVarpReplaySkipIds = linkedSetOf<Int>()
    private var lastDeferredBootstrapVarpDrainAtNanos = 0L

    var initedPlayerList = false
    @Volatile var currentBootstrapStage: String? = null
    @Volatile var lastCompletedBootstrapStage: String? = null
    val completedBootstrapStages = CopyOnWriteArrayList<String>()

    fun traceBootstrap(message: String) {
        synchronized(bootstrapTraceLock) {
            val bootstrapTracePath = bootstrapTracePath()
            Files.createDirectories(bootstrapTracePath.parent)
            Files.writeString(
                bootstrapTracePath,
                "${Instant.now()} $message\n",
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            )
        }
    }

    fun receive(pair: OpcodeWithBuffer) {
        val bootstrapStage = currentBootstrapStage ?: lastCompletedBootstrapStage ?: "none"
        var payloadBytes = ByteArray(0)
        var registration: PacketRegistry.Registration? = null
        try {
            dumper?.dump(pair.opcode, pair.buf)
            payloadBytes = ByteBufUtil.getBytes(pair.buf, pair.buf.readerIndex(), pair.buf.readableBytes(), false)

            registration = PacketRegistry.getRegistration(side, pair.opcode)
            if (registration == null) {
                val inspectionRegistration =
                    if (processUnidentifiedPackets || dumper != null) PacketRegistry.getInspectionRegistration(side, pair.opcode) else null
                if (inspectionRegistration != null) {
                    dumpStructuredPayload(inspectionRegistration, payloadBytes, "inspection-generated")
                }
                val previewLength = minOf(32, pair.buf.readableBytes())
                val preview =
                    if (previewLength <= 0) "<empty>"
                    else ByteBufUtil.hexDump(pair.buf, pair.buf.readerIndex(), previewLength)
                logger.info {
                    "Unregistered opcode ${pair.opcode} received from ${channel.remoteAddress()} " +
                        "on side $side with ${pair.buf.readableBytes()} bytes " +
                        "[bootstrapStage=$bootstrapStage, preview=$preview]"
                }
                if (side == Side.CLIENT) {
                    traceBootstrap(
                        "recv-raw opcode=${pair.opcode} bytes=${pair.buf.readableBytes()} " +
                            "remote=${channel.remoteAddress()} stage=$bootstrapStage preview=$preview"
                    )
                }
                if (processUnidentifiedPackets)
                    incomingQueue.add(UnidentifiedPacket(OpcodeWithBuffer(pair.opcode, pair.buf.copy())))
                return
            }
            dumpStructuredPayload(registration, payloadBytes, "registered")
            recordBootstrapPacketEvidenceIfNeeded(
                registration = registration,
                payloadBytes = payloadBytes,
                bootstrapStage = bootstrapStage
            )
            if (side == Side.CLIENT) {
                logger.info {
                    "Decoded client packet ${registration.name} opcode=${pair.opcode} from ${channel.remoteAddress()} " +
                        "with ${payloadBytes.size} bytes [bootstrapStage=$bootstrapStage]"
                }
                traceBootstrap(
                    "recv-decoded name=${registration.name} opcode=${pair.opcode} bytes=${payloadBytes.size} " +
                        "remote=${channel.remoteAddress()} stage=$bootstrapStage"
                )
            }

            // TODO How can we do the following in a better way? This is getting very spaghetti.
            // TODO Clean up the following code...
            if (registration.name == "REBUILD_NORMAL" && !initedPlayerList) {
                val copy = UnidentifiedPacket(OpcodeWithBuffer(pair.opcode, pair.buf.copy()))
                incomingQueue.add(copy)

                val playerIndex = channel.attr(ProxyChannelAttributes.PLAYER_INDEX).get()
                println("RECEIVED REBUILD NORMAL -- DECODE PLAYER LIST FIRST - PLAYER INDEX IS $playerIndex")
                initedPlayerList = true

                val reader = GamePacketReader(pair.buf)
                reader.switchToBitAccess()
                reader.getBits(0x1e)
                for (i in 1 until 2048) {
                    if (i == playerIndex) {
                        println("I IS PLAYER INDEX @ $i")
                        continue
                    }

                    reader.getBits(0x14)
                }
                reader.switchToByteAccess()

                val decoded = registration.codec.decode(reader)
                val unreadBytes = pair.buf.readableBytes()
                if (unreadBytes != 0 ){
                    logger.warn { "Readable bytes in packet ${registration.name}: $unreadBytes" }
                }
                GoldenPacketSupport.traceReceive(channel, side, registration, payloadBytes, decoded, unreadBytes)

                logger.info { decoded.toString() }
                return
            }

            val decoded = registration.codec.decode(GamePacketReader(pair.buf))
            val unreadBytes = pair.buf.readableBytes()
            if (unreadBytes != 0 ){
                logger.warn { "Readable bytes in packet ${registration.name}: $unreadBytes" }
            }
            GoldenPacketSupport.traceReceive(channel, side, registration, payloadBytes, decoded, unreadBytes)

            incomingQueue.add(decoded)
        } catch (e: Exception) {
            if (side == Side.CLIENT && bootstrapStage == "social-state" && processUnidentifiedPackets) {
                logger.warn(e) {
                    "Falling back to unidentified social-state packet for opcode ${pair.opcode} " +
                        "from ${channel.remoteAddress()} on side $side [bootstrapStage=$bootstrapStage]"
                }
                traceBootstrap(
                    "recv-decode-fallback name=${registration?.name ?: "unknown"} opcode=${pair.opcode} " +
                        "bytes=${payloadBytes.size} remote=${channel.remoteAddress()} stage=$bootstrapStage " +
                        "type=${e::class.qualifiedName ?: e::class.simpleName ?: "unknown"} " +
                        "message=${e.message ?: "<none>"}"
                )
                incomingQueue.add(UnidentifiedPacket(OpcodeWithBuffer(pair.opcode, Unpooled.wrappedBuffer(payloadBytes))))
                return
            }
            logger.error(e) {
                "Failed to decode opcode ${pair.opcode} from ${channel.remoteAddress()} on side $side " +
                    "[bootstrapStage=$bootstrapStage]"
            }
        } finally {
            pair.buf.release()
        }
    }

    private fun dumpStructuredPayload(
        registration: PacketRegistry.Registration,
        payloadBytes: ByteArray,
        source: String,
    ) {
        val structuredFields =
            runCatching {
                when (val codec = registration.codec) {
                    is DynamicGamePacketCodec<*> -> {
                        codec.readFieldMap(GamePacketReader(Unpooled.wrappedBuffer(payloadBytes)))
                    }
                    else -> GoldenPacketSupport.inspect(registration, payloadBytes).fields
                }
            }.getOrElse {
                mapOf("decodeError" to (it.message ?: it::class.simpleName.orEmpty()))
            }

        dumper?.dumpStructured(
            opcode = registration.opcode,
            packet = registration.name,
            source = source,
            fields = structuredFields,
        )
    }

    private fun recordBootstrapPacketEvidenceIfNeeded(
        registration: PacketRegistry.Registration,
        payloadBytes: ByteArray,
        bootstrapStage: String,
    ) {
        if (side != Side.CLIENT || registration.name !in bootstrapEvidencePackets) {
            return
        }

        val payloadHex = payloadBytes.toHexString()
        val decodeSummary = buildBootstrapDecodeSummary(registration.opcode, payloadBytes)
        val expectation = bootstrapExpectation(registration.opcode)
        val mismatchFlags = bootstrapMismatchFlags(registration.opcode, payloadBytes)
        val now = Instant.now()
        val record = BootstrapPacketCaptureRecord(
            timestamp = now.toString(),
            timestampEpochMillis = now.toEpochMilli(),
            packet = registration.name,
            opcode = registration.opcode,
            payloadSize = payloadBytes.size,
            payloadHex = payloadHex,
            previewHex = payloadHex.take(48),
            bootstrapStage = bootstrapStage,
            lastCompletedBootstrapStage = lastCompletedBootstrapStage,
            remoteAddress = channel.remoteAddress()?.toString().orEmpty(),
            localAddress = channel.localAddress()?.toString().orEmpty(),
            channelId = channel.id().asLongText(),
            username = channel.attr(ProxyChannelAttributes.USERNAME).get(),
            loginUsername = channel.attr(RSChannelAttributes.LOGIN_USERNAME).get(),
            playerIndex = channel.attr(ProxyChannelAttributes.PLAYER_INDEX).get(),
            decodeSummary = decodeSummary,
            expectation = expectation,
            mismatchFlags = mismatchFlags
        )

        synchronized(bootstrapPacketCaptureLock) {
            val capturePath = bootstrapPacketCapturePath()
            Files.createDirectories(capturePath.parent)
            Files.writeString(
                capturePath,
                bootstrapPacketCaptureJson.toJson(record) + System.lineSeparator(),
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            )
        }
    }

    private fun buildBootstrapDecodeSummary(opcode: Int, payloadBytes: ByteArray): Map<String, Any?> {
        val summary = linkedMapOf<String, Any?>(
            "payloadSize" to payloadBytes.size
        )
        when (opcode) {
            28 -> {
                summary["kind"] = "opaque-variable-blob"
                summary["entryCount"] = if (payloadBytes.isNotEmpty()) payloadBytes[0].toInt() and 0xFF else null
            }
            50 -> {
                summary["kind"] = "unsigned-int-be"
                summary["value"] = if (payloadBytes.size == Int.SIZE_BYTES) payloadBytes.readUnsignedIntBe() else null
                summary["valueHex"] = payloadBytes.toHexString()
            }
            82 -> {
                summary["kind"] = "unsigned-medium-be"
                summary["value"] = if (payloadBytes.size == 3) payloadBytes.readUnsignedMediumBe() else null
                summary["valueHex"] = payloadBytes.toHexString()
            }
        }
        return summary
    }

    private fun bootstrapExpectation(opcode: Int): Map<String, Any?> =
        when (opcode) {
            28 -> linkedMapOf(
                "shape" to "variable",
                "entryCountOffset" to 0,
                "notes" to "opaque bootstrap blob"
            )
            50 -> linkedMapOf(
                "shape" to "fixed",
                "expectedSize" to Int.SIZE_BYTES,
                "decode" to "unsigned-int-be"
            )
            82 -> linkedMapOf(
                "shape" to "fixed",
                "expectedSize" to 3,
                "decode" to "unsigned-medium-be"
            )
            else -> emptyMap()
        }

    private fun bootstrapMismatchFlags(opcode: Int, payloadBytes: ByteArray): List<String> {
        val flags = mutableListOf<String>()
        when (opcode) {
            28 -> if (payloadBytes.isEmpty()) {
                flags += "empty-payload"
            }
            50 -> if (payloadBytes.size != Int.SIZE_BYTES) {
                flags += "expected-size-4-got-${payloadBytes.size}"
            }
            82 -> if (payloadBytes.size != 3) {
                flags += "expected-size-3-got-${payloadBytes.size}"
            }
        }
        return flags
    }

    private fun ByteArray.toHexString(): String = joinToString(separator = "") { byte ->
        (byte.toInt() and 0xFF).toString(16).padStart(2, '0')
    }

    private fun ByteArray.readUnsignedIntBe(): Long =
        ((this[0].toLong() and 0xFF) shl 24) or
            ((this[1].toLong() and 0xFF) shl 16) or
            ((this[2].toLong() and 0xFF) shl 8) or
            (this[3].toLong() and 0xFF)

    private fun ByteArray.readUnsignedMediumBe(): Int =
        ((this[0].toInt() and 0xFF) shl 16) or
            ((this[1].toInt() and 0xFF) shl 8) or
            (this[2].toInt() and 0xFF)

    fun write(pair: OpcodeWithBuffer) {
        if (side == Side.CLIENT) {
            val bootstrapStage = currentBootstrapStage ?: lastCompletedBootstrapStage ?: "none"
            val previewLength = minOf(32, pair.buf.readableBytes())
            val preview =
                if (previewLength <= 0) "<empty>"
                else ByteBufUtil.hexDump(pair.buf, pair.buf.readerIndex(), previewLength)
            traceBootstrap(
                "send-raw opcode=${pair.opcode} bytes=${pair.buf.readableBytes()} " +
                    "remote=${channel.remoteAddress()} stage=$bootstrapStage preview=$preview"
            )
        }
        channel.write(pair)
    }

    fun write(packet: GamePacket) {
        if (packet is UnidentifiedPacket) {
            write(packet.packet)
            return
        }

        try {
            val registration =
                PacketRegistry.getRegistration(if (side == Side.CLIENT) Side.SERVER else Side.CLIENT, packet::class)

            if (registration == null) {
                logger.warn("Registration not found for packet $packet side $side")
                return
            }

            val bootstrapStage = currentBootstrapStage ?: lastCompletedBootstrapStage ?: "none"
            val varpDecision = evaluateLobbyBootstrapVarpFilter(packet, bootstrapStage)
            if (!varpDecision.allowed) {
                logger.info {
                    "Skipping bootstrap varp ${varpDecision.id} for ${channel.remoteAddress()} " +
                        "outside configured range ${OpenNXT.config.lobbyBootstrap.defaultVarpMinId}.." +
                        "${OpenNXT.config.lobbyBootstrap.defaultVarpMaxId} [bootstrapStage=$bootstrapStage]"
                }
                return
            }

            if (shouldSkipLateDefaultVarpReplay(packet, bootstrapStage)) {
                return
            }

            if (shouldDeferLateBootstrapVarp(packet, bootstrapStage)) {
                deferredBootstrapVarpQueue.addLast(DeferredServerPacket(registration, packet))
            } else {
                writeEncodedPacket(registration, packet, bootstrapStage)
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun pendingDeferredBootstrapVarpCount(): Int = deferredBootstrapVarpQueue.size

    fun primeLateDefaultVarpReplaySkip(ids: Iterable<Int>) {
        lateDefaultVarpReplaySkipIds.addAll(ids)
    }

    fun withLateDefaultVarpReplaySkip(ids: Iterable<Int>, block: () -> Unit) {
        val additions = ids.toList()
        if (additions.isEmpty()) {
            block()
            return
        }

        lateDefaultVarpReplaySkipIds.addAll(additions)
        try {
            block()
        } finally {
            additions.forEach { lateDefaultVarpReplaySkipIds.remove(it) }
        }
    }

    private fun shouldDeferLateBootstrapVarp(packet: GamePacket, bootstrapStage: String): Boolean {
        if (side != Side.CLIENT || bootstrapStage != "late-default-varps") {
            return false
        }

        return packet is VarpSmall || packet is VarpLarge
    }

    private fun drainDeferredBootstrapVarps(maxPerFlush: Int = LATE_BOOTSTRAP_VARP_BATCH_SIZE) {
        if (deferredBootstrapVarpQueue.isEmpty()) {
            return
        }

        val now = System.nanoTime()
        if (
            LATE_BOOTSTRAP_VARP_BATCH_INTERVAL_NANOS > 0L &&
            lastDeferredBootstrapVarpDrainAtNanos != 0L &&
            now - lastDeferredBootstrapVarpDrainAtNanos < LATE_BOOTSTRAP_VARP_BATCH_INTERVAL_NANOS
        ) {
            return
        }

        var drained = 0
        while (drained < maxPerFlush) {
            val deferred = deferredBootstrapVarpQueue.removeFirstOrNull() ?: break
            writeEncodedPacket(deferred.registration, deferred.packet, "late-default-varps")
            drained++
        }
        lastDeferredBootstrapVarpDrainAtNanos = now

        if (side == Side.CLIENT && drained > 0) {
            traceBootstrap(
                "send-late-default-varps-batch remote=${channel.remoteAddress()} drained=$drained " +
                    "remaining=${deferredBootstrapVarpQueue.size}"
            )
            if (deferredBootstrapVarpQueue.isNotEmpty()) {
                PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class)?.let { registration ->
                    writeEncodedPacket(registration, NoTimeout, "late-default-varps")
                    traceBootstrap(
                        "send-late-default-varps-keepalive remote=${channel.remoteAddress()} " +
                            "remaining=${deferredBootstrapVarpQueue.size}"
                    )
                }
            }
        }
    }

    private fun writeEncodedPacket(
        registration: PacketRegistry.Registration,
        packet: GamePacket,
        bootstrapStage: String
    ) {
        if (side == Side.CLIENT) {
            logger.info {
                "Sending packet ${registration.name} (${packet::class.simpleName}) " +
                    "to ${channel.remoteAddress()} on opcode ${registration.opcode} " +
                    "[bootstrapStage=$bootstrapStage]"
            }
        }

        val buffer = Unpooled.buffer()
        @Suppress("UNCHECKED_CAST")
        (registration.codec as GamePacketCodec<GamePacket>).encode(packet, GamePacketBuilder(buffer))
        if (side == Side.CLIENT) {
            val previewLength = minOf(32, buffer.writerIndex())
            val preview =
                if (previewLength <= 0) "<empty>"
                else ByteBufUtil.hexDump(buffer, 0, previewLength)
            traceBootstrap(
                "send-raw opcode=${registration.opcode} bytes=${buffer.writerIndex()} " +
                    "remote=${channel.remoteAddress()} stage=$bootstrapStage preview=$preview"
            )
        }
        GoldenPacketSupport.traceSend(
            channel = channel,
            localSide = if (side == Side.CLIENT) Side.SERVER else Side.CLIENT,
            registration = registration,
            payload = ByteBufUtil.getBytes(buffer, 0, buffer.writerIndex(), false),
            packet = packet
        )
        channel.write(OpcodeWithBuffer(registration.opcode, buffer))
    }

    private fun shouldSkipLateDefaultVarpReplay(packet: GamePacket, bootstrapStage: String): Boolean {
        if (side != Side.CLIENT || bootstrapStage != "late-default-varps" || lateDefaultVarpReplaySkipIds.isEmpty()) {
            return false
        }

        val id =
            when (packet) {
                is VarpSmall -> packet.id
                is VarpLarge -> packet.id
                else -> return false
            }

        if (id !in lateDefaultVarpReplaySkipIds) {
            return false
        }

        traceBootstrap("skip-late-default-varp-replay remote=${channel.remoteAddress()} id=$id stage=$bootstrapStage")
        return true
    }

    private fun evaluateLobbyBootstrapVarpFilter(packet: GamePacket, bootstrapStage: String): VarpFilterDecision {
        if (
            side != Side.CLIENT ||
            (bootstrapStage != "default-state" &&
                bootstrapStage != "default-varps" &&
                bootstrapStage != "late-default-varps")
        ) {
            return VarpFilterDecision(allowed = true)
        }

        val id =
            when (packet) {
                is VarpSmall -> packet.id
                is VarpLarge -> packet.id
                else -> return VarpFilterDecision(allowed = true)
            }

        val lobbyBootstrap = OpenNXT.config.lobbyBootstrap
        val allowed = id in lobbyBootstrap.defaultVarpMinId..lobbyBootstrap.defaultVarpMaxId
        return VarpFilterDecision(allowed = allowed, id = id)
    }

    fun flush() {
        drainDeferredBootstrapVarps()
        channel.flush()
    }
}
