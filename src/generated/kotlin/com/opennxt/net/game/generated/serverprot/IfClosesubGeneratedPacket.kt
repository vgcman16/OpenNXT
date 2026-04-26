package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfClosesubGeneratedPacket(val parent: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("parent", "int", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfClosesubGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfClosesubGeneratedPacket {
            return IfClosesubGeneratedPacket(
                parent = packet["parent"] as Int
            )
        }

        override fun toMap(packet: IfClosesubGeneratedPacket): Map<String, Any> = linkedMapOf(
                "parent" to packet.parent
        )
    }
}
