package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem
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
}
