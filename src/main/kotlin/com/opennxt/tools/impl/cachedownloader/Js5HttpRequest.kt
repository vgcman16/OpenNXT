package com.opennxt.tools.impl.cachedownloader

import java.net.URL

class Js5HttpRequest(
    val url: URL,
    val request: Js5RequestHandler.ArchiveRequest,
    private val timeoutMillis: Int
): Runnable {
    override fun run() {
        try {
            val connection = url.openConnection()
            connection.connectTimeout = timeoutMillis
            connection.readTimeout = timeoutMillis

            val data = connection.getInputStream().use { it.readBytes() }

            request.allocateBuffer(data.size + 2)
            request.buffer!!.put(data, 0, data.size)
            request.buffer!!.flip()

            request.notifyCompleted()
        } catch (_: Exception) {
            request.crashed = true
        }
    }
}
