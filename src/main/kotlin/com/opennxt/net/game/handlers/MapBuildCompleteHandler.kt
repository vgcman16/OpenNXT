package com.opennxt.net.game.handlers

import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.game.clientprot.MapBuildComplete
import com.opennxt.net.game.pipeline.GamePacketHandler

object MapBuildCompleteHandler : GamePacketHandler<WorldPlayer, MapBuildComplete> {
    override fun handle(context: WorldPlayer, packet: MapBuildComplete) {
        context.awaitingMapBuildComplete = false
    }
}
