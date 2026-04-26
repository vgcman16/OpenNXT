package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSetplayerheadGeneratedPacket(val component: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("component", "intv1", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSetplayerheadGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSetplayerheadGeneratedPacket {
            return IfSetplayerheadGeneratedPacket(
                component = packet["component"] as Int
            )
        }

        override fun toMap(packet: IfSetplayerheadGeneratedPacket): Map<String, Any> = linkedMapOf(
                "component" to packet.component
        )
    }
}
