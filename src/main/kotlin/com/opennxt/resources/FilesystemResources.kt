package com.opennxt.resources

import com.opennxt.filesystem.Filesystem
import com.opennxt.resources.config.enums.EnumFilesystemCodec
import com.opennxt.resources.config.enums.EnumDiskCodec
import com.opennxt.resources.config.params.ParamDiskCodec
import com.opennxt.resources.config.params.ParamFilesystemCodec
import com.opennxt.resources.config.structs.StructDiskCodec
import com.opennxt.resources.config.structs.StructFilesystemCodec
import com.opennxt.resources.config.varbits.VarbitDiskCodec
import com.opennxt.resources.config.varbits.VarbitFilesystemCodec
import com.opennxt.resources.config.vars.VarDefinitionFilesystemCodec
import com.opennxt.resources.config.vars.VarConfigArchiveGroups
import com.opennxt.resources.config.vars.VarDefinitionDiskCodec
import com.opennxt.resources.config.vars.impl.VarClanDefinition
import com.opennxt.resources.config.vars.impl.VarClanSettingDefinition
import com.opennxt.resources.config.vars.impl.VarClientDefinition
import com.opennxt.resources.config.vars.impl.VarNpcDefinition
import com.opennxt.resources.config.vars.impl.VarObjectDefinition
import com.opennxt.resources.config.vars.impl.VarPlayerDefinition
import com.opennxt.resources.config.vars.impl.VarRegionDefinition
import com.opennxt.resources.config.vars.impl.VarWorldDefinition
import com.opennxt.resources.defaults.Defaults
import java.nio.file.Files
import java.nio.file.Path
import java.util.*
import kotlin.reflect.KClass

class FilesystemResources(val filesystem: Filesystem, val path: Path) {
    companion object {
        lateinit var instance: FilesystemResources
    }

    private val fsCodices = EnumMap<ResourceType, FilesystemResourceCodec<*>>(ResourceType::class.java)
    private val diskCodices = EnumMap<ResourceType, DiskResourceCodec<*>>(ResourceType::class.java)

    val defaults = Defaults(filesystem)

    init {
        instance = this

        if (!Files.exists(path))
            Files.createDirectories(path)

        fsCodices[ResourceType.ENUM] = EnumFilesystemCodec
        fsCodices[ResourceType.PARAM] = ParamFilesystemCodec
        fsCodices[ResourceType.STRUCT] = StructFilesystemCodec
        fsCodices[ResourceType.VAR_PLAYER] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.PLAYER,
            emptyProvider = ::VarPlayerDefinition
        )
        fsCodices[ResourceType.VAR_NPC] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.NPC,
            emptyProvider = ::VarNpcDefinition
        )
        fsCodices[ResourceType.VAR_CLIENT] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.CLIENT,
            emptyProvider = ::VarClientDefinition
        )
        fsCodices[ResourceType.VAR_WORLD] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.WORLD,
            emptyProvider = ::VarWorldDefinition
        )
        fsCodices[ResourceType.VAR_REGION] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.REGION,
            emptyProvider = ::VarRegionDefinition
        )
        fsCodices[ResourceType.VAR_OBJECT] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.OBJECT,
            emptyProvider = ::VarObjectDefinition
        )
        fsCodices[ResourceType.VAR_CLAN] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.CLAN,
            emptyProvider = ::VarClanDefinition
        )
        fsCodices[ResourceType.VAR_CLAN_SETTING] = VarDefinitionFilesystemCodec(
            archiveCandidates = VarConfigArchiveGroups.CLAN_SETTING,
            emptyProvider = ::VarClanSettingDefinition
        )
        fsCodices[ResourceType.VARBIT] = VarbitFilesystemCodec

        diskCodices[ResourceType.ENUM] = EnumDiskCodec
        diskCodices[ResourceType.PARAM] = ParamDiskCodec
        diskCodices[ResourceType.STRUCT] = StructDiskCodec
        diskCodices[ResourceType.VAR_PLAYER] = VarDefinitionDiskCodec(::VarPlayerDefinition)
        diskCodices[ResourceType.VAR_NPC] = VarDefinitionDiskCodec(::VarNpcDefinition)
        diskCodices[ResourceType.VAR_CLIENT] = VarDefinitionDiskCodec(::VarClientDefinition)
        diskCodices[ResourceType.VAR_WORLD] = VarDefinitionDiskCodec(::VarWorldDefinition)
        diskCodices[ResourceType.VAR_REGION] = VarDefinitionDiskCodec(::VarRegionDefinition)
        diskCodices[ResourceType.VAR_OBJECT] = VarDefinitionDiskCodec(::VarObjectDefinition)
        diskCodices[ResourceType.VAR_CLAN] = VarDefinitionDiskCodec(::VarClanDefinition)
        diskCodices[ResourceType.VAR_CLAN_SETTING] = VarDefinitionDiskCodec(::VarClanSettingDefinition)
        diskCodices[ResourceType.VARBIT] = VarbitDiskCodec
    }

    fun getFilesystemCodex(type: KClass<*>): FilesystemResourceCodec<*> {
        val resourceType =
            ResourceType.forClass(type) ?: throw NullPointerException("No resource type linked to type $type")

        return fsCodices[resourceType] ?: throw NullPointerException("No filesystem codex found for type $type")
    }

    fun getDiskCodec(type: KClass<*>): DiskResourceCodec<*> {
        val resourceType =
            ResourceType.forClass(type) ?: throw NullPointerException("No resource type linked to type $type")

        return diskCodices[resourceType] ?: throw NullPointerException("No disk codex found for type $type")
    }

    fun hasFilesystemCodec(type: KClass<*>): Boolean {
        val resourceType = ResourceType.forClass(type) ?: return false
        return fsCodices.containsKey(resourceType)
    }

    fun hasDiskCodec(type: KClass<*>): Boolean {
        val resourceType = ResourceType.forClass(type) ?: return false
        return diskCodices.containsKey(resourceType)
    }

    @Suppress("UNCHECKED_CAST")
    inline fun <reified T : Any> get(id: Int): T? {
        return getFilesystemCodex(T::class).load(filesystem, id) as? T
    }

    @Suppress("UNCHECKED_CAST")
    fun <T : Any> list(type: KClass<out T>): Map<Int, T> {
        return getFilesystemCodex(type).list(filesystem) as Map<Int, T>
    }
}
