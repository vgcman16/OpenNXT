package com.opennxt.net.login

import com.opennxt.model.Build
import java.net.InetSocketAddress
import java.net.SocketAddress
import java.util.concurrent.ConcurrentHashMap

object LoginHandoffStore {
    data class LobbySnapshot(
        val build: Build,
        val username: String,
        val password: String,
        val remaining: ByteArray
    )

    private val latestByHost = ConcurrentHashMap<String, LobbySnapshot>()

    fun remember(remoteAddress: SocketAddress?, request: LoginPacket.LobbyLoginRequest) {
        val key = hostKey(remoteAddress) ?: return

        request.remaining.markReaderIndex()
        val remaining = ByteArray(request.remaining.readableBytes())
        request.remaining.readBytes(remaining)
        request.remaining.resetReaderIndex()

        latestByHost[key] = LobbySnapshot(
            build = request.build,
            username = request.username,
            password = request.password,
            remaining = remaining
        )
    }

    fun recall(remoteAddress: SocketAddress?): LobbySnapshot? {
        val key = hostKey(remoteAddress) ?: return null
        return latestByHost[key]
    }

    private fun hostKey(remoteAddress: SocketAddress?): String? {
        val address = remoteAddress as? InetSocketAddress ?: return remoteAddress?.toString()
        return address.address?.hostAddress ?: address.hostString
    }
}
