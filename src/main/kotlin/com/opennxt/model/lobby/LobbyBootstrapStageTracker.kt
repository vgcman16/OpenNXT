package com.opennxt.model.lobby

import com.opennxt.net.ConnectedClient
import mu.KotlinLogging

enum class LobbyBootstrapStage(val wireName: String) {
    RESET("reset"),
    DEFAULT_VARPS("default-varps"),
    VARCS("varcs"),
    RUNCLIENTSCRIPT("runclientscript"),
    ROOT_INTERFACE("root-interface"),
    CHILD_INTERFACES("child-interfaces")
}

class LobbyBootstrapStageTracker(
    private val client: ConnectedClient,
    private val playerName: String
) {
    private val logger = KotlinLogging.logger { }

    fun run(stage: LobbyBootstrapStage, block: () -> Unit) {
        logger.info { "Lobby bootstrap stage start for $playerName: ${stage.wireName}" }
        client.currentBootstrapStage = stage.wireName
        try {
            block()
            client.lastCompletedBootstrapStage = stage.wireName
            client.completedBootstrapStages += stage.wireName
            logger.info { "Lobby bootstrap stage complete for $playerName: ${stage.wireName}" }
        } catch (e: Exception) {
            logger.error(e) {
                "Lobby bootstrap stage failed for $playerName at ${stage.wireName} " +
                    "(lastCompleted=${client.lastCompletedBootstrapStage ?: "none"})"
            }
            throw e
        } finally {
            if (client.currentBootstrapStage == stage.wireName) {
                client.currentBootstrapStage = null
            }
        }
    }
}
