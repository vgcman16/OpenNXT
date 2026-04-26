package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ClientSetvarcstrSmallGeneratedPacket(val value: String, val id: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("value", "string", "String"),
            GeneratedPacketCatalog.Field("id", "ushort", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ClientSetvarcstrSmallGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ClientSetvarcstrSmallGeneratedPacket {
            return ClientSetvarcstrSmallGeneratedPacket(
                value = packet["value"] as String,
                id = packet["id"] as Int
            )
        }

        override fun toMap(packet: ClientSetvarcstrSmallGeneratedPacket): Map<String, Any> = linkedMapOf(
                "value" to packet.value,
                "id" to packet.id
        )
    }
}
