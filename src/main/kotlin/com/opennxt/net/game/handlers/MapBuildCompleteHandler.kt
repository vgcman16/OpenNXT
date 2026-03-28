package com.opennxt.net.game.handlers

import com.opennxt.model.world.WorldPlayer
import com.opennxt.net.game.clientprot.MapBuildComplete
import com.opennxt.net.game.pipeline.GamePacketHandler
import mu.KotlinLogging

object MapBuildCompleteHandler : GamePacketHandler<WorldPlayer, MapBuildComplete> {
    private val logger = KotlinLogging.logger { }

    override fun handle(context: WorldPlayer, packet: MapBuildComplete) {
        logger.info { "Received MAP_BUILD_COMPLETE for ${context.name}" }
        context.client.traceBootstrap("world-map-build-complete name=${context.name}")
        context.awaitingMapBuildComplete = false
        context.completeDeferredBootstrap()
    }
}
