package com.opennxt.net.game.generated.clientprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class WorldlistFetchGeneratedPacket(val checksum: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("checksum", "int", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<WorldlistFetchGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): WorldlistFetchGeneratedPacket {
            return WorldlistFetchGeneratedPacket(
                checksum = packet["checksum"] as Int
            )
        }

        override fun toMap(packet: WorldlistFetchGeneratedPacket): Map<String, Any> = linkedMapOf(
                "checksum" to packet.checksum
        )
    }
}
