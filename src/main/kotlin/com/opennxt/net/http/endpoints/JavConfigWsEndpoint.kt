package com.opennxt.net.http.endpoints

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.ClientConfig
import com.opennxt.model.files.FileChecker
import io.netty.buffer.Unpooled
import io.netty.channel.ChannelFutureListener
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.DefaultFullHttpResponse
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.HttpHeaders
import io.netty.handler.codec.http.HttpHeaderNames
import io.netty.handler.codec.http.HttpResponseStatus
import io.netty.handler.codec.http.HttpUtil
import io.netty.handler.codec.http.HttpVersion
import io.netty.handler.codec.http.QueryStringDecoder
import mu.KotlinLogging
import java.net.URI
import java.net.URLEncoder
import java.net.URL
import java.nio.file.Path
import java.nio.file.Paths
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.Locale

object JavConfigWsEndpoint {
    private val logger = KotlinLogging.logger { }
    private const val LOCAL_PROXY_HOST = "localhost"
    private const val LOCAL_GAME_HOST = "127.0.0.1"
    private const val LOCAL_CONTENT_HOST = LOCAL_PROXY_HOST
    private const val LOCAL_CODEBASE_SCHEME = "http"
    internal const val ORIGINAL_HOST_HEADER = "X-OpenNXT-Original-Host"
    private const val LIVE_JAV_CONFIG_URL = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws"
    private const val LIVE_CONFIG_CACHE_MILLIS = 60_000L
    private const val LIVE_CONFIG_CONNECT_TIMEOUT_MILLIS = 5_000
    private const val LIVE_CONFIG_READ_TIMEOUT_MILLIS = 5_000
    private const val EXPIRES_EPOCH_GMT = "Thu, 01-Jan-1970 00:00:00 GMT"
    private val CONTENT_ROUTE_PARAMS = listOf(37, 49)
    private val WORLD_ROUTE_PARAMS = listOf(35, 40)
    private val WORLD_HOST_PATTERN = Regex("^world[0-9]+[a-z]*\\.runescape\\.com$")
    private val LOCAL_ONLY_WORLD_QUERY_KEYS = setOf(
        "baseConfigPath",
        "baseConfigSnapshotPath",
        "baseConfigSource",
        "binaryType",
        "codebaseRewrite",
        "contentRouteRewrite",
        "downloadMetadataSource",
        "gameHostOverride",
        "gameHostRewrite",
        "gamePortOverride",
        "hostRewrite",
        "lobbyHostRewrite",
        "liveCache",
        "localRewrite",
        "requestedWorldHost",
        "worldUrlRewrite",
    )
    private val HTTP_DATE_FORMATTER: DateTimeFormatter =
        DateTimeFormatter.ofPattern("EEE, dd-MMM-yyyy HH:mm:ss 'GMT'", Locale.US).withZone(ZoneOffset.UTC)

    private data class CachedConfig(val loadedAt: Long, val config: ClientConfig, val cookie: String?)
    internal data class LiveConfigResponse(val config: ClientConfig, val cookie: String?)
    internal data class PreparedJavConfig(
        val config: ClientConfig,
        val source: String,
        val localRewrite: Boolean,
        val hostRewrite: Boolean,
        val contentRouteRewrite: Boolean,
        val worldUrlRewrite: Boolean,
        val codebaseRewrite: Boolean,
        val lobbyHostRewrite: Boolean,
        val gameHostOverride: String?,
        val gamePortOverride: Int?,
        val downloadMetadataSource: String
    )

    internal data class RewriteDecisions(
        val localRewrite: Boolean,
        val hostRewrite: Boolean,
        val contentRouteRewrite: Boolean,
        val worldUrlRewrite: Boolean,
        val codebaseRewrite: Boolean,
        val lobbyHostRewrite: Boolean,
    )

    @Volatile
    private var cachedLiveConfigByKey: Map<String, CachedConfig> = emptyMap()
    private val liveConfigCacheLock = Any()

    internal var liveConfigResponseFetcher: (String, BinaryType) -> LiveConfigResponse = { url, type ->
        val resolvedUrl = ensureBinaryTypeQuery(url, type)
        val connection = URL(resolvedUrl).openConnection().apply {
            connectTimeout = LIVE_CONFIG_CONNECT_TIMEOUT_MILLIS
            readTimeout = LIVE_CONFIG_READ_TIMEOUT_MILLIS
            setRequestProperty("User-Agent", "OpenNXT/1.0")
        }
        val body = connection.getInputStream().use { stream ->
            stream.readBytes().toString(Charsets.ISO_8859_1)
        }
        val cookie = connection.headerFields["Set-Cookie"]
            .orEmpty()
            .firstOrNull { it.startsWith("JXADDINFO=", ignoreCase = true) }
        LiveConfigResponse(
            config = ClientConfig.parse(body),
            cookie = cookie,
        )
    }

