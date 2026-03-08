package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.opennxt.Constants
import com.opennxt.config.RsaConfig
import com.opennxt.config.TomlConfig
import com.opennxt.filesystem.ChecksumTable
import com.opennxt.filesystem.Container
import com.opennxt.tools.Tool
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.security.MessageDigest

class ChecksumTableDumper : Tool(
    "checksum-table-dumper",
    "Dumps the generated 255/255 checksum tables and signatures for JS5 debugging"
) {
    private val outputDir by option(help = "Directory where the dumped checksum-table files should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("checksum-table").toString())

    override fun runTool() {
        val rsaConfig = TomlConfig.load<RsaConfig>(RsaConfig.DEFAULT_PATH, mustExist = true)
        val baseDir = Paths.get(outputDir)
        Files.createDirectories(baseDir)

        dumpVariant(baseDir, "js5", false, rsaConfig.js5)
        dumpVariant(baseDir, "http", true, rsaConfig.js5)

        logger.info { "Dumped checksum tables to $baseDir" }
    }

    private fun dumpVariant(baseDir: Path, name: String, http: Boolean, keyPair: RsaConfig.RsaKeyPair) {
        val table = ChecksumTable.create(filesystem, http)
        val payload = table.encode(keyPair.modulus, keyPair.exponent)
        val containerBuffer = Container.wrap(payload)
        val containerBytes = ByteArray(containerBuffer.remaining())
        containerBuffer.get(containerBytes)

        val decoded = Container.decode(ByteBuffer.wrap(containerBytes)).data
        val signatureOffset = 1 + table.entries.size * ENTRY_SIZE
        require(decoded.size >= signatureOffset) {
            "Decoded checksum table for $name is too short: ${decoded.size} < $signatureOffset"
        }

        val entriesBytes = decoded.copyOfRange(0, signatureOffset)
        val signatureBytes = decoded.copyOfRange(signatureOffset, decoded.size)

        Files.write(baseDir.resolve("${name}-255-255.container.bin"), containerBytes)
        Files.write(baseDir.resolve("${name}-255-255.payload.bin"), payload)
        Files.write(baseDir.resolve("${name}-255-255.entries.bin"), entriesBytes)
        Files.write(baseDir.resolve("${name}-255-255.signature.bin"), signatureBytes)
        Files.writeString(baseDir.resolve("${name}-255-255.manifest.txt"), buildManifest(name, http, keyPair, table, containerBytes, payload, entriesBytes, signatureBytes))
    }

    private fun buildManifest(
        name: String,
        http: Boolean,
        keyPair: RsaConfig.RsaKeyPair,
        table: ChecksumTable,
        containerBytes: ByteArray,
        payload: ByteArray,
        entriesBytes: ByteArray,
        signatureBytes: ByteArray
    ): String {
        val out = StringBuilder()
        out.appendLine("variant=$name")
        out.appendLine("http=$http")
        out.appendLine("entries=${table.entries.size}")
        out.appendLine("nonEmptyEntries=${table.entries.count { it != ChecksumTable.TableEntry.EMPTY }}")
        out.appendLine("containerBytes=${containerBytes.size}")
        out.appendLine("payloadBytes=${payload.size}")
        out.appendLine("entriesBytes=${entriesBytes.size}")
        out.appendLine("signatureBytes=${signatureBytes.size}")
        out.appendLine("rsaModulusBits=${keyPair.modulus.bitLength()}")
        out.appendLine("containerSha256=${containerBytes.sha256Hex()}")
        out.appendLine("payloadSha256=${payload.sha256Hex()}")
        out.appendLine("entriesSha256=${entriesBytes.sha256Hex()}")
        out.appendLine("signatureSha256=${signatureBytes.sha256Hex()}")
        out.appendLine()
        out.appendLine("index crc version files size whirlpool")

        table.entries.forEachIndexed { index, entry ->
            out.appendLine(
                "%03d %s %s %d %d %s".format(
                    index,
                    entry.crc.toUInt().toString(16).padStart(8, '0'),
                    entry.version.toUInt().toString(16).padStart(8, '0'),
                    entry.files,
                    entry.size,
                    entry.whirlpool.toHex()
                )
            )
        }

        return out.toString()
    }

    private fun ByteArray.sha256Hex(): String = MessageDigest.getInstance("SHA-256").digest(this).toHex()

    private fun ByteArray.toHex(): String = joinToString("") { byte ->
        "%02x".format(byte.toInt() and 0xff)
    }

    companion object {
        private const val ENTRY_SIZE = 4 + 4 + 4 + 4 + 64
    }
}
