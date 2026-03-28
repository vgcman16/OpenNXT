package com.opennxt.filesystem.prefetches

import com.opennxt.filesystem.Filesystem
import com.opennxt.filesystem.Index
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

    override fun describe(): String = "index:${Index.nameOf(index)}($index)"

    override fun diagnose(store: Filesystem): List<String> {
        val problems = mutableListOf<String>()
        val refTable = store.readReferenceTable(index)
        if (refTable == null) {
            problems += "missing-reference-table"
            return problems
        }

        val table = store.getReferenceTable(index)
        if (table == null) {
            problems += "missing-decoded-table"
            return problems
        }

        if (table.mask and 0x4 == 0) {
            val missingArchives = table.archives.keys.count { archiveId ->
                store.read(index, archiveId) == null
            }
            if (missingArchives > 0) {
                problems += "missing-archives=$missingArchives"
            }
        }

        return problems
    }

    override fun needs(store: Filesystem): List<String> {
        val needs = mutableListOf<String>()
        val refTable = store.readReferenceTable(index)
        if (refTable == null) {
            needs += "reference table for ${Index.nameOf(index)}($index)"
            return needs
        }

        val table = store.getReferenceTable(index)
        if (table == null) {
            needs += "decoded reference table for ${Index.nameOf(index)}($index)"
            return needs
        }

        if (table.mask and 0x4 == 0) {
            val missingArchives = table.archives.keys.count { archiveId ->
                store.read(index, archiveId) == null
            }
            if (missingArchives > 0) {
                needs += "$missingArchives archive container(s) in ${Index.nameOf(index)}($index)"
            }
        }

        return needs
    }
}
