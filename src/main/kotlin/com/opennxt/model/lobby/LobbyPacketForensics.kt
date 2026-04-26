package com.opennxt.model.lobby

import com.google.gson.GsonBuilder
import com.opennxt.Constants
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption
import java.time.Instant

object LobbyPacketForensics {
    private val lock = Any()
    private val gson = GsonBuilder().disableHtmlEscaping().create()

    private data class LobbyClientPacketRecord(
        val timestamp: String,
        val timestampEpochMillis: Long,
        val username: String,
        val remoteAddress: String,
        val localAddress: String,
        val opcode: Int,
        val payloadSize: Int,
        val payloadHex: String,
        val previewHex: String,
        val bootstrapStage: String,
        val probableFamily: String?,
    )

    private fun tracePath(): Path =
        Constants.DATA_PATH.resolve("debug").resolve("lobby-client-packets.jsonl")

    fun recordClientPacket(
        username: String,
        remoteAddress: String,
        localAddress: String,
        opcode: Int,
        payloadHex: String,
        previewHex: String,
        bootstrapStage: String,
    ) {
        val probableFamily =
            when (opcode) {
                12, 118, 122 -> "if-button"
                27, 44, 57, 62, 89, 94, 109, 30625 -> "post-login-compat"
                else -> null
            }
        val now = Instant.now()
        val record = LobbyClientPacketRecord(
            timestamp = now.toString(),
            timestampEpochMillis = now.toEpochMilli(),
            username = username,
            remoteAddress = remoteAddress,
            localAddress = localAddress,
            opcode = opcode,
            payloadSize = payloadHex.length / 2,
            payloadHex = payloadHex,
            previewHex = previewHex,
            bootstrapStage = bootstrapStage,
            probableFamily = probableFamily,
        )

        synchronized(lock) {
            val path = tracePath()
            Files.createDirectories(path.parent)
            Files.writeString(
                path,
                gson.toJson(record) + System.lineSeparator(),
                StandardOpenOption.CREATE,
                StandardOpenOption.APPEND
            )
        }
    }
}
