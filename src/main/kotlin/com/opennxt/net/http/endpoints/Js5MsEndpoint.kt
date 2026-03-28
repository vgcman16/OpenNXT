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
import java.nio.ByteBuffer
import java.security.SecureRandom
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

object Js5MsEndpoint {
    private val logger = KotlinLogging.logger { }
    private const val CACHE_MAX_AGE_SECONDS = 25_920_000L
    private const val LAST_MODIFIED_OFFSET_SECONDS = 7L * 24L * 60L * 60L
    private const val JXADDINFO_PREFIX = "DBXPZaBPotHnzeZldoHBT"
    private const val JXADDINFO_SUFFIX_LENGTH = 18
    private val HTTP_DATE_FORMATTER: DateTimeFormatter =
        DateTimeFormatter.ofPattern("EEE, dd-MMM-yyyy HH:mm:ss 'GMT'", Locale.US).withZone(ZoneOffset.UTC)
    private val cookieRandom = SecureRandom()
    private val sessionCookie = buildSessionCookie()

    internal data class ResolvedPayload(
        val data: ByteBuffer,
        val kind: String
    )

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

        val payload = resolvePayload(index, archive)
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

    private fun sendFile(request: FullHttpRequest, ctx: ChannelHandlerContext, buf: ByteBuf) {
        val size = buf.readableBytes()
        val response = DefaultFullHttpResponse(request.protocolVersion(), HttpResponseStatus.OK, buf)
        val keepAlive = HttpUtil.isKeepAlive(request)
        applyRetailMsHeaders(response.headers(), size, keepAlive = keepAlive)

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
    ) {
        val expiresAt = now.plusSeconds(CACHE_MAX_AGE_SECONDS)
        val lastModifiedAt = now.minusSeconds(LAST_MODIFIED_OFFSET_SECONDS)
        val formattedNow = HTTP_DATE_FORMATTER.format(now)
        headers.set("Date", formattedNow)
        headers.set("Server", "JAGeX/3.1")
        headers.set("Content-type", "application/octet-stream")
        headers.set("Cache-control", "public, max-age=$CACHE_MAX_AGE_SECONDS")
        headers.set("Expires", HTTP_DATE_FORMATTER.format(expiresAt))
        headers.set("Last-modified", HTTP_DATE_FORMATTER.format(lastModifiedAt))
        headers.set("Set-Cookie", sessionCookie)
        headers.set("Connection", if (keepAlive) "Keep-alive" else "close")
        headers.set("Content-length", size)
    }

    private fun buildSessionCookie(): String {
        val alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        val suffix = buildString(JXADDINFO_SUFFIX_LENGTH) {
            repeat(JXADDINFO_SUFFIX_LENGTH) {
                append(alphabet[cookieRandom.nextInt(alphabet.length)])
            }
        }
        return "JXADDINFO=$JXADDINFO_PREFIX$suffix; version=1; path=/; domain=.runescape.com"
    }
}
