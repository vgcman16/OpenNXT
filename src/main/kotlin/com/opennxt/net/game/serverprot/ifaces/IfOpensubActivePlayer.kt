package com.opennxt.net.game.serverprot.ifaces

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfOpensubActivePlayer(
    val subInterfaceId: Int,
    val playerIndex: Int,
    val targetComponent: Int,
    val mode: Int
) : GamePacket {
    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfOpensubActivePlayer>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfOpensubActivePlayer {
            return IfOpensubActivePlayer(
                subInterfaceId = packet["subInterfaceId"] as Int,
                playerIndex = packet["playerIndex"] as Int,
                targetComponent = packet["targetComponent"] as Int,
                mode = packet["mode"] as Int
            )
        }

        override fun toMap(packet: IfOpensubActivePlayer): Map<String, Any> = mapOf(
            "subInterfaceId" to packet.subInterfaceId,
            "playerIndex" to packet.playerIndex,
            "reserved0" to 0,
            "targetComponent" to packet.targetComponent,
            "reserved1" to 0L,
            "mode" to packet.mode,
            "reserved2" to 0
        )
    }
}
