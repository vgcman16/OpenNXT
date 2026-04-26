package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSetcolourGeneratedPacket(val component: Int, val colour: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("component", "intv1", "Int"),
            GeneratedPacketCatalog.Field("colour", "ushort128", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSetcolourGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSetcolourGeneratedPacket {
            return IfSetcolourGeneratedPacket(
                component = packet["component"] as Int,
                colour = packet["colour"] as Int
            )
        }

        override fun toMap(packet: IfSetcolourGeneratedPacket): Map<String, Any> = linkedMapOf(
                "component" to packet.component,
                "colour" to packet.colour
        )
    }
}