    internal fun resetLiveConfigCacheForTests() {
        synchronized(liveConfigCacheLock) {
            cachedLiveConfigByKey = emptyMap()
        }
        liveConfigResponseFetcher = { url, type ->
            val resolvedUrl = ensureBinaryTypeQuery(url, type)
            val connection = URL(resolvedUrl).openConnection().apply {
                connectTimeout = LIVE_CONFIG_CONNECT_TIMEOUT_MILLIS
                readTimeout = LIVE_CONFIG_READ_TIMEOUT_MILLIS
                setRequestProperty("User-Agent", "OpenNXT/1.0")
            }
            val body = connection.getInputStream().use { stream ->
                stream.readBytes().toString(Charsets.ISO_8859_1)
            }
            val cookie = connection.headerFields["Set-Cookie"]
                .orEmpty()
                .firstOrNull { it.startsWith("JXADDINFO=", ignoreCase = true) }
            LiveConfigResponse(
                config = ClientConfig.parse(body),
                cookie = cookie,
            )
        }
        RetailSessionCookie.resetForTests()
        StartupContractHints.resetForTests()
        RetailUpstreamCookie.resetForTests()
    }

    private fun ensureBinaryTypeQuery(sourceUrl: String, type: BinaryType): String {
        val normalized = sourceUrl.trim()
        if (normalized.contains("binaryType=", ignoreCase = true)) {
            return normalized
        }
        val separator = if (normalized.contains("?")) "&" else "?"
        return "$normalized${separator}binaryType=${type.id}"
    }

    private fun shouldUse947Win64SplashDefaults(type: BinaryType): Boolean {
        return OpenNXT.config.build >= 947 && (type == BinaryType.WIN64 || type == BinaryType.WIN64C)
    }

    private fun shouldForce947DownloadMetadata(type: BinaryType): Boolean {
        return OpenNXT.config.build >= 947 && (type == BinaryType.WIN64 || type == BinaryType.WIN64C)
    }

    private fun resolveImplicitDownloadMetadataSource(type: BinaryType): String {
        return if (shouldForce947DownloadMetadata(type)) {
            "patched"
        } else {
            ""
        }
    }

    private fun shouldUse947BundledBaseConfig(type: BinaryType): Boolean {
        return OpenNXT.config.build >= 947 && (type == BinaryType.WIN64 || type == BinaryType.WIN64C)
    }

    private fun hasExplicitQueryParameter(query: QueryStringDecoder, name: String): Boolean {
        return !query.parameters()[name]?.firstOrNull()?.trim().isNullOrEmpty()
    }

    private val LIVE_STARTUP_SESSION_PARAMS = listOf(2, 18, 27, 29, 31, 34, 57)
    private val LIVE_STARTUP_ROUTE_PARAMS = listOf(3, 35, 37, 40, 49)
    private val LIVE_STARTUP_TOP_LEVEL_KEYS = listOf("codebase")

    private fun applyLocalPortRewrite(config: ClientConfig, gamePort: Int) {
        for (param in listOf(41, 43, 45, 47)) {
            config["param=$param"] = gamePort.toString()
        }
    }

    private fun applyLocalHostRewrite(config: ClientConfig, rewriteLobbyHost: Boolean) {
        val params = mutableListOf(37, 49)
        if (rewriteLobbyHost) {
            params += 3
        }

        for (param in params) {
            config["param=$param"] = LOCAL_PROXY_HOST
        }
    }

    private fun applyContentRouteRewrite(config: ClientConfig) {
        for (param in CONTENT_ROUTE_PARAMS) {
            config["param=$param"] = LOCAL_CONTENT_HOST
        }
    }

    private fun buildRewrittenBaseUrl(
        scheme: String,
        host: String,
        port: Int?,
        path: String,
    ): String {
        val normalizedPort = port ?: -1
        return try {
            URI(
                scheme,
                null,
                host,
                normalizedPort,
                path,
                null,
                null
            ).toString()
        } catch (_: Exception) {
            val portSuffix = if (normalizedPort >= 0) ":$normalizedPort" else ""
            "$scheme://$host$portSuffix$path"
        }
    }

    internal fun rewriteBaseUrlPreservingPath(
        original: String?,
        ensureTrailingSlash: Boolean,
        scheme: String = LOCAL_CODEBASE_SCHEME,
        host: String = LOCAL_PROXY_HOST,
        port: Int? = OpenNXT.config.ports.http,
    ): String {
        val fallbackPath = if (ensureTrailingSlash) "/" else ""
        if (original.isNullOrBlank()) {
            return buildRewrittenBaseUrl(scheme, host, port, fallbackPath)
        }

        return try {
            val uri = URI(original)
            val preservedPath = when {
                uri.path.isNullOrBlank() -> fallbackPath
                ensureTrailingSlash && !uri.path.endsWith("/") -> "${uri.path}/"
                !ensureTrailingSlash && uri.path.endsWith("/") && uri.path.length > 1 -> uri.path.removeSuffix("/")
                else -> uri.path
            }
            val path = if (preservedPath.isBlank()) fallbackPath else preservedPath
            buildRewrittenBaseUrl(scheme, host, port, path)
        } catch (_: Exception) {
            buildRewrittenBaseUrl(scheme, host, port, fallbackPath)
        }
    }

