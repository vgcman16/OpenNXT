package com.opennxt.filesystem

import com.opennxt.filesystem.sqlite.SqliteFilesystem
import com.opennxt.filesystem.sqljet.SqlJetFilesystem
import mu.KotlinLogging
import java.nio.file.Path

private val filesystemLogger = KotlinLogging.logger { }

private const val FILESYSTEM_BACKEND_PROPERTY = "opennxt.filesystem.backend"
private const val FILESYSTEM_BACKEND_ENV = "OPENNXT_FILESYSTEM_BACKEND"

fun openFilesystem(path: Path): Filesystem {
    return when (resolveFilesystemBackend()) {
        FilesystemBackend.SQLITE -> {
            filesystemLogger.info { "Opening cache filesystem with native SQLite backend from $path" }
            SqliteFilesystem(path)
        }

        FilesystemBackend.SQLJET -> {
            filesystemLogger.info { "Opening cache filesystem with pure-Java SQLJet backend from $path" }
            SqlJetFilesystem(path)
        }

        FilesystemBackend.AUTO -> {
            try {
                filesystemLogger.info { "Opening cache filesystem with auto backend selection from $path" }
                SqliteFilesystem(path)
            } catch (t: Throwable) {
                if (t is VirtualMachineError || t is ThreadDeath) {
                    throw t
                }
                filesystemLogger.warn(t) {
                    "Native SQLite backend failed for $path; falling back to pure-Java SQLJet backend"
                }
                SqlJetFilesystem(path)
            }
        }
    }
}

private fun resolveFilesystemBackend(): FilesystemBackend {
    val raw = System.getProperty(FILESYSTEM_BACKEND_PROPERTY)
        ?: System.getenv(FILESYSTEM_BACKEND_ENV)
        ?: return FilesystemBackend.AUTO

    return when (raw.trim().lowercase()) {
        "sqlite" -> FilesystemBackend.SQLITE
        "sqljet" -> FilesystemBackend.SQLJET
        "auto" -> FilesystemBackend.AUTO
        else -> {
            filesystemLogger.warn {
                "Ignoring unknown filesystem backend '$raw'; expected auto, sqlite, or sqljet"
            }
            FilesystemBackend.AUTO
        }
    }
}

private enum class FilesystemBackend {
    AUTO,
    SQLITE,
    SQLJET,
}
