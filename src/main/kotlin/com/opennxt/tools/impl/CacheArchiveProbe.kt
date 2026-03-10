package com.opennxt.tools.impl

import com.github.ajalt.clikt.parameters.options.default
import com.github.ajalt.clikt.parameters.options.flag
import com.github.ajalt.clikt.parameters.options.option
import com.opennxt.tools.Tool

class CacheArchiveProbe : Tool(
    "cache-archive-probe",
    "Inspects selected cache archives and lists their file ids and sizes"
) {
    private val indicesArg by option(help = "Comma-separated indices to inspect")
        .default("3")
    private val archivesArg by option(help = "Comma-separated archive ids to inspect")
        .default("906,1322,814")
    private val includeFiles by option(help = "Include file ids and sizes for matching archives")
        .flag(default = true)

    override fun runTool() {
        val indices = parseCsv(indicesArg)
        val archives = parseCsv(archivesArg)

        require(indices.isNotEmpty()) { "No indices supplied" }
        require(archives.isNotEmpty()) { "No archives supplied" }

        val report = buildString {
            indices.forEach { index ->
                appendLine("index=$index")
                val table = filesystem.getReferenceTable(index)
                if (table == null) {
                    appendLine("  status=missing-reference-table")
                    appendLine()
                    return@forEach
                }

                appendLine("  archiveCount=${table.archives.size}")
                archives.forEach { archiveId ->
                    val entry = table.archives[archiveId]
                    if (entry == null) {
                        appendLine("  archive=$archiveId status=missing")
                        return@forEach
                    }

                    appendLine(
                        "  archive=$archiveId status=present compressedSize=${entry.compressedSize} " +
                            "uncompressedSize=${entry.uncompressedSize} version=${entry.version}"
                    )

                    if (!includeFiles) return@forEach

                    val loaded = table.loadArchive(archiveId)
                    if (loaded == null) {
                        appendLine("    loadStatus=failed")
                        return@forEach
                    }

                    val fileSummary = loaded.files.values.joinToString(", ") { file ->
                        "${file.id}:${file.data.size}"
                    }
                    appendLine("    fileCount=${loaded.files.size}")
                    appendLine("    files=$fileSummary")
                }
                appendLine()
            }
        }

        print(report)
    }

    private fun parseCsv(value: String): List<Int> = value.split(",")
        .mapNotNull { token ->
            val trimmed = token.trim()
            if (trimmed.isEmpty()) null else trimmed.toInt()
        }
}
