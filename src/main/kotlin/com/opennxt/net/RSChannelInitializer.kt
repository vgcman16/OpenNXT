package com.opennxt.net

import com.opennxt.net.handshake.HandshakeDecoder
import com.opennxt.net.handshake.HandshakeHandler
import io.netty.channel.ChannelInitializer
import io.netty.channel.socket.SocketChannel
import mu.KotlinLogging

class RSChannelInitializer: ChannelInitializer<SocketChannel>() {
    val logger = KotlinLogging.logger {  }
    private val tlsContext = ServerTls.context

    override fun initChannel(ch: SocketChannel) {
        val localPort = ch.localAddress().port
        logger.info { "TODO : Accept inbound connection from ${ch.remoteAddress()} to port $localPort" }
        PreLoginForensics.recordTransportEvent(
            localPort = localPort,
            remoteAddress = ch.remoteAddress().toString(),
            event = "channel-accepted",
        )

        ch.pipeline()
            .addLast("transport-sniffer", TransportSniffer(tlsContext))
            .addLast("handshake-decoder", HandshakeDecoder())
            .addLast("handshake-handler", HandshakeHandler())
    }
}
