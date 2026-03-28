package com.opennxt.net.http.endpoints

import com.opennxt.Constants
import com.opennxt.OpenNXT
import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.ClientConfig
import com.opennxt.model.files.FileChecker
import com.opennxt.net.http.sendHttpText
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.codec.http.FullHttpRequest
import io.netty.handler.codec.http.QueryStringDecoder
import mu.KotlinLogging
import java.net.URI
import java.nio.file.Path
import java.nio.file.Paths

object JavConfigWsEndpoint {
    private val logger = KotlinLogging.logger { }
    private const val LOCAL_PROXY_HOST = "localhost"
    private const val LOCAL_GAME_HOST = "127.0.0.1"
    private const val LOCAL_CONTENT_HOST = LOCAL_PROXY_HOST
    private const val LOCAL_CODEBASE_SCHEME = "http"
    private const val LIVE_JAV_CONFIG_URL = "https://rs.config.runescape.com/k=5/l=0/jav_config.ws"
    private const val LIVE_CONFIG_CACHE_MILLIS = 60_000L
    private val CONTENT_ROUTE_PARAMS = listOf(37, 49)
    private val WORLD_ROUTE_PARAMS = listOf(35, 40)

    private data class CachedConfig(val loadedAt: Long, val config: ClientConfig)
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

    @Volatile
    private var cachedLiveConfigByType: Map<BinaryType, CachedConfig> = emptyMap()
    private val liveConfigCacheLock = Any()

    internal var liveConfigFetcher: (BinaryType) -> ClientConfig = { type ->
        ClientConfig.download(LIVE_JAV_CONFIG_URL, type)
    }

    internal fun resetLiveConfigCacheForTests() {
        synchronized(liveConfigCacheLock) {
            cachedLiveConfigByType = emptyMap()
        }
        liveConfigFetcher = { type -> ClientConfig.download(LIVE_JAV_CONFIG_URL, type) }
    }

    private fun shouldUse947Win64SplashDefaults(type: BinaryType): Boolean {
        return OpenNXT.config.build >= 947 && (type == BinaryType.WIN64 || type == BinaryType.WIN64C)
    }

    private fun shouldForce947DownloadMetadata(type: BinaryType): Boolean {
        return OpenNXT.config.build >= 947 && (type == BinaryType.WIN64 || type == BinaryType.WIN64C)
    }

    private fun shouldUse947BundledBaseConfig(type: BinaryType): Boolean {
        return OpenNXT.config.build >= 947 && (type == BinaryType.WIN64 || type == BinaryType.WIN64C)
    }

    private val LIVE_STARTUP_SESSION_PARAMS = listOf(2, 18, 27, 29, 31, 34)
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

