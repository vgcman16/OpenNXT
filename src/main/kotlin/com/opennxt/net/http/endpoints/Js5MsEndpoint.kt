package com.opennxt.net.http.endpoints

import com.opennxt.OpenNXT
import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.FileChecker
import com.opennxt.net.http.sendHttpError
import com.opennxt.net.http.sendHttpFile
import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.*
import mu.KotlinLogging
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

object Js5MsEndpoint {
    private val logger = KotlinLogging.logger { }
    private const val CACHE_MAX_AGE_SECONDS = 25_920_000L
    private const val LAST_MODIFIED_OFFSET_SECONDS = 7L * 24L * 60L * 60L
    private const val UPSTREAM_MS_CONNECT_TIMEOUT_MILLIS = 5_000
    private const val UPSTREAM_MS_READ_TIMEOUT_MILLIS = 5_000
    private val HTTP_DATE_FORMATTER: DateTimeFormatter =
        DateTimeFormatter.ofPattern("EEE, dd-MMM-yyyy HH:mm:ss 'GMT'", Locale.US).withZone(ZoneOffset.UTC)

    internal data class ResolvedPayload(
        val data: ByteBuffer,
        val kind: String
    )

    internal data class UpstreamMsResponse(
        val bytes: ByteArray,
        val cookie: String? = null,
    )

    @Volatile
    internal var payloadResolver: (Int, Int) -> ResolvedPayload? = ::resolvePayload

    @Volatile
    internal var upstreamPayloadFetcher: (String, String?) -> UpstreamMsResponse? = ::fetchUpstreamPayload

    internal fun resetForTests() {
        payloadResolver = ::resolvePayload
        upstreamPayloadFetcher = ::fetchUpstreamPayload
    }

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {
        if (!query.parameters().containsKey("a") || !query.parameters().containsKey("g")) {
            logger.warn { "Rejecting /ms request with missing parameters: uri=${msg.uri()}" }
            ctx.sendHttpError(HttpResponseStatus.BAD_REQUEST)
            return
        }

        val index: Int = try {
            query.parameters().getValue("a").first().toInt()
        } catch (e: NumberFormatException) {
            ctx.sendHttpError(HttpResponseStatus.BAD_REQUEST)
            return
        }

        val archive: Int = try {
            query.parameters().getValue("g").first().toInt()
        } catch (e: NumberFormatException) {
            ctx.sendHttpError(HttpResponseStatus.BAD_REQUEST)
            return
        }

        val payload =
            payloadResolver(index, archive)
                ?: resolveRetailFallbackPayload(msg, index, archive)
        if (payload == null) {
            logger.warn {
                "Missing /ms payload for ${ctx.channel().remoteAddress()}: index=$index archive=$archive"
            }
            ctx.sendHttpError(HttpResponseStatus.NOT_FOUND)
            return
        }

        logger.info {
            "Serving /ms ${payload.kind} to ${ctx.channel().remoteAddress()}: " +
                "index=$index archive=$archive bytes=${payload.data.remaining()}"
        }
        sendFile(msg, ctx, Unpooled.wrappedBuffer(payload.data))
    }

    internal fun resolvePayload(index: Int, archive: Int): ResolvedPayload? {
        if (index == 255 && archive == 255) {
            return ResolvedPayload(ByteBuffer.wrap(OpenNXT.httpChecksumTable), "checksum-table")
        }

        if (index == 255) {
            val data = OpenNXT.filesystem.readReferenceTable(archive) ?: return null
            return ResolvedPayload(data, "reference-table")
        }

        val data = OpenNXT.filesystem.read(index, archive) ?: return null
        return ResolvedPayload(data, "archive")
    }

    private fun resolveRetailFallbackPayload(
        request: FullHttpRequest,
        index: Int,
        archive: Int,
    ): ResolvedPayload? {
        val upstreamUrl = buildRetailMsUrl(request.uri())
        val cookie = RetailUpstreamCookie.resolveMsCookie()
        val requestCookie = cookie.substringBefore(';').trim().takeIf { it.startsWith("JXADDINFO=") }
        val response = upstreamPayloadFetcher(upstreamUrl, requestCookie)
        if (response == null) {
            logger.warn {
                "Retail /ms fallback unavailable for index=$index archive=$archive url=$upstreamUrl"
            }
            return null
        }
        response.cookie?.let(RetailSessionCookie::noteCurrent)
        logger.info {
            "Using retail /ms fallback for index=$index archive=$archive bytes=${response.bytes.size} url=$upstreamUrl"
        }
        return ResolvedPayload(ByteBuffer.wrap(response.bytes), "retail-upstream")
    }

