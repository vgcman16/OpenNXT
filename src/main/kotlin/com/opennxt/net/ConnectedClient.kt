package com.opennxt.net

import com.opennxt.model.proxy.PacketDumper
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.golden.GoldenPacketSupport
import com.opennxt.net.game.pipeline.GamePacketCodec
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.proxy.ProxyChannelAttributes
import com.opennxt.net.proxy.UnidentifiedPacket
import io.netty.buffer.ByteBufUtil
import io.netty.buffer.Unpooled
import io.netty.channel.Channel
import mu.KotlinLogging
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

    val logger = KotlinLogging.logger { }

    val incomingQueue = ConcurrentLinkedQueue<GamePacket>()

    var initedPlayerList = false
    @Volatile var currentBootstrapStage: String? = null
    @Volatile var lastCompletedBootstrapStage: String? = null
    val completedBootstrapStages = CopyOnWriteArrayList<String>()

    fun receive(pair: OpcodeWithBuffer) {
        try {
            dumper?.dump(pair.opcode, pair.buf)

            val registration = PacketRegistry.getRegistration(side, pair.opcode)
            if (registration == null) {
                if (processUnidentifiedPackets)
                    incomingQueue.add(UnidentifiedPacket(OpcodeWithBuffer(pair.opcode, pair.buf.copy())))
                return
            }
            val payloadBytes = ByteBufUtil.getBytes(pair.buf, pair.buf.readerIndex(), pair.buf.readableBytes(), false)

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
            e.printStackTrace()
        } finally {
            pair.buf.release()
        }
    }

    fun write(pair: OpcodeWithBuffer) {
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

            if (side == Side.CLIENT) {
                val bootstrapStage = currentBootstrapStage ?: lastCompletedBootstrapStage ?: "none"
                logger.info {
                    "Sending packet ${registration.name} (${packet::class.simpleName}) " +
                        "to ${channel.remoteAddress()} on opcode ${registration.opcode} " +
                        "[bootstrapStage=$bootstrapStage]"
                }
            }

            val buffer = Unpooled.buffer()
            @Suppress("UNCHECKED_CAST")
            (registration.codec as GamePacketCodec<GamePacket>).encode(packet, GamePacketBuilder(buffer))
            GoldenPacketSupport.traceSend(
                channel = channel,
                localSide = if (side == Side.CLIENT) Side.SERVER else Side.CLIENT,
                registration = registration,
                payload = ByteBufUtil.getBytes(buffer, 0, buffer.writerIndex(), false),
                packet = packet
            )

            channel.write(OpcodeWithBuffer(registration.opcode, buffer))
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    fun flush() {
        channel.flush()
    }
}
