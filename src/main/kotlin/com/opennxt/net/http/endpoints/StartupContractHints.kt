package com.opennxt.net.http.endpoints

import com.opennxt.model.files.BinaryType
import mu.KotlinLogging
import java.net.URI
import java.net.URLDecoder
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlin.io.path.getLastModifiedTime

internal object StartupContractHints {
    private val logger = KotlinLogging.logger { }
    private val allowedSources = setOf("original", "patched", "compressed", "live")
    private val relativeHintPath: Path = Paths.get("data", "debug", "direct-rs2client-patch", "latest-startup-contract.json")
    private val pidRegex = Regex("\"pid\"\\s*:\\s*(\\d+)")
    private val sourceRegex = Regex("\"downloadMetadataSource\"\\s*:\\s*\"([^\"]+)\"")
    private val variantRegex = Regex("\"clientVariant\"\\s*:\\s*\"([^\"]+)\"")
    private val configUrlRegex = Regex("\"configUrl\"\\s*:\\s*\"([^\"]+)\"")
    private const val MAX_HINT_AGE_MILLIS = 15L * 60L * 1000L

    internal data class StartupRewriteContract(
        val binaryTypeId: Int?,
        val localRewrite: Boolean,
        val hostRewrite: Boolean,
        val lobbyHostRewrite: Boolean,
        val contentRouteRewrite: Boolean,
        val worldUrlRewrite: Boolean,
        val codebaseRewrite: Boolean,
    )

    internal data class StartupContractHint(
        val path: Path,
        val pid: Long?,
        val clientVariant: String?,
        val downloadMetadataSource: String,
        val configUrl: String?,
        val rewriteContract: StartupRewriteContract?,
    )

    @Volatile
    internal var overridePathForTests: Path? = null

    internal fun resetForTests() {
        overridePathForTests = null
    }

    internal fun latest(): StartupContractHint? {
        val path = resolveHintPath() ?: return null
        if (!Files.exists(path)) {
            return null
        }

        return try {
            val ageMillis = System.currentTimeMillis() - path.getLastModifiedTime().toMillis()
            if (ageMillis > MAX_HINT_AGE_MILLIS) {
                return null
            }

            val text = Files.readString(path)
            val source = sourceRegex.find(text)?.groupValues?.getOrNull(1)?.trim()?.lowercase()
                ?.takeIf { it in allowedSources }
                ?: return null
            val pid = pidRegex.find(text)?.groupValues?.getOrNull(1)?.toLongOrNull()
            if (pid != null) {
                val processHandle = ProcessHandle.of(pid)
                if (processHandle.isEmpty || !processHandle.get().isAlive) {
                    return null
                }
            }
            val variant = variantRegex.find(text)?.groupValues?.getOrNull(1)?.trim()?.lowercase()
                ?.takeIf { it.isNotEmpty() }
            val configUrl = configUrlRegex.find(text)?.groupValues?.getOrNull(1)?.trim()
                ?.takeIf { it.isNotEmpty() }

            StartupContractHint(
                path = path,
                pid = pid,
                clientVariant = variant,
                downloadMetadataSource = source,
                configUrl = configUrl,
                rewriteContract = parseRewriteContract(configUrl),
            )
        } catch (e: Exception) {
            logger.warn(e) { "Failed to read startup contract hints from $path" }
            null
        }
    }

    internal fun latestDownloadMetadataSource(): String? = latest()?.downloadMetadataSource

    internal fun latestRewriteContract(type: BinaryType? = null): StartupRewriteContract? {
        val contract = latest()?.rewriteContract ?: return null
        if (type == null || contract.binaryTypeId == null || contract.binaryTypeId == type.id) {
            return contract
        }
        return null
    }

    private fun parseRewriteContract(configUrl: String?): StartupRewriteContract? {
        if (configUrl.isNullOrBlank()) {
            return null
        }

        return try {
            val uri = URI(configUrl)
            val queryValues = parseQueryParameters(configUrl)
            val localhostRequestedWorldBridge =
                isLoopbackHost(uri.host?.trim()?.lowercase()) &&
                    !queryValues["requestedWorldHost"].isNullOrBlank()
            StartupRewriteContract(
                binaryTypeId = queryValues["binaryType"]?.toIntOrNull(),
                localRewrite = parseFlag(queryValues["localRewrite"], defaultValue = true),
                hostRewrite = parseFlag(queryValues["hostRewrite"], defaultValue = false),
                lobbyHostRewrite = parseFlag(queryValues["lobbyHostRewrite"], defaultValue = false),
                contentRouteRewrite = parseFlag(
                    queryValues["contentRouteRewrite"],
                    defaultValue = localhostRequestedWorldBridge,
                ),
                worldUrlRewrite = parseFlag(queryValues["worldUrlRewrite"], defaultValue = false),
                codebaseRewrite = parseFlag(queryValues["codebaseRewrite"], defaultValue = false),
            )
        } catch (e: Exception) {
            logger.warn(e) { "Failed to parse startup rewrite contract from configUrl=$configUrl" }
            null
        }
    }

    private fun resolveHintPath(): Path? {
        overridePathForTests?.let { return it }
        val direct = relativeHintPath
        if (Files.exists(direct)) {
            return direct
        }

        for (root in discoveryRoots()) {
            var cursor: Path? = root
            repeat(10) {
                if (cursor == null) {
                    return@repeat
                }
                val candidate = cursor.resolve(relativeHintPath).normalize()
                if (Files.exists(candidate)) {
                    return candidate
                }
                cursor = cursor.parent
            }
        }
        return direct
    }

    private fun discoveryRoots(): List<Path> {
        val roots = linkedSetOf<Path>()
        roots.add(Paths.get("").toAbsolutePath().normalize())
        val codeSourcePath =
            try {
                StartupContractHints::class.java.protectionDomain?.codeSource?.location?.toURI()?.let(Paths::get)
            } catch (_: Exception) {
                null
            }
        if (codeSourcePath != null) {
            val normalized = codeSourcePath.toAbsolutePath().normalize()
            roots.add(if (Files.isDirectory(normalized)) normalized else normalized.parent ?: normalized)
        }
        return roots.toList()
    }

    private fun parseQueryParameters(configUrl: String): Map<String, String> {
        val rawQuery = URI(configUrl).rawQuery ?: return emptyMap()
        if (rawQuery.isBlank()) {
            return emptyMap()
        }

        return buildMap {
            for (pair in rawQuery.split("&")) {
                if (pair.isBlank()) {
                    continue
                }
                val separatorIndex = pair.indexOf('=')
                val rawKey = if (separatorIndex >= 0) pair.substring(0, separatorIndex) else pair
                val rawValue = if (separatorIndex >= 0) pair.substring(separatorIndex + 1) else ""
                val key = URLDecoder.decode(rawKey, StandardCharsets.UTF_8).trim()
                if (key.isEmpty()) {
                    continue
                }
                put(key, URLDecoder.decode(rawValue, StandardCharsets.UTF_8))
            }
        }
    }

    private fun parseFlag(rawValue: String?, defaultValue: Boolean): Boolean {
        return when (rawValue?.trim()?.lowercase()) {
            null, "" -> defaultValue
            "1", "true", "yes", "on" -> true
            "0", "false", "no", "off" -> false
            else -> true
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