    private fun rewriteBaseUrlPreservingPath(original: String?, ensureTrailingSlash: Boolean): String {
        val fallbackPath = if (ensureTrailingSlash) "/" else ""
        if (original.isNullOrBlank()) {
            return "$LOCAL_CODEBASE_SCHEME://$LOCAL_PROXY_HOST:${OpenNXT.config.ports.http}$fallbackPath"
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
            URI(
                LOCAL_CODEBASE_SCHEME,
                null,
                LOCAL_PROXY_HOST,
                OpenNXT.config.ports.http,
                path,
                null,
                null
            ).toString()
        } catch (_: Exception) {
            "$LOCAL_CODEBASE_SCHEME://$LOCAL_PROXY_HOST:${OpenNXT.config.ports.http}$fallbackPath"
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

    private fun clearDownloadMetadata(config: ClientConfig) {
        config.getFiles().map { it.id }.forEach { id ->
            config.entries.remove("download_name_$id")
            config.entries.remove("download_crc_$id")
            config.entries.remove("download_hash_$id")
        }
    }

    private fun applyDownloadMetadata(config: ClientConfig, type: BinaryType, folder: String) {
        val sourceConfig = FileChecker.getConfig(folder, type) ?: return
        clearDownloadMetadata(config)

        sourceConfig.getFiles().forEach { file ->
            val id = file.id
            config["download_name_$id"] = file.name
            config["download_crc_$id"] = file.crc.toString()
            config["download_hash_$id"] = file.hash
        }
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

    internal fun shouldUseLiveConfigCache(query: QueryStringDecoder, type: BinaryType): Boolean {
        val flag = query.parameters()["liveCache"]?.firstOrNull()?.trim()?.lowercase()
        return when (flag) {
            "0", "false", "no", "off" -> false
            "1", "true", "yes", "on" -> true
            else -> !(OpenNXT.config.build >= 947 && (type == BinaryType.WIN64C || type == BinaryType.WIN64))
        }
    }

    private fun shouldApplyLocalGamePortRewrite(type: BinaryType, gameHostOverride: String?): Boolean {
        return !shouldUse947Win64SplashDefaults(type) || gameHostOverride != null
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
            "original", "patched", "compressed" -> source
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

    internal fun loadLiveConfig(type: BinaryType, useLiveCache: Boolean): Pair<ClientConfig, String>? {
        val cached = cachedLiveConfigByType[type]
        val now = System.currentTimeMillis()
        if (useLiveCache && cached != null && now - cached.loadedAt < LIVE_CONFIG_CACHE_MILLIS) {
            return copyOf(cached.config) to "live-cache"
        }

        synchronized(liveConfigCacheLock) {
            val lockedNow = System.currentTimeMillis()
            val lockedCached = cachedLiveConfigByType[type]
            if (useLiveCache && lockedCached != null && lockedNow - lockedCached.loadedAt < LIVE_CONFIG_CACHE_MILLIS) {
                return copyOf(lockedCached.config) to "live-cache"
            }

            return try {
                val liveConfig = liveConfigFetcher(type)
                val liveBuild = liveConfig["server_version"]?.toIntOrNull()
                if (liveBuild == OpenNXT.config.build) {
                    if (useLiveCache) {
                        cachedLiveConfigByType = cachedLiveConfigByType + (type to CachedConfig(lockedNow, liveConfig))
                    } else {
                        cachedLiveConfigByType = cachedLiveConfigByType - type
                    }
                    copyOf(liveConfig) to "live"
                } else {
                    logger.warn {
                        "Live jav_config build mismatch for $type: expected ${OpenNXT.config.build}, got ${liveBuild ?: "unknown"}; " +
                            "skipping live session overlay"
                    }
                    null
                }
            } catch (e: Exception) {
                logger.warn(e) { "Failed to download live jav_config for $type; skipping live session overlay" }
                null
            }
        }
    }

    private fun loadMatchingLiveConfig(type: BinaryType, useLiveCache: Boolean): ClientConfig? {
        return loadLiveConfig(type, useLiveCache)?.first
    }

    internal fun loadBaseConfig(type: BinaryType, sourceOverride: String, useLiveCache: Boolean): Pair<ClientConfig, String> {
        if (sourceOverride != "live") {
            return loadBundledConfig(type, sourceOverride)
        }

        loadLiveConfig(type, useLiveCache)?.let { return it }

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
        baseConfigOverride: ClientConfig? = null
    ): PreparedJavConfig {
        val baseConfigSource = resolveBaseConfigSource(query, type)
        val useLiveCache = shouldUseLiveConfigCache(query, type)
        val snapshotConfig = if (baseConfigOverride == null) {
            resolveBaseConfigSnapshotPath(query)?.let(::loadSnapshotConfig)
        } else {
            null
        }
        val (config, loadedSource) = when {
            baseConfigOverride != null -> copyOf(baseConfigOverride) to "override"
            snapshotConfig != null -> snapshotConfig to "snapshot"
            else -> loadBaseConfig(type, baseConfigSource, useLiveCache)
        }
        val overlaidLiveSession = if (
            baseConfigOverride == null &&
            snapshotConfig == null &&
            loadedSource != "live" &&
            shouldUse947BundledBaseConfig(type)
        ) {
            val liveConfig = loadMatchingLiveConfig(type, useLiveCache)
            if (liveConfig != null) {
                overlayLiveStartupSessionParams(config, liveConfig, type)
            } else {
                false
            }
        } else {
            false
        }
        val source = if (overlaidLiveSession) "$loadedSource+live-session" else loadedSource
        val localRewrite = shouldApplyLocalRewrite(query)
        val hostRewrite = shouldRewriteHost(query, type)
        val contentRouteRewrite = shouldRewriteContentRoute(query, type)
        val worldUrlRewrite = shouldRewriteWorldUrls(query, type)
        val codebaseRewrite = shouldRewriteCodebase(query, type)
        val lobbyHostRewrite = shouldRewriteLobbyHost(query, type)
        val gameHostOverride = resolveGameHostOverride(query, type)
        val gamePortOverride = resolveGamePortOverride(query, type, gameHostOverride)
        val downloadMetadataSource = resolveDownloadMetadataSource(query, type)
        if (downloadMetadataSource.isNotEmpty()) {
            applyDownloadMetadata(config, type, downloadMetadataSource)
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

    fun handle(ctx: ChannelHandlerContext, msg: FullHttpRequest, query: QueryStringDecoder) {
        val type = BinaryType.values()[query.parameters().getOrElse("binaryType") { listOf("2") }.first().toInt()]
        val prepared = prepareConfig(type, query)
        val config = prepared.config
        logger.info {
                "Serving /jav_config.ws to ${ctx.channel().remoteAddress()}: " +
                "binaryType=$type source=${prepared.source} localRewrite=${prepared.localRewrite} " +
                "gameHost=${config["param=3"]} gameHostOverride=${prepared.gameHostOverride ?: "none"} " +
                "gamePort=${config["param=41"]} gamePortOverride=${prepared.gamePortOverride ?: "none"} " +
                "hostRewrite=${prepared.hostRewrite} contentRouteRewrite=${prepared.contentRouteRewrite} " +
                "worldUrlRewrite=${prepared.worldUrlRewrite} " +
                "contentHosts=${CONTENT_ROUTE_PARAMS.joinToString(",") { "${config["param=$it"]}" }} " +
                "worldUrls=${WORLD_ROUTE_PARAMS.joinToString(",") { "${config["param=$it"]}" }} " +
                "codebaseRewrite=${prepared.codebaseRewrite} lobbyHostRewrite=${prepared.lobbyHostRewrite} " +
                "downloadMetadataSource=${if (prepared.downloadMetadataSource.isEmpty()) "disabled" else prepared.downloadMetadataSource} " +
                "codebase=${config["codebase"]} files=${config.getFiles().size}"
        }
        ctx.sendHttpText(config.toString().toByteArray(Charsets.ISO_8859_1))
    }
}
