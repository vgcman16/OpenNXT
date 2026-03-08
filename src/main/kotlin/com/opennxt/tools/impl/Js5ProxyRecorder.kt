package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.net.handshake.HandshakeType
import com.opennxt.tools.Tool
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.IOException
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.time.Duration
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

class Js5ProxyRecorder : Tool(
    "js5-proxy-recorder",
    "Proxies a local JS5 port to live Jagex and records the client's request sequence"
) {
    private val bindHost by option(help = "Local host to bind to").default("127.0.0.1")
    private val bindPort by option(help = "Local port to bind to").int().default(43595)
    private val remoteHost by option(help = "Remote JS5 host").default("content.runescape.com")
    private val remotePort by option(help = "Remote JS5 port").int().default(43594)
    private val maxSessions by option(help = "Maximum number of client sessions to record").int().default(6)
    private val idleTimeoutSeconds by option(help = "Stop after this many idle seconds without a new client").int().default(20)
    private val sessionIdleTimeoutSeconds by option(help = "Close a proxied session after this many idle seconds").int().default(10)
    private val socketTimeoutMillis by option(help = "Socket read timeout in milliseconds").int().default(1000)
    private val outputDir by option(help = "Directory where request traces should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("js5-proxy-recorder").toString())

    override fun runTool() {
        val outputPath = Paths.get(outputDir)
        Files.createDirectories(outputPath)

        val summaryLines = mutableListOf<String>()
        val timestamp = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneOffset.UTC).format(Instant.now())
        val summaryPath = outputPath.resolve("summary-$timestamp.log")

        logger.info { "Binding JS5 proxy on $bindHost:$bindPort -> $remoteHost:$remotePort" }

        ServerSocket(bindPort, 50).use { server ->
            server.reuseAddress = true
            server.soTimeout = 1000

            var sessionCount = 0
            var lastAccept = System.nanoTime()

            while (sessionCount < maxSessions) {
                val idleElapsed = Duration.ofNanos(System.nanoTime() - lastAccept)
                if (idleElapsed.seconds >= idleTimeoutSeconds && sessionCount > 0) {
                    logger.info { "Stopping proxy after ${idleElapsed.seconds}s of idle time" }
                    break
                }

                val client = try {
                    server.accept()
                } catch (_: SocketTimeoutException) {
                    continue
                }

                lastAccept = System.nanoTime()
                sessionCount++

                val sessionLines = handleSession(sessionCount, client)
                val sessionPath = outputPath.resolve("session-${sessionCount.toString().padStart(2, '0')}-$timestamp.log")
                Files.write(sessionPath, sessionLines)
                summaryLines += sessionLines
                summaryLines += ""
            }
        }

        Files.write(summaryPath, summaryLines)
        logger.info { "Wrote JS5 proxy traces to $outputPath" }
    }

    private fun handleSession(sessionId: Int, client: Socket): List<String> {
        val lines = mutableListOf<String>()
        val parser = ClientRequestParser(sessionId, lines)
        val lastActivity = AtomicLong(System.nanoTime())
        val started = Instant.now()

        client.soTimeout = socketTimeoutMillis
        client.tcpNoDelay = true

        lines += "session#$sessionId start=${started}"
        lines += "session#$sessionId client=${client.remoteSocketAddress}"

        Socket().use { remote ->
            remote.soTimeout = socketTimeoutMillis
            remote.tcpNoDelay = true
            remote.connect(java.net.InetSocketAddress(remoteHost, remotePort), socketTimeoutMillis)
            lines += "session#$sessionId remote=$remoteHost:$remotePort"

            val done = CountDownLatch(2)
            val clientToRemote = Thread {
                try {
                    pump(
                        source = client,
                        destination = remote,
                        lastActivity = lastActivity,
                        inspect = { bytes, length -> parser.feed(bytes, length) }
                    )
                } finally {
                    done.countDown()
                }
            }
            val remoteToClient = Thread {
                try {
                    pump(
                        source = remote,
                        destination = client,
                        lastActivity = lastActivity
                    )
                } finally {
                    done.countDown()
                }
            }

            clientToRemote.name = "js5-proxy-client-$sessionId"
            remoteToClient.name = "js5-proxy-remote-$sessionId"
            clientToRemote.start()
            remoteToClient.start()

            while (!done.await(1, TimeUnit.SECONDS)) {
                val idle = Duration.ofNanos(System.nanoTime() - lastActivity.get()).seconds
                if (idle >= sessionIdleTimeoutSeconds) {
                    lines += "session#$sessionId idle-timeout=${idle}s"
                    break
                }
            }

            closeQuietly(client)
            closeQuietly(remote)
            clientToRemote.join(2000)
            remoteToClient.join(2000)
        }

        lines += "session#$sessionId end=${Instant.now()}"
        return lines
    }

    private fun pump(
        source: Socket,
        destination: Socket,
        lastActivity: AtomicLong,
        inspect: ((ByteArray, Int) -> Unit)? = null
    ) {
        val input = BufferedInputStream(source.getInputStream())
        val output = BufferedOutputStream(destination.getOutputStream())
        val buffer = ByteArray(8192)

        while (!source.isClosed && !destination.isClosed) {
            val read = try {
                input.read(buffer)
            } catch (_: SocketTimeoutException) {
                continue
            } catch (_: IOException) {
                break
            }

            if (read < 0) {
                break
            }

            lastActivity.set(System.nanoTime())
            inspect?.invoke(buffer, read)
            output.write(buffer, 0, read)
            output.flush()
        }
    }

    private fun closeQuietly(socket: Socket) {
        try {
            socket.close()
        } catch (_: IOException) {
        }
    }

    private class ClientRequestParser(
        private val sessionId: Int,
        private val lines: MutableList<String>
    ) {
        private var pending = ByteArray(0)
        private var outerHandshakeDecoded = false
        private var js5HandshakeDecoded = false

        fun feed(source: ByteArray, length: Int) {
            pending += source.copyOf(length)
            parse()
        }

        private fun parse() {
            while (true) {
                if (!outerHandshakeDecoded) {
                    if (pending.size < 1) return

                    val handshakeType = pending[0].toInt() and 0xff
                    lines += "session#$sessionId handshake-type=${HandshakeType.fromId(handshakeType) ?: handshakeType}"
                    pending = pending.copyOfRange(1, pending.size)
                    outerHandshakeDecoded = true
                    continue
                }

                if (!js5HandshakeDecoded) {
                    if (pending.size < 1) return

                    val size = pending[0].toInt() and 0xff
                    if (pending.size < size + 1) return

                    val major = readInt(pending, 1)
                    val minor = readInt(pending, 5)
                    val tokenLength = size - 10
                    val token = if (tokenLength > 0) {
                        pending.copyOfRange(9, 9 + tokenLength).toString(StandardCharsets.US_ASCII)
                    } else {
                        ""
                    }
                    val language = pending[size].toInt() and 0xff

                    lines += "session#$sessionId js5-handshake build=$major.$minor language=$language tokenLength=${token.length}"
                    pending = pending.copyOfRange(size + 1, pending.size)
                    js5HandshakeDecoded = true
                    continue
                }

                if (pending.size < 10) {
                    return
                }

                val opcode = pending[0].toInt() and 0xff
                val frame = pending.copyOfRange(0, 10)
                lines += describeFrame(opcode, frame)
                pending = pending.copyOfRange(10, pending.size)
            }
        }

        private fun describeFrame(opcode: Int, frame: ByteArray): String {
            return when (opcode) {
                0, 1, 17, 32, 33 -> {
                    val index = frame[1].toInt() and 0xff
                    val archive = readInt(frame, 2)
                    val build = readUnsignedShort(frame, 6)
                    val priority = opcode == 1 || opcode == 17 || opcode == 33
                    val nxt = opcode == 17 || opcode == 32 || opcode == 33
                    "session#$sessionId request opcode=$opcode priority=$priority nxt=$nxt build=$build ${describeArchive(index, archive)}"
                }

                6 -> {
                    val value = readMedium(frame, 1)
                    val build = readUnsignedShort(frame, 6)
                    "session#$sessionId connection-initialized value=$value build=$build"
                }

                2 -> {
                    val build = readUnsignedShort(frame, 6)
                    "session#$sessionId logged-in build=$build"
                }

                3 -> {
                    val build = readUnsignedShort(frame, 6)
                    "session#$sessionId logged-out build=$build"
                }

                4 -> {
                    val xor = frame[1].toInt() and 0xff
                    "session#$sessionId xor-request xor=$xor"
                }

                7 -> {
                    val build = readUnsignedShort(frame, 6)
                    "session#$sessionId request-termination build=$build"
                }

                else -> {
                    "session#$sessionId unknown opcode=$opcode frame=${frame.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }}"
                }
            }
        }

        private fun describeArchive(index: Int, archive: Int): String = when {
            index == 255 && archive == 255 -> "master-reference-table"
            index == 255 -> "reference-table[$archive]"
            else -> "archive[$index,$archive]"
        }

        private fun readInt(bytes: ByteArray, offset: Int): Int {
            return ((bytes[offset].toInt() and 0xff) shl 24) or
                ((bytes[offset + 1].toInt() and 0xff) shl 16) or
                ((bytes[offset + 2].toInt() and 0xff) shl 8) or
                (bytes[offset + 3].toInt() and 0xff)
        }

        private fun readUnsignedShort(bytes: ByteArray, offset: Int): Int {
            return ((bytes[offset].toInt() and 0xff) shl 8) or
                (bytes[offset + 1].toInt() and 0xff)
        }

        private fun readMedium(bytes: ByteArray, offset: Int): Int {
            return ((bytes[offset].toInt() and 0xff) shl 16) or
                ((bytes[offset + 1].toInt() and 0xff) shl 8) or
                (bytes[offset + 2].toInt() and 0xff)
        }
    }
}
