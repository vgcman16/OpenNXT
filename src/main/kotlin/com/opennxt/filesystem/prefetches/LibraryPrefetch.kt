package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem

class LibraryPrefetch(private val name: String) : Prefetch {
    override fun calculateValue(store: Filesystem): Int {
        val file = store.read(30, name.lowercase()) ?: return 0

        return file.capacity() - 2
    }

    override fun describe(): String = "library:$name"

    override fun diagnose(store: Filesystem): List<String> =
        if (store.read(30, name.lowercase()) == null) {
            listOf("missing-library=$name")
        } else {
            emptyList()
        }

    override fun needs(store: Filesystem): List<String> =
        if (store.read(30, name.lowercase()) == null) {
            listOf("library $name in DLLS(30)")
        } else {
            emptyList()
        }
}
