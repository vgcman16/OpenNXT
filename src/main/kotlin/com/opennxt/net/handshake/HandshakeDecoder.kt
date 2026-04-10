package com.opennxt.net.handshake

import com.opennxt.net.PreLoginForensics
import com.opennxt.net.http.endpoints.ClientErrorWsEndpoint
import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.ByteToMessageDecoder
import mu.KotlinLogging
import java.io.ByteArrayOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.InetSocketAddress
import java.nio.charset.StandardCharsets
import java.util.Locale
import java.util.concurrent.Executors

class HandshakeDecoder: ByteToMessageDecoder() {
    val logger = KotlinLogging.logger {  }

    companion object {
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
        val localPort = (ctx.channel().localAddress() as? InetSocketAddress)?.port ?: -1
        val remoteAddress = ctx.channel().remoteAddress().toString()
        val previewLength = minOf(buf.readableBytes(), 32)
        val preview = ByteArray(previewLength)
        if (previewLength > 0) {
            buf.getBytes(buf.readerIndex(), preview)
        }
        val previewHex = preview.joinToString(" ") { "%02x".format(it.toInt() and 0xff) }
        val id = buf.readUnsignedByte().toInt()
        val type = HandshakeType.fromId(id)

        if (type == null) {
            val postIdPreviewLength = minOf(buf.readableBytes(), 32)
            val postIdPreview = ByteArray(postIdPreviewLength)
            if (postIdPreviewLength > 0) {
                buf.getBytes(buf.readerIndex(), postIdPreview)
            }
            val methodPrefix = buildString {
                append(id.toChar())
                append(postIdPreview.toString(StandardCharsets.ISO_8859_1))
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
                PreLoginForensics.recordTransportEvent(
                    localPort = localPort,
                    remoteAddress = remoteAddress,
                    event = "handshake-http-misroute",
                    details = mapOf(
                        "handshakeId" to id,
                        "previewHex" to previewHex,
                        "requestTarget" to extractHttpRequestTarget(httpText),
                    ),
                )

                if (httpText.contains("/nxtclienterror.ws")) {
                    ClientErrorWsEndpoint.handleRawHttpText(ctx, httpText)
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
                PreLoginForensics.recordTransportEvent(
                    localPort = localPort,
                    remoteAddress = remoteAddress,
                    event = "handshake-unknown",
                    details = mapOf(
                        "handshakeId" to id,
                        "previewHex" to previewHex,
                        "remainingBytes" to buf.readableBytes(),
                    ),
                )
            }

            ctx.close()
            buf.skipBytes(buf.readableBytes())
            return
        }

        logger.info { "Received handshake from ${ctx.channel().remoteAddress()} with type $type" }
        PreLoginForensics.recordTransportEvent(
            localPort = localPort,
            remoteAddress = remoteAddress,
            event = "handshake-detected",
            details = mapOf(
                "handshakeId" to id,
                "handshakeType" to type.name,
                "previewHex" to previewHex,
                "remainingBytes" to buf.readableBytes(),
            ),
        )
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
}
