package com.opennxt.net.http.endpoints

import com.opennxt.OpenNXT
import com.opennxt.model.files.BinaryType
import mu.KotlinLogging
import java.net.URL

internal object RetailUpstreamCookie {
    private val logger = KotlinLogging.logger { }
    private const val MS_COOKIE_CACHE_MILLIS = 60_000L
    private const val CONNECT_TIMEOUT_MILLIS = 5_000
    private const val READ_TIMEOUT_MILLIS = 5_000

    private data class CachedCookie(
        val loadedAt: Long,
        val value: String,
    )

    @Volatile
    internal var cookieFetcher: (String) -> List<String> = { url ->
        val connection = URL(url).openConnection().apply {
            connectTimeout = CONNECT_TIMEOUT_MILLIS
            readTimeout = READ_TIMEOUT_MILLIS
            setRequestProperty("User-Agent", "OpenNXT/1.0")
        }
        connection.getInputStream().use { stream ->
            while (stream.read() != -1) {
                // Drain the body so HTTPS servers reliably finalize headers/cookies.
            }
        }
        connection.headerFields["Set-Cookie"].orEmpty()
    }

    @Volatile
    private var cachedCookiesByUrl: Map<String, CachedCookie> = emptyMap()
    private val cookieCacheLock = Any()

    internal fun resetForTests() {
        cookieFetcher = { url ->
            val connection = URL(url).openConnection().apply {
                connectTimeout = CONNECT_TIMEOUT_MILLIS
                readTimeout = READ_TIMEOUT_MILLIS
                setRequestProperty("User-Agent", "OpenNXT/1.0")
            }
            connection.getInputStream().use { stream ->
                while (stream.read() != -1) {
                    // Drain the body so HTTPS servers reliably finalize headers/cookies.
                }
            }
            connection.headerFields["Set-Cookie"].orEmpty()
        }
        cachedCookiesByUrl = emptyMap()
    }

    fun resolveJavConfigCookie(sourceUrl: String?, type: BinaryType): String {
        if (RetailSessionCookie.isPinned()) {
            return RetailSessionCookie.current()
        }
        val resolved = if (sourceUrl.isNullOrBlank()) {
            RetailSessionCookie.current()
        } else {
            val resolvedUrl = ensureBinaryTypeQuery(sourceUrl, type)
            currentCachedCookie(resolvedUrl)
                ?: fetchAndCacheCookie(resolvedUrl)
                ?: RetailSessionCookie.current()
        }
        RetailSessionCookie.noteCurrent(resolved)
        return RetailSessionCookie.current()
    }

    fun resolveMsCookie(): String {
        if (RetailSessionCookie.isPinned()) {
            return RetailSessionCookie.current()
        }

        val sourceUrl = buildMsCookieUrl()
        val resolved =
            currentCachedCookie(sourceUrl)
                ?: fetchAndCacheCookie(sourceUrl)
                ?: RetailSessionCookie.current()
        RetailSessionCookie.noteCurrent(resolved)
        if (!RetailSessionCookie.isPinned()) {
            RetailSessionCookie.pinCurrent()
        }
        return RetailSessionCookie.current()
    }

    private fun buildMsCookieUrl(): String {
        val build = OpenNXT.config.build
        return "https://content.runescape.com/ms?m=0&a=255&k=$build&g=255&c=0&v=0"
    }

    private fun ensureBinaryTypeQuery(sourceUrl: String, type: BinaryType): String {
        val normalized = sourceUrl.trim()
        if (normalized.contains("binaryType=", ignoreCase = true)) {
            return normalized
        }
        val separator = if (normalized.contains("?")) "&" else "?"
        return "$normalized${separator}binaryType=${type.id}"
    }

    private fun currentCachedCookie(sourceUrl: String): String? {
        val now = System.currentTimeMillis()
        val cached = cachedCookiesByUrl[sourceUrl]
        return cached?.takeIf { now - it.loadedAt < MS_COOKIE_CACHE_MILLIS }?.value
    }

    fun noteJavConfigCookie(sourceUrl: String?, type: BinaryType, value: String?) {
        if (sourceUrl.isNullOrBlank() || value.isNullOrBlank()) {
            return
        }
        noteCookie(ensureBinaryTypeQuery(sourceUrl, type), value)
    }

    private fun noteCookie(sourceUrl: String, value: String) {
        cachedCookiesByUrl = cachedCookiesByUrl + (sourceUrl to CachedCookie(System.currentTimeMillis(), value))
    }

    private fun fetchAndCacheCookie(sourceUrl: String): String? {
        synchronized(cookieCacheLock) {
            currentCachedCookie(sourceUrl)?.let { return it }

            val lockedNow = System.currentTimeMillis()
            val fetched = fetchCookie(sourceUrl)
            if (fetched != null) {
                cachedCookiesByUrl = cachedCookiesByUrl + (sourceUrl to CachedCookie(lockedNow, fetched))
                return fetched
            }

            return null
        }
    }

    private fun fetchCookie(sourceUrl: String): String? {
        return try {
            cookieFetcher(sourceUrl)
                .firstOrNull { it.startsWith("JXADDINFO=", ignoreCase = true) }
        } catch (e: Exception) {
            logger.warn(e) { "Failed to fetch retail session cookie from $sourceUrl; using fallback cookie" }
            null
        }
    }
}
