package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class UpdateStatGeneratedPacket(val stat: Int, val level: Int, val experience: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("stat", "ubyte", "Int"),
            GeneratedPacketCatalog.Field("level", "u128byte", "Int"),
            GeneratedPacketCatalog.Field("experience", "int", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<UpdateStatGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): UpdateStatGeneratedPacket {
            return UpdateStatGeneratedPacket(
                stat = packet["stat"] as Int,
                level = packet["level"] as Int,
                experience = packet["experience"] as Int
            )
        }

        override fun toMap(packet: UpdateStatGeneratedPacket): Map<String, Any> = linkedMapOf(
                "stat" to packet.stat,
                "level" to packet.level,
                "experience" to packet.experience
        )
    }
}
