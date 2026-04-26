package com.opennxt.net.game.handlers

import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.game.clientprot.ClientBootstrapBlob28
import com.opennxt.net.game.pipeline.GamePacketHandler

object ClientBootstrapBlob28Handler : GamePacketHandler<WorldPlayer, ClientBootstrapBlob28> {
    override fun handle(context: WorldPlayer, packet: ClientBootstrapBlob28) {
        context.handleClientBootstrapBlob28(packet)
    }
}
