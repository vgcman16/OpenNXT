package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSeteventsGeneratedPacket(val mask: Int, val fromSlot: Int, val parent: Int, val toSlot: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("mask", "intle", "Int"),
            GeneratedPacketCatalog.Field("fromSlot", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("parent", "intv2", "Int"),
            GeneratedPacketCatalog.Field("toSlot", "ushortle128", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSeteventsGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSeteventsGeneratedPacket {
            return IfSeteventsGeneratedPacket(
                mask = packet["mask"] as Int,
                fromSlot = packet["fromSlot"] as Int,
                parent = packet["parent"] as Int,
                toSlot = packet["toSlot"] as Int
            )
        }

        override fun toMap(packet: IfSeteventsGeneratedPacket): Map<String, Any> = linkedMapOf(
                "mask" to packet.mask,
                "fromSlot" to packet.fromSlot,
                "parent" to packet.parent,
                "toSlot" to packet.toSlot
        )
    }
}
