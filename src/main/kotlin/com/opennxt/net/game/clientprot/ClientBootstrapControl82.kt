package com.opennxt.net.game.clientprot

import com.opennxt.net.buf.DataType
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.pipeline.GamePacketCodec

data class ClientBootstrapControl82(val value: Int) : GamePacket {
    object Codec : GamePacketCodec<ClientBootstrapControl82> {
        override fun decode(buf: GamePacketReader): ClientBootstrapControl82 =
            ClientBootstrapControl82(buf.getUnsigned(DataType.MEDIUM).toInt())

        override fun encode(packet: ClientBootstrapControl82, buf: GamePacketBuilder) {
            buf.put(DataType.MEDIUM, packet.value)
        }
    }
}
