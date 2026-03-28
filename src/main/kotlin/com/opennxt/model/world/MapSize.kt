package com.opennxt.model.world

enum class MapSize(val id: Int, val size: Int) {
    SIZE_104(0, 104),
    SIZE_120(1, 120),
    SIZE_136(2, 136),
    SIZE_168(3, 168),
    SIZE_72(4, 72),
    SIZE_256(5, 256);

    fun rebuildWireId(build: Int): Int {
        // Historical 946 plateau logs consistently use wire value 5 for the
        // standard 104-tile world bootstrap, even though local scene math uses 104.
        return if (build == 946 && this == SIZE_104) SIZE_256.id else id
    }
}
