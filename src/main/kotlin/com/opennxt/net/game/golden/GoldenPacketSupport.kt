package com.opennxt.net.game.golden

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.net.Side
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.pipeline.GamePacketCodec
import com.opennxt.net.game.serverprot.RunClientScript
import com.opennxt.net.game.serverprot.ifaces.IfOpenSub
import com.opennxt.net.game.serverprot.ifaces.IfOpenTop
import com.opennxt.net.game.serverprot.variables.VarpLarge
import com.opennxt.net.game.serverprot.variables.VarpSmall
import io.netty.buffer.ByteBufUtil
import io.netty.buffer.Unpooled
import io.netty.channel.Channel
import mu.KotlinLogging
import java.nio.file.Files
import java.nio.file.StandardOpenOption
import java.time.Instant

object GoldenPacketSupport {
    data class Definition(
        val name: String,
        val opcode: Int,
        val size: Int,
        val fields: List<String>? = null
    )

    data class Inspection(
        val packet: GamePacket,
        val fields: Map<String, Any>,
        val unreadBytes: Int
    )

    private val logger = KotlinLogging.logger { }
    private val tracePath = Constants.DATA_PATH.resolve("debug").resolve("golden-packets.log")
    private val traceLock = Any()

    private val server946Definitions = listOf(
        Definition("VARP_LARGE", 51, 6, listOf("value int", "id ushort")),
        Definition("VARP_SMALL", 72, 3, listOf("id ushort", "value ubyte")),
        Definition(
            "IF_OPENTOP",
            126,
            19,
            listOf("xtea0 int", "xtea1 int", "xtea2 int", "id ushortle", "xtea3 int", "bool ubyte")
        ),
        Definition(
            "IF_OPENSUB",
            38,
            23,
            listOf(
                "xtea0 int",
                "parent intle",
                "xtea1 int",
                "xtea2 int",
                "flag u128byte",
                "id ushortle128",
                "xtea3 int"
            )
        ),
        Definition("RUNCLIENTSCRIPT", 141, -2)
    )

    private val server946DefinitionsByName = server946Definitions.associateBy { it.name }
    private val server946DefinitionsByOpcode = server946Definitions.associateBy { it.opcode }

    fun requiredDefinitions(build: Int, side: Side): List<Definition> {
        return if (build == 946 && side == Side.SERVER) server946Definitions else emptyList()
    }

    fun requiredDefinition(build: Int, side: Side, name: String): Definition? {
        return if (build == 946 && side == Side.SERVER) server946DefinitionsByName[name] else null
    }

    fun isGolden(side: Side, opcode: Int): Boolean {
        return OpenNXT.config.build == 946 && side == Side.SERVER && server946DefinitionsByOpcode.containsKey(opcode)
    }

    fun isGolden(side: Side, name: String): Boolean {
        return OpenNXT.config.build == 946 && side == Side.SERVER && server946DefinitionsByName.containsKey(name)
    }

    fun inspect(registration: PacketRegistry.Registration, payload: ByteArray): Inspection {
        val fields = decodeFields(registration, payload)
        val packetBuffer = Unpooled.wrappedBuffer(payload)
        val reader = GamePacketReader(packetBuffer)
        @Suppress("UNCHECKED_CAST")
        val packet = (registration.codec as GamePacketCodec<GamePacket>).decode(reader)
        return Inspection(packet = packet, fields = fields, unreadBytes = packetBuffer.readableBytes())
    }

    fun encode(registration: PacketRegistry.Registration, packet: GamePacket): ByteArray {
        val buffer = Unpooled.buffer()
        @Suppress("UNCHECKED_CAST")
        (registration.codec as GamePacketCodec<GamePacket>).encode(packet, GamePacketBuilder(buffer))
        return ByteBufUtil.getBytes(buffer, 0, buffer.writerIndex(), false)
    }

