package com.opennxt.net.http.endpoints

import java.security.SecureRandom

internal object RetailSessionCookie {
    private const val JXADDINFO_PREFIX = "DBXPZaBPotHnzeZldoHBT"
    private const val JXADDINFO_SUFFIX_LENGTH = 18
    private const val RETAIL_COOKIE_DOMAIN_SUFFIX = "; domain=.runescape.com"
    private val domainAttributeRegex = Regex(""";\s*domain=[^;]+""", RegexOption.IGNORE_CASE)
    private val cookieRandom = SecureRandom()
    private val allowedDownloadMetadataSources = setOf("original", "patched", "compressed", "live")

    @Volatile
    private var cookie: String = buildCookie()

    @Volatile
    private var pinned: Boolean = false

    @Volatile
    private var downloadMetadataSource: String = ""

    fun current(): String = cookie

    fun isPinned(): Boolean = pinned

    fun pinCurrent(): String {
        pinned = true
        return cookie
    }

    fun noteCurrent(value: String?) {
        val normalized = value?.trim().orEmpty()
        if (normalized.startsWith("JXADDINFO=", ignoreCase = true)) {
            cookie = normalized
            pinned = true
        }
    }

    fun currentDownloadMetadataSource(defaultSource: String): String {
        val current = downloadMetadataSource.trim().lowercase()
        return current.takeIf { it in allowedDownloadMetadataSources } ?: defaultSource
    }

    fun noteDownloadMetadataSource(source: String?) {
        val normalized = source?.trim()?.lowercase().orEmpty()
        if (normalized in allowedDownloadMetadataSources) {
            downloadMetadataSource = normalized
        }
    }

    fun headerValueForRequest(cookie: String, requestHost: String?): String {
        val retailScopedCookie = ensureRetailCookieDomain(cookie)
        val normalizedHost = normalizeRequestHost(requestHost)
        if (!isLoopbackHost(normalizedHost)) {
            return retailScopedCookie
        }
        return domainAttributeRegex.replace(retailScopedCookie, "")
    }

    fun resetForTests() {
        cookie = buildCookie()
        pinned = false
        downloadMetadataSource = ""
    }

    private fun buildCookie(): String {
        val alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        val suffix = buildString(JXADDINFO_SUFFIX_LENGTH) {
            repeat(JXADDINFO_SUFFIX_LENGTH) {
                append(alphabet[cookieRandom.nextInt(alphabet.length)])
            }
        }
        return "JXADDINFO=$JXADDINFO_PREFIX$suffix; version=1; path=/$RETAIL_COOKIE_DOMAIN_SUFFIX"
    }

    private fun ensureRetailCookieDomain(rawCookie: String): String {
        val trimmed = rawCookie.trim()
        if (!trimmed.startsWith("JXADDINFO=", ignoreCase = true)) {
            return trimmed
        }
        if (domainAttributeRegex.containsMatchIn(trimmed)) {
            return trimmed
        }
        return trimmed + RETAIL_COOKIE_DOMAIN_SUFFIX
    }

    private fun normalizeRequestHost(rawHost: String?): String? {
        val trimmed = rawHost?.trim()?.lowercase()?.takeIf { it.isNotEmpty() } ?: return null
        if (trimmed.startsWith("[")) {
            return trimmed.substringAfter("[").substringBefore("]")
        }
        return if (trimmed.count { it == ':' } == 1) {
            trimmed.substringBefore(":")
        } else {
            trimmed
        }
    }

    private fun isLoopbackHost(host: String?): Boolean {
        return when (host) {
            null -> false
            "localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1" -> true
            else -> false
        }
    }
}
