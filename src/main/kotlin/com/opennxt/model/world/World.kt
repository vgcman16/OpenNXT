package com.opennxt.model.world

import com.opennxt.model.entity.EntityList
import com.opennxt.model.entity.PlayerEntity
import com.opennxt.model.lobby.LobbyPlayer
import com.opennxt.model.tick.Tickable
import mu.KotlinLogging
import java.util.concurrent.ConcurrentLinkedQueue

class World : Tickable {
    private val logger = KotlinLogging.logger { }

    private val playerEntities = EntityList<PlayerEntity>(2000)
    private val players = HashSet<WorldPlayer>()

    private val toAdd = ConcurrentLinkedQueue<WorldPlayer>()

    private fun removePlayer(player: WorldPlayer, reason: String, closeChannel: Boolean = false) {
        logger.info { "Removing world player ${player.name}: $reason" }
        players -= player
        playerEntities.remove(player.entity)
        if (closeChannel && player.client.channel.isOpen) {
            player.client.channel.close()
        }
    }

    override fun tick() {
        while (true) {
            val player = toAdd.poll() ?: break
            try {
                players
                    .filter { existing -> existing.name.equals(player.name, ignoreCase = true) }
                    .toList()
                    .forEach { existing ->
                        removePlayer(
                            existing,
                            reason = "replaced by a newer world login for the same username",
                            closeChannel = true
                        )
                    }

                players += player
                if (!playerEntities.add(player.entity)) {
                    logger.warn { "Failed to allocate entity slot for world player ${player.name}" }
                    players -= player
                    player.client.channel.close()
                    continue
                }
                player.added()
            } catch (e: Exception) {
                logger.error(e) { "Failed to bootstrap world player ${player.name}" }
                players -= player
                playerEntities.remove(player.entity)
                player.client.channel.close()
            }
        }

        players.toList().forEach { player ->
            if (player.client.channel.isActive) {
                return@forEach
            }

            removePlayer(player, reason = "channel became inactive")
        }

        players.toList().forEach { player ->
            try {
                player.handleIncomingPackets()
                player.tick()
                player.client.flush()
            } catch (e: Exception) {
                logger.error(e) { "World tick failed for ${player.name}" }
                players -= player
                playerEntities.remove(player.entity)
                player.client.channel.close()
            }
        }
    }

    fun getPlayer(index: Int): PlayerEntity? = playerEntities[index]

    fun addPlayer(player: WorldPlayer) {
        logger.info { "Queueing world player ${player.name}" }
        toAdd += player
    }
}
