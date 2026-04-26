package com.opennxt.net.game.clientprot

import com.opennxt.net.buf.DataType
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.pipeline.GamePacketCodec

data class ClientBootstrapControl50(val value: Int) : GamePacket {
    object Codec : GamePacketCodec<ClientBootstrapControl50> {
        override fun decode(buf: GamePacketReader): ClientBootstrapControl50 =
            ClientBootstrapControl50(buf.getUnsigned(DataType.INT).toInt())

        override fun encode(packet: ClientBootstrapControl50, buf: GamePacketBuilder) {
            buf.put(DataType.INT, packet.value)
        }
    }
}
