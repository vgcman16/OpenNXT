package com.opennxt.resources.config.varbits

import com.opennxt.ext.toByteArray
import com.opennxt.filesystem.Filesystem
import com.opennxt.resources.FilesystemResourceCodec
import com.opennxt.resources.ResourceType
import it.unimi.dsi.fastutil.ints.Int2ObjectAVLTreeMap
import java.nio.ByteBuffer

object VarbitFilesystemCodec : FilesystemResourceCodec<VarbitDefinition> {
    private const val CONFIG_INDEX = 22
    private const val FILES_PER_ARCHIVE = 10

    override fun getMaxId(fs: Filesystem): Int {
        val table = fs.getReferenceTable(CONFIG_INDEX) ?: return 0
        val maxArchive = table.highestEntry() - 1
        val files = table.archives[maxArchive]?.files?.lastKey() ?: return 0
        return maxArchive * FILES_PER_ARCHIVE + files
    }

    override fun list(fs: Filesystem): Map<Int, VarbitDefinition> {
        val result = Int2ObjectAVLTreeMap<VarbitDefinition>()
        for (i in 0..getMaxId(fs)) {
            val def = load(fs, i) ?: continue
            result[i] = def
        }
        return result
    }

    override fun load(fs: Filesystem, id: Int): VarbitDefinition? {
        val table = fs.getReferenceTable(CONFIG_INDEX) ?: return null
        val archiveId = ResourceType.getArchive(id, 5)
        val fileId = ResourceType.getFile(id, 5)
        val archive = table.loadArchive(archiveId) ?: return null
        val file = archive.files[fileId] ?: return null
        val buffer = ByteBuffer.wrap(file.data)
        val definition = VarbitDefinition()

        while (buffer.hasRemaining()) {
            when (val opcode = buffer.get().toInt() and 0xFF) {
                0 -> return definition
                1 -> {
                    definition.baseVar = buffer.short.toInt() and 0xFFFF
                    definition.leastSignificantBit = buffer.get().toInt() and 0xFF
                    definition.mostSignificantBit = buffer.get().toInt() and 0xFF
                }
                else -> throw IllegalArgumentException("invalid VarbitDefinition opcode $opcode")
            }
        }

        return definition
    }

    override fun store(fs: Filesystem, id: Int, data: VarbitDefinition) {
        val table = fs.getReferenceTable(CONFIG_INDEX)
            ?: throw NullPointerException("index $CONFIG_INDEX table")
        val archiveId = ResourceType.getArchive(id, 5)
        val fileId = ResourceType.getFile(id, 5)
        val archive = table.loadOrCreateArchive(archiveId)
            ?: throw NullPointerException("failed to create or get archive $archiveId")

        val buffer = ByteBuffer.allocate(6)
        buffer.put(1)
        buffer.putShort(data.baseVar.toShort())
        buffer.put(data.leastSignificantBit.toByte())
        buffer.put(data.mostSignificantBit.toByte())
        buffer.put(0)
        buffer.flip()
        archive.putFile(fileId, buffer.toByteArray())
    }
}
