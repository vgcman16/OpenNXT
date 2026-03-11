package com.opennxt.net.game.golden

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.config.ServerConfig
import com.opennxt.model.InterfaceHash
import com.opennxt.net.RSChannelAttributes
import com.opennxt.net.Side
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.pipeline.GamePacketEncoder
import com.opennxt.net.game.pipeline.GamePacketFraming
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.game.protocol.ProtocolInformation
import com.opennxt.net.game.serverprot.RunClientScript
import com.opennxt.net.game.serverprot.ifaces.IfOpenSub
import com.opennxt.net.game.serverprot.ifaces.IfOpenTop
import com.opennxt.net.game.serverprot.variables.VarpLarge
import com.opennxt.net.game.serverprot.variables.VarpSmall
import com.opennxt.util.ISAACCipher
import io.netty.buffer.ByteBufUtil
import io.netty.buffer.Unpooled
import io.netty.channel.embedded.EmbeddedChannel
import kotlin.io.path.createDirectories
import kotlin.io.path.writeText
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

class GoldenPacketProtocolTest {
    @BeforeTest
    fun loadProtocol() {
        OpenNXT.config = ServerConfig().apply { build = 946 }
        OpenNXT.protocol = ProtocolInformation(Constants.PROT_PATH.resolve("946"))
        OpenNXT.protocol.load()
    }

    @Test
    fun `round trips the golden packets with exact 946 payload bytes`() {
        val cases = listOf(
            VarpLarge(id = 0x3456, value = 0x12345678) to hex("123456783456"),
            VarpSmall(id = 0x3456, value = 0xAB) to hex("3456ab"),
            IfOpenTop(id = 0x3456) to hex("00000000000000000000000056340000000000"),
            IfOpenSub(id = 0x3456, flag = true, parent = InterfaceHash(0x11223344)) to
                hex("000000004433221100000000000000007fd63400000000"),
            RunClientScript(script = 0x11223344, args = arrayOf(0x01020304, "abc", 0x05060708)) to
                hex("6973690005060708616263000102030411223344")
        )

        cases.forEach { (packet, expectedBytes) ->
            val registration = PacketRegistry.getRegistration(Side.SERVER, packet::class)
                ?: error("Missing registration for ${packet::class.simpleName}")
            val encoded = GoldenPacketSupport.encode(registration, packet)
            val inspection = GoldenPacketSupport.inspect(registration, encoded)

            assertContentEquals(expectedBytes, encoded, "Unexpected 946 payload for ${registration.name}")
            assertEquals(packet, inspection.packet, "Round-trip packet mismatch for ${registration.name}")
            assertEquals(0, inspection.unreadBytes, "Expected full payload consumption for ${registration.name}")
        }
    }

    @Test
    fun `frames golden opcodes with correct fixed and variable sizes`() {
        val cases = listOf(
            51 to hex("123456783456"),
            72 to hex("3456ab"),
            126 to hex("00000000000000000000000056340000000000"),
            38 to hex("000000004433221100000000000000007fd63400000000"),
            141 to hex("6973690005060708616263000102030411223344")
        )

        cases.forEach { (opcode, payload) ->
            val decoded = frameServerPacket(opcode, payload)
            try {
                assertEquals(opcode, decoded.opcode)
                assertContentEquals(payload, ByteBufUtil.getBytes(decoded.buf))
            } finally {
                decoded.buf.release()
            }
        }
    }

    @Test
    fun `build 946 refuses a golden packet fallback to 919`() {
        val tempProtocol = kotlin.io.path.createTempDirectory("opennxt-946-golden-test")
        tempProtocol.resolve("clientProt").createDirectories()
        tempProtocol.resolve("serverProt").createDirectories()
        tempProtocol.resolve("clientProtNames.toml").writeText("[values]\n")
        tempProtocol.resolve("clientProtSizes.toml").writeText("[values]\n")
        tempProtocol.resolve("serverProtNames.toml").writeText(
            buildString {
                appendLine("[values]")
                GoldenPacketSupport.requiredDefinitions(946, Side.SERVER).forEach { appendLine("${it.opcode} = \"${it.name}\"") }
            }
        )
        tempProtocol.resolve("serverProtSizes.toml").writeText(
            buildString {
                appendLine("[values]")
                GoldenPacketSupport.requiredDefinitions(946, Side.SERVER).forEach { appendLine("${it.opcode} = ${it.size}") }
            }
        )
        GoldenPacketSupport.requiredDefinitions(946, Side.SERVER)
            .filter { it.fields != null && it.name != "IF_OPENSUB" }
            .forEach { definition ->
                tempProtocol.resolve("serverProt").resolve("${definition.name}.txt")
                    .writeText(definition.fields!!.joinToString(separator = "\n", postfix = "\n"))
            }

        OpenNXT.config = ServerConfig().apply { build = 946 }
        val exception = assertFailsWith<IllegalStateException> {
            OpenNXT.protocol = ProtocolInformation(tempProtocol)
            OpenNXT.protocol.load()
        }

        assertTrue(exception.message.orEmpty().contains("IF_OPENSUB"))
    }

    private fun frameServerPacket(opcode: Int, payload: ByteArray): OpcodeWithBuffer {
        val seeds = intArrayOf(1, 2, 3, 4)

        val encoderChannel = EmbeddedChannel(GamePacketEncoder()).also {
            it.attr(RSChannelAttributes.SIDE).set(Side.CLIENT)
            it.attr(RSChannelAttributes.OUTGOING_ISAAC).set(ISAACCipher(seeds.copyOf()))
        }
        assertTrue(encoderChannel.writeOutbound(OpcodeWithBuffer(opcode, Unpooled.wrappedBuffer(payload))))
        val framed = encoderChannel.readOutbound<io.netty.buffer.ByteBuf>() ?: error("No framed packet produced")

        val decoderChannel = EmbeddedChannel(GamePacketFraming()).also {
            it.attr(RSChannelAttributes.SIDE).set(Side.SERVER)
            it.attr(RSChannelAttributes.INCOMING_ISAAC).set(ISAACCipher(seeds.copyOf()))
        }
        assertTrue(decoderChannel.writeInbound(framed))
        val decoded = decoderChannel.readInbound<OpcodeWithBuffer>() ?: error("No decoded packet produced")
        assertNull(decoderChannel.readInbound<Any>())
        return decoded
    }

    private fun hex(value: String): ByteArray {
        return value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }
}
