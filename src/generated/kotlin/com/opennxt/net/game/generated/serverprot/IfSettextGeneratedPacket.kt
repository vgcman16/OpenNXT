package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfSettextGeneratedPacket(val text: String, val parent: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("text", "string", "String"),
            GeneratedPacketCatalog.Field("parent", "intle", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfSettextGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfSettextGeneratedPacket {
            return IfSettextGeneratedPacket(
                text = packet["text"] as String,
                parent = packet["parent"] as Int
            )
        }

        override fun toMap(packet: IfSettextGeneratedPacket): Map<String, Any> = linkedMapOf(
                "text" to packet.text,
                "parent" to packet.parent
        )
    }
}
