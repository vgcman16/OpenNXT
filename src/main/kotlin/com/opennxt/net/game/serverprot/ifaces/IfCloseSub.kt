package com.opennxt.net.game.serverprot.ifaces

import com.opennxt.model.InterfaceHash
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfCloseSub(val parent: InterfaceHash) : GamePacket {
    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfCloseSub>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfCloseSub {
            return IfCloseSub(InterfaceHash(packet["parent"] as Int))
        }

        override fun toMap(packet: IfCloseSub): Map<String, Any> = mapOf(
            "parent" to packet.parent.hash
        )
    }
}
