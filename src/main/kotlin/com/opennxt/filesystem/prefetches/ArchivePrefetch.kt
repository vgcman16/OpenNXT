package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem
import com.opennxt.filesystem.Index
import mu.KotlinLogging

class ArchivePrefetch(private val index: Int, private val archive: Int) : Prefetch {
    private val logger = KotlinLogging.logger { }

    override fun calculateValue(store: Filesystem): Int {
        val file = store.read(index, archive)
        if (file == null) {
            logger.warn { "Missing prefetch archive [$index, $archive]; using 0" }
            return 0
        }

        return file.capacity() - 2
    }

    override fun describe(): String = "archive:${Index.nameOf(index)}($index)/$archive"

    override fun diagnose(store: Filesystem): List<String> =
        if (store.read(index, archive) == null) {
            listOf("missing-archive=$archive")
        } else {
            emptyList()
        }

    override fun needs(store: Filesystem): List<String> =
        if (store.read(index, archive) == null) {
            listOf("archive $archive in ${Index.nameOf(index)}($index)")
        } else {
            emptyList()
        }
}
