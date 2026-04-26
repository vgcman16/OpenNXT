package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSethideGeneratedPacket(val parent: Int, val hidden: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("parent", "int", "Int"),
            GeneratedPacketCatalog.Field("hidden", "u128byte", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSethideGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSethideGeneratedPacket {
            return IfSethideGeneratedPacket(
                parent = packet["parent"] as Int,
                hidden = packet["hidden"] as Int
            )
        }

        override fun toMap(packet: IfSethideGeneratedPacket): Map<String, Any> = linkedMapOf(
                "parent" to packet.parent,
                "hidden" to packet.hidden
        )
    }
}
