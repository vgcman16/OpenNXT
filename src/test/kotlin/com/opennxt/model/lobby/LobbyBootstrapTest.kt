package com.opennxt.model.lobby

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.config.ServerConfig
import com.opennxt.net.ConnectedClient
import com.opennxt.net.Side
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.clientprot.WorldlistFetch
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.game.protocol.ProtocolInformation
import com.opennxt.net.game.serverprot.WorldListFetchReply
import com.opennxt.net.game.handlers.WorldlistFetchHandler
import io.netty.channel.embedded.EmbeddedChannel
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class LobbyBootstrapTest {
    @BeforeTest
    fun loadProtocol() {
        OpenNXT.config = ServerConfig().apply {
            build = 946
            lobbyBootstrap = ServerConfig.LobbyBootstrap(
                sendDefaultVarps = true,
                openRootInterface = true,
                openPrimaryChild814 = true,
                openAlternateChild1322 = true,
                sendPrimaryVarcLarge2771 = true,
                sendPrimaryVarcSmall3496 = true,
                sendPrimaryVarcString2508 = true,
                sendPrimaryClientScript10936 = true
            )
        }
        OpenNXT.protocol = ProtocolInformation(Constants.PROT_PATH.resolve("946"))
        OpenNXT.protocol.load()
    }

    @Test
    fun `lobby bootstrap records ordered stages and emits golden packets`() {
        val channel = EmbeddedChannel()
        val client = ConnectedClient(Side.CLIENT, channel)
        val player = LobbyPlayer(client, "golden-bootstrap")

        player.added()
        client.flush()

        assertEquals(
            listOf(
                "reset",
                "default-varps",
                "varcs",
                "secondary-varcs",
                "runclientscript",
                "root-interface",
                "child-interfaces",
                "news-scripts",
                "social-state"
            ),
            client.completedBootstrapStages.toList()
        )
        assertEquals("social-state", client.lastCompletedBootstrapStage)

        val outboundNames = mutableListOf<String>()
        while (true) {
            val outbound = channel.readOutbound<OpcodeWithBuffer>() ?: break
            try {
                outboundNames += PacketRegistry.getRegistration(Side.SERVER, outbound.opcode)?.name ?: "unknown"
            } finally {
                outbound.buf.release()
            }
        }

        assertTrue(outboundNames.contains("RESET_CLIENT_VARCACHE"))
        assertTrue(outboundNames.contains("VARP_SMALL"))
        assertTrue(outboundNames.contains("VARP_LARGE"))
        assertTrue(outboundNames.contains("CLIENT_SETVARC_LARGE"))
        assertTrue(outboundNames.contains("CLIENT_SETVARC_SMALL"))
        assertTrue(outboundNames.contains("CLIENT_SETVARCSTR_SMALL"))
        assertTrue(outboundNames.contains("RUNCLIENTSCRIPT"))
        assertTrue(outboundNames.contains("IF_OPENTOP"))
        assertTrue(outboundNames.count { it == "IF_OPENSUB" } >= 2)
    }

    @Test
    fun `lobby world list fetch falls back to configured compatibility opcode when reply mapping is missing`() {
        OpenNXT.config.lobbyBootstrap =
            OpenNXT.config.lobbyBootstrap.copy(compatWorldlistFetchReplyOpcode = 154)

        val channel = EmbeddedChannel()
        val client = ConnectedClient(Side.CLIENT, channel)
        val player = LobbyPlayer(client, "worldlist-compat")

        assertNull(PacketRegistry.getRegistration(Side.SERVER, WorldListFetchReply::class))

        WorldlistFetchHandler.handle(player, WorldlistFetch(-1))
        client.flush()

        val outbound = generateSequence { channel.readOutbound<OpcodeWithBuffer>() }.toList()
        assertTrue(outbound.isNotEmpty(), "Expected a compatibility world list reply to be emitted")
        try {
            assertTrue(outbound.all { it.opcode == 154 }, "Expected all world list reply chunks to use compat opcode 154")
            assertTrue(outbound.any { it.buf.readableBytes() > 0 }, "Expected compatibility world list reply payload bytes")
        } finally {
            outbound.forEach { it.buf.release() }
        }
    }
}
