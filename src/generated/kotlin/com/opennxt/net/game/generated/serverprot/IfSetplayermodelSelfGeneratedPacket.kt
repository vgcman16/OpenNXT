package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSetplayermodelSelfGeneratedPacket(val component: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("component", "intv2", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSetplayermodelSelfGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSetplayermodelSelfGeneratedPacket {
            return IfSetplayermodelSelfGeneratedPacket(
                component = packet["component"] as Int
            )
        }

        override fun toMap(packet: IfSetplayermodelSelfGeneratedPacket): Map<String, Any> = linkedMapOf(
                "component" to packet.component
        )
    }
}
