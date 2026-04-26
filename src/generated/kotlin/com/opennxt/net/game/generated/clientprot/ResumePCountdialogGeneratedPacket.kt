package com.opennxt.net.game.generated.clientprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class ResumePCountdialogGeneratedPacket(val count: Long) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("count", "long", "Long")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<ResumePCountdialogGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): ResumePCountdialogGeneratedPacket {
            return ResumePCountdialogGeneratedPacket(
                count = packet["count"] as Long
            )
        }

        override fun toMap(packet: ResumePCountdialogGeneratedPacket): Map<String, Any> = linkedMapOf(
                "count" to packet.count
        )
    }
}
