package com.opennxt.config

import com.moandjiezana.toml.Toml
import com.opennxt.Constants

class ServerConfig : TomlConfig() {
    companion object {
        val DEFAULT_PATH = Constants.CONFIG_PATH.resolve("server.toml")
    }

    data class Ports(
        var game: Int = 43594,
        var gameBackend: Int = 43594,
        var http: Int = 8080,
        var https: Int = 8443
    )

    data class LobbyBootstrap(
        var sendDefaultVarps: Boolean = false,
        var openRootInterface: Boolean = true,
        var openPrimaryChild814: Boolean = false,
        var openAlternateChild1322: Boolean = false,
        var sendPrimaryVarcLarge2771: Boolean = false,
        var sendPrimaryVarcSmall3496: Boolean = false,
        var sendPrimaryVarcString2508: Boolean = false,
        var sendPrimaryClientScript10936: Boolean = false
    )

    var ports = Ports()
    var hostname = "127.0.0.1"
    var configUrl = "http://127.0.0.1:8080/jav_config.ws?binaryType=6"

    var build = 946
    var lobbyBootstrap = LobbyBootstrap()

    override fun save(map: MutableMap<String, Any>) {
        map["networking"] = mapOf(
            "ports" to mapOf(
                "game" to ports.game,
                "gameBackend" to ports.gameBackend,
                "http" to ports.http,
                "https" to ports.https
            )
        )
        map["hostname"] = hostname
        map["configUrl"] = configUrl
        map["build"] = build
        map["lobby"] = mapOf(
            "bootstrap" to mapOf(
                "sendDefaultVarps" to lobbyBootstrap.sendDefaultVarps,
                "openRootInterface" to lobbyBootstrap.openRootInterface,
                "openPrimaryChild814" to lobbyBootstrap.openPrimaryChild814,
                "openAlternateChild1322" to lobbyBootstrap.openAlternateChild1322,
                "sendPrimaryVarcLarge2771" to lobbyBootstrap.sendPrimaryVarcLarge2771,
                "sendPrimaryVarcSmall3496" to lobbyBootstrap.sendPrimaryVarcSmall3496,
                "sendPrimaryVarcString2508" to lobbyBootstrap.sendPrimaryVarcString2508,
                "sendPrimaryClientScript10936" to lobbyBootstrap.sendPrimaryClientScript10936
            )
        )
    }

    override fun load(toml: Toml) {
        hostname = toml.getString("hostname", hostname)
        configUrl = toml.getString("configUrl", configUrl)
        build = toml.getLong("build", build.toLong()).toInt()

        val networking = toml.getTable("networking")
        if (networking != null) {
            val ports = networking.getTable("ports")
            if (ports != null) {
                this.ports.game = ports.getLong("game", this.ports.game.toLong()).toInt()
                this.ports.gameBackend = ports.getLong("gameBackend", this.ports.gameBackend.toLong()).toInt()
                this.ports.http = ports.getLong("http", this.ports.http.toLong()).toInt()
                this.ports.https = ports.getLong("https", this.ports.https.toLong()).toInt()
            }
        }

        val lobby = toml.getTable("lobby")
        if (lobby != null) {
            val bootstrap = lobby.getTable("bootstrap")
            if (bootstrap != null) {
                lobbyBootstrap.sendDefaultVarps =
                    bootstrap.getBoolean("sendDefaultVarps", lobbyBootstrap.sendDefaultVarps)
                lobbyBootstrap.openRootInterface =
                    bootstrap.getBoolean("openRootInterface", lobbyBootstrap.openRootInterface)
                lobbyBootstrap.openPrimaryChild814 =
                    bootstrap.getBoolean("openPrimaryChild814", lobbyBootstrap.openPrimaryChild814)
                lobbyBootstrap.openAlternateChild1322 =
                    bootstrap.getBoolean("openAlternateChild1322", lobbyBootstrap.openAlternateChild1322)
                lobbyBootstrap.sendPrimaryVarcLarge2771 =
                    bootstrap.getBoolean("sendPrimaryVarcLarge2771", lobbyBootstrap.sendPrimaryVarcLarge2771)
                lobbyBootstrap.sendPrimaryVarcSmall3496 =
                    bootstrap.getBoolean("sendPrimaryVarcSmall3496", lobbyBootstrap.sendPrimaryVarcSmall3496)
                lobbyBootstrap.sendPrimaryVarcString2508 =
                    bootstrap.getBoolean("sendPrimaryVarcString2508", lobbyBootstrap.sendPrimaryVarcString2508)
                lobbyBootstrap.sendPrimaryClientScript10936 =
                    bootstrap.getBoolean(
                        "sendPrimaryClientScript10936",
                        lobbyBootstrap.sendPrimaryClientScript10936
                    )
            }
        }
    }
}
