package com.opennxt.filesystem.sqljet

import org.tmatesoft.sqljet.core.SqlJetException
import org.tmatesoft.sqljet.core.table.ISqlJetCursor
import org.tmatesoft.sqljet.core.table.SqlJetDb
import java.io.Closeable
import java.nio.file.Files
import java.nio.file.Path

/**
 * Read-write accessor to cache indices using SQLJet's pure-Java SQLite engine.
 */
class SqlJetIndexFile(val path: Path) : Closeable, AutoCloseable {
    private val dbLock = Any()
    private val db: SqlJetDb

    init {
        val parent = path.parent
        if (parent != null && !Files.exists(parent)) {
            Files.createDirectories(parent)
        }

        db = SqlJetDb.open(path.toFile(), true)
        ensureSchema()
    }

    private fun ensureSchema() {
        synchronized(dbLock) {
            val schema = db.schema
            if (schema.getTable(CACHE_TABLE) == null) {
                db.createTable(
                    """
                    CREATE TABLE $CACHE_TABLE(
                      KEY INTEGER PRIMARY KEY,
                      DATA BLOB,
                      VERSION INTEGER,
                      CRC INTEGER
                    );
                    """.trimIndent()
                )
            }
            if (schema.getTable(CACHE_INDEX_TABLE) == null) {
                db.createTable(
                    """
                    CREATE TABLE $CACHE_INDEX_TABLE(
                      KEY INTEGER PRIMARY KEY,
                      DATA BLOB,
                      VERSION INTEGER,
                      CRC INTEGER
                    );
                    """.trimIndent()
                )
            }
        }
    }

    fun putRawTable(data: ByteArray, version: Int, crc: Int): Int {
        synchronized(dbLock) {
            db.runWriteTransaction { database ->
                upsert(database, CACHE_INDEX_TABLE, 1L, data, version, crc)
                1
            }
        }
        return 1
    }

    fun putRaw(archive: Int, data: ByteArray, version: Int, crc: Int): Int {
        synchronized(dbLock) {
            db.runWriteTransaction { database ->
                upsert(database, CACHE_TABLE, archive.toLong(), data, version, crc)
                1
            }
        }
        return 1
    }

    fun hasReferenceTable(): Boolean = exists(CACHE_INDEX_TABLE, 1)

    fun getMaxArchive(): Int {
        synchronized(dbLock) {
            return db.runReadTransaction { database ->
                val table = database.getTable(CACHE_TABLE)
                table.order(null).useCursor { cursor ->
                    if (!cursor.last()) {
                        0
                    } else {
                        cursor.getInteger(KEY_COLUMN).toInt()
                    }
                }
            } as Int
        }
    }

    fun exists(id: Int): Boolean = exists(CACHE_TABLE, id)

    private fun exists(tableName: String, id: Int): Boolean {
        synchronized(dbLock) {
            return db.runReadTransaction { database ->
                database.getTable(tableName).lookup(null, id.toLong()).useCursor { cursor ->
                    !cursor.eof()
                }
            } as Boolean
        }
    }

    fun getRaw(id: Int): ByteArray? = getBlob(CACHE_TABLE, id)

    fun getRawTable(): ByteArray? = getBlob(CACHE_INDEX_TABLE, 1)

    private fun getBlob(tableName: String, id: Int): ByteArray? {
        synchronized(dbLock) {
            return db.runReadTransaction { database ->
                database.getTable(tableName).lookup(null, id.toLong()).useCursor { cursor ->
                    if (cursor.eof()) {
                        null
                    } else {
                        cursor.getBlobAsArray(DATA_COLUMN)
                    }
                }
            } as ByteArray?
        }
    }

    override fun close() {
        synchronized(dbLock) {
            db.close()
        }
    }

    private fun upsert(
        database: SqlJetDb,
        tableName: String,
        key: Long,
        data: ByteArray,
        version: Int,
        crc: Int,
    ) {
        val table = database.getTable(tableName)
        table.lookup(null, key).useCursor { cursor ->
            if (cursor.eof()) {
                table.insertByFieldNames(
                    linkedMapOf<String, Any>(
                        KEY_COLUMN to key,
                        DATA_COLUMN to data,
                        VERSION_COLUMN to version,
                        CRC_COLUMN to crc,
                    )
                )
            } else {
                cursor.updateByFieldNames(
                    linkedMapOf<String, Any>(
                        DATA_COLUMN to data,
                        VERSION_COLUMN to version,
                        CRC_COLUMN to crc,
                    )
                )
            }
        }
    }

    private inline fun <T> ISqlJetCursor.useCursor(block: (ISqlJetCursor) -> T): T {
        return try {
            block(this)
        } finally {
            try {
                close()
            } catch (_: SqlJetException) {
            }
        }
    }

    private companion object {
        private const val CACHE_TABLE = "cache"
        private const val CACHE_INDEX_TABLE = "cache_index"
        private const val KEY_COLUMN = "KEY"
        private const val DATA_COLUMN = "DATA"
        private const val VERSION_COLUMN = "VERSION"
        private const val CRC_COLUMN = "CRC"
    }
}
