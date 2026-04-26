package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem

class ZeroPrefetch(private val label: String) : Prefetch {
    override fun calculateValue(store: Filesystem): Int = 0

    override fun describe(): String = label
}
