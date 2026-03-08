package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.config.ServerConfig
import com.opennxt.config.TomlConfig
import com.opennxt.net.handshake.HandshakeType
import com.opennxt.tools.Tool
import com.opennxt.tools.impl.cachedownloader.Js5Credentials
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.security.MessageDigest
import kotlin.math.min

class Js5WireCompare : Tool(
    "js5-wire-compare",
    "Captures the raw first JS5 255/255 exchange from live Jagex and a local OpenNXT server and compares them byte-for-byte"
) {
    private val outputDir by option(help = "Directory for wire-capture artifacts")
        .default(Constants.DATA_PATH.resolve("debug").resolve("js5-wire-compare").toString())
    private val liveHost by option(help = "Live JS5 host").default("content.runescape.com")
    private val livePort by option(help = "Live JS5 port").int().default(43594)
    private val localHost by option(help = "Local JS5 host").default("127.0.0.1")
    private val localPort by option(help = "Local JS5 port").int()
    private val tokenUrl by option(help = "jav_config.ws URL used to fetch JS5 version/token")
        .default("https://world5.runescape.com/jav_config.ws")
    private val timeoutMillis by option(help = "Socket timeout in milliseconds").int().default(10_000)
    private val index by option(help = "JS5 index to request").int().default(255)
    private val archive by option(help = "JS5 archive to request").int().default(255)
    private val skipRequest by option(help = "Only capture unsolicited bytes after handshake/init without requesting an archive")
        .flag(default = false)

    override fun runTool() {
        val outputPath = Paths.get(outputDir)
        Files.createDirectories(outputPath)

        val credentials = Js5Credentials.download(tokenUrl)
        val serverConfig = TomlConfig.load<ServerConfig>(ServerConfig.DEFAULT_PATH, mustExist = true)
        val resolvedLocalPort = localPort ?: serverConfig.ports.game

        logger.info {
            "Capturing raw JS5 $index/$archive for build ${credentials.version} " +
                "from live=$liveHost:$livePort and local=$localHost:$resolvedLocalPort"
        }

        val liveCapture = capture(
            label = "live",
            host = liveHost,
            port = livePort,
            build = credentials.version,
            token = credentials.token,
            index = index,
            archive = archive,
            timeoutMillis = timeoutMillis,
            skipRequest = skipRequest
        )
        val localCapture = capture(
            label = "local",
            host = localHost,
            port = resolvedLocalPort,
            build = credentials.version,
            token = credentials.token,
            index = index,
            archive = archive,
            timeoutMillis = timeoutMillis,
            skipRequest = skipRequest
        )

        writeCapture(outputPath, liveCapture)
        writeCapture(outputPath, localCapture)
        Files.writeString(outputPath.resolve("compare-report.txt"), buildReport(liveCapture, localCapture))
        logger.info { "Wrote JS5 wire comparison artifacts to $outputPath" }
    }

    private fun capture(
        label: String,
        host: String,
        port: Int,
        build: Int,
        token: String,
        index: Int,
        archive: Int,
        timeoutMillis: Int,
        skipRequest: Boolean
    ): Capture {
        Socket().use { socket ->
            socket.soTimeout = timeoutMillis
            socket.tcpNoDelay = true
            socket.connect(InetSocketAddress(host, port), timeoutMillis)

            val input = BufferedInputStream(socket.getInputStream())
            val output = DataOutputStream(BufferedOutputStream(socket.getOutputStream()))

            val handshakeBytes = buildHandshake(build, token)
            output.write(handshakeBytes)
            output.flush()

            val handshakeResponse = input.read()
            check(handshakeResponse >= 0) { "No JS5 handshake response from $label ($host:$port)" }

            val requestBytes = buildRequestSequence(build, index, archive, skipRequest)
            output.write(requestBytes)
            output.flush()

            val responseBytes: ByteArray
            val trailingBytes: ByteArray
            val parsed: ParsedHeader?
            if (skipRequest) {
                parsed = null
                trailingBytes = drainTrailing(input)
                responseBytes = byteArrayOf(handshakeResponse.toByte())
            } else {
                val headerBytes = readFully(input, 10)
                parsed = parseHeader(headerBytes)
                val bodyBytes = readFully(input, parsed.containerBytes - 5)

                responseBytes = ByteArray(1 + headerBytes.size + bodyBytes.size)
                responseBytes[0] = handshakeResponse.toByte()
                System.arraycopy(headerBytes, 0, responseBytes, 1, headerBytes.size)
                System.arraycopy(bodyBytes, 0, responseBytes, 1 + headerBytes.size, bodyBytes.size)

                trailingBytes = drainTrailing(input)
            }

            return Capture(
                label = label,
                host = host,
                port = port,
                requestBytes = handshakeBytes + requestBytes,
                responseBytes = responseBytes,
                trailingBytes = trailingBytes,
                handshakeResponse = handshakeResponse,
                header = parsed,
                skipRequest = skipRequest
            )
        }
    }

    private fun buildHandshake(build: Int, token: String): ByteArray {
        val tokenBytes = token.toByteArray(Charsets.US_ASCII)
        val handshakeSize = 4 + 4 + tokenBytes.size + 1 + 1

        val bytes = ArrayList<Byte>(16 + tokenBytes.size)

        fun addInt(value: Int) {
            bytes += ((value ushr 24) and 0xff).toByte()
            bytes += ((value ushr 16) and 0xff).toByte()
            bytes += ((value ushr 8) and 0xff).toByte()
            bytes += (value and 0xff).toByte()
        }

        bytes += HandshakeType.JS_5.id.toByte()
        bytes += handshakeSize.toByte()
        addInt(build)
        addInt(1)
        tokenBytes.forEach(bytes::add)
        bytes += 0.toByte()
        bytes += 0.toByte()

        return bytes.toByteArray()
    }

    private fun buildRequestSequence(build: Int, index: Int, archive: Int, skipRequest: Boolean): ByteArray {
        val bytes = ArrayList<Byte>(32)

        fun addInt(value: Int) {
            bytes += ((value ushr 24) and 0xff).toByte()
            bytes += ((value ushr 16) and 0xff).toByte()
            bytes += ((value ushr 8) and 0xff).toByte()
            bytes += (value and 0xff).toByte()
        }

        fun addShort(value: Int) {
            bytes += ((value ushr 8) and 0xff).toByte()
            bytes += (value and 0xff).toByte()
        }

        fun addMedium(value: Int) {
            bytes += ((value ushr 16) and 0xff).toByte()
            bytes += ((value ushr 8) and 0xff).toByte()
            bytes += (value and 0xff).toByte()
        }

        bytes += 6.toByte()
        addMedium(5)
        addShort(0)
        addShort(build)
        addShort(0)

        bytes += 3.toByte()
        addMedium(5)
        addShort(0)
        addShort(build)
        addShort(0)

        if (!skipRequest) {
            bytes += 33.toByte()
            bytes += index.toByte()
            addInt(archive)
            addShort(build)
            addShort(0)
        }

        return bytes.toByteArray()
    }

    private fun parseHeader(bytes: ByteArray): ParsedHeader {
        check(bytes.size == 10) { "Expected 10 header bytes, got ${bytes.size}" }

        val index = bytes[0].toInt() and 0xff
        val hash = readInt(bytes, 1)
        val compression = bytes[5].toInt() and 0xff
        val fileSize = readInt(bytes, 6)
        val priority = (hash and Int.MIN_VALUE) == 0
        val archive = hash and Int.MAX_VALUE
        val containerBytes = fileSize + if (compression == 0) 5 else 9

        return ParsedHeader(index, archive, priority, compression, fileSize, containerBytes)
    }

    private fun readInt(bytes: ByteArray, offset: Int): Int {
        return ((bytes[offset].toInt() and 0xff) shl 24) or
            ((bytes[offset + 1].toInt() and 0xff) shl 16) or
            ((bytes[offset + 2].toInt() and 0xff) shl 8) or
            (bytes[offset + 3].toInt() and 0xff)
    }

    private fun readFully(input: BufferedInputStream, length: Int): ByteArray {
        val bytes = ByteArray(length)
        var offset = 0
        while (offset < length) {
            val read = input.read(bytes, offset, length - offset)
            check(read >= 0) { "Socket closed while reading $length bytes at offset $offset" }
            offset += read
        }
        return bytes
    }

    private fun drainTrailing(input: BufferedInputStream): ByteArray {
        val bytes = ArrayList<Byte>()
        val scratch = ByteArray(1024)
        while (true) {
            val read = try {
                input.read(scratch)
            } catch (_: SocketTimeoutException) {
                break
            }
            if (read <= 0) break
            for (i in 0 until read) {
                bytes += scratch[i]
            }
            if (read < scratch.size) {
                break
            }
        }
        return bytes.toByteArray()
    }

    private fun writeCapture(outputPath: Path, capture: Capture) {
        Files.write(outputPath.resolve("${capture.label}.request.bin"), capture.requestBytes)
        Files.write(outputPath.resolve("${capture.label}.response.bin"), capture.responseBytes)
        Files.write(outputPath.resolve("${capture.label}.trailing.bin"), capture.trailingBytes)
        Files.writeString(outputPath.resolve("${capture.label}.manifest.txt"), buildManifest(capture))
    }

    private fun buildManifest(capture: Capture): String {
        return buildString {
            appendLine("label=${capture.label}")
            appendLine("host=${capture.host}")
            appendLine("port=${capture.port}")
            appendLine("requestBytes=${capture.requestBytes.size}")
            appendLine("responseBytes=${capture.responseBytes.size}")
            appendLine("trailingBytes=${capture.trailingBytes.size}")
            appendLine("handshakeResponse=${capture.handshakeResponse}")
            appendLine("skipRequest=${capture.skipRequest}")
            if (capture.header != null) {
                appendLine("index=${capture.header.index}")
                appendLine("archive=${capture.header.archive}")
                appendLine("priority=${capture.header.priority}")
                appendLine("compression=${capture.header.compression}")
                appendLine("fileSize=${capture.header.fileSize}")
                appendLine("containerBytes=${capture.header.containerBytes}")
            }
            appendLine("requestSha256=${capture.requestBytes.sha256()}")
            appendLine("responseSha256=${capture.responseBytes.sha256()}")
            appendLine("trailingSha256=${capture.trailingBytes.sha256()}")
            appendLine("requestHead=${capture.requestBytes.headHex()}")
            appendLine("responseHead=${capture.responseBytes.headHex()}")
            appendLine("trailingHead=${capture.trailingBytes.headHex()}")
        }
    }

    private fun buildReport(live: Capture, local: Capture): String {
        val responseMismatch = firstMismatch(live.responseBytes, local.responseBytes)
        val trailingMismatch = firstMismatch(live.trailingBytes, local.trailingBytes)

        return buildString {
            appendLine("liveHandshake=${live.handshakeResponse}")
            appendLine("localHandshake=${local.handshakeResponse}")
            appendLine("requestBytesMatch=${live.requestBytes.contentEquals(local.requestBytes)}")
            appendLine("responseBytesMatch=${live.responseBytes.contentEquals(local.responseBytes)}")
            appendLine("trailingBytesMatch=${live.trailingBytes.contentEquals(local.trailingBytes)}")
            appendLine("liveResponseBytes=${live.responseBytes.size}")
            appendLine("localResponseBytes=${local.responseBytes.size}")
            appendLine("liveTrailingBytes=${live.trailingBytes.size}")
            appendLine("localTrailingBytes=${local.trailingBytes.size}")
            appendLine("liveHeader=${live.header ?: "none"}")
            appendLine("localHeader=${local.header ?: "none"}")
            appendLine("firstResponseMismatch=${responseMismatch?.describe(live.responseBytes, local.responseBytes) ?: "none"}")
            appendLine("firstTrailingMismatch=${trailingMismatch?.describe(live.trailingBytes, local.trailingBytes) ?: "none"}")

            if (responseMismatch != null) {
                appendLine()
                appendLine("responseWindowLive=${windowHex(live.responseBytes, responseMismatch.offset)}")
                appendLine("responseWindowLocal=${windowHex(local.responseBytes, responseMismatch.offset)}")
            }

            if (trailingMismatch != null) {
                appendLine()
                appendLine("trailingWindowLive=${windowHex(live.trailingBytes, trailingMismatch.offset)}")
                appendLine("trailingWindowLocal=${windowHex(local.trailingBytes, trailingMismatch.offset)}")
            }
        }
    }

    private fun firstMismatch(left: ByteArray, right: ByteArray): Mismatch? {
        val minSize = min(left.size, right.size)
        for (i in 0 until minSize) {
            if (left[i] != right[i]) {
                return Mismatch(i, left[i].toInt() and 0xff, right[i].toInt() and 0xff)
            }
        }
        if (left.size != right.size) {
            return Mismatch(minSize, left.getOrNull(minSize)?.toInt()?.and(0xff), right.getOrNull(minSize)?.toInt()?.and(0xff))
        }
        return null
    }

    private fun windowHex(bytes: ByteArray, center: Int, radius: Int = 16): String {
        if (bytes.isEmpty()) return ""
        val from = maxOf(0, center - radius)
        val to = min(bytes.size, center + radius + 1)
        return bytes.copyOfRange(from, to).joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun ByteArray.sha256(): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(this)
        return digest.joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    private fun ByteArray.headHex(length: Int = 32): String {
        if (isEmpty()) return ""
        return copyOfRange(0, min(size, length)).joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
    }

    private data class ParsedHeader(
        val index: Int,
        val archive: Int,
        val priority: Boolean,
        val compression: Int,
        val fileSize: Int,
        val containerBytes: Int
    )

    private data class Capture(
        val label: String,
        val host: String,
        val port: Int,
        val requestBytes: ByteArray,
        val responseBytes: ByteArray,
        val trailingBytes: ByteArray,
        val handshakeResponse: Int,
        val header: ParsedHeader?,
        val skipRequest: Boolean
    )

    private data class Mismatch(val offset: Int, val left: Int?, val right: Int?) {
        fun describe(leftBytes: ByteArray, rightBytes: ByteArray): String {
            return "offset=$offset left=${left?.toString() ?: "eof"} right=${right?.toString() ?: "eof"} " +
                "leftSize=${leftBytes.size} rightSize=${rightBytes.size}"
        }
    }
}
