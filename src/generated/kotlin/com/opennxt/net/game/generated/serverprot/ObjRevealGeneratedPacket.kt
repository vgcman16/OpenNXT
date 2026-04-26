package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ObjRevealGeneratedPacket(val count: Int, val id: Int, val packedCoord: Int, val playerIndex: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("count", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("id", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("packedCoord", "ubyte", "Int"),
            GeneratedPacketCatalog.Field("playerIndex", "ushortle", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ObjRevealGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ObjRevealGeneratedPacket {
            return ObjRevealGeneratedPacket(
                count = packet["count"] as Int,
                id = packet["id"] as Int,
                packedCoord = packet["packedCoord"] as Int,
                playerIndex = packet["playerIndex"] as Int
            )
        }

        override fun toMap(packet: ObjRevealGeneratedPacket): Map<String, Any> = linkedMapOf(
                "count" to packet.count,
                "id" to packet.id,
                "packedCoord" to packet.packedCoord,
                "playerIndex" to packet.playerIndex
        )
    }
}
