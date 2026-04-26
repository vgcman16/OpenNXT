package com.opennxt.net.game.generated.serverprot

import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.generated.GeneratedPacketCatalog
import com.opennxt.net.game.pipeline.DynamicGamePacketCodec
import com.opennxt.net.game.protocol.PacketFieldDeclaration

data class IfOpensubActivePlayerGeneratedPacket(val subInterfaceId: Int, val playerIndex: Int, val reserved0: Int, val targetComponent: Int, val reserved1: Long, val mode: Int, val reserved2: Int) : GamePacket {
    companion object {
        val catalogFields = listOf(
            GeneratedPacketCatalog.Field("subInterfaceId", "ushort", "Int"),
            GeneratedPacketCatalog.Field("playerIndex", "ushort128", "Int"),
            GeneratedPacketCatalog.Field("reserved0", "int", "Int"),
            GeneratedPacketCatalog.Field("targetComponent", "intv1", "Int"),
            GeneratedPacketCatalog.Field("reserved1", "long", "Long"),
            GeneratedPacketCatalog.Field("mode", "ubytec", "Int"),
            GeneratedPacketCatalog.Field("reserved2", "int", "Int")
        )
    }

    class Codec(fields: Array<PacketFieldDeclaration>) : DynamicGamePacketCodec<IfOpensubActivePlayerGeneratedPacket>(fields) {
        override fun fromMap(packet: Map<String, Any>): IfOpensubActivePlayerGeneratedPacket {
            return IfOpensubActivePlayerGeneratedPacket(
                subInterfaceId = packet["subInterfaceId"] as Int,
                playerIndex = packet["playerIndex"] as Int,
                reserved0 = packet["reserved0"] as Int,
                targetComponent = packet["targetComponent"] as Int,
                reserved1 = packet["reserved1"] as Long,
                mode = packet["mode"] as Int,
                reserved2 = packet["reserved2"] as Int
            )
        }

        override fun toMap(packet: IfOpensubActivePlayerGeneratedPacket): Map<String, Any> = linkedMapOf(
                "subInterfaceId" to packet.subInterfaceId,
                "playerIndex" to packet.playerIndex,
                "reserved0" to packet.reserved0,
                "targetComponent" to packet.targetComponent,
                "reserved1" to packet.reserved1,
                "mode" to packet.mode,
                "reserved2" to packet.reserved2
        )
    }
}