    private fun applyLocalWorldUrlRewrite(config: ClientConfig) {
        for (param in WORLD_ROUTE_PARAMS) {
            config["param=$param"] = rewriteBaseUrlPreservingPath(config["param=$param"], ensureTrailingSlash = false)
        }
    }

    private fun applyGameHostOverride(config: ClientConfig, host: String) {
        config["param=3"] = host
    }

    private fun applyLocalCodebaseRewrite(config: ClientConfig) {
        val codebase = rewriteBaseUrlPreservingPath(config["codebase"], ensureTrailingSlash = true)
        config["codebase"] = codebase
    }

    internal fun normalizeRequestedWorldHost(rawHost: String?): String? {
        val trimmed = rawHost?.trim()?.lowercase() ?: return null
        if (trimmed.isEmpty()) {
            return null
        }
        val withoutPort = when {
            trimmed.startsWith("[") -> trimmed.substringBefore("]").removePrefix("[")
            trimmed.count { it == ':' } == 1 -> trimmed.substringBefore(":")
            else -> trimmed
        }
        return withoutPort.takeIf { WORLD_HOST_PATTERN.matches(it) }
    }

    internal fun extractRequestedWorldHost(msg: FullHttpRequest, query: QueryStringDecoder? = null): String? {
        return normalizeRequestedWorldHost(msg.headers().get(ORIGINAL_HOST_HEADER))
            ?: normalizeRequestedWorldHost(msg.headers().get(HttpHeaderNames.HOST))
            ?: normalizeRequestedWorldHost(query?.parameters()?.get("requestedWorldHost")?.firstOrNull())
    }

    internal fun applyRequestedWorldHostRewrite(config: ClientConfig, worldHost: String) {
        config["param=3"] = worldHost
        for (param in WORLD_ROUTE_PARAMS) {
            config["param=$param"] = rewriteBaseUrlPreservingPath(
                config["param=$param"],
                ensureTrailingSlash = false,
                scheme = "https",
                host = worldHost,
                port = null,
            )
        }
        config["codebase"] = rewriteBaseUrlPreservingPath(
            config["codebase"],
            ensureTrailingSlash = true,
            scheme = "https",
            host = worldHost,
            port = null,
        )
    }

    private fun clearDownloadMetadata(config: ClientConfig) {
        config.entries.remove("download")
        config.getFiles().map { it.id }.forEach { id ->
            config.entries.remove("download_name_$id")
            config.entries.remove("download_crc_$id")
            config.entries.remove("download_hash_$id")
        }
    }

    private fun applyDownloadMetadata(config: ClientConfig, sourceConfig: ClientConfig) {
        clearDownloadMetadata(config)
        sourceConfig.entries.forEach { (key, value) ->
            if (
                key == "download" ||
                key.startsWith("download_name_") ||
                key.startsWith("download_crc_") ||
                key.startsWith("download_hash_")
            ) {
                config[key] = value
            }
        }
    }

    private fun applyDownloadMetadata(config: ClientConfig, type: BinaryType, folder: String) {
        val sourceConfig = FileChecker.getConfig(folder, type) ?: return
        applyDownloadMetadata(config, sourceConfig)
    }

    private fun copyOf(config: ClientConfig): ClientConfig = ClientConfig(config.entries.toMutableMap())

    private fun shouldApplyLocalRewrite(query: QueryStringDecoder): Boolean {
        val flag = query.parameters()["localRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            null, "", "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
        }
    }

    private fun shouldRewriteCodebase(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["codebaseRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            null, "" -> !shouldUse947Win64SplashDefaults(type)
            "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
        }
    }

    private fun shouldRewriteLobbyHost(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["lobbyHostRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            null, "" -> !shouldUse947Win64SplashDefaults(type)
            "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
        }
    }

    private fun shouldRewriteHost(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["hostRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            null, "" -> !shouldUse947Win64SplashDefaults(type)
            "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
        }
    }

    private fun shouldRewriteContentRoute(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["contentRouteRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            null, "" -> !shouldUse947Win64SplashDefaults(type)
            "0", "false", "no", "off" -> false
            "1", "true", "yes", "on" -> true
            else -> true
        }
    }

    private fun shouldRewriteWorldUrls(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["worldUrlRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            null, "" -> false
            "0", "false", "no", "off" -> false
            "1", "true", "yes", "on" -> true
            else -> true
        }
    }