    fun traceSend(
        channel: Channel,
        localSide: Side,
        registration: PacketRegistry.Registration,
        payload: ByteArray,
        packet: GamePacket
    ) {
        if (!isGolden(Side.SERVER, registration.name)) {
            return
        }

        writeTrace(
            direction = "send",
            channel = channel,
            localSide = localSide,
            registration = registration,
            payload = payload,
            fields = fieldsForPacket(packet),
            packet = packet.toString(),
            unreadBytes = 0
        )
    }

    fun traceReceive(
        channel: Channel,
        remoteSide: Side,
        registration: PacketRegistry.Registration,
        payload: ByteArray,
        packet: GamePacket,
        unreadBytes: Int
    ) {
        if (!isGolden(remoteSide, registration.opcode)) {
            return
        }

        val fields = runCatching { decodeFields(registration, payload) }
            .getOrElse { mapOf("decodeFieldsError" to (it.message ?: it::class.simpleName.orEmpty())) }

        writeTrace(
            direction = "recv",
            channel = channel,
            localSide = if (remoteSide == Side.CLIENT) Side.SERVER else Side.CLIENT,
            registration = registration,
            payload = payload,
            fields = fields,
            packet = packet.toString(),
            unreadBytes = unreadBytes
        )
    }

    private fun decodeFields(registration: PacketRegistry.Registration, payload: ByteArray): Map<String, Any> {
        val codec = registration.codec
        return when (codec) {
            is DynamicGamePacketCodec<*> -> {
                val reader = GamePacketReader(Unpooled.wrappedBuffer(payload))
                codec.readFieldMap(reader)
            }
            else -> {
                val inspectionBuffer = Unpooled.wrappedBuffer(payload)
                val reader = GamePacketReader(inspectionBuffer)
                @Suppress("UNCHECKED_CAST")
                val packet = (codec as GamePacketCodec<GamePacket>).decode(reader)
                fieldsForPacket(packet)
            }
        }
    }

    private fun fieldsForPacket(packet: GamePacket): Map<String, Any> {
        val fields = LinkedHashMap<String, Any>()
        when (packet) {
            is VarpLarge -> {
                fields["value"] = packet.value
                fields["id"] = packet.id
            }
            is VarpSmall -> {
                fields["id"] = packet.id
                fields["value"] = packet.value
            }
            is IfOpenTop -> {
                fields["xtea0"] = 0
                fields["xtea1"] = 0
                fields["xtea2"] = 0
                fields["id"] = packet.id
                fields["xtea3"] = 0
                fields["bool"] = 0
            }
            is IfOpenSub -> {
                fields["xtea0"] = 0
                fields["parent"] = packet.parent.hash
                fields["xtea1"] = 0
                fields["xtea2"] = 0
                fields["flag"] = if (packet.flag) 1 else 0
                fields["id"] = packet.id
                fields["xtea3"] = 0
            }
            is RunClientScript -> {
                fields["desc"] = String(packet.args.map { if (it is String) 's' else 'i' }.toCharArray())
                fields["args"] = packet.args.toList()
                fields["script"] = packet.script
            }
            else -> fields["packet"] = packet.toString()
        }
        return fields
    }

    private fun writeTrace(
        direction: String,
        channel: Channel,
        localSide: Side,
        registration: PacketRegistry.Registration,
        payload: ByteArray,
        fields: Map<String, Any>,
        packet: String,
        unreadBytes: Int
    ) {
        val line = buildString {
            append("timestamp=").append(Instant.now())
            append(" direction=").append(direction)
            append(" localSide=").append(localSide)
            append(" packet=").append(registration.name)
            append(" opcode=").append(registration.opcode)
            append(" size=").append(payload.size)
            append(" unread=").append(unreadBytes)
            append(" remote=").append(channel.remoteAddress())
            append(" fields=").append(fields)
            append(" packetValue=").append(packet)
            append(" hex=").append(ByteBufUtil.hexDump(payload))
        }

        synchronized(traceLock) {
            if (!Files.exists(tracePath.parent)) {
                Files.createDirectories(tracePath.parent)
            }
            Files.writeString(
                tracePath,
                "$line${System.lineSeparator()}",
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            )
        }

        if (unreadBytes > 0) {
            logger.warn { line }
        } else {
            logger.info { line }
        }
    }
}
