package com.opennxt.net.http.endpoints

import com.opennxt.net.PreLoginForensics
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.DefaultFullHttpResponse
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpHeaderNames
import io.netty.handler.codec.http.HttpResponseStatus
import io.netty.handler.codec.http.HttpVersion
import io.netty.handler.codec.http.QueryStringDecoder
import mu.KotlinLogging
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Base64
import java.util.Locale
import java.util.regex.Pattern
import kotlin.io.path.createDirectories

object ClientErrorWsEndpoint {
    private val logger = KotlinLogging.logger { }

    private val clientErrorTimestamp: DateTimeFormatter =
        DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss", Locale.US).withZone(ZoneOffset.UTC)
    private val dataParamPattern: Pattern = Pattern.compile("(?:(?:^|&)data=)([^&]+)")

    @Volatile
    internal var outputDirectoryOverride: Path? = null

    private fun clientErrorDir(): Path =
        outputDirectoryOverride
            ?: Paths.get(System.getProperty("user.dir"))
                .resolve("data")
                .resolve("debug")
                .resolve("clienterror")
                .toAbsolutePath()
                .normalize()

    private data class ClientErrorArtifacts(
        val requestTarget: String?,
        val clientToken: String?,
        val clientReportedTimestamp: Instant?,
        val urlDecodedData: String?,
        val decodedBytes: ByteArray?,
        val decodeVariant: String?,
        val decodeError: String?,
    )

    private data class Base64DecodeResult(
        val bytes: ByteArray,
        val variant: String,
    )

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {
        val httpText = buildRawHttpText(msg)
        persistClientErrorReport(ctx.channel().remoteAddress().toString(), httpText)
        logger.info {
            "Accepted /nxtclienterror.ws POST from ${ctx.channel().remoteAddress()}: uri=${query.uri()}"
        }
        sendNoContent(ctx)
    }

    fun handleRawHttpText(ctx: ChannelHandlerContext, httpText: String) {
        persistClientErrorReport(ctx.channel().remoteAddress().toString(), httpText)
        sendRawNoContent(ctx)
    }

