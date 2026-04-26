package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfOpensubGeneratedPacket(val xtea0: Int, val parent: Int, val xtea1: Int, val xtea2: Int, val flag: Int, val id: Int, val xtea3: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("xtea0", "int", "Int"),
            GeneratedPacketCatalog.Field("parent", "intle", "Int"),
            GeneratedPacketCatalog.Field("xtea1", "int", "Int"),
            GeneratedPacketCatalog.Field("xtea2", "int", "Int"),
            GeneratedPacketCatalog.Field("flag", "u128byte", "Int"),
            GeneratedPacketCatalog.Field("id", "ushortle128", "Int"),
            GeneratedPacketCatalog.Field("xtea3", "int", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfOpensubGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfOpensubGeneratedPacket {
            return IfOpensubGeneratedPacket(
                xtea0 = packet["xtea0"] as Int,
                parent = packet["parent"] as Int,
                xtea1 = packet["xtea1"] as Int,
                xtea2 = packet["xtea2"] as Int,
                flag = packet["flag"] as Int,
                id = packet["id"] as Int,
                xtea3 = packet["xtea3"] as Int
            )
        }

        override fun toMap(packet: IfOpensubGeneratedPacket): Map<String, Any> = linkedMapOf(
                "xtea0" to packet.xtea0,
                "parent" to packet.parent,
                "xtea1" to packet.xtea1,
                "xtea2" to packet.xtea2,
                "flag" to packet.flag,
                "id" to packet.id,
                "xtea3" to packet.xtea3
        )
    }
}
