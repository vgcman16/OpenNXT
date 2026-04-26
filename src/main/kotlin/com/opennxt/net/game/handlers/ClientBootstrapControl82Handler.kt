package com.opennxt.net.game.handlers

import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.game.clientprot.ClientBootstrapControl82
import com.opennxt.net.game.pipeline.GamePacketHandler

object ClientBootstrapControl82Handler : GamePacketHandler<WorldPlayer, ClientBootstrapControl82> {
    override fun handle(context: WorldPlayer, packet: ClientBootstrapControl82) {
        context.handleClientBootstrapControl82(packet)
    }
}
