package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem

interface Prefetch {
    fun calculateValue(store: Filesystem): Int
    fun describe(): String = this::class.simpleName ?: "UnknownPrefetch"
    fun diagnose(store: Filesystem): List<String> = emptyList()
    fun needs(store: Filesystem): List<String> = emptyList()
}
