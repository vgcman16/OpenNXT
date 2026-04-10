package com.opennxt.net

import com.google.gson.JsonParser
import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.config.ServerConfig
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.game.protocol.ProtocolInformation
import com.opennxt.net.proxy.UnidentifiedPacket
import com.opennxt.net.proxy.ProxyChannelAttributes
import io.netty.buffer.Unpooled
import io.netty.channel.embedded.EmbeddedChannel
import kotlin.io.path.createTempDirectory
import kotlin.io.path.readLines
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs

class ConnectedClientBootstrapCaptureTest {
    private val packetCaptureProperty = "opennxt.bootstrap.packet.capture.path"
    private val traceProperty = "opennxt.bootstrap.trace.path"

    @BeforeTest
    fun setUp() {
        OpenNXT.config = ServerConfig().apply {
            build = 947
        }
        OpenNXT.protocol = ProtocolInformation(Constants.PROT_PATH.resolve("947"))
        OpenNXT.protocol.load()
    }

    @AfterTest
    fun tearDown() {
        System.clearProperty(packetCaptureProperty)
        System.clearProperty(traceProperty)
    }

    @Test
    fun `captures opcode 28 payload hex and entry count`() {
        val tempDir = createTempDirectory("bootstrap-capture-28")
        val capturePath = tempDir.resolve("world-bootstrap-packets.jsonl")
        val tracePath = tempDir.resolve("world-bootstrap-raw.log")
        System.setProperty(packetCaptureProperty, capturePath.toString())
        System.setProperty(traceProperty, tracePath.toString())

        val channel = EmbeddedChannel()
        channel.attr(ProxyChannelAttributes.USERNAME).set("capture-user")
        channel.attr(ProxyChannelAttributes.PLAYER_INDEX).set(321)
        val client = ConnectedClient(Side.CLIENT, channel)
        client.currentBootstrapStage = "capture-stage"

        client.receive(OpcodeWithBuffer(28, Unpooled.wrappedBuffer(byteArrayOf(0x02, 0xAA.toByte(), 0xBB.toByte()))))

        val lines = capturePath.readLines()
        assertEquals(1, lines.size)
        val record = JsonParser.parseString(lines.single()).asJsonObject
        assertEquals(28, record["opcode"].asInt)
        assertEquals("CLIENT_BOOTSTRAP_BLOB_28", record["packet"].asString)
        assertEquals(3, record["payloadSize"].asInt)
        assertEquals("02aabb", record["payloadHex"].asString)
        assertEquals("capture-user", record["username"].asString)
        assertEquals(321, record["playerIndex"].asInt)
        assertEquals(2, record["decodeSummary"].asJsonObject["entryCount"].asInt)
    }

    @Test
    fun `captures fixed bootstrap controls with exact hex and values`() {
        val tempDir = createTempDirectory("bootstrap-capture-fixed")
        val capturePath = tempDir.resolve("world-bootstrap-packets.jsonl")
        val tracePath = tempDir.resolve("world-bootstrap-raw.log")
        System.setProperty(packetCaptureProperty, capturePath.toString())
        System.setProperty(traceProperty, tracePath.toString())

        val channel = EmbeddedChannel()
        val client = ConnectedClient(Side.CLIENT, channel)
        client.currentBootstrapStage = "capture-stage"

        client.receive(OpcodeWithBuffer(50, Unpooled.wrappedBuffer(byteArrayOf(0x12, 0x34, 0x56, 0x78))))
        client.receive(OpcodeWithBuffer(82, Unpooled.wrappedBuffer(byteArrayOf(0x01, 0x02, 0x03))))

        val records = capturePath.readLines().map { JsonParser.parseString(it).asJsonObject }
        assertEquals(listOf(50, 82), records.map { it["opcode"].asInt })
        assertEquals("12345678", records[0]["payloadHex"].asString)
        assertEquals(305419896L, records[0]["decodeSummary"].asJsonObject["value"].asLong)
        assertEquals("010203", records[1]["payloadHex"].asString)
        assertEquals(66051, records[1]["decodeSummary"].asJsonObject["value"].asInt)
    }

    @Test
    fun `falls back to unidentified packet on social state decode failure`() {
        val channel = EmbeddedChannel()
        val client = ConnectedClient(Side.CLIENT, channel).apply {
            currentBootstrapStage = "social-state"
            processUnidentifiedPackets = true
        }

        client.receive(OpcodeWithBuffer(56, Unpooled.wrappedBuffer(byteArrayOf(1, 1))))

        val packet = assertIs<UnidentifiedPacket>(client.incomingQueue.poll())
        try {
            assertEquals(56, packet.packet.opcode)
            assertEquals(2, packet.packet.buf.readableBytes())
            val bytes = ByteArray(packet.packet.buf.readableBytes())
            packet.packet.buf.getBytes(packet.packet.buf.readerIndex(), bytes)
            assertEquals(listOf(1.toByte(), 1.toByte()), bytes.toList())
        } finally {
            packet.packet.buf.release()
        }
    }
}
