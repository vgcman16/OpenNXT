package com.opennxt.net.game.clientprot

import com.opennxt.net.buf.DataType
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.pipeline.GamePacketCodec

data class ClientDisplayState106(
    val mode: Int,
    val width: Int,
    val height: Int,
    val trailingFlag: Int
) : GamePacket {
    object Codec : GamePacketCodec<ClientDisplayState106> {
        override fun decode(buf: GamePacketReader): ClientDisplayState106 =
            ClientDisplayState106(
                mode = buf.getUnsigned(DataType.BYTE).toInt(),
                width = buf.getUnsigned(DataType.SHORT).toInt(),
                height = buf.getUnsigned(DataType.SHORT).toInt(),
                trailingFlag = buf.getUnsigned(DataType.BYTE).toInt()
            )

        override fun encode(packet: ClientDisplayState106, buf: GamePacketBuilder) {
            buf.put(DataType.BYTE, packet.mode)
            buf.put(DataType.SHORT, packet.width)
            buf.put(DataType.SHORT, packet.height)
            buf.put(DataType.BYTE, packet.trailingFlag)
        }
    }
}
