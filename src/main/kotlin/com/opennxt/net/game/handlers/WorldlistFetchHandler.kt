package com.opennxt.net.game.handlers

import com.opennxt.OpenNXT
import com.opennxt.model.lobby.LobbyPlayer
import com.opennxt.net.Side
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.clientprot.WorldlistFetch
import com.opennxt.net.game.pipeline.GamePacketHandler
import com.opennxt.net.game.serverprot.WorldListFetchReply
import mu.KotlinLogging

object WorldlistFetchHandler : GamePacketHandler<LobbyPlayer, WorldlistFetch> {
    private val logger = KotlinLogging.logger { }

    override fun handle(context: LobbyPlayer, packet: WorldlistFetch) {
        val registration = PacketRegistry.getRegistration(Side.SERVER, WorldListFetchReply::class)
        if (registration != null) {
            logger.info {
                "Handling lobby world list fetch for ${context.name}: checksum=${packet.checksum}, opcode=${registration.opcode}"
            }
            context.client.traceBootstrap(
                "lobby-worldlist-fetch name=${context.name} checksum=${packet.checksum} mode=registered opcode=${registration.opcode}"
            )
            context.worldList.handleRequest(packet.checksum, context.client)
            return
        }

        val compatOpcode = OpenNXT.config.lobbyBootstrap.compatWorldlistFetchReplyOpcode
        if (compatOpcode >= 0) {
            logger.info {
                "Handling lobby world list fetch for ${context.name} via compatibility reply opcode $compatOpcode " +
                    "(checksum=${packet.checksum})"
            }
            context.client.traceBootstrap(
                "lobby-worldlist-fetch name=${context.name} checksum=${packet.checksum} mode=compat opcode=$compatOpcode"
            )
            context.worldList.handleCompatRequest(packet.checksum, context.client, compatOpcode)
            context.client.traceBootstrap(
                "lobby-send-worldlist-fetch-reply-compat name=${context.name} opcode=$compatOpcode checksum=${packet.checksum}"
            )
            return
        }

        logger.warn {
            "Dropping lobby world list fetch for ${context.name}: checksum=${packet.checksum}, " +
                "no registered WORLDLIST_FETCH_REPLY opcode and no compatWorldlistFetchReplyOpcode configured"
        }
        context.client.traceBootstrap(
            "lobby-drop-worldlist-fetch-reply name=${context.name} checksum=${packet.checksum} reason=no-reply-opcode"
        )
    }
}