    internal fun resolveRewriteDecisions(
        query: QueryStringDecoder,
        type: BinaryType,
        useStartupContractHints: Boolean = false,
    ): RewriteDecisions {
        val hint = if (useStartupContractHints) StartupContractHints.latestRewriteContract(type) else null
        return RewriteDecisions(
            localRewrite = resolveLocalRewriteFlag(query, hint),
            hostRewrite = resolveHostRewriteFlag(query, type, hint),
            contentRouteRewrite = resolveContentRouteRewriteFlag(query, type, hint),
            worldUrlRewrite = resolveWorldUrlRewriteFlag(query, type, hint),
            codebaseRewrite = resolveCodebaseRewriteFlag(query, type, hint),
            lobbyHostRewrite = resolveLobbyHostRewriteFlag(query, type, hint),
        )
    }

    private fun resolveLocalRewriteFlag(
        query: QueryStringDecoder,
        hint: StartupContractHints.StartupRewriteContract?,
    ): Boolean = resolveFlagWithHint(
        rawFlag = query.parameters()["localRewrite"]?.firstOrNull()?.trim()?.lowercase(),
        defaultValue = true,
        hintedValue = hint?.localRewrite,
    )

    private fun resolveCodebaseRewriteFlag(
        query: QueryStringDecoder,
        type: BinaryType,
        hint: StartupContractHints.StartupRewriteContract?,
    ): Boolean = resolveFlagWithHint(
        rawFlag = query.parameters()["codebaseRewrite"]?.firstOrNull()?.trim()?.lowercase(),
        defaultValue = !shouldUse947Win64SplashDefaults(type),
        hintedValue = hint?.codebaseRewrite,
    )

    private fun resolveLobbyHostRewriteFlag(
        query: QueryStringDecoder,
        type: BinaryType,
        hint: StartupContractHints.StartupRewriteContract?,
    ): Boolean = resolveFlagWithHint(
        rawFlag = query.parameters()["lobbyHostRewrite"]?.firstOrNull()?.trim()?.lowercase(),
        defaultValue = !shouldUse947Win64SplashDefaults(type),
        hintedValue = hint?.lobbyHostRewrite,
    )

    private fun resolveHostRewriteFlag(
        query: QueryStringDecoder,
        type: BinaryType,
        hint: StartupContractHints.StartupRewriteContract?,
    ): Boolean = resolveFlagWithHint(
        rawFlag = query.parameters()["hostRewrite"]?.firstOrNull()?.trim()?.lowercase(),
        defaultValue = !shouldUse947Win64SplashDefaults(type),
        hintedValue = hint?.hostRewrite,
    )

    private fun resolveContentRouteRewriteFlag(
        query: QueryStringDecoder,
        type: BinaryType,
        hint: StartupContractHints.StartupRewriteContract?,
    ): Boolean = resolveFlagWithHint(
        rawFlag = query.parameters()["contentRouteRewrite"]?.firstOrNull()?.trim()?.lowercase(),
        defaultValue = !shouldUse947Win64SplashDefaults(type),
        hintedValue = hint?.contentRouteRewrite,
    )

    private fun resolveWorldUrlRewriteFlag(
        query: QueryStringDecoder,
        type: BinaryType,
        hint: StartupContractHints.StartupRewriteContract?,
    ): Boolean = resolveFlagWithHint(
        rawFlag = query.parameters()["worldUrlRewrite"]?.firstOrNull()?.trim()?.lowercase(),
        defaultValue = false,
        hintedValue = hint?.worldUrlRewrite,
    )

    private fun resolveFlagWithHint(
        rawFlag: String?,
        defaultValue: Boolean,
        hintedValue: Boolean?,
    ): Boolean {
        return when (rawFlag) {
            null, "" -> hintedValue ?: defaultValue
            "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
        }
    }

    internal fun shouldUseLiveConfigCache(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["liveCache"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            "0", "false", "no", "off" -> false
            "1", "true", "yes", "on" -> true
            else -> !(OpenNXT.config.build >= 947 && (type == BinaryType.WIN64C || type == BinaryType.WIN64))
        }
    }

    private fun shouldUseSticky947StartupSessionCache(
        query: QueryStringDecoder,
        type: BinaryType,
        baseConfigSource: String,
        liveConfigUrlOverride: String?,
    ): Boolean {
        if (!shouldUse947BundledBaseConfig(type)) {
            return false
        }
        if (liveConfigUrlOverride != null) {
            return false
        }
        if (baseConfigSource == "live") {
            return false
        }
        return !hasExplicitQueryParameter(query, "liveCache")
    }

    private fun shouldApplyLocalGamePortRewrite(type: BinaryType, gameHostOverride: String?): Boolean {
        return !shouldUse947Win64SplashDefaults(type) || gameHostOverride != null
    }

