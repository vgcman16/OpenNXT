package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.options.required
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.config.ServerConfig
import com.opennxt.net.Side
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.golden.GoldenPacketSupport
import com.opennxt.net.game.protocol.ProtocolInformation
import com.opennxt.tools.Tool
import java.io.DataInputStream
import java.io.EOFException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths

class GoldenPacketCompare : Tool(
    "golden-packet-compare",
    "Decodes and re-encodes a 946 golden packet from a proxy dump or Ghidra byte-read note and asserts byte parity"
) {
    private val input by option(help = "Path to a .bin proxy dump or a text file containing hex byte reads").required()
    private val packetName by option(help = "Golden packet name when the input is a raw hex/note file")
    private val occurrence by option(help = "0-based matching occurrence to inspect in a dump").int().default(0)
    private val build by option(help = "Protocol build to load").int().default(946)

    override fun runTool() {
        val inputPath = Paths.get(input)
        check(Files.exists(inputPath)) { "Input path does not exist: $inputPath" }

        OpenNXT.config = ServerConfig().apply { this.build = build }
        OpenNXT.protocol = ProtocolInformation(Constants.PROT_PATH.resolve(build.toString()))
        OpenNXT.protocol.load()

        val sample = if (inputPath.fileName.toString().endsWith(".bin")) {
            readDumpSample(inputPath)
        } else {
            readHexSample(inputPath)
        }

        val registration = PacketRegistry.getRegistration(Side.SERVER, sample.opcode)
            ?: throw IllegalStateException("No registered golden packet for opcode ${sample.opcode}")
        val inspection = GoldenPacketSupport.inspect(registration, sample.payload)
        val reencoded = GoldenPacketSupport.encode(registration, inspection.packet)

        logger.info {
            "Golden packet compare packet=${registration.name} opcode=${registration.opcode} size=${sample.payload.size} " +
                "fields=${inspection.fields} unread=${inspection.unreadBytes}"
        }

        check(inspection.unreadBytes == 0) {
            "Decoded ${registration.name} with ${inspection.unreadBytes} unread byte(s)"
        }
        check(sample.payload.contentEquals(reencoded)) {
            "Re-encoded ${registration.name} does not match input bytes." +
                " input=${sample.payload.toHex()} output=${reencoded.toHex()}"
        }
    }

    private fun readDumpSample(path: Path): Sample {
        val normalizedName = packetName?.uppercase()
        val expectedOpcode = normalizedName?.let {
            GoldenPacketSupport.requiredDefinition(build, Side.SERVER, it)?.opcode
                ?: throw IllegalArgumentException("Unsupported golden packet name '$packetName'")
        }

        DataInputStream(Files.newInputStream(path)).use { input ->
            var matchIndex = 0
            while (true) {
                val opcode = try {
                    input.readLong()
                    input.readUnsignedShort()
                } catch (_: EOFException) {
                    break
                }
                val size = input.readInt()
                val payload = ByteArray(size)
                input.readFully(payload)

                val isMatch = if (expectedOpcode != null) {
                    opcode == expectedOpcode
                } else {
                    GoldenPacketSupport.isGolden(Side.SERVER, opcode)
                }
                if (!isMatch) {
                    continue
                }
                if (matchIndex++ != occurrence) {
                    continue
                }
                return Sample(opcode = opcode, payload = payload)
            }
        }

        throw IllegalStateException(
            "No golden packet match found in $path for packet=${packetName ?: "<first-golden>"} occurrence=$occurrence"
        )
    }

    private fun readHexSample(path: Path): Sample {
        val normalizedName = packetName?.uppercase()
            ?: throw IllegalArgumentException("--packet is required for raw hex and Ghidra note inputs")
        val definition = GoldenPacketSupport.requiredDefinition(build, Side.SERVER, normalizedName)
            ?: throw IllegalArgumentException("Unsupported golden packet name '$packetName'")
        val text = Files.readString(path)
        val bytes = Regex("(?i)\\b[0-9a-f]{2}\\b")
            .findAll(text)
            .map { it.value.toInt(16).toByte() }
            .toList()
            .toByteArray()
        check(bytes.isNotEmpty()) { "No byte reads found in $path" }
        return Sample(opcode = definition.opcode, payload = bytes)
    }

    private data class Sample(
        val opcode: Int,
        val payload: ByteArray
    )

    private fun ByteArray.toHex(): String = joinToString(separator = "") { "%02x".format(it) }
}
