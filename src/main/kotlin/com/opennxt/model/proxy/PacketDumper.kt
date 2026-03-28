package com.opennxt.model.proxy

import com.google.gson.GsonBuilder
import io.netty.buffer.ByteBuf
import java.io.OutputStream
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Path
import java.time.Instant
import java.util.concurrent.atomic.AtomicBoolean

class PacketDumper(file: Path) : AutoCloseable {
    data class StructuredRecord(
        val timestamp: Long,
        val opcode: Int,
        val packet: String,
        val source: String,
        val fields: Map<String, Any?>
    )

    var file: Path = file
        set(value) {
            if (open.get()) {
                throw IllegalStateException("Attempted to set path while file was already opened")
            }

            field = value
        }

    private val open = AtomicBoolean(false)
    private val lock = Any()
    private val gson = GsonBuilder().disableHtmlEscaping().create()

    private lateinit var stream: OutputStream
    private lateinit var structuredStream: OutputStream

    val structuredFile: Path
        get() = file.resolveSibling("${file.fileName.toString().substringBeforeLast('.', file.fileName.toString())}.jsonl")

    private fun ensureOpen() {
        if (!open.get()) {
            if (!Files.exists(file.parent))
                Files.createDirectories(file.parent)

            if (!Files.exists(file))
                Files.createFile(file)
            if (!Files.exists(structuredFile))
                Files.createFile(structuredFile)
            stream = Files.newOutputStream(file)
            structuredStream = Files.newOutputStream(structuredFile)

            open.set(true)
        }
    }

    fun dump(opcode: Int, data: ByteBuf) {
        val raw = ByteArray(data.readableBytes())
        data.markReaderIndex()
        data.readBytes(raw)
        data.resetReaderIndex()

        dump(opcode, raw)
    }

    fun dump(opcode: Int, data: ByteArray) {
        synchronized(lock) {
            ensureOpen()

            if (!open.get()) {
                throw IllegalStateException("Tried to write to closed file")
            }

            val toWrite = ByteArray(data.size + 14)

            val wrapper = ByteBuffer.wrap(toWrite)
            wrapper.putLong(Instant.now().toEpochMilli())
            wrapper.putShort(opcode.toShort())
            wrapper.putInt(data.size)
            wrapper.put(data)

            stream.write(toWrite)
        }
    }

    fun dumpStructured(opcode: Int, packet: String, source: String, fields: Map<String, Any?>) {
        synchronized(lock) {
            ensureOpen()

            if (!open.get()) {
                throw IllegalStateException("Tried to write to closed file")
            }

            val line = gson.toJson(
                StructuredRecord(
                    timestamp = Instant.now().toEpochMilli(),
                    opcode = opcode,
                    packet = packet,
                    source = source,
                    fields = LinkedHashMap(fields)
                )
            ) + System.lineSeparator()

            structuredStream.write(line.toByteArray(Charsets.UTF_8))
        }
    }

    override fun close() {
        synchronized(lock) {
            if (!open.get()) {
                return
            }
            open.set(false)

            stream.close()
            structuredStream.close()
        }
    }
}