    private fun liveConfigCacheKey(type: BinaryType, sourceUrl: String): String {
        return "$sourceUrl|${type.id}"
    }

    internal fun buildLiveWorldConfigUrl(worldHost: String): String {
        return "https://$worldHost/k=5/jav_config.ws"
    }

    internal fun buildLiveWorldConfigUrl(worldHost: String, query: QueryStringDecoder): String {
        val forwardedPairs = buildList {
            for ((key, values) in query.parameters()) {
                if (key in LOCAL_ONLY_WORLD_QUERY_KEYS) {
                    continue
                }
                for (value in values) {
                    add(key to value)
                }
            }
        }
        if (forwardedPairs.isEmpty()) {
            return buildLiveWorldConfigUrl(worldHost)
        }

        val encodedQuery = forwardedPairs.joinToString("&") { (key, value) ->
            "${URLEncoder.encode(key, Charsets.UTF_8)}=${URLEncoder.encode(value, Charsets.UTF_8)}"
        }
        return "${buildLiveWorldConfigUrl(worldHost)}?$encodedQuery"
    }

    private fun resolveGamePortOverride(query: QueryStringDecoder, type: BinaryType, gameHostOverride: String?): Int? {
        val explicit = query.parameters()["gamePortOverride"]?.firstOrNull()?.trim()?.toIntOrNull() ?: return null
        if (shouldApplyLocalGamePortRewrite(type, gameHostOverride)) {
            return explicit
        }

        logger.info {
            "Ignoring gamePortOverride=$explicit for build ${OpenNXT.config.build} $type startup; " +
                "keeping the retail game port until login because local raw-game bootstrap stalls the splash phase"
        }
        return null
    }

    private fun resolveGameHostOverride(query: QueryStringDecoder, type: BinaryType): String? {
        val explicit = query.parameters()["gameHostOverride"]?.firstOrNull()?.trim()
        if (!explicit.isNullOrEmpty()) {
            return explicit
        }

        val rewrite = query.parameters()["gameHostRewrite"]?.firstOrNull()?.trim()?.lowercase()
        return when (rewrite) {
            "1", "true", "yes", "on" -> LOCAL_GAME_HOST
            // 947 win64 splash bootstrap must stay on the retail game host until the
            // client reaches login. Forcing localhost here pulls the client into the
            // local raw-game JS5 loop while it is still in "Loading application resources".
            null, "" -> null
            else -> null
        }
    }

    private fun resolveDownloadMetadataSource(query: QueryStringDecoder, type: BinaryType): String {
        return when (val source = query.parameters()["downloadMetadataSource"]?.firstOrNull()?.trim()?.lowercase()) {
            null, "" -> "original"
            "original", "patched", "compressed", "live" -> source
            "none", "off", "false", "disabled" ->
                if (shouldForce947DownloadMetadata(type)) {
                    logger.warn { "Ignoring downloadMetadataSource='$source' for build ${OpenNXT.config.build} $type startup; using original metadata" }
                    "original"
                } else {
                    ""
                }
            else -> {
                logger.warn { "Unknown downloadMetadataSource='$source'; using original metadata" }
                "original"
            }
        }
    }

    internal fun resolveBaseConfigSnapshotPath(query: QueryStringDecoder): Path? {
        val rawPath = query.parameters()["baseConfigSnapshotPath"]?.firstOrNull()?.trim()
            ?: query.parameters()["baseConfigPath"]?.firstOrNull()?.trim()
            ?: return null
        if (rawPath.isEmpty()) {
            return null
        }

        return try {
            Paths.get(rawPath)
        } catch (_: Exception) {
            null
        }
    }

    internal fun loadSnapshotConfig(path: Path): ClientConfig? {
        return try {
            copyOf(ClientConfig.load(path))
        } catch (e: Exception) {
            logger.warn(e) { "Failed to load jav_config snapshot from $path; falling back to regular config resolution" }
            null
        }
    }

    internal fun resolveBaseConfigSource(query: QueryStringDecoder, type: BinaryType? = null): String {
        return when (val source = query.parameters()["baseConfigSource"]?.firstOrNull()?.trim()?.lowercase()) {
            null, "" ->
                if (type != null && shouldUse947BundledBaseConfig(type)) {
                    "original"
                } else {
                    "live"
                }
            "live" -> "live"
            "bundled" -> "compressed"
            "original", "patched", "compressed" -> source
            else -> {
                logger.warn { "Unknown baseConfigSource='$source'; using live config" }
                "live"
            }
        }
    }

