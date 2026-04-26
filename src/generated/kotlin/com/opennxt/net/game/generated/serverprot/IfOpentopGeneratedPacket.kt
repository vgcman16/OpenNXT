package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfOpentopGeneratedPacket(val xtea0: Int, val xtea1: Int, val xtea2: Int, val id: Int, val xtea3: Int, val bool: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("xtea0", "int", "Int"),
            GeneratedPacketCatalog.Field("xtea1", "int", "Int"),
            GeneratedPacketCatalog.Field("xtea2", "int", "Int"),
            GeneratedPacketCatalog.Field("id", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("xtea3", "int", "Int"),
            GeneratedPacketCatalog.Field("bool", "ubyte", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfOpentopGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfOpentopGeneratedPacket {
            return IfOpentopGeneratedPacket(
                xtea0 = packet["xtea0"] as Int,
                xtea1 = packet["xtea1"] as Int,
                xtea2 = packet["xtea2"] as Int,
                id = packet["id"] as Int,
                xtea3 = packet["xtea3"] as Int,
                bool = packet["bool"] as Int
            )
        }

        override fun toMap(packet: IfOpentopGeneratedPacket): Map<String, Any> = linkedMapOf(
                "xtea0" to packet.xtea0,
                "xtea1" to packet.xtea1,
                "xtea2" to packet.xtea2,
                "id" to packet.id,
                "xtea3" to packet.xtea3,
                "bool" to packet.bool
        )
    }
}
