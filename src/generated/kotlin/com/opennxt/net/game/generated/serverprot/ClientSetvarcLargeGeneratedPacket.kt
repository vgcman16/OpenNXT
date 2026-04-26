package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ClientSetvarcLargeGeneratedPacket(val id: Int, val value: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("id", "ushortle", "Int"),
            GeneratedPacketCatalog.Field("value", "intv1", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ClientSetvarcLargeGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ClientSetvarcLargeGeneratedPacket {
            return ClientSetvarcLargeGeneratedPacket(
                id = packet["id"] as Int,
                value = packet["value"] as Int
            )
        }

        override fun toMap(packet: ClientSetvarcLargeGeneratedPacket): Map<String, Any> = linkedMapOf(
                "id" to packet.id,
                "value" to packet.value
        )
    }
}
