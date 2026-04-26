package com.opennxt.net.login

import java.net.InetSocketAddress
import java.net.SocketAddress
import java.util.concurrent.ConcurrentHashMap

object LoginUniqueIdStore {
    private val latestByHost = ConcurrentHashMap<String, Long>()

    fun getOrCreate(remoteAddress: SocketAddress?, generator: () -> Long): Long {
        val key = hostKey(remoteAddress) ?: return generator()
        return latestByHost.computeIfAbsent(key) { generator() }
    }

    fun resetForTests() {
        latestByHost.clear()
    }

    private fun hostKey(remoteAddress: SocketAddress?): String? {
        val address = remoteAddress as? InetSocketAddress ?: return remoteAddress?.toString()
        return address.address?.hostAddress ?: address.hostString
    }
}
