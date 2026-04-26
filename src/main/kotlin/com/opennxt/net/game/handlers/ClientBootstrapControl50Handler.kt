package com.opennxt.net.game.handlers

import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.game.clientprot.ClientBootstrapControl50
import com.opennxt.net.game.pipeline.GamePacketHandler

object ClientBootstrapControl50Handler : GamePacketHandler<WorldPlayer, ClientBootstrapControl50> {
    override fun handle(context: WorldPlayer, packet: ClientBootstrapControl50) {
        context.handleClientBootstrapControl50(packet)
    }
}
