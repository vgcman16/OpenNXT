package com.opennxt.net.proxy.handler

import com.opennxt.model.InterfaceHash
import com.opennxt.net.game.pipeline.GamePacketHandler
import com.opennxt.net.game.serverprot.ifaces.IfOpensubActivePlayer
import com.opennxt.net.proxy.ProxyPlayer

object IfOpensubActivePlayerProxyHandler : GamePacketHandler<ProxyPlayer, IfOpensubActivePlayer> {
    override fun handle(context: ProxyPlayer, packet: IfOpensubActivePlayer) {
        val target = InterfaceHash(packet.targetComponent)
        context.plaintextDumpFile.appendLine(
            "player.interfaces.openActivePlayer(" +
                "subInterfaceId = ${packet.subInterfaceId}, " +
                "component = ${target.component}, " +
                "playerIndex = ${packet.playerIndex}, " +
                "mode = ${packet.mode})"
        )
    }
}
