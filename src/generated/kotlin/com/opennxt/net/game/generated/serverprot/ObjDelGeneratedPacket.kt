package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ObjDelGeneratedPacket(val packedCoord: Int, val id: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("packedCoord", "u128byte", "Int"),
            GeneratedPacketCatalog.Field("id", "ushort", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ObjDelGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ObjDelGeneratedPacket {
            return ObjDelGeneratedPacket(
                packedCoord = packet["packedCoord"] as Int,
                id = packet["id"] as Int
            )
        }

        override fun toMap(packet: ObjDelGeneratedPacket): Map<String, Any> = linkedMapOf(
                "packedCoord" to packet.packedCoord,
                "id" to packet.id
        )
    }
}
