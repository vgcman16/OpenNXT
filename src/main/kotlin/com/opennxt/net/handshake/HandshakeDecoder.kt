package com.opennxt.net.handshake

import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLDecoder
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.nio.charset.StandardCharsets
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Base64
import java.util.Locale
import java.util.concurrent.Executors
import java.util.regex.Pattern
import kotlin.io.path.createDirectories

class HandshakeDecoder: ByteToMessageDecoder() {
    val logger = KotlinLogging.logger {  }

    companion object {
        private val CLIENT_ERROR_DIR: Path =
            Paths.get(System.getProperty("user.dir"))
                .resolve("data")
                .resolve("debug")
                .resolve("clienterror")
                .toAbsolutePath()
                .normalize()
        private val CLIENT_ERROR_TIMESTAMP: DateTimeFormatter =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss", Locale.US).withZone(ZoneOffset.UTC)
        private val DATA_PARAM_PATTERN: Pattern = Pattern.compile("(?:(?:^|&)data=)([^&]+)")
        private val CLIENT_ERROR_RESPONSE: ByteArray =
            ("HTTP/1.1 204 No Content\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
                .toByteArray(StandardCharsets.ISO_8859_1)
        private val CONTENT_PROXY_EXECUTOR = Executors.newCachedThreadPool { runnable ->
            Thread(runnable, "handshake-ms-proxy").apply { isDaemon = true }
        }
        private val PROXIED_RESPONSE_HEADER_NAMES = listOf(
            "Content-Type",
            "Cache-Control",
            "Expires",
            "Last-Modified",
            "Set-Cookie",
            "Server",
        )

        internal fun extractHttpRequestTarget(httpText: String): String? {
            val requestLine = httpText.lineSequence().firstOrNull()?.trim().orEmpty()
            if (requestLine.isEmpty()) {
                return null
            }
            val parts = requestLine.split(' ')
            if (parts.size < 2) {
                return null
            }
            return parts[1]
        }

        internal fun shouldProxyMsHttpRequest(httpText: String): Boolean {
            val target = extractHttpRequestTarget(httpText) ?: return false
            return target.startsWith("/ms?")
        }
    }

    init {
        isSingleDecode = true
    }

    override fun decode(ctx: ChannelHandlerContext, buf: ByteBuf, out: MutableList<Any>) {
        val id = buf.readUnsignedByte().toInt()
        val type = HandshakeType.fromId(id)

        if (type == null) {
            val previewLength = minOf(buf.readableBytes(), 32)
            val preview = ByteArray(previewLength)
            buf.getBytes(buf.readerIndex(), preview)
            val previewHex = preview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
            val methodPrefix = buildString {
                append(id.toChar())
                append(preview.toString(StandardCharsets.ISO_8859_1))
            }

            if (methodPrefix.startsWith("POST ") || methodPrefix.startsWith("GET ") || methodPrefix.startsWith("HTTP/")) {
                val httpLength = minOf(buf.readableBytes() + 1, 4096)
                val httpBytes = ByteArray(httpLength)
                httpBytes[0] = id.toByte()
                buf.getBytes(buf.readerIndex(), httpBytes, 1, httpLength - 1)
                val httpText = httpBytes.toString(StandardCharsets.ISO_8859_1)
                logger.warn {
                    "Client from ${ctx.channel().remoteAddress()} attempted to handshake with unknown id: $id " +
                        "(remaining=${buf.readableBytes()}, preview=$previewHex)"
                }
                logger.warn {
                    "Plaintext HTTP reached HandshakeDecoder from ${ctx.channel().remoteAddress()}:\n$httpText"
                }

                if (httpText.contains("/nxtclienterror.ws")) {
                    recordClientErrorReport(ctx, httpText)
                    ctx.writeAndFlush(Unpooled.wrappedBuffer(CLIENT_ERROR_RESPONSE)).addListener {
                        ctx.close()
                    }
                    buf.skipBytes(buf.readableBytes())
                    return
                }

                if (shouldProxyMsHttpRequest(httpText)) {
                    proxyMsRequest(ctx, httpText)
                    buf.skipBytes(buf.readableBytes())
                    return
                }
            } else {
                logger.warn {
                    "Client from ${ctx.channel().remoteAddress()} attempted to handshake with unknown id: $id " +
                        "(remaining=${buf.readableBytes()}, preview=$previewHex)"
                }
            }

            ctx.close()
            buf.skipBytes(buf.readableBytes())
            return
        }

        logger.info { "Received handshake from ${ctx.channel().remoteAddress()} with type $type" }
        out.add(HandshakeRequest(type))
    }

    private fun proxyMsRequest(ctx: ChannelHandlerContext, httpText: String) {
        val target = extractHttpRequestTarget(httpText) ?: return
        logger.warn {
            "Proxying misrouted HTTP content request from ${ctx.channel().remoteAddress()} through handshake path: $target"
        }

        CONTENT_PROXY_EXECUTOR.execute {
            val responseBytes =
                try {
                    fetchMsResponse(httpText, target)
                } catch (error: Exception) {
                    logger.warn(error) {
                        "Failed to proxy misrouted HTTP content request from ${ctx.channel().remoteAddress()}: $target"
                    }
                    buildErrorHttpResponse(502, "Bad Gateway", "proxy-failed")
                }

            ctx.executor().execute {
                ctx.writeAndFlush(Unpooled.wrappedBuffer(responseBytes))
                    .addListener(ChannelFutureListener.CLOSE)
            }
        }
    }

    private fun fetchMsResponse(httpText: String, target: String): ByteArray {
        val requestLines = httpText.split("\r\n")
        val requestMethod = requestLines.firstOrNull()?.substringBefore(' ')?.ifBlank { "GET" } ?: "GET"
        val connection = URL("https", "content.runescape.com", target).openConnection() as HttpURLConnection
        connection.requestMethod = requestMethod
        connection.instanceFollowRedirects = false
        connection.connectTimeout = 5000
        connection.readTimeout = 15000
        connection.doInput = true

        for (line in requestLines.drop(1)) {
            if (line.isBlank() || ':' !in line) {
                continue
            }
            val (name, rawValue) = line.split(':', limit = 2)
            val value = rawValue.trim()
            when (name.trim().lowercase(Locale.US)) {
                "host", "connection", "content-length" -> Unit
                else -> connection.setRequestProperty(name.trim(), value)
            }
        }

        val statusCode = connection.responseCode
        val statusMessage = connection.responseMessage ?: "OK"
        val body =
            (if (statusCode >= 400) connection.errorStream else connection.inputStream)
                ?.use { it.readBytes() }
                ?: ByteArray(0)

        val headers = linkedMapOf<String, MutableList<String>>()
        for (headerName in PROXIED_RESPONSE_HEADER_NAMES) {
            val values = connection.headerFields[headerName]
            if (!values.isNullOrEmpty()) {
                headers[headerName] = values.toMutableList()
            }
        }
        val contentType = connection.contentType
        if (!contentType.isNullOrBlank()) {
            headers.getOrPut("Content-Type") { mutableListOf() }.apply {
                clear()
                add(contentType)
            }
        }

        return buildHttpResponse(statusCode, statusMessage, headers, body)
    }

    private fun buildErrorHttpResponse(statusCode: Int, statusMessage: String, bodyText: String): ByteArray {
        val body = bodyText.toByteArray(StandardCharsets.ISO_8859_1)
        return buildHttpResponse(
            statusCode = statusCode,
            statusMessage = statusMessage,
            headers = linkedMapOf("Content-Type" to mutableListOf("text/plain; charset=ISO-8859-1")),
            body = body,
        )
    }

    private fun buildHttpResponse(
        statusCode: Int,
        statusMessage: String,
        headers: Map<String, List<String>>,
        body: ByteArray,
    ): ByteArray {
        val output = ByteArrayOutputStream()
        val headerText = buildString {
            append("HTTP/1.1 ")
            append(statusCode)
            append(' ')
            append(statusMessage)
            append("\r\n")
            for ((name, values) in headers) {
                for (value in values) {
                    append(name)
                    append(": ")
                    append(value)
                    append("\r\n")
                }
            }
            append("Connection: close\r\n")
            append("Content-Length: ")
            append(body.size)
            append("\r\n\r\n")
        }
        output.write(headerText.toByteArray(StandardCharsets.ISO_8859_1))
        output.write(body)
        return output.toByteArray()
    }

    private fun recordClientErrorReport(ctx: ChannelHandlerContext, httpText: String) {
        try {
            CLIENT_ERROR_DIR.createDirectories()
            val stamp = CLIENT_ERROR_TIMESTAMP.format(Instant.now())
            val remote = ctx.channel().remoteAddress().toString()
                .replace('/', '_')
                .replace(':', '-')
            val baseName = "nxtclienterror-$stamp-$remote"
            val rawPath = CLIENT_ERROR_DIR.resolve("$baseName.http.txt")
            Files.writeString(rawPath, httpText, StandardCharsets.ISO_8859_1)

            val httpBody = extractHttpBody(httpText)
            val matcher = DATA_PARAM_PATTERN.matcher(httpBody)
            if (!matcher.find()) {
                Files.writeString(
                    CLIENT_ERROR_DIR.resolve("$baseName.summary.txt"),
                    buildString {
                        appendLine("remote=${ctx.channel().remoteAddress()}")
                        appendLine("timestamp=${Instant.now()}")
                        appendLine("decodedBytes=0")
                        appendLine("message=<missing data= body>")
                        appendLine("httpBodyLength=${httpBody.length}")
                    },
                    StandardCharsets.UTF_8
                )
                logger.warn {
                    "Persisted raw nxtclienterror request without data body at $rawPath"
                }
                return
            }

            val encoded = matcher.group(1)
            val urlDecoded = URLDecoder.decode(encoded.replace("+", "%2B"), StandardCharsets.UTF_8)
            val decoded = Base64.getDecoder().decode(urlDecoded)
            val decodedPath = CLIENT_ERROR_DIR.resolve("$baseName.decoded.bin")
            Files.write(decodedPath, decoded)

            val summaryText = buildString {
                appendLine("remote=${ctx.channel().remoteAddress()}")
                appendLine("timestamp=${Instant.now()}")
                appendLine("decodedBytes=${decoded.size}")
                appendLine(
                    "message=" +
                        decoded
                            .copyOfRange(0, decoded.indexOfFirst { it == 0.toByte() }.let { if (it >= 0) it else decoded.size })
                            .toString(StandardCharsets.UTF_8)
                )
            }
            val summaryPath = CLIENT_ERROR_DIR.resolve("$baseName.summary.txt")
            Files.writeString(summaryPath, summaryText, StandardCharsets.UTF_8)
            logger.warn {
                "Persisted nxtclienterror report to $summaryPath"
            }
        } catch (error: Exception) {
            logger.warn(error) { "Failed to persist nxtclienterror report from ${ctx.channel().remoteAddress()}" }
        }
    }

    private fun extractHttpBody(httpText: String): String {
        return when {
            httpText.contains("\r\n\r\n") -> httpText.substringAfter("\r\n\r\n", "")
            httpText.contains("\n\n") -> httpText.substringAfter("\n\n", "")
            else -> ""
        }
    }
}
