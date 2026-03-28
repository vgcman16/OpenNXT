package com.opennxt.net

import com.opennxt.Constants
import com.opennxt.OpenNXT
import io.netty.channel.ChannelHandlerContext
import io.netty.handler.ssl.SslContext
import io.netty.handler.ssl.SslContextBuilder
import io.netty.handler.ssl.SslHandler
import io.netty.handler.ssl.SslProvider
import mu.KotlinLogging
import java.nio.file.Files
import java.security.KeyStore
import java.security.PrivateKey
import java.security.cert.Certificate
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import javax.net.ssl.KeyManagerFactory

object ServerTls {
    private val logger = KotlinLogging.logger {}

    private const val PFX_PASSWORD = "opennxt-dev"
    private const val MANAGED_ROOT_SUBJECT = "CN=OpenNXT Local Root"
    private val LEGACY_BACKEND_CERTIFICATE_HOSTS = listOf("lobby45a.runescape.com", "lobby46a.runescape.com")

    internal fun normalizeLoopbackHost(host: String?): String? {
        val normalized = host?.trim()
        if (normalized.isNullOrEmpty()) {
            return null
        }
        return when (normalized.lowercase()) {
            "127.0.0.1", "::1", "localhost" -> "localhost"
            else -> normalized
        }
    }

    internal fun resolveCertificateHost(
        configuredGameHost: String?,
        configuredLobbyHost: String?,
        availableCertificateHosts: Set<String>
    ): String {
        val normalizedGameHost = normalizeLoopbackHost(configuredGameHost)
        val normalizedLobbyHost = normalizeLoopbackHost(configuredLobbyHost) ?: "localhost"
        val configuredCandidates = listOfNotNull(normalizedGameHost, normalizedLobbyHost).distinct()

        val explicitNonLoopback = configuredCandidates.firstOrNull { candidate ->
            candidate != "localhost" && candidate in availableCertificateHosts
        }
        if (explicitNonLoopback != null) {
            return explicitNonLoopback
        }

        // When the canonical no-hosts route rewrites the visible connect target to localhost,
        // keep serving the older lobby certificate profile on the secure-game backend if it is
        // available. That profile still covers localhost via SAN and matches the only fully
        // successful secure-game handoff we have captured.
        val legacyBackend = LEGACY_BACKEND_CERTIFICATE_HOSTS.firstOrNull { it in availableCertificateHosts }
        if (legacyBackend != null) {
            return legacyBackend
        }

        return configuredCandidates.firstOrNull { it in availableCertificateHosts } ?: normalizedLobbyHost
    }

    private fun resolveCertificateHost(): String {
        val configuredGameHost = runCatching { OpenNXT.config.gameHostname }.getOrNull()
        val configuredLobbyHost = runCatching { OpenNXT.config.hostname }.getOrElse { "lobby45a.runescape.com" }
        val tlsDir = Constants.DATA_PATH.resolve("tls")
        val availableCertificateHosts = runCatching {
            Files.list(tlsDir).use { stream ->
                stream
                    .filter { Files.isRegularFile(it) }
                    .map { it.fileName.toString() }
                    .filter { it.endsWith(".pfx", ignoreCase = true) }
                    .map { it.removeSuffix(".pfx") }
                    .toList()
                    .toSet()
            }
        }.getOrDefault(emptySet())

        val resolved = resolveCertificateHost(
            configuredGameHost = configuredGameHost,
            configuredLobbyHost = configuredLobbyHost,
            availableCertificateHosts = availableCertificateHosts
        )
        val normalizedLobbyHost = normalizeLoopbackHost(configuredLobbyHost) ?: "localhost"

        if (resolved != normalizedLobbyHost) {
            logger.info {
                "Using backend TLS certificate host $resolved instead of lobby host $normalizedLobbyHost " +
                    "for secure world handoff"
            }
        }

        return resolved
    }

    private fun loadManagedRootCertificate(): X509Certificate? {
        val rootPath = Constants.DATA_PATH.resolve("tls").resolve("opennxt-local-root.cer")
        if (!Files.exists(rootPath)) {
            return null
        }
        return runCatching {
            Files.newInputStream(rootPath).use { input ->
                CertificateFactory.getInstance("X.509").generateCertificate(input) as X509Certificate
            }
        }.getOrNull()
    }

    private fun buildCertificateChain(
        alias: String,
        keyStore: KeyStore,
        password: CharArray
    ): Pair<PrivateKey, Array<Certificate>> {
        val key = keyStore.getKey(alias, password) as? PrivateKey
            ?: error("Missing private key for TLS alias $alias")
        val existingChain = keyStore.getCertificateChain(alias)?.toMutableList() ?: mutableListOf()
        val leaf = existingChain.firstOrNull() as? X509Certificate
            ?: error("Missing leaf certificate for TLS alias $alias")
        val managedRoot = loadManagedRootCertificate()

        if (
            existingChain.size == 1 &&
            managedRoot != null &&
            leaf.issuerX500Principal.name == managedRoot.subjectX500Principal.name &&
            managedRoot.subjectX500Principal.name == MANAGED_ROOT_SUBJECT
        ) {
            existingChain += managedRoot
            logger.info {
                "Appending managed root ${managedRoot.subjectX500Principal.name} to backend TLS chain " +
                    "for alias $alias"
            }
        }

        return key to existingChain.toTypedArray()
    }

    val context: SslContext by lazy {
        val configuredHost = resolveCertificateHost()
        val pfxPath = Constants.DATA_PATH.resolve("tls").resolve("$configuredHost.pfx")
        require(Files.exists(pfxPath)) {
            "Missing TLS certificate at $pfxPath"
        }

        logger.info { "Loading backend TLS certificate for host $configuredHost from $pfxPath" }

        val password = PFX_PASSWORD.toCharArray()
        val keyStore = KeyStore.getInstance("PKCS12")
        Files.newInputStream(pfxPath).use { input ->
            keyStore.load(input, password)
        }

        val alias = keyStore.aliases().toList().firstOrNull()
            ?: error("No TLS certificate alias found in $pfxPath")
        val (privateKey, certificateChain) = buildCertificateChain(alias, keyStore, password)
        val leafCertificate = certificateChain.firstOrNull() as? X509Certificate
        if (leafCertificate != null) {
            logger.info {
                "Backend TLS certificate subject=${leafCertificate.subjectX500Principal.name} " +
                    "issuer=${leafCertificate.issuerX500Principal.name} " +
                    "chainLength=${certificateChain.size}"
            }
        }
        keyStore.setKeyEntry(alias, privateKey, password, certificateChain)

        val keyManagerFactory = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        keyManagerFactory.init(keyStore, password)

        SslContextBuilder.forServer(keyManagerFactory)
            .sslProvider(SslProvider.JDK)
            .build()
    }

    fun newHandler(ctx: ChannelHandlerContext): SslHandler = context.newHandler(ctx.alloc())
}
