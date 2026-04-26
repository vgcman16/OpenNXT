package com.opennxt.net.game.clientprot

import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.buf.GamePacketReader
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.pipeline.GamePacketCodec

data class ClientBootstrapBlob28(
    val payload: ByteArray,
    val entryCount: Int = if (payload.isNotEmpty()) payload[0].toInt() and 0xFF else 0
) : GamePacket {
    object Codec : GamePacketCodec<ClientBootstrapBlob28> {
        override fun decode(buf: GamePacketReader): ClientBootstrapBlob28 {
            val payload = ByteArray(buf.buffer.readableBytes())
            buf.getBytes(payload)
            return ClientBootstrapBlob28(payload)
        }

        override fun encode(packet: ClientBootstrapBlob28, buf: GamePacketBuilder) {
            buf.putBytes(packet.payload)
        }
    }
}
