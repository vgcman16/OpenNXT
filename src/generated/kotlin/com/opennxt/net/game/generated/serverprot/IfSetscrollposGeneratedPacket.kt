package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSetscrollposGeneratedPacket(val component: Int, val scrollPosition: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("component", "intle", "Int"),
            GeneratedPacketCatalog.Field("scrollPosition", "ushort", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSetscrollposGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSetscrollposGeneratedPacket {
            return IfSetscrollposGeneratedPacket(
                component = packet["component"] as Int,
                scrollPosition = packet["scrollPosition"] as Int
            )
        }

        override fun toMap(packet: IfSetscrollposGeneratedPacket): Map<String, Any> = linkedMapOf(
                "component" to packet.component,
                "scrollPosition" to packet.scrollPosition
        )
    }
}
