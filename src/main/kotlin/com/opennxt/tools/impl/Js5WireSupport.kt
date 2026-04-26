package com.opennxt.tools.impl

import java.nio.ByteBuffer

object Js5WireSupport {
    data class ParsedResponseHeader(
        val index: Int,
        val archive: Int,
        val priority: Boolean,
        val compression: Int,
        val fileSize: Int,
        val containerBytes: Int
    )

    fun parseResponseHeader(headerBytes: ByteArray): ParsedResponseHeader {
        require(headerBytes.size >= 10) { "Expected at least 10 JS5 response header bytes, got ${headerBytes.size}" }

        val buffer = ByteBuffer.wrap(headerBytes)
        val rawIndex = buffer.get().toInt() and 0xFF
        val archive = buffer.int
        val compression = buffer.get().toInt() and 0xFF
        val fileSize = buffer.int
        val priority = rawIndex and 0x80 != 0
        val index = rawIndex and 0x7F

        return ParsedResponseHeader(
            index = index,
            archive = archive,
            priority = priority,
            compression = compression,
            fileSize = fileSize,
            containerBytes = fileSize + 5
        )
    }
}
