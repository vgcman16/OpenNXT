package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class VarpLargeGeneratedPacket(val value: Int, val id: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("value", "int", "Int"),
            GeneratedPacketCatalog.Field("id", "ushort", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<VarpLargeGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): VarpLargeGeneratedPacket {
            return VarpLargeGeneratedPacket(
                value = packet["value"] as Int,
                id = packet["id"] as Int
            )
        }

        override fun toMap(packet: VarpLargeGeneratedPacket): Map<String, Any> = linkedMapOf(
                "value" to packet.value,
                "id" to packet.id
        )
    }
}
