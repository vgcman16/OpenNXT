package com.opennxt.login

import com.opennxt.Constants
import com.opennxt.model.proxy.PacketDumper
import com.opennxt.net.RSChannelAttributes
import com.opennxt.net.login.LoginPacket
import com.opennxt.net.proxy.ConnectedProxyClient
import com.opennxt.net.proxy.ProxyChannelAttributes
import com.opennxt.net.proxy.ProxyConnectionFactory
import com.opennxt.net.proxy.ProxyConnectionHandler
import com.opennxt.net.proxy.ProxyPlayer
import io.netty.channel.Channel
import mu.KotlinLogging
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.util.Locale

fun interface LoginProcessor {
    fun process(context: LoginContext)
}

object AuthoritativeLoginProcessor : LoginProcessor {
    override fun process(context: LoginContext) {
        context.result = LoginResult.SUCCESS
        context.callback(context)
    }
}

class ProxyLoginProcessor(
    private val usernames: Set<String>,
    private val connectionFactory: ProxyConnectionFactory,
    private val connectionHandler: ProxyConnectionHandler
) : LoginProcessor {
    private val logger = KotlinLogging.logger { }

    override fun process(context: LoginContext) {
        if (usernames.isNotEmpty() && context.username.lowercase() !in usernames) {
            logger.warn { "Rejecting proxy login for ${context.username}: username is not allow-listed" }
            context.result = LoginResult.INVALID_USERNAME_PASS
            context.callback(context)
            return
        }

        connectionFactory.createLogin(context.packet) { channel, result ->
            if (channel != null) {
                bindProxyPair(context, channel)
            }

            context.result = result
            context.callback(context)
        }
    }

    private fun bindProxyPair(context: LoginContext, upstreamChannel: Channel) {
        val now = DateTimeFormatter.ISO_LOCAL_DATE_TIME
            .withLocale(Locale.getDefault())
            .format(LocalDateTime.now())
            .replace(':', '-')
        val type = if (context.packet is LoginPacket.LobbyLoginRequest) "lobby" else "game"
        val dumpBase = Constants.PROXY_DUMP_PATH.resolve("$now-$type-${context.username}")

        val clientSide = ConnectedProxyClient(
            context.channel.attr(RSChannelAttributes.CONNECTED_CLIENT).get(),
            PacketDumper(dumpBase.resolve("clientprot.bin"))
        )
        val serverSide = ConnectedProxyClient(
            upstreamChannel.attr(RSChannelAttributes.CONNECTED_CLIENT).get(),
            PacketDumper(dumpBase.resolve("serverprot.bin"))
        )

        val player = ProxyPlayer(clientSide)

        context.channel.attr(ProxyChannelAttributes.PROXY_PLAYER).set(player)
        upstreamChannel.attr(ProxyChannelAttributes.PROXY_PLAYER).set(player)

        clientSide.connection.processUnidentifiedPackets = true
        serverSide.connection.processUnidentifiedPackets = true

        clientSide.other = serverSide
        serverSide.other = clientSide

        context.channel.attr(ProxyChannelAttributes.PROXY_CLIENT).set(clientSide)
        upstreamChannel.attr(ProxyChannelAttributes.PROXY_CLIENT).set(serverSide)

        context.channel.attr(RSChannelAttributes.PASSTHROUGH_CHANNEL).set(upstreamChannel)
        upstreamChannel.attr(RSChannelAttributes.PASSTHROUGH_CHANNEL).set(context.channel)

        connectionHandler.registerProxyConnection(clientSide, serverSide)
    }
}
