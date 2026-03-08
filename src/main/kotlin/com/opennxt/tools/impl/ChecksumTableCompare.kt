package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.config.RsaConfig
import com.opennxt.config.TomlConfig
import com.opennxt.filesystem.ChecksumTable
import com.opennxt.filesystem.Container
import com.opennxt.tools.Tool
import com.opennxt.tools.impl.cachedownloader.Js5ClientPool
import com.opennxt.tools.impl.cachedownloader.Js5Credentials
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

class ChecksumTableCompare : Tool(
    "checksum-table-compare",
    "Fetches live 255/255, dumps both sides, and compares the generated JS5 checksum table against Jagex"
) {
    private val outputDir by option(help = "Directory where comparison artifacts should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("checksum-table-compare").toString())
    private val ip by option(help = "Live js5 host").default("content.runescape.com")
    private val port by option(help = "Live js5 port").int().default(43594)
    private val timeoutSeconds by option(help = "Request timeout in seconds").int().default(30)

    override fun runTool() {
        val baseDir = Paths.get(outputDir)
        Files.createDirectories(baseDir)

        val rsaConfig = TomlConfig.load<RsaConfig>(RsaConfig.DEFAULT_PATH, mustExist = true)
        val local = createLocalDump(rsaConfig.js5)
        writeDump(baseDir, "local-js5", local)

        val liveCredentials = Js5Credentials.download()
        val live = fetchLiveDump()
        writeDump(baseDir, "live-js5", live)

        val report = buildComparisonReport(local, live, liveCredentials.version)
        Files.writeString(baseDir.resolve("compare-report.txt"), report)
        logger.info { "Wrote checksum-table comparison artifacts to $baseDir" }
    }

    private fun createLocalDump(keyPair: RsaConfig.RsaKeyPair): DumpedChecksumTable {
        val table = ChecksumTable.create(filesystem, false)
        val payload = table.encode(keyPair.modulus, keyPair.exponent)
        val container = Container.wrap(payload)
        val containerBytes = ByteArray(container.remaining())
        container.get(containerBytes)
        return decodeDump("local-js5", containerBytes)
    }

    private fun fetchLiveDump(): DumpedChecksumTable {
        val pool = Js5ClientPool(1, 1, ip, port)
        try {
            pool.openConnections(amount = 1)
            val client = pool.getClient()
            check(client.awaitConnected(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for live JS5 connection to $ip:$port"
            }

            val request = pool.addRequest(true, 255, 255)
                ?: throw IllegalStateException("Failed to enqueue live request for [255,255]")
            check(request.awaitCompletion(timeoutSeconds.toLong(), TimeUnit.SECONDS)) {
                "Timed out waiting for live checksum table from $ip:$port"
            }

            val buffer = request.buffer ?: throw IllegalStateException("Live checksum table buffer was null")
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            buffer.rewind()
            return decodeDump("live-js5", bytes)
        } finally {
            pool.close()
        }
    }

    private fun decodeDump(label: String, containerBytes: ByteArray): DumpedChecksumTable {
        val payload = Container.decode(ByteBuffer.wrap(containerBytes)).data
        val entryCount = payload.firstOrNull()?.toInt()?.and(0xff)
            ?: throw IllegalStateException("Empty checksum payload for $label")
        val entriesSize = 1 + entryCount * ENTRY_SIZE
        require(payload.size >= entriesSize) {
            "Checksum payload for $label is too short: ${payload.size} < $entriesSize"
        }

        val entriesBytes = payload.copyOfRange(0, entriesSize)
        val signatureBytes = payload.copyOfRange(entriesSize, payload.size)
        val table = ChecksumTable.decode(ByteBuffer.wrap(entriesBytes))
        return DumpedChecksumTable(containerBytes, payload, entriesBytes, signatureBytes, table)
    }

    private fun writeDump(baseDir: Path, prefix: String, dump: DumpedChecksumTable) {
        Files.write(baseDir.resolve("$prefix.container.bin"), dump.containerBytes)
        Files.write(baseDir.resolve("$prefix.payload.bin"), dump.payloadBytes)
        Files.write(baseDir.resolve("$prefix.entries.bin"), dump.entriesBytes)
        Files.write(baseDir.resolve("$prefix.signature.bin"), dump.signatureBytes)
        Files.writeString(baseDir.resolve("$prefix.manifest.txt"), buildManifest(prefix, dump))
    }

    private fun buildManifest(prefix: String, dump: DumpedChecksumTable): String {
        val out = StringBuilder()
        out.appendLine("label=$prefix")
        out.appendLine("entries=${dump.table.entries.size}")
        out.appendLine("nonEmptyEntries=${dump.table.entries.count { it != ChecksumTable.TableEntry.EMPTY }}")
        out.appendLine("containerBytes=${dump.containerBytes.size}")
        out.appendLine("payloadBytes=${dump.payloadBytes.size}")
        out.appendLine("entriesBytes=${dump.entriesBytes.size}")
        out.appendLine("signatureBytes=${dump.signatureBytes.size}")
        out.appendLine("containerSha256=${dump.containerBytes.sha256Hex()}")
        out.appendLine("payloadSha256=${dump.payloadBytes.sha256Hex()}")
        out.appendLine("entriesSha256=${dump.entriesBytes.sha256Hex()}")
        out.appendLine("signatureSha256=${dump.signatureBytes.sha256Hex()}")
        out.appendLine()
        out.appendLine("index crc version files size whirlpool")

        dump.table.entries.forEachIndexed { index, entry ->
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

    private fun buildComparisonReport(
        local: DumpedChecksumTable,
        live: DumpedChecksumTable,
        liveVersion: Int
    ): String {
        val out = StringBuilder()
        out.appendLine("liveVersion=$liveVersion")
        out.appendLine("localEntries=${local.table.entries.size}")
        out.appendLine("liveEntries=${live.table.entries.size}")
        out.appendLine("entriesBytesMatch=${local.entriesBytes.contentEquals(live.entriesBytes)}")
        out.appendLine("signatureBytesMatch=${local.signatureBytes.contentEquals(live.signatureBytes)}")
        out.appendLine("containerBytesMatch=${local.containerBytes.contentEquals(live.containerBytes)}")
        out.appendLine("localEntriesSha256=${local.entriesBytes.sha256Hex()}")
        out.appendLine("liveEntriesSha256=${live.entriesBytes.sha256Hex()}")
        out.appendLine("localSignatureSha256=${local.signatureBytes.sha256Hex()}")
        out.appendLine("liveSignatureSha256=${live.signatureBytes.sha256Hex()}")
        out.appendLine()

        val maxEntries = minOf(local.table.entries.size, live.table.entries.size)
        val mismatches = ArrayList<String>()
        for (index in 0 until maxEntries) {
            val localEntry = local.table.entries[index]
            val liveEntry = live.table.entries[index]
            if (localEntry == liveEntry) continue

            mismatches += buildString {
                append("index=$index")
                if (localEntry.crc != liveEntry.crc) {
                    append(" crc=${localEntry.crc.toUInt().toString(16).padStart(8, '0')}!=${liveEntry.crc.toUInt().toString(16).padStart(8, '0')}")
                }
                if (localEntry.version != liveEntry.version) {
                    append(" version=${localEntry.version.toUInt().toString(16).padStart(8, '0')}!=${liveEntry.version.toUInt().toString(16).padStart(8, '0')}")
                }
                if (localEntry.files != liveEntry.files) {
                    append(" files=${localEntry.files}!=${liveEntry.files}")
                }
                if (localEntry.size != liveEntry.size) {
                    append(" size=${localEntry.size}!=${liveEntry.size}")
                }
                if (!localEntry.whirlpool.contentEquals(liveEntry.whirlpool)) {
                    append(" whirlpool=${localEntry.whirlpool.toHex()}!=${liveEntry.whirlpool.toHex()}")
                }
            }
        }

        out.appendLine("entryMismatchCount=${mismatches.size}")
        if (mismatches.isEmpty()) {
            out.appendLine("All entry rows match. Any remaining rejection is in the RSA/signature side.")
        } else {
            out.appendLine("First mismatches:")
            mismatches.take(25).forEach(out::appendLine)
        }

        return out.toString()
    }

    private fun ByteArray.sha256Hex(): String = MessageDigest.getInstance("SHA-256").digest(this).toHex()

    private fun ByteArray.toHex(): String = joinToString("") { byte ->
        "%02x".format(byte.toInt() and 0xff)
    }

    private data class DumpedChecksumTable(
        val containerBytes: ByteArray,
        val payloadBytes: ByteArray,
        val entriesBytes: ByteArray,
        val signatureBytes: ByteArray,
        val table: ChecksumTable
    )

    companion object {
        private const val ENTRY_SIZE = 4 + 4 + 4 + 4 + 64
    }
}
