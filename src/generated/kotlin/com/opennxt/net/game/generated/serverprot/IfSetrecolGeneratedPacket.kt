package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSetrecolGeneratedPacket(val value0: Int, val value1: Int, val value2: Int, val value3: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("value0", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("value1", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("value2", "ubytec", "Int"),
            GeneratedPacketCatalog.Field("value3", "intle", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSetrecolGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSetrecolGeneratedPacket {
            return IfSetrecolGeneratedPacket(
                value0 = packet["value0"] as Int,
                value1 = packet["value1"] as Int,
                value2 = packet["value2"] as Int,
                value3 = packet["value3"] as Int
            )
        }

        override fun toMap(packet: IfSetrecolGeneratedPacket): Map<String, Any> = linkedMapOf(
                "value0" to packet.value0,
                "value1" to packet.value1,
                "value2" to packet.value2,
                "value3" to packet.value3
        )
    }
}
