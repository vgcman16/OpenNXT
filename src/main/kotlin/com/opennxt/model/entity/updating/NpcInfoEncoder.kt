package com.opennxt.model.entity.updating

import io.netty.buffer.ByteBuf
import io.netty.buffer.Unpooled

object NpcInfoEncoder {
    fun createEmptyBuffer(): ByteBuf = Unpooled.buffer(0, 0)
}