    internal fun loadLiveConfig(
        type: BinaryType,
        useLiveCache: Boolean,
        sourceUrl: String = LIVE_JAV_CONFIG_URL,
    ): Pair<ClientConfig, String>? {
        val cacheKey = liveConfigCacheKey(type, sourceUrl)
        val cached = cachedLiveConfigByKey[cacheKey]
        val now = System.currentTimeMillis()
        if (useLiveCache && cached != null && now - cached.loadedAt < LIVE_CONFIG_CACHE_MILLIS) {
            RetailUpstreamCookie.noteJavConfigCookie(sourceUrl, type, cached.cookie)
            return copyOf(cached.config) to if (sourceUrl == LIVE_JAV_CONFIG_URL) "live-cache" else "live-cache-world"
        }

        synchronized(liveConfigCacheLock) {
            val lockedNow = System.currentTimeMillis()
            val lockedCached = cachedLiveConfigByKey[cacheKey]
            if (useLiveCache && lockedCached != null && lockedNow - lockedCached.loadedAt < LIVE_CONFIG_CACHE_MILLIS) {
                RetailUpstreamCookie.noteJavConfigCookie(sourceUrl, type, lockedCached.cookie)
                return copyOf(lockedCached.config) to if (sourceUrl == LIVE_JAV_CONFIG_URL) "live-cache" else "live-cache-world"
            }

            return try {
                val liveResponse = liveConfigResponseFetcher(sourceUrl, type)
                val liveConfig = liveResponse.config
                val liveBuild = liveConfig["server_version"]?.toIntOrNull()
                if (liveBuild == OpenNXT.config.build) {
                    RetailUpstreamCookie.noteJavConfigCookie(sourceUrl, type, liveResponse.cookie)
                    if (useLiveCache) {
                        cachedLiveConfigByKey = cachedLiveConfigByKey + (cacheKey to CachedConfig(lockedNow, liveConfig, liveResponse.cookie))
                    } else {
                        cachedLiveConfigByKey = cachedLiveConfigByKey - cacheKey
                    }
                    copyOf(liveConfig) to if (sourceUrl == LIVE_JAV_CONFIG_URL) "live" else "live-world"
                } else {
                    logger.warn {
                        "Live jav_config build mismatch for $type from $sourceUrl: expected ${OpenNXT.config.build}, got ${liveBuild ?: "unknown"}; " +
                            "skipping live session overlay"
                    }
                    null
                }
            } catch (e: Exception) {
                logger.warn(e) { "Failed to download live jav_config for $type from $sourceUrl; skipping live session overlay" }
                null
            }
        }
    }

    private fun loadMatchingLiveConfig(type: BinaryType, useLiveCache: Boolean, sourceUrl: String): ClientConfig? {
        return loadLiveConfig(type, useLiveCache, sourceUrl)?.first
    }

    internal fun loadBaseConfig(
        type: BinaryType,
        sourceOverride: String,
        useLiveCache: Boolean,
        liveConfigUrlOverride: String? = null,
    ): Pair<ClientConfig, String> {
        if (sourceOverride != "live") {
            return loadBundledConfig(type, sourceOverride)
        }

        loadLiveConfig(type, useLiveCache, liveConfigUrlOverride ?: LIVE_JAV_CONFIG_URL)?.let { return it }

        return loadBundledConfig(type, "compressed")
    }

    internal fun overlayLiveStartupSessionParams(baseConfig: ClientConfig, liveConfig: ClientConfig, type: BinaryType): Boolean {
        if (!shouldUse947BundledBaseConfig(type)) {
            return false
        }

        var changed = false
        for (param in LIVE_STARTUP_SESSION_PARAMS) {
            val key = "param=$param"
            val liveValue = liveConfig[key] ?: continue
            if (baseConfig[key] != liveValue) {
                baseConfig[key] = liveValue
                changed = true
            }
        }
        for (param in LIVE_STARTUP_ROUTE_PARAMS) {
            val key = "param=$param"
            val liveValue = liveConfig[key] ?: continue
            if (baseConfig[key] != liveValue) {
                baseConfig[key] = liveValue
                changed = true
            }
        }
        for (key in LIVE_STARTUP_TOP_LEVEL_KEYS) {
            val liveValue = liveConfig[key] ?: continue
            if (baseConfig[key] != liveValue) {
                baseConfig[key] = liveValue
                changed = true
            }
        }
        return changed
    }

    private fun loadBundledConfig(type: BinaryType, folder: String): Pair<ClientConfig, String> {
        val bundled = FileChecker.getConfig(folder, type)
            ?: throw NullPointerException("Can't get bundled config for type $type from folder '$folder'")
        return copyOf(bundled) to folder
    }

