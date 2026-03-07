package com.opennxt.resources

import com.opennxt.resources.config.enums.EnumDefinition
import com.opennxt.resources.config.params.ParamDefinition
import com.opennxt.resources.config.structs.StructDefinition
import com.opennxt.resources.config.vars.impl.VarClanDefinition
import com.opennxt.resources.config.vars.impl.VarClanSettingDefinition
import com.opennxt.resources.config.vars.impl.VarClientDefinition
import com.opennxt.resources.config.vars.impl.VarNpcDefinition
import com.opennxt.resources.config.vars.impl.VarObjectDefinition
import com.opennxt.resources.config.vars.impl.VarPlayerDefinition
import com.opennxt.resources.config.vars.impl.VarRegionDefinition
import com.opennxt.resources.config.vars.impl.VarWorldDefinition
import kotlin.reflect.KClass

enum class ResourceType(val identifier: String, val kclass: KClass<*>) {
    ENUM("enum", EnumDefinition::class),
    PARAM("param", ParamDefinition::class),
    STRUCT("struct", StructDefinition::class),
    VAR_PLAYER("var-player", VarPlayerDefinition::class),
    VAR_NPC("var-npc", VarNpcDefinition::class),
    VAR_CLIENT("var-client", VarClientDefinition::class),
    VAR_WORLD("var-world", VarWorldDefinition::class),
    VAR_REGION("var-region", VarRegionDefinition::class),
    VAR_OBJECT("var-object", VarObjectDefinition::class),
    VAR_CLAN("var-clan", VarClanDefinition::class),
    VAR_CLAN_SETTING("var-clan-setting", VarClanSettingDefinition::class),
    ;

    companion object {
        private val values = values()

        fun getArchive(id: Int, size: Int): Int = id.ushr(size)

        fun getFile(id: Int, size: Int): Int = (id and (1 shl size) - 1)

        fun forClass(kclass: KClass<*>): ResourceType? = values.firstOrNull { it.kclass == kclass }
    }
}
