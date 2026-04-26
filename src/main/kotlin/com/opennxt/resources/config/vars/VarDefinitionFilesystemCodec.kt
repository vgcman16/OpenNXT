package com.opennxt.resources.config.vars

import com.opennxt.ext.getSmallSmartInt
import com.opennxt.ext.toByteArray
import com.opennxt.filesystem.Filesystem
import com.opennxt.resources.FilesystemResourceCodec
import it.unimi.dsi.fastutil.ints.Int2ObjectAVLTreeMap
import java.nio.ByteBuffer

class VarDefinitionFilesystemCodec<T : VarDefinition>(
    private val archiveCandidates: IntArray = intArrayOf(),
    private val emptyProvider: () -> T
) : FilesystemResourceCodec<T> {
    companion object {
        private const val CONFIG_INDEX = 2
    }

    override fun getMaxId(fs: Filesystem): Int {
        val table = fs.getReferenceTable(CONFIG_INDEX) ?: return 0
        val archives = candidateArchives(table.archives.keys.toIntArray())
        var maxId = 0
        archives.forEach { archiveId ->
            val fileIds = table.archives[archiveId]?.files?.keys ?: return@forEach
            if (fileIds.isNotEmpty()) {
                maxId = maxOf(maxId, fileIds.maxOrNull() ?: 0)
            }
        }
        return maxId
    }

    override fun list(fs: Filesystem): Map<Int, T> {
        val result = Int2ObjectAVLTreeMap<T>()
        val table = fs.getReferenceTable(CONFIG_INDEX) ?: return result
        candidateArchives(table.archives.keys.toIntArray()).forEach { archiveId ->
            val archive = table.loadArchive(archiveId) ?: return@forEach
            archive.files.forEach { (fileId, file) ->
                result[fileId] = decode(ByteBuffer.wrap(file.data))
            }
        }
        return result
    }

    override fun load(fs: Filesystem, id: Int): T? {
        val table = fs.getReferenceTable(CONFIG_INDEX) ?: return null
        candidateArchives(table.archives.keys.toIntArray()).forEach { archiveId ->
            val archive = table.loadArchive(archiveId) ?: return@forEach
            val file = archive.files[id] ?: return@forEach
            return decode(ByteBuffer.wrap(file.data))
        }
        return null
    }

    override fun store(fs: Filesystem, id: Int, data: T) {
        val table = fs.getReferenceTable(CONFIG_INDEX)
            ?: throw NullPointerException("index $CONFIG_INDEX table")
        val archiveId = candidateArchives(table.archives.keys.toIntArray()).firstOrNull() ?: 0
        val archive = table.loadOrCreateArchive(archiveId)
            ?: throw NullPointerException("failed to create or get archive $archiveId")
        archive.putFile(id, encode(data).toByteArray())
    }

    private fun candidateArchives(fallbackArchives: IntArray): IntArray {
        return if (archiveCandidates.isNotEmpty()) archiveCandidates else fallbackArchives
    }

    private fun decode(buffer: ByteBuffer): T {
        val definition = emptyProvider()
        while (buffer.hasRemaining()) {
            when (val opcode = buffer.get().toInt() and 0xFF) {
                0 -> return definition
                1 -> definition.type = ScriptVarType.getByChar((buffer.get().toInt() and 0xFF).toChar())
                2 -> definition.lifetime = buffer.get().toInt() and 0xFF
                4 -> definition.forceDefault = false
                101 -> definition.type = ScriptVarType.getById(buffer.getSmallSmartInt()) ?: definition.type
                else -> throw IllegalArgumentException("invalid VarDefinition opcode $opcode")
            }
        }
        return definition
    }

    private fun encode(data: T): ByteBuffer {
        val buffer = ByteBuffer.allocate(16)
        buffer.put(101.toByte())
        buffer.put(data.type.id.toByte())
        if (data.lifetime != 0) {
            buffer.put(2)
            buffer.put(data.lifetime.toByte())
        }
        if (!data.forceDefault) {
            buffer.put(4)
        }
        buffer.put(0)
        buffer.flip()
        return buffer
    }
}
