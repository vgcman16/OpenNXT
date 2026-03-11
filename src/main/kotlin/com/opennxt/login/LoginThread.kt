package com.opennxt.login

import com.opennxt.net.login.LoginPacket
import io.netty.channel.Channel
import mu.KotlinLogging
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.atomic.AtomicBoolean

// TODO This should probably be re-done entirely.
object LoginThread : Thread("login-thread") {
    private val logger = KotlinLogging.logger { }
    @Volatile private var processor: LoginProcessor = AuthoritativeLoginProcessor

    val queue = LinkedBlockingQueue<LoginContext>()
    val running = AtomicBoolean(true)

    override fun run() {
        while (running.get()) {
            try {
                val next = queue.take()

                process(next)
            } catch (e: Exception) {
                logger.error(e) { "Uncaught exception occurred handling login request" }
            }
        }
    }

    fun configure(processor: LoginProcessor) {
        this.processor = processor
    }

    private fun process(context: LoginContext) {
        processor.process(context)
    }

    fun login(packet: LoginPacket, channel: Channel, callback: (LoginContext) -> Unit) {
        when (packet) {
            is LoginPacket.LobbyLoginRequest -> {
                queue.add(
                    LoginContext(
                        packet,
                        callback,
                        packet.build,
                        packet.username,
                        packet.password,
                        channel = channel
                    )
                )
            }
            is LoginPacket.GameLoginRequest -> {
                queue.add(
                    LoginContext(
                        packet,
                        callback,
                        packet.build,
                        packet.username,
                        packet.password,
                        channel = channel
                    )
                )
            }
            else -> throw IllegalArgumentException("expected LobbyLoginRequest or GameLoginRequest, got $packet")
        }
    }
}
