package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class VarpSmallGeneratedPacket(val id: Int, val value: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("id", "ushort", "Int"),
            GeneratedPacketCatalog.Field("value", "ubyte", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<VarpSmallGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): VarpSmallGeneratedPacket {
            return VarpSmallGeneratedPacket(
                id = packet["id"] as Int,
                value = packet["value"] as Int
            )
        }

        override fun toMap(packet: VarpSmallGeneratedPacket): Map<String, Any> = linkedMapOf(
                "id" to packet.id,
                "value" to packet.value
        )
    }
}
