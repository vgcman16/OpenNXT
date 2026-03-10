package com.opennxt.net.handshake

enum class HandshakeType(val id: Int) {
    LOGIN(14),
    LOGIN_ALT(22),
    JS_5(15),
    ;

    companion object {
        private val VALUES = values();
        fun fromId(id: Int): HandshakeType? = VALUES.firstOrNull { it.id == id }
    }

}
