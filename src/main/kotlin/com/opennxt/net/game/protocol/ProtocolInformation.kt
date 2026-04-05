package com.opennxt.net.game.protocol

import com.opennxt.OpenNXT
import com.opennxt.config.TomlConfig
import com.opennxt.net.game.PacketRegistry
import mu.KotlinLogging
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlin.system.exitProcess

class ProtocolInformation(val path: Path) {
    private val logger = KotlinLogging.logger {  }
    lateinit var clientProtSizes: Opcode2SizeConfig
    lateinit var serverProtSizes: Opcode2SizeConfig
    lateinit var clientProtNames: Name2OpcodeConfig
    lateinit var serverProtNames: Name2OpcodeConfig

    private fun loadNameConfig(primary: Path, generatedFallback: Path): Name2OpcodeConfig {
        val primaryConfig =
            if (Files.exists(primary) && Files.size(primary) > 0L) {
                TomlConfig.load<Name2OpcodeConfig>(primary, mustExist = true)
            } else {
                null
            }

        if (primaryConfig != null && !primaryConfig.values.isEmpty()) {
            return primaryConfig
        }

        if (!Files.exists(generatedFallback) || Files.size(generatedFallback) == 0L) {
            return TomlConfig.load(primary, mustExist = true)
        }

        logger.warn {
            "Active protocol name mapping at $primary is missing or empty; " +
                "falling back to $generatedFallback and repairing the primary file"
        }
        val generatedConfig =
            TomlConfig.load<Name2OpcodeConfig>(generatedFallback, saveAfterLoad = false, mustExist = true)
        TomlConfig.save(primary, generatedConfig)
        return generatedConfig
    }

    fun load() {
        logger.info { "Loading protocol information from $path" }
        val clientProtSizesPath = path.resolve("clientProtSizes.toml")
        val serverProtSizesPath = path.resolve("serverProtSizes.toml")

        try {
            clientProtSizes = TomlConfig.load(clientProtSizesPath, mustExist = true)
        } catch (e: Exception) {
            e.printStackTrace()
            logger.error { "Protocol information not found for build ${OpenNXT.config.build}." }
            logger.error { " Looked in: ${path.resolve("clientProtSizes.toml")}" }
            logger.error { " Please look check out the following wiki page for help: <TO-DO>" }
            exitProcess(1)
        }
        logger.info {
            "Loaded client protocol sizes from ${clientProtSizesPath.toAbsolutePath().normalize()} " +
                "(cwd=${Paths.get("").toAbsolutePath().normalize()}, " +
                "lastModified=${Files.getLastModifiedTime(clientProtSizesPath)}, " +
                "opcode27=${clientProtSizes.values.getOrDefault(27, Int.MIN_VALUE)}, " +
                "opcode92=${clientProtSizes.values.getOrDefault(92, Int.MIN_VALUE)})"
        }

        try {
            serverProtSizes = TomlConfig.load(serverProtSizesPath, mustExist = true)
        } catch (e: Exception) {
            e.printStackTrace()
            logger.error { "Protocol information not found for build ${OpenNXT.config.build}." }
            logger.error { " Looked in: ${path.resolve("serverProtSizes.toml")}" }
            logger.error { " Please look check out the following wiki page for help: <TO-DO>" }
            exitProcess(1)
        }
        logger.info {
            "Loaded server protocol sizes from ${serverProtSizesPath.toAbsolutePath().normalize()} " +
                "(lastModified=${Files.getLastModifiedTime(serverProtSizesPath)})"
        }

        try {
            clientProtNames =
                loadNameConfig(
                    primary = path.resolve("clientProtNames.toml"),
                    generatedFallback = path.resolve("generated").resolve("phase3").resolve("clientProtNames.generated.toml")
                )
        } catch (e: Exception) {
            e.printStackTrace()
            logger.error { "Protocol information not found for build ${OpenNXT.config.build}." }
            logger.error { " Looked in: ${path.resolve("clientProtNames.toml")}" }
            logger.error { " Please look check out the following wiki page for help: <TO-DO>" }
            exitProcess(1)
        }

        try {
            serverProtNames =
                loadNameConfig(
                    primary = path.resolve("serverProtNames.toml"),
                    generatedFallback = path.resolve("generated").resolve("phase3").resolve("serverProtNames.generated.toml")
                )
        } catch (e: Exception) {
            e.printStackTrace()
            logger.error { "Protocol information not found for build ${OpenNXT.config.build}." }
            logger.error { " Looked in: ${path.resolve("serverProtNames.toml")}" }
            logger.error { " Please look check out the following wiki page for help: <TO-DO>" }
            exitProcess(1)
        }

        refreshPacketCodecs()
    }

    fun refreshPacketCodecs() {
        logger.info { "Refreshing packet codecs" }

        if (!Files.exists(path.resolve("clientProt")))
            Files.createDirectories(path.resolve("clientProt"))

        if (!Files.exists(path.resolve("serverProt")))
            Files.createDirectories(path.resolve("serverProt"))

        PacketRegistry.reload()
    }
}
