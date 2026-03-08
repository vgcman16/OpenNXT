package com.opennxt

import com.opennxt.net.js5.Js5Session
import mu.KotlinLogging
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.atomic.AtomicBoolean

// TODO This should probably be re-done entirely.
object Js5Thread: Thread("js5-thread") {

    private val running = AtomicBoolean(true)
    private val logger = KotlinLogging.logger {  }
    private val sessions = CopyOnWriteArrayList<Js5Session>()
    private val waitLock = java.lang.Object()

    override fun run() {
        while (running.get()) {
            if (sessions.isEmpty()) {
                synchronized(waitLock) {
                    if (sessions.isEmpty() && running.get()) {
                        waitLock.wait(10)
                    }
                }
                continue
            }

            var processedAny = false
            sessions.forEach {
                if (it.process(10_000_000) != 0) {
                    processedAny = true
                }
            }

            if (!processedAny) {
                synchronized(waitLock) {
                    if (running.get()) {
                        waitLock.wait(1)
                    }
                }
            }
        }
    }

    fun addSession(session: Js5Session) {
        if (!sessions.contains(session)) {
            sessions.add(session)
        }
        wake()
    }

    fun removeSession(session: Js5Session) {
        sessions.remove(session)
        wake()
    }

    fun wake() {
        synchronized(waitLock) {
            waitLock.notifyAll()
        }
    }

}
