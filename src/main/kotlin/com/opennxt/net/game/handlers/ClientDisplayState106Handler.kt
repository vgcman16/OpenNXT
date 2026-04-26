package com.opennxt.net.game.handlers

import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.game.clientprot.ClientDisplayState106
import com.opennxt.net.game.pipeline.GamePacketHandler

object ClientDisplayState106Handler : GamePacketHandler<WorldPlayer, ClientDisplayState106> {
    override fun handle(context: WorldPlayer, packet: ClientDisplayState106) {
        context.handleClientDisplayState106(packet)
    }
}
