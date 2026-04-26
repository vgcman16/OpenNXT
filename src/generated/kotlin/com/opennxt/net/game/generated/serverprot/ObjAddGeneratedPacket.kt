package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ObjAddGeneratedPacket(val count: Int, val packedCoord: Int, val id: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("count", "ushortle128", "Int"),
            GeneratedPacketCatalog.Field("packedCoord", "ubytec", "Int"),
            GeneratedPacketCatalog.Field("id", "ushort128", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ObjAddGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ObjAddGeneratedPacket {
            return ObjAddGeneratedPacket(
                count = packet["count"] as Int,
                packedCoord = packet["packedCoord"] as Int,
                id = packet["id"] as Int
            )
        }

        override fun toMap(packet: ObjAddGeneratedPacket): Map<String, Any> = linkedMapOf(
                "count" to packet.count,
                "packedCoord" to packet.packedCoord,
                "id" to packet.id
        )
    }
}
