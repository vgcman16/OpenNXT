package com.opennxt.filesystem.sqljet

import org.junit.jupiter.api.io.TempDir
import java.nio.ByteBuffer
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertContentEquals
import kotlin.test.assertEquals
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SqlJetFilesystemTest {
    @TempDir
    lateinit var tempDir: Path

    @Test
    fun `sqljet filesystem roundtrips raw archives and reference tables`() {
        SqlJetFilesystem(tempDir).use { filesystem ->
            filesystem.createIndex(0)
            filesystem.createIndex(1)

            filesystem.writeReferenceTable(
                index = 0,
                compressed = byteArrayOf(0x01, 0x02, 0x03, 0x04),
                version = 7,
                crc = 99,
            )
            filesystem.write(
                index = 0,
                archive = 22,
                compressed = byteArrayOf(0x05, 0x06, 0x07),
                version = 3,
                crc = 44,
            )

            assertEquals(2, filesystem.numIndices())
            assertTrue(filesystem.exists(0, 22))
            assertContentEquals(
                byteArrayOf(0x05, 0x06, 0x07),
                filesystem.read(0, 22).requireBytes(),
            )
            assertContentEquals(
                byteArrayOf(0x01, 0x02, 0x03, 0x04),
                filesystem.readReferenceTable(0).requireBytes(),
            )
        }

        SqlJetFilesystem(tempDir).use { reopened ->
            assertEquals(2, reopened.numIndices())
            assertTrue(reopened.exists(0, 22))
            assertContentEquals(
                byteArrayOf(0x05, 0x06, 0x07),
                reopened.read(0, 22).requireBytes(),
            )
            assertContentEquals(
                byteArrayOf(0x01, 0x02, 0x03, 0x04),
                reopened.readReferenceTable(0).requireBytes(),
            )
        }
    }

    private fun ByteBuffer?.requireBytes(): ByteArray {
        val buffer = assertNotNull(this)
        val duplicate = buffer.duplicate()
        return ByteArray(duplicate.remaining()).also(duplicate::get)
    }
}