    internal fun prepareConfig(
        type: BinaryType,
        query: QueryStringDecoder,
        baseConfigOverride: ClientConfig? = null,
        liveConfigUrlOverride: String? = null,
        rewriteDecisionsOverride: RewriteDecisions? = null,
    ): PreparedJavConfig {
        val preferLiveWorldConfig =
            liveConfigUrlOverride != null &&
                !hasExplicitQueryParameter(query, "baseConfigSource") &&
                !shouldUse947Win64SplashDefaults(type)
        val baseConfigSource = if (preferLiveWorldConfig) "live" else resolveBaseConfigSource(query, type)
        val useLiveCache = shouldUseLiveConfigCache(query, type)
        val useSticky947StartupSessionCache = shouldUseSticky947StartupSessionCache(
            query = query,
            type = type,
            baseConfigSource = baseConfigSource,
            liveConfigUrlOverride = liveConfigUrlOverride,
        )
        val effectiveLiveCache = useLiveCache || useSticky947StartupSessionCache
        val snapshotConfig = if (baseConfigOverride == null) {
            resolveBaseConfigSnapshotPath(query)?.let(::loadSnapshotConfig)
        } else {
            null
        }
        val (config, loadedSource) = when {
            baseConfigOverride != null -> copyOf(baseConfigOverride) to "override"
            snapshotConfig != null -> snapshotConfig to "snapshot"
            else -> loadBaseConfig(type, baseConfigSource, effectiveLiveCache, liveConfigUrlOverride)
        }
        var overlaidSessionConfig: ClientConfig? = null
        val overlaidLiveSession = if (
            baseConfigOverride == null &&
            snapshotConfig == null &&
            !loadedSource.startsWith("live") &&
            shouldUse947BundledBaseConfig(type)
        ) {
            val liveConfig = loadMatchingLiveConfig(type, effectiveLiveCache, liveConfigUrlOverride ?: LIVE_JAV_CONFIG_URL)
            if (liveConfig != null) {
                overlaidSessionConfig = liveConfig
                overlayLiveStartupSessionParams(config, liveConfig, type)
            } else {
                false
            }
        } else {
            false
        }
        val source = if (overlaidLiveSession) "$loadedSource+live-session" else loadedSource
        val rewriteDecisions =
            rewriteDecisionsOverride ?: resolveRewriteDecisions(
                query = query,
                type = type,
                useStartupContractHints = liveConfigUrlOverride != null,
            )
        val localRewrite = rewriteDecisions.localRewrite
        val hostRewrite = rewriteDecisions.hostRewrite
        val contentRouteRewrite = rewriteDecisions.contentRouteRewrite
        val worldUrlRewrite = rewriteDecisions.worldUrlRewrite
        val codebaseRewrite = rewriteDecisions.codebaseRewrite
        val lobbyHostRewrite = rewriteDecisions.lobbyHostRewrite
        val gameHostOverride = resolveGameHostOverride(query, type)
        val gamePortOverride = resolveGamePortOverride(query, type, gameHostOverride)
        val startupHintDownloadMetadataSource =
            if (preferLiveWorldConfig && !hasExplicitQueryParameter(query, "downloadMetadataSource")) {
                StartupContractHints.latestDownloadMetadataSource()
            } else {
                null
            }
        val downloadMetadataSource =
            if (preferLiveWorldConfig && !hasExplicitQueryParameter(query, "downloadMetadataSource")) {
                startupHintDownloadMetadataSource
                    ?: RetailSessionCookie.currentDownloadMetadataSource(resolveImplicitDownloadMetadataSource(type))
            } else {
                resolveDownloadMetadataSource(query, type)
            }
        when {
            downloadMetadataSource == "live" && !loadedSource.startsWith("live") -> {
                overlaidSessionConfig?.let { applyDownloadMetadata(config, it) }
            }
            downloadMetadataSource.isNotEmpty() && downloadMetadataSource != "live" -> {
                applyDownloadMetadata(config, type, downloadMetadataSource)
            }
        }
        if (localRewrite) {
            if (hostRewrite) {
                applyLocalHostRewrite(config, lobbyHostRewrite)
            }
            if (contentRouteRewrite) {
                applyContentRouteRewrite(config)
            }
            if (worldUrlRewrite) {
                applyLocalWorldUrlRewrite(config)
            }
            if (codebaseRewrite) {
                applyLocalCodebaseRewrite(config)
            }
            if (gameHostOverride != null) {
                applyGameHostOverride(config, gameHostOverride)
            }
            if (shouldApplyLocalGamePortRewrite(type, gameHostOverride)) {
                applyLocalPortRewrite(config, gamePortOverride ?: OpenNXT.config.ports.game)
            }
        }
        return PreparedJavConfig(
            config = config,
            source = source,
            localRewrite = localRewrite,
            hostRewrite = hostRewrite,
            contentRouteRewrite = contentRouteRewrite,
            worldUrlRewrite = worldUrlRewrite,
            codebaseRewrite = codebaseRewrite,
            lobbyHostRewrite = lobbyHostRewrite,
            gameHostOverride = gameHostOverride,
            gamePortOverride = gamePortOverride,
            downloadMetadataSource = downloadMetadataSource
        )
    }

