package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ObjCountGeneratedPacket(val packedCoord: Int, val id: Int, val oldCount: Int, val newCount: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("packedCoord", "ubyte", "Int"),
            GeneratedPacketCatalog.Field("id", "ushort", "Int"),
            GeneratedPacketCatalog.Field("oldCount", "ushort", "Int"),
            GeneratedPacketCatalog.Field("newCount", "ushort", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ObjCountGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ObjCountGeneratedPacket {
            return ObjCountGeneratedPacket(
                packedCoord = packet["packedCoord"] as Int,
                id = packet["id"] as Int,
                oldCount = packet["oldCount"] as Int,
                newCount = packet["newCount"] as Int
            )
        }

        override fun toMap(packet: ObjCountGeneratedPacket): Map<String, Any> = linkedMapOf(
                "packedCoord" to packet.packedCoord,
                "id" to packet.id,
                "oldCount" to packet.oldCount,
                "newCount" to packet.newCount
        )
    }
}
