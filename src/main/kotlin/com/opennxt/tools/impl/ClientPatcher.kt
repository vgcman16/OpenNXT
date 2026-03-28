package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.defaultLazy
import com.github.ajalt.clikt.parameters.options.option
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.types.int
import com.google.common.io.ByteStreams
import com.opennxt.Constants
import com.opennxt.config.RsaConfig
import com.opennxt.config.ServerConfig
import com.opennxt.config.TomlConfig
import com.opennxt.ext.indexOf
import com.opennxt.ext.replaceFirst
import com.opennxt.model.files.BinaryType
import com.opennxt.model.files.ClientConfig
import com.opennxt.tools.Tool
import com.opennxt.util.RSAUtil
import com.opennxt.util.Whirlpool
import lzma.sdk.lzma.Encoder
import lzma.streams.LzmaEncoderWrapper
import lzma.streams.LzmaOutputStream
import org.cservenak.streams.Coder
import org.cservenak.streams.CoderOutputStream
import java.io.*
import java.math.BigInteger
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.util.*
import java.util.zip.CRC32
import kotlin.system.exitProcess


class ClientPatcher :
    Tool("client-patcher", "Patches all clients and configs files. Uses most recent revision by default") {

    private val RUNESCAPE_REGEX = "^https?://[a-z0-9\\-]*\\.?runescape.com(:[0-9]+)?/\u0000"
    private val RUNESCAPE_CONFIG_URLS = listOf(
        "http://www.runescape.com/k=5/l=$(Language:0)/jav_config.ws",
        "https://rs.config.runescape.com/k=5/l=$(Language:0)/jav_config.ws"
    )
    private val ASCII = Charsets.US_ASCII

    private val PATCHED_REGEX = "^.*"
    private data class BinaryPatch(
        val offset: Int,
        val expected: ByteArray,
        val replacement: ByteArray,
        val description: String
    )

    private val secureWorldValidationBypassPatches = mapOf(
        BinaryType.WIN64C to listOf(
            BinaryPatch(
                offset = 0x648b4b,
                expected = byteArrayOf(0x4d, 0x8b.toByte(), 0xc7.toByte()),
                replacement = byteArrayOf(0x45, 0x33, 0xc0.toByte()),
                description = "Clear secure world Schannel target principal"
            ),
            BinaryPatch(
                offset = 0x648d56,
                expected = byteArrayOf(0x0f, 0x84.toByte(), 0x26, 0x01, 0x00, 0x00),
                replacement = byteArrayOf(0xe9.toByte(), 0x27, 0x01, 0x00, 0x00, 0x90.toByte()),
                description = "Skip secure world pinned public key validation block"
            ),
            BinaryPatch(
                offset = 0x648e8a,
                expected = byteArrayOf(0x0f, 0x84.toByte(), 0x98.toByte(), 0x00, 0x00, 0x00),
                replacement = byteArrayOf(0xe9.toByte(), 0x99.toByte(), 0x00, 0x00, 0x00, 0x90.toByte()),
                description = "Skip secure world certificate validation branch"
            ),
            BinaryPatch(
                offset = 0xe9a12,
                expected = byteArrayOf(
                    0x83.toByte(), 0x38, 0x00,
                    0x75, 0x04,
                    0xc6.toByte(), 0x46, 0x48, 0x00,
                    0x8b.toByte(), 0x00,
                    0x85.toByte(), 0xc0.toByte(),
                    0x74, 0x75,
                    0x83.toByte(), 0xf8.toByte(), 0x01,
                    0x75, 0x70
                ),
                replacement = byteArrayOf(
                    0x48, 0x85.toByte(), 0xc0.toByte(),
                    0x74, 0x7f,
                    0x8b.toByte(), 0x00,
                    0x85.toByte(), 0xc0.toByte(),
                    0x74, 0x79,
                    0x83.toByte(), 0xf8.toByte(), 0x01,
                    0x75, 0x74,
                    0x90.toByte(), 0x90.toByte(), 0x90.toByte(), 0x90.toByte()
                ),
                description = "Treat null secure world status pointers as handshake failure instead of crashing"
            ),
            BinaryPatch(
                offset = 0x1405e0,
                expected = byteArrayOf(
                    0x40, 0x53,
                    0x48, 0x83.toByte(), 0xec.toByte(), 0x20,
                    0x48, 0x8b.toByte(), 0x42, 0x18
                ),
                replacement = byteArrayOf(
                    0x53,
                    0x48, 0x83.toByte(), 0xec.toByte(), 0x20,
                    0xe9.toByte(), 0x70, 0x00, 0x00, 0x00
                ),
                description = "Skip crashing secure world decoder that feeds uninitialized 0x68-byte entries"
            )
        )
    )

    private val nativeRuntimeFiles = listOf(
        "chrome_100_percent.pak",
        "chrome_200_percent.pak",
        "chrome_elf.dll",
        "d3dcompiler_47.dll",
        "icudtl.dat",
        "libcef.dll",
        "libEGL.dll",
        "libGLESv2.dll",
        "resources.pak",
        "snapshot_blob.bin",
        "v8_context_snapshot.bin",
        "vk_swiftshader.dll",
        "vk_swiftshader_icd.json",
        "vulkan-1.dll"
    )

    private val version by option(help = "The version of the client to patch")
        .int()
        .defaultLazy {
            val path = Constants.CLIENTS_PATH
            if (!Files.exists(path)) return@defaultLazy -1

            var version = -1
            Files.list(path).forEach {
                try {
                    val thisVersion = it.fileName.toString().toInt()
                    if (version < thisVersion) version = thisVersion
                } catch (e: NumberFormatException) {
                }
            }

            version
        }

    private val skipLauncher by option(
        help = "Skip patching launcher binaries and only patch client/config files."
    ).flag(default = false)

    var oldJs5: ByteArray? = null
    var oldLogin: ByteArray? = null
    var oldLauncher: ByteArray? = null

    lateinit var rsaConfig: RsaConfig
    lateinit var serverConfig: ServerConfig

    private fun shouldSkipJs5Patch(): Boolean {
        return System.getenv("OPENNXT_SKIP_JS5_CLIENT_PATCH")
            ?.trim()
            ?.lowercase()
            ?.let { it == "1" || it == "true" || it == "yes" }
            ?: false
    }

    override fun runTool() {
        logger.info { "Patching clients for version $version" }

        val path = Constants.CLIENTS_PATH.resolve(version.toString())
        if (!Files.exists(path)) throw FileNotFoundException("$path: do clients with version $version exist? did you run `run-tool client-downloader` yet?")

        logger.info { "Patching clients in $path" }
        rsaConfig = try {
            TomlConfig.load(RsaConfig.DEFAULT_PATH, mustExist = true)
        } catch (e: FileNotFoundException) {
            logger.info { "Could not find RSA config: $e. Please run `run-tool rsa-key-generator`" }
            exitProcess(1)
        }
        logger.info { "Using RSA config from ${RsaConfig.DEFAULT_PATH}" }

        serverConfig = TomlConfig.load(ServerConfig.DEFAULT_PATH)
        logger.info { "Using server config from ${ServerConfig.DEFAULT_PATH}" }

        BinaryType.values().forEach { type ->
            val fromDirectory =
                Constants.CLIENTS_PATH.resolve(version.toString()).resolve(type.name.lowercase()).resolve("original")
            val toDirectory =
                Constants.CLIENTS_PATH.resolve(version.toString()).resolve(type.name.lowercase()).resolve("patched")
            if (!Files.exists(toDirectory)) Files.createDirectories(toDirectory)
            val compressedDirectory =
                Constants.CLIENTS_PATH.resolve(version.toString()).resolve(type.name.lowercase()).resolve("compressed")
            if (!Files.exists(compressedDirectory)) Files.createDirectories(compressedDirectory)

            logger.info { "Patching type $type" }
            val config = ClientConfig.load(fromDirectory.resolve("jav_config.ws"))

            config.getFiles().forEach { file ->
                logger.info { "Patching file ${file.name}" }
                val isClient = file.name.contains("rs2client")
                Files.deleteIfExists(toDirectory.resolve(file.name))

                patchFile(type, fromDirectory.resolve(file.name), toDirectory.resolve(file.name), isClient)
            }

            logger.info { "Patching client config" }
            patchConfig(type, config, toDirectory)
            copyNativeRuntimeCompanions(type, toDirectory)

            Files.deleteIfExists(compressedDirectory.resolve("jav_config.ws"))
            Files.copy(toDirectory.resolve("jav_config.ws"), compressedDirectory.resolve("jav_config.ws"))
            config.getFiles().forEach { file ->
                logger.info { "Compressing ${file.name}" }
                val compressed = RSLZMAOutputStream.compress(Files.readAllBytes(toDirectory.resolve(file.name)))
                Files.write(compressedDirectory.resolve(file.name), compressed)
            }
        }

        if (skipLauncher) {
            logger.info { "Skipping launcher patching because --skip-launcher was requested" }
            return
        }

        logger.info { "Patching launchers from ${Constants.LAUNCHERS_PATH}" }
        if (!Files.exists(Constants.LAUNCHERS_PATH) || Files.list(Constants.LAUNCHERS_PATH).count() == 0L) {
            logger.warn { "No launchers found in ${Constants.LAUNCHERS_PATH}" }
            logger.warn { "Unable to patch launchers" }
            logger.warn { "Please place the un-patched Windows launcher in ${Constants.LAUNCHERS_PATH.resolve("win").resolve(
                "original.exe"
            )}" }
            return
        }

        Files.list(Constants.LAUNCHERS_PATH).forEach { type ->
            logger.info { "Patching launcher ${type.fileName}" }

            val from = type.resolve("original.exe")
            val to = type.resolve("patched.exe")

            if (!Files.exists(from))
                throw FileNotFoundException("original (un-patched) launcher at $from")

            logger.info { "Patching launcher $from to $to" }
            patchLauncher(from, to)
            copyLauncherRuntimeCompanions(type)
        }
    }

    private fun copyNativeRuntimeCompanions(type: BinaryType, toDirectory: Path) {
        if (type != BinaryType.WIN32C && type != BinaryType.WIN64C) {
            return
        }

        val launcherRoot = findLauncherRoot()
        if (launcherRoot == null) {
            logger.warn { "Could not find a Jagex Launcher install root; skipping native runtime companion copy for $type" }
            return
        }

        logger.info { "Syncing native runtime companion files for $type from $launcherRoot" }

        nativeRuntimeFiles.forEach { name ->
            val source = launcherRoot.resolve(name)
            val destination = toDirectory.resolve(name)
            if (!Files.exists(source) || Files.exists(destination)) {
                return@forEach
            }
            Files.copy(source, destination, StandardCopyOption.REPLACE_EXISTING)
        }

        copyDirectoryIfExists(launcherRoot.resolve("locales"), toDirectory.resolve("locales"))
        copyDirectoryIfExists(launcherRoot.resolve("swiftshader"), toDirectory.resolve("swiftshader"))
    }

    private fun copyLauncherRuntimeCompanions(toDirectory: Path) {
        val launcherRoot = findLauncherRoot()
        if (launcherRoot == null) {
            logger.warn { "Could not find a Jagex Launcher install root; skipping launcher runtime companion copy" }
            return
        }

        logger.info { "Syncing launcher runtime companion files from $launcherRoot" }

        nativeRuntimeFiles.forEach { name ->
            val source = launcherRoot.resolve(name)
            val destination = toDirectory.resolve(name)
            if (!Files.exists(source) || Files.exists(destination)) {
                return@forEach
            }
            Files.copy(source, destination, StandardCopyOption.REPLACE_EXISTING)
        }

        copyDirectoryIfExists(launcherRoot.resolve("locales"), toDirectory.resolve("locales"))
        copyDirectoryIfExists(launcherRoot.resolve("swiftshader"), toDirectory.resolve("swiftshader"))
    }

    private fun findLauncherRoot(): Path? {
        val candidates = listOfNotNull(
            System.getenv("ProgramFiles(x86)")?.let { Path.of(it).resolve("Jagex Launcher") },
            System.getenv("ProgramFiles")?.let { Path.of(it).resolve("Jagex Launcher") }
        )

        return candidates.firstOrNull { Files.exists(it.resolve("JagexLauncher.exe")) }
    }

    private fun copyDirectoryIfExists(source: Path, destination: Path) {
        if (!Files.exists(source) || Files.exists(destination)) {
            return
        }

        Files.walk(source).use { paths ->
            paths.forEach { path ->
                val relative = source.relativize(path)
                val target = destination.resolve(relative.toString())
                if (Files.isDirectory(path)) {
                    Files.createDirectories(target)
                } else {
                    Files.createDirectories(target.parent)
                    Files.copy(path, target, StandardCopyOption.REPLACE_EXISTING)
                }
            }
        }
    }

    private fun patchConfig(type: BinaryType, config: ClientConfig, filesPath: Path) {
        // Keep the original secure hostnames intact so the client still validates against
        // RuneScape endpoints on the secure path. We only rewrite the game socket ports here;
        // hostname interception is handled externally when needed.
        for (param in listOf(41, 43, 45, 47)) {
            config["param=$param"] = serverConfig.ports.game.toString()
        }

        config.getFiles().forEach { file ->
            val data = Files.readAllBytes(filesPath.resolve(file.name))
            val id = file.id

            config["download_hash_$id"] = generateFileHash(data, rsaConfig.launcher.modulus, rsaConfig.launcher.exponent)
            config["download_crc_$id"] = crc32(data).toString()
        }

        ClientConfig.save(config, filesPath.resolve("jav_config.ws"))
    }

    private fun applyBinaryPatch(raw: ByteArray, type: BinaryType, patch: BinaryPatch): Boolean {
        val end = patch.offset + patch.expected.size
        if (end > raw.size || patch.replacement.size != patch.expected.size) {
            logger.warn { "Invalid ${patch.description} patch definition for $type at 0x${patch.offset.toString(16)}" }
            return false
        }

        val window = raw.copyOfRange(patch.offset, end)
        if (window.contentEquals(patch.replacement)) {
            logger.info { "${patch.description} already present for $type at 0x${patch.offset.toString(16)}" }
            return true
        }

        if (!window.contentEquals(patch.expected)) {
            logger.warn {
                "Skipping ${patch.description} for $type at 0x${patch.offset.toString(16)} because bytes did not match"
            }
            return false
        }

        patch.replacement.copyInto(raw, patch.offset)
        logger.info { "Applied ${patch.description} for $type at 0x${patch.offset.toString(16)}" }
        return true
    }

    private fun patchFile(type: BinaryType, from: Path, to: Path, isClient: Boolean) {
        val raw = Files.readAllBytes(from)
        val skipJs5Patch = shouldSkipJs5Patch()

        // nothing to patch in non-client files
        if (!isClient) {
            Files.write(to, raw)
            return
        }

        if (!skipJs5Patch && oldJs5 == null) {
            val key = RSAUtil.findRSAKey(raw, 4096)
            if (key == null) {
                logger.warn { "Failed to find js5 RSA key in $from - copying file unchanged" }
                Files.write(to, raw)
                return
            }
            oldJs5 = key.toString(16).toByteArray(ASCII)
            logger.info { "Jagex public js5 key: ${key.toString(16)}" }
        }

        if (oldLogin == null) {
            val key = RSAUtil.findRSAKey(raw, 1024)
            if (key == null) {
                logger.warn { "Failed to find login RSA key in $from - copying file unchanged" }
                Files.write(to, raw)
                return
            }
            oldLogin = key.toString(16).toByteArray(ASCII)
            logger.info { "Jagex public login key: ${key.toString(16)}" }
        }

        if (skipJs5Patch) {
            logger.warn { "Skipping js5 key patch in ${type.name} file $from because OPENNXT_SKIP_JS5_CLIENT_PATCH is enabled" }
        } else if (!raw.replaceFirst(oldJs5!!, rsaConfig.js5.modulus.toString(16).toByteArray())) {
            logger.warn { "Failed to patch js5 key in ${type.name} file $from - copying file unchanged" }
            Files.write(to, raw)
            return
        }

        if (!raw.replaceFirst(oldLogin!!, rsaConfig.login.modulus.toString(16).toByteArray())) {
            logger.warn { "Failed to patch login key in ${type.name} file $from - copying file unchanged" }
            Files.write(to, raw)
            return
        }

        secureWorldValidationBypassPatches[type]?.forEach { patch ->
            applyBinaryPatch(raw, type, patch)
        }

        Files.write(to, raw)
    }

    private fun patchLauncher(from: Path, to: Path) {
        val raw = Files.readAllBytes(from)

        if (serverConfig.configUrl.length >= RUNESCAPE_CONFIG_URLS.maxOf { it.length }) {
            throw RuntimeException("Failed to patch launcher config url in $from because server config URL is too long")
        }

        if (oldLauncher == null) {
            val key = RSAUtil.findRSAKey(raw, 4096)
            if (key == null) {
                logger.error { "Failed to find launcher RSA key in $from - can't patch launcher" }
                exitProcess(1)
            }
            oldLauncher = key.toString(16).toByteArray(ASCII)
        }

        if (!raw.replaceFirst(oldLauncher!!, rsaConfig.launcher.modulus.toString(16).toByteArray()))
            throw RuntimeException("Failed to patch launcher rsa key in $from")

        if (!raw.replaceFirst(RUNESCAPE_REGEX.toByteArray(ASCII), "${PATCHED_REGEX}\u0000".toByteArray(ASCII)))
            throw RuntimeException("Failed to patch launcher regex in $from")

        val replacementConfigUrl = serverConfig.configUrl.toByteArray(ASCII)
        val patchedConfigUrl = RUNESCAPE_CONFIG_URLS.any { configUrl ->
            val needle = configUrl.toByteArray(ASCII)
            val index = raw.indexOf(needle)
            if (index == -1) {
                return@any false
            }

            for (offset in needle.indices) {
                raw[index + offset] = 0
            }
            replacementConfigUrl.copyInto(raw, index)
            true
        }

        if (!patchedConfigUrl)
            throw RuntimeException("Failed to patch launcher config url in $from")

        Files.write(to, raw)
    }

    private fun crc32(data: ByteArray): Long {
        val crc = CRC32()
        crc.update(data, 0, data.size)
        return crc.value
    }

    companion object {
        fun generateFileHash(data: ByteArray, modulus: BigInteger, exponent: BigInteger): String {
            val hash = ByteArray(65)
            hash[0] = 10
            Whirlpool.getHash(data, 0, data.size).copyInto(hash, 1)

            val rsa = BigInteger(hash).modPow(exponent, modulus).toByteArray()

            return Base64.getEncoder().encodeToString(rsa)
                .replace("\\+".toRegex(), "\\*")
                .replace("/".toRegex(), "\\-")
                .replace("=".toRegex(), "")
        }
    }

    class RSLZMAEncoderWrapper(
        private val encoder: Encoder,
        private val length: Int
    ) : Coder {
        override fun code(`in`: InputStream, out: OutputStream) {
            encoder.writeCoderProperties(out)
            for (i in 0..7) {
                out.write((length.toLong() ushr 8 * i).toInt() and 0xFF)
            }
            encoder.code(`in`, out, -1, -1, null)
        }
    }

    class RSLZMAOutputStream : CoderOutputStream {
        constructor(out: OutputStream, lzmaEncoder: Encoder, length: Int) : super(
            out,
            RSLZMAEncoderWrapper(lzmaEncoder, length)
        )

        constructor(out: OutputStream, wrapper: LzmaEncoderWrapper, length: Int) : super(out, wrapper)

        companion object {
            fun create(out: OutputStream, encoder: Encoder, length: Int): RSLZMAOutputStream {
                encoder.setDictionarySize(1 shl 23)
                encoder.setEndMarkerMode(true)
                encoder.setMatchFinder(1)
                encoder.setNumFastBytes(0x20)
                return RSLZMAOutputStream(out, encoder, length)
            }

            fun compress(data: ByteArray): ByteArray {
                val baos = ByteArrayOutputStream()
                val out = create(baos, Encoder(), data.size)
                out.write(data)
                out.flush()
                out.close()
                return baos.toByteArray()
            }
        }
    }

}
