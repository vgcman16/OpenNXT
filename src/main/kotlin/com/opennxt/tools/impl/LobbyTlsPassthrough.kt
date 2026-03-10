package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.types.int
import com.opennxt.Constants
import com.opennxt.tools.Tool
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketTimeoutException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong

class LobbyTlsPassthrough : Tool(
    "lobby-tls-passthrough",
    "Binds a local TLS passthrough for the RuneScape lobby host and records connection sizes"
) {
    private val bindHost by option(help = "Local host to bind to").default("127.0.0.1")
    private val bindPort by option(help = "Local port to bind to").int().default(443)
    private val remoteHost by option(help = "Remote lobby host").default("8.42.17.230")
    private val remotePort by option(help = "Remote lobby port").int().default(443)
    private val maxSessions by option(help = "Maximum number of proxied sessions before exiting").int().default(8)
    private val acceptTimeoutMillis by option(help = "Server accept timeout in milliseconds").int().default(1000)
    private val socketTimeoutMillis by option(help = "Socket read timeout in milliseconds").int().default(1000)
    private val idleTimeoutSeconds by option(help = "Stop after this many idle seconds with no new clients").int().default(60)
    private val sessionIdleTimeoutSeconds by option(help = "Close a session after this many idle seconds").int().default(20)
    private val outputDir by option(help = "Directory where session logs should be written")
        .default(Constants.DATA_PATH.resolve("debug").resolve("lobby-tls-passthrough").toString())

    override fun runTool() {
        val outputPath = Paths.get(outputDir)
        Files.createDirectories(outputPath)

        val timestamp = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss").withZone(ZoneOffset.UTC).format(Instant.now())
        val summaryPath = outputPath.resolve("summary-$timestamp.log")
        val summaryLines = mutableListOf<String>()

        logger.info { "Binding lobby TLS passthrough on $bindHost:$bindPort -> $remoteHost:$remotePort" }

        ServerSocket().use { server ->
            server.reuseAddress = true
            server.soTimeout = acceptTimeoutMillis
            server.bind(InetSocketAddress(bindHost, bindPort))

            var sessionCount = 0
            var lastAccept = System.nanoTime()

            while (sessionCount < maxSessions) {
                val idleSeconds = TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - lastAccept)
                if (sessionCount > 0 && idleSeconds >= idleTimeoutSeconds) {
                    logger.info { "Stopping lobby passthrough after ${idleSeconds}s of idle time" }
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
        logger.info { "Wrote lobby TLS passthrough logs to $outputPath" }
    }

    private fun handleSession(sessionId: Int, client: Socket): List<String> {
        val lines = mutableListOf<String>()
        val started = Instant.now()
        val lastActivity = AtomicLong(System.nanoTime())
        val clientToRemoteBytes = AtomicLong(0)
        val remoteToClientBytes = AtomicLong(0)

        client.soTimeout = socketTimeoutMillis
        client.tcpNoDelay = true

        lines += "session#$sessionId start=$started"
        lines += "session#$sessionId client=${client.remoteSocketAddress}"
        lines += "session#$sessionId remote=$remoteHost:$remotePort"

        Socket().use { remote ->
            remote.soTimeout = socketTimeoutMillis
            remote.tcpNoDelay = true
            remote.connect(InetSocketAddress(remoteHost, remotePort), socketTimeoutMillis)

            val done = CountDownLatch(2)
            val clientToRemote = Thread {
                try {
                    pump(
                        source = client,
                        destination = remote,
                        lastActivity = lastActivity,
                        byteCounter = clientToRemoteBytes,
                        lines = lines,
                        prefix = "client->remote"
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
                        lastActivity = lastActivity,
                        byteCounter = remoteToClientBytes,
                        lines = lines,
                        prefix = "remote->client"
                    )
                } finally {
                    done.countDown()
                }
            }

            clientToRemote.name = "lobby-tls-client-$sessionId"
            remoteToClient.name = "lobby-tls-remote-$sessionId"
            clientToRemote.start()
            remoteToClient.start()

            while (!done.await(1, TimeUnit.SECONDS)) {
                val idle = TimeUnit.NANOSECONDS.toSeconds(System.nanoTime() - lastActivity.get())
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

        lines += "session#$sessionId bytes client->remote=${clientToRemoteBytes.get()} remote->client=${remoteToClientBytes.get()}"
        lines += "session#$sessionId end=${Instant.now()}"
        return lines
    }

    private fun pump(
        source: Socket,
        destination: Socket,
        lastActivity: AtomicLong,
        byteCounter: AtomicLong,
        lines: MutableList<String>,
        prefix: String
    ) {
        val input = BufferedInputStream(source.getInputStream())
        val output = BufferedOutputStream(destination.getOutputStream())
        val buffer = ByteArray(8192)
        var chunkIndex = 0

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
            byteCounter.addAndGet(read.toLong())
            output.write(buffer, 0, read)
            output.flush()
            chunkIndex++

            if (chunkIndex <= 3) {
                lines += "$prefix first-chunk-$chunkIndex bytes=$read hex=${previewHex(buffer, read)}"
            }

            if (read >= 1024) {
                lines += "$prefix chunk=$read"
            }
        }
    }

    private fun closeQuietly(socket: Socket) {
        try {
            socket.close()
        } catch (_: IOException) {
        }
    }

    private fun previewHex(bytes: ByteArray, length: Int): String {
        val previewLength = minOf(length, 32)
        return bytes.copyOf(previewLength).joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
    }
}