    internal fun persistClientErrorReport(
        remoteAddress: String,
        httpText: String,
        outputDirectory: Path = clientErrorDir(),
        now: Instant = Instant.now(),
    ) {
        try {
            outputDirectory.createDirectories()
            val stamp = clientErrorTimestamp.format(now)
            val remote = remoteAddress.replace('/', '_').replace(':', '-')
            val baseName = "nxtclienterror-$stamp-$remote"
            val rawPath = outputDirectory.resolve("$baseName.http.txt")
            Files.writeString(rawPath, httpText, StandardCharsets.ISO_8859_1)

            val artifacts = extractArtifacts(httpText)
            val httpBody = extractHttpBody(httpText)
            if (artifacts.urlDecodedData != null) {
                Files.writeString(
                    outputDirectory.resolve("$baseName.data.txt"),
                    artifacts.urlDecodedData,
                    StandardCharsets.UTF_8,
                )
            }
            if (artifacts.decodedBytes != null) {
                Files.write(outputDirectory.resolve("$baseName.decoded.bin"), artifacts.decodedBytes)
            } else if (artifacts.decodeError != null) {
                Files.writeString(
                    outputDirectory.resolve("$baseName.decode-error.txt"),
                    artifacts.decodeError,
                    StandardCharsets.UTF_8,
                )
            }

            val messageBytes = artifacts.decodedBytes?.copyOfRange(
                0,
                artifacts.decodedBytes.indexOfFirst { it == 0.toByte() }.let { if (it >= 0) it else artifacts.decodedBytes.size },
            ) ?: ByteArray(0)
            val summaryPath = outputDirectory.resolve("$baseName.summary.txt")
            Files.writeString(
                summaryPath,
                buildString {
                    appendLine("remote=$remoteAddress")
                    appendLine("timestamp=$now")
                    appendLine("requestTarget=${artifacts.requestTarget ?: "<unknown>"}")
                    appendLine("clientToken=${artifacts.clientToken ?: "<missing>"}")
                    appendLine("clientReportedTimestamp=${artifacts.clientReportedTimestamp ?: "<missing>"}")
                    appendLine("httpBodyLength=${httpBody.length}")
                    appendLine("decodeStatus=${when {
                        artifacts.urlDecodedData == null -> "missing-data"
                        artifacts.decodedBytes != null -> "success"
                        else -> "failed"
                    }}")
                    appendLine("decodeVariant=${artifacts.decodeVariant ?: "<none>"}")
                    appendLine("decodedBytes=${artifacts.decodedBytes?.size ?: 0}")
                    appendLine("message=${if (messageBytes.isEmpty()) "<none>" else messageBytes.toString(StandardCharsets.UTF_8)}")
                    appendLine("decodeError=${artifacts.decodeError ?: "<none>"}")
                },
                StandardCharsets.UTF_8,
            )
            PreLoginForensics.writeCorrelationSummary(
                outputPath = outputDirectory.resolve("$baseName.correlation.txt"),
                reportInstant = artifacts.clientReportedTimestamp,
                remoteAddress = remoteAddress,
                requestTarget = artifacts.requestTarget,
                now = now,
            )
            logger.warn { "Persisted nxtclienterror report to $summaryPath" }
        } catch (error: Exception) {
            logger.warn(error) { "Failed to persist nxtclienterror report from $remoteAddress" }
        }
    }

    internal fun buildRawHttpText(msg: FullHttpRequest): String {
        val bodyBytes = ByteArray(msg.content().readableBytes())
        msg.content().getBytes(msg.content().readerIndex(), bodyBytes)
        return buildString {
            append(msg.method().name())
            append(' ')
            append(msg.uri())
            append(' ')
            append(msg.protocolVersion().text())
            append("\r\n")
            for (header in msg.headers()) {
                append(header.key)
                append(": ")
                append(header.value)
                append("\r\n")
            }
            append("\r\n")
            append(bodyBytes.toString(StandardCharsets.ISO_8859_1))
        }
    }

    private fun sendNoContent(ctx: ChannelHandlerContext) {
        val response = DefaultFullHttpResponse(
            HttpVersion.HTTP_1_1,
            HttpResponseStatus.NO_CONTENT,
            Unpooled.EMPTY_BUFFER,
        )
        response.headers().set(HttpHeaderNames.CONTENT_LENGTH, 0)
        response.headers().set(HttpHeaderNames.CONNECTION, "close")
        ctx.writeAndFlush(response).addListener(ChannelFutureListener.CLOSE)
    }

    private fun sendRawNoContent(ctx: ChannelHandlerContext) {
        val bytes = "HTTP/1.1 204 No Content\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
            .toByteArray(StandardCharsets.ISO_8859_1)
        ctx.writeAndFlush(Unpooled.wrappedBuffer(bytes)).addListener(ChannelFutureListener.CLOSE)
    }

    private fun extractArtifacts(httpText: String): ClientErrorArtifacts {
        val requestTarget = extractRequestTarget(httpText)
        val query = requestTarget?.let { QueryStringDecoder(it) }
        val clientToken = query?.parameters()?.get("clientToken")?.firstOrNull()
        val clientReportedTimestamp = query?.parameters()?.get("timeStamp")?.firstOrNull()
            ?.toLongOrNull()
            ?.let(Instant::ofEpochMilli)
        val httpBody = extractHttpBody(httpText)
        val matcher = dataParamPattern.matcher(httpBody)
        if (!matcher.find()) {
            return ClientErrorArtifacts(
                requestTarget = requestTarget,
                clientToken = clientToken,
                clientReportedTimestamp = clientReportedTimestamp,
                urlDecodedData = null,
                decodedBytes = null,
                decodeVariant = null,
                decodeError = null,
            )
        }

        val encoded = matcher.group(1)
        val urlDecoded = URLDecoder.decode(encoded.replace("+", "%2B"), StandardCharsets.UTF_8)
        val decoded = runCatching { decodeBase64(urlDecoded) }
        return ClientErrorArtifacts(
            requestTarget = requestTarget,
            clientToken = clientToken,
            clientReportedTimestamp = clientReportedTimestamp,
            urlDecodedData = urlDecoded,
            decodedBytes = decoded.getOrNull()?.bytes,
            decodeVariant = decoded.getOrNull()?.variant,
            decodeError = decoded.exceptionOrNull()?.let { "${it::class.simpleName}: ${it.message}" },
        )
    }

    private fun extractRequestTarget(httpText: String): String? {
        val requestLine = httpText.lineSequence().firstOrNull()?.trim().orEmpty()
        if (requestLine.isBlank()) {
            return null
        }
        val parts = requestLine.split(' ')
        if (parts.size < 2) {
            return null
        }
        return parts[1]
    }

    private fun decodeBase64(value: String): Base64DecodeResult {
        val candidates = linkedMapOf<String, Pair<Base64.Decoder, String>>()
        fun addCandidate(name: String, decoder: Base64.Decoder, candidate: String) {
            candidates.putIfAbsent("$name::$candidate", decoder to candidate)
        }

        addCandidate("standard", Base64.getDecoder(), value)
        addCandidate("standard-padded", Base64.getDecoder(), padBase64(value))
        addCandidate("url-safe", Base64.getUrlDecoder(), value)
        addCandidate("url-safe-padded", Base64.getUrlDecoder(), padBase64(value))

        if (value.contains('*')) {
            val urlSafeAsterisk = value.replace('*', '_')
            addCandidate("url-safe-asterisk", Base64.getUrlDecoder(), urlSafeAsterisk)
            addCandidate("url-safe-asterisk-padded", Base64.getUrlDecoder(), padBase64(urlSafeAsterisk))

            val standardAsterisk = value.replace('*', '/')
            addCandidate("standard-asterisk", Base64.getDecoder(), standardAsterisk)
            addCandidate("standard-asterisk-padded", Base64.getDecoder(), padBase64(standardAsterisk))
        }

        var lastError: IllegalArgumentException? = null
        for ((key, attempt) in candidates) {
            val (decoder, candidate) = attempt
            try {
                return Base64DecodeResult(decoder.decode(candidate), key.substringBefore("::"))
            } catch (error: IllegalArgumentException) {
                lastError = error
            }
        }
        throw lastError ?: IllegalArgumentException("Unable to decode Base64 payload")
    }

    private fun padBase64(value: String): String {
        val remainder = value.length % 4
        return if (remainder == 0) value else value + "=".repeat(4 - remainder)
    }

    private fun extractHttpBody(httpText: String): String =
        when {
            httpText.contains("\r\n\r\n") -> httpText.substringAfter("\r\n\r\n", "")
            httpText.contains("\n\n") -> httpText.substringAfter("\n\n", "")
            else -> ""
        }
}
