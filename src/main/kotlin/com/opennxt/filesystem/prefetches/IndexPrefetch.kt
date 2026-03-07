package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem
import mu.KotlinLogging

class IndexPrefetch(private val index: Int) : Prefetch {
    private val logger = KotlinLogging.logger { }

    override fun calculateValue(store: Filesystem): Int {
        var value = 0
        val buf = store.readReferenceTable(index)
        if (buf == null) {
            logger.warn { "Missing reference table for prefetch index $index; using 0" }
            return 0
        }

        val table = store.getReferenceTable(index)
        if (table == null) {
            logger.warn { "Missing decoded table for prefetch index $index; using 0" }
            return 0
        }

        if (table.mask and 0x4 != 0) {
            value += table.totalCompressedSize().toInt()
        } else {
            for (entry in table.archives.keys) {
                val archive = store.read(index, entry)
                if (archive == null) {
                    logger.debug { "Missing archive $entry in prefetch index $index; skipping it" }
                    continue
                }

                value += archive.capacity() - 2
            }
        }

        return value + buf.capacity()
    }
}
