package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem
import com.opennxt.filesystem.Index

class FilePrefetch(private val index: Int, private val name: String) : Prefetch {
    override fun calculateValue(store: Filesystem): Int {
        val file = store.read(index, name.lowercase()) ?: return 0

        return file.capacity() - 2
    }

    override fun describe(): String = "file:${Index.nameOf(index)}($index)/$name"

    override fun diagnose(store: Filesystem): List<String> =
        if (store.read(index, name.lowercase()) == null) {
            listOf("missing-file=$name")
        } else {
            emptyList()
        }

    override fun needs(store: Filesystem): List<String> =
        if (store.read(index, name.lowercase()) == null) {
            listOf("file $name in ${Index.nameOf(index)}($index)")
        } else {
            emptyList()
        }
}