    internal fun buildRetailMsUrl(requestUri: String): String {
        val rawPath = requestUri.substringBefore('?')
        val canonicalPath = canonicalizePath(rawPath)
        val querySuffix = requestUri.substringAfter('?', "")
        return buildString {
            append("https://content.runescape.com")
            append(canonicalPath)
            if (querySuffix.isNotEmpty()) {
                append('?')
                append(querySuffix)
            }
        }
    }

    private fun canonicalizePath(path: String): String {
        var normalized = path
        while (true) {
            val next =
                when {
                    normalized.matches(Regex("^/(k|l)=[^/]+/.*$")) -> normalized.replaceFirst(Regex("^/(k|l)=[^/]+"), "")
                    normalized.matches(Regex("^/(k|l)=[^/]+$")) -> "/"
                    else -> null
                }
            normalized = next ?: break
        }
        return normalized
    }

    private fun fetchUpstreamPayload(url: String, cookie: String?): UpstreamMsResponse? {
        val connection = (URL(url).openConnection() as? HttpURLConnection) ?: return null
        connection.requestMethod = "GET"
        connection.connectTimeout = UPSTREAM_MS_CONNECT_TIMEOUT_MILLIS
        connection.readTimeout = UPSTREAM_MS_READ_TIMEOUT_MILLIS
        connection.setRequestProperty("Accept", "*/*")
        connection.setRequestProperty("Connection", "close")
        connection.setRequestProperty("User-Agent", "OpenNXT/1.0")
        if (!cookie.isNullOrBlank()) {
            connection.setRequestProperty("Cookie", cookie)
        }
        return try {
            val status = connection.responseCode
            if (status != HttpURLConnection.HTTP_OK) {
                logger.warn { "Retail /ms fetch returned status=$status for $url" }
                null
            } else {
                val body = connection.inputStream.use { input -> input.readBytes() }
                val responseCookie = connection.headerFields["Set-Cookie"]
                    .orEmpty()
                    .firstOrNull { it.startsWith("JXADDINFO=", ignoreCase = true) }
                UpstreamMsResponse(body, responseCookie)
            }
        } catch (e: Exception) {
            logger.warn(e) { "Failed to fetch retail /ms payload from $url" }
            null
        } finally {
            connection.disconnect()
        }
    }

    private fun sendFile(request: FullHttpRequest, ctx: ChannelHandlerContext, buf: ByteBuf) {
        val size = buf.readableBytes()
        val response = DefaultFullHttpResponse(request.protocolVersion(), HttpResponseStatus.OK, buf)
        val keepAlive = HttpUtil.isKeepAlive(request)
        val cookie = RetailUpstreamCookie.resolveMsCookie()
        applyRetailMsHeaders(
            response.headers(),
            size,
            keepAlive = keepAlive,
            cookie = cookie,
            requestHost = JavConfigWsEndpoint.effectiveCookieRequestHost(request.headers()),
        )

        val future = ctx.channel().writeAndFlush(response)
        if (!keepAlive) {
            future.addListener(ChannelFutureListener.CLOSE)
        }
    }

    internal fun applyRetailMsHeaders(
        headers: HttpHeaders,
        size: Int,
        now: Instant = Instant.now(),
        keepAlive: Boolean = true,
        cookie: String = RetailSessionCookie.current(),
        requestHost: String? = null,
    ) {
        val expiresAt = now.plusSeconds(CACHE_MAX_AGE_SECONDS)
        val lastModifiedAt = now.minusSeconds(LAST_MODIFIED_OFFSET_SECONDS)
        val formattedNow = HTTP_DATE_FORMATTER.format(now)
        val headerCookie = RetailSessionCookie.headerValueForRequest(cookie, requestHost)
        headers.set("Date", formattedNow)
        headers.set("Server", "JAGeX/3.1")
        headers.set("Content-type", "application/octet-stream")
        headers.set("Cache-control", "public, max-age=$CACHE_MAX_AGE_SECONDS")
        headers.set("Expires", HTTP_DATE_FORMATTER.format(expiresAt))
        headers.set("Last-modified", HTTP_DATE_FORMATTER.format(lastModifiedAt))
        headers.set("Set-Cookie", headerCookie)
        headers.set("Connection", if (keepAlive) "Keep-alive" else "close")
        headers.set("Content-length", size)
    }
}
