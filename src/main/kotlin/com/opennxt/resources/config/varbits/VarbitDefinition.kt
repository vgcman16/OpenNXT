package com.opennxt.resources.config.varbits

import com.opennxt.resources.DefaultStateChecker

data class VarbitDefinition(
    var baseVar: Int = 0,
    var leastSignificantBit: Int = 0,
    var mostSignificantBit: Int = 0
) : DefaultStateChecker {
    companion object {
        private val DEFAULT = VarbitDefinition()
    }

    override fun isDefault(): Boolean = this == DEFAULT
}
