package com.opennxt.resources.config.varbits

import com.moandjiezana.toml.Toml
import com.moandjiezana.toml.TomlWriter
import com.opennxt.resources.DiskResourceCodec
import it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap
import java.nio.file.Files
import java.nio.file.Path

object VarbitDiskCodec : DiskResourceCodec<VarbitDefinition> {
    override fun list(path: Path): Map<String, Path> {
        val result = Object2ObjectOpenHashMap<String, Path>()
        if (!Files.exists(path)) {
            return result
        }

        Files.list(path).forEach { file ->
            if (Files.isRegularFile(file)) {
                val name = file.fileName.toString().lowercase()
                if (name.endsWith(".toml")) {
                    result[name.substring(0, name.length - 5)] = file
                }
            } else if (Files.isDirectory(file)) {
                result.putAll(list(file))
            }
        }
        return result
    }

    override fun load(path: Path): VarbitDefinition? {
        if (!Files.exists(path)) return null

        val values = Toml().read(path.toFile()).getTable("values")?.toMap() ?: emptyMap<String, Any>()
        return VarbitDefinition(
            baseVar = (values["baseVar"] as? Number)?.toInt() ?: 0,
            leastSignificantBit = (values["leastSignificantBit"] as? Number)?.toInt() ?: 0,
            mostSignificantBit = (values["mostSignificantBit"] as? Number)?.toInt() ?: 0
        )
    }

    override fun store(path: Path, data: VarbitDefinition) {
        Files.createDirectories(path.parent)
        Files.deleteIfExists(path)
        TomlWriter().write(
            mapOf(
                "values" to mapOf(
                    "baseVar" to data.baseVar,
                    "leastSignificantBit" to data.leastSignificantBit,
                    "mostSignificantBit" to data.mostSignificantBit
                )
            ),
            path.toFile()
        )
    }

    override fun getFileExtension(resource: VarbitDefinition): String? = "toml"
}
