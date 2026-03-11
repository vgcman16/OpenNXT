package com.opennxt.model.lobby

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.config.ServerConfig
import com.opennxt.net.ConnectedClient
import com.opennxt.net.Side
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.game.protocol.ProtocolInformation
import io.netty.channel.embedded.EmbeddedChannel
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
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
            listOf("reset", "default-varps", "varcs", "runclientscript", "root-interface", "child-interfaces"),
            client.completedBootstrapStages.toList()
        )
        assertEquals("child-interfaces", client.lastCompletedBootstrapStage)

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
}