    internal fun applyRetailJavConfigHeaders(
        headers: HttpHeaders,
        size: Int,
        now: Instant = Instant.now(),
        keepAlive: Boolean = true,
        cookie: String = RetailSessionCookie.current(),
        requestHost: String? = null,
    ) {
        val headerCookie = RetailSessionCookie.headerValueForRequest(cookie, requestHost)
        headers.set("Date", HTTP_DATE_FORMATTER.format(now))
        headers.set("Server", "JAGeX/3.1")
        headers.set("Content-type", "text/plain; charset=ISO-8859-1")
        headers.set("Cache-control", "no-cache")
        headers.set("Pragma", "no-cache")
        headers.set("Expires", EXPIRES_EPOCH_GMT)
        headers.set("Set-Cookie", headerCookie)
        headers.set("Connection", if (keepAlive) "Keep-alive" else "close")
        headers.set("Content-length", size)
    }

    private fun sendRetailJavConfigResponse(
        ctx: ChannelHandlerContext,
        request: FullHttpRequest,
        body: ByteArray,
        cookie: String,
    ) {
        val keepAlive = HttpUtil.isKeepAlive(request)
        val response = DefaultFullHttpResponse(
            request.protocolVersion(),
            HttpResponseStatus.OK,
            Unpooled.wrappedBuffer(body),
        )
        applyRetailJavConfigHeaders(
            response.headers(),
            body.size,
            keepAlive = keepAlive,
            cookie = cookie,
            requestHost = request.headers().get(HttpHeaderNames.HOST),
        )
        val future = ctx.channel().writeAndFlush(response)
        if (!keepAlive) {
            future.addListener(ChannelFutureListener.CLOSE)
        }
    }

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {
        val type = BinaryType.values()[query.parameters().getOrElse("binaryType") { listOf("2") }.first().toInt()]
        val explicitDownloadMetadataSource =
            if (hasExplicitQueryParameter(query, "downloadMetadataSource")) {
                resolveDownloadMetadataSource(query, type)
            } else {
                ""
            }
        if (explicitDownloadMetadataSource.isNotEmpty()) {
            RetailSessionCookie.noteDownloadMetadataSource(explicitDownloadMetadataSource)
        }
        val requestedWorldHostCandidate = extractRequestedWorldHost(msg, query)
        val rewriteDecisions = resolveRewriteDecisions(
            query = query,
            type = type,
            useStartupContractHints = requestedWorldHostCandidate != null,
        )
        val requestedWorldHost = if (!rewriteDecisions.worldUrlRewrite && !rewriteDecisions.codebaseRewrite) {
            requestedWorldHostCandidate
        } else {
            null
        }
        val liveConfigUrlOverride = requestedWorldHostCandidate?.let { buildLiveWorldConfigUrl(it, query) }
        val prepared = prepareConfig(
            type = type,
            query = query,
            liveConfigUrlOverride = liveConfigUrlOverride,
            rewriteDecisionsOverride = rewriteDecisions,
        )
        val config = prepared.config
        if (prepared.downloadMetadataSource.isNotEmpty()) {
            RetailSessionCookie.noteDownloadMetadataSource(prepared.downloadMetadataSource)
        }
        if (requestedWorldHost != null) {
            applyRequestedWorldHostRewrite(config, requestedWorldHost)
        }
        logger.info {
                "Serving /jav_config.ws to ${ctx.channel().remoteAddress()}: " +
                "binaryType=$type source=${prepared.source} localRewrite=${prepared.localRewrite} " +
                "gameHost=${config["param=3"]} gameHostOverride=${prepared.gameHostOverride ?: "none"} " +
                "gamePort=${config["param=41"]} gamePortOverride=${prepared.gamePortOverride ?: "none"} " +
                "hostRewrite=${prepared.hostRewrite} contentRouteRewrite=${prepared.contentRouteRewrite} " +
                "worldUrlRewrite=${prepared.worldUrlRewrite} " +
                "requestedWorldHost=${requestedWorldHost ?: "none"} " +
                "contentHosts=${CONTENT_ROUTE_PARAMS.joinToString(",") { "${config["param=$it"]}" }} " +
                "worldUrls=${WORLD_ROUTE_PARAMS.joinToString(",") { "${config["param=$it"]}" }} " +
                "codebaseRewrite=${prepared.codebaseRewrite} lobbyHostRewrite=${prepared.lobbyHostRewrite} " +
                "downloadMetadataSource=${if (prepared.downloadMetadataSource.isEmpty()) "disabled" else prepared.downloadMetadataSource} " +
                "codebase=${config["codebase"]} files=${config.getFiles().size}"
        }
        val cookieSourceUrl = liveConfigUrlOverride ?: LIVE_JAV_CONFIG_URL
        val cookie = RetailUpstreamCookie.resolveJavConfigCookie(cookieSourceUrl, type)
        sendRetailJavConfigResponse(ctx, msg, config.toString().toByteArray(Charsets.ISO_8859_1), cookie)
    }
}
