package com.opennxt.config

import com.moandjiezana.toml.Toml
import com.opennxt.Constants

class ServerConfig : TomlConfig() {
    companion object {
        val DEFAULT_PATH = Constants.CONFIG_PATH.resolve("server.toml")
    }

    data class Ports(
        var game: Int = 43594,
        var gameBackend: Int = 43596,
        var http: Int = 8080,
        var httpAliases: ArrayList<Int> = arrayListOf(),
        var https: Int = 8443
    )

    data class LobbyBootstrap(
        var sendWorldInitState: Boolean = false,
        var sendInitialStats: Boolean = true,
        var sendDefaultVarps: Boolean = true,
        var useForcedFallbackCandidateDefaultVarps: Boolean = false,
        var defaultVarpMinId: Int = 0,
        var defaultVarpMaxId: Int = Int.MAX_VALUE,
        var rebuildNormalAreaType: Int = 474,
        var rebuildNormalHash1: Int = Int.MIN_VALUE,
        var rebuildNormalHash2: Int = Int.MAX_VALUE,
        var sendInterfaceBootstrapScripts: Boolean = true,
        var sendInterfaceBootstrapAnnouncementScripts: Boolean = true,
        var sendInterfaceBootstrapPanelScripts: Boolean = true,
        var sendInterfaceBootstrapCompletionScripts: Boolean = true,
        var sendInterfaceBootstrapWidgetStateScripts: Boolean = true,
        var sendImmediateFollowupWorldSync: Boolean = false,
        var sendExperimentalActivePlayerOpensub: Boolean = true,
        var worldInterfaceSelfModelComponent: Int = 1,
        var worldInterfaceSelfHeadComponent: Int = -1,
        var sendServerTickEnd: Boolean = false,
        var compatServerpermAckOpcode: Int = 206,
        var compatWorldlistFetchReplyOpcode: Int = -1,
        var openRootInterface: Boolean = true,
        var openSupplementalChildInterfaces: Boolean = false,
        var trimWorldInterfaceTail: Boolean = false,
        var sendDeferredCompletionScripts: Boolean = true,
        var sendDeferredCompletionLiteScripts: Boolean = false,
        var sendDeferredCompletion10623Batch: Boolean = false,
        var sendDeferredCompletionCoreScripts: Boolean = false,
        var sendDeferredCompletionEventDelta: Boolean = false,
        var sendLateRootInterfaceEvents: Boolean = true,
        var openPrimaryChild814: Boolean = false,
        var openAlternateChild1322: Boolean = false,
        var sendPrimaryVarcLarge2771: Boolean = false,
        var sendPrimaryVarcSmall3496: Boolean = false,
        var sendPrimaryVarcString2508: Boolean = false,
        var sendPrimaryClientScript10936: Boolean = false,
        var sendSecondaryLobbyVarcs: Boolean = false,
        var sendLobbyNewsScripts: Boolean = false,
        var sendSocialInitPackets: Boolean = true
    )

    data class LobbyLoginResponse(
        var rights: Int = 0,
        var ip: Int = 0,
        var defaultWorldPort2: Int = 443
    )

    var ports = Ports()
    var hostname = "localhost"
    var gameHostname = "localhost"
    var configUrl = "http://content.runescape.com:8080/jav_config.ws?binaryType=6&hostRewrite=0&gameHostRewrite=1"

    var build = 947
    var lobbyBootstrap = LobbyBootstrap()
    var lobbyLoginResponse = LobbyLoginResponse()

    override fun save(map: MutableMap<String, Any>) {
        map["networking"] = mapOf(
            "ports" to mapOf(
                "game" to ports.game,
                "gameBackend" to ports.gameBackend,
                "http" to ports.http,
                "httpAliases" to ArrayList(ports.httpAliases),
                "https" to ports.https
            )
        )
        map["hostname"] = hostname
        map["gameHostname"] = gameHostname
        map["configUrl"] = configUrl
        map["build"] = build
        map["lobby"] = mapOf(
            "loginResponse" to mapOf(
                "rights" to lobbyLoginResponse.rights,
                "ip" to lobbyLoginResponse.ip,
                "defaultWorldPort2" to lobbyLoginResponse.defaultWorldPort2
            ),
            "bootstrap" to mapOf(
                "sendWorldInitState" to lobbyBootstrap.sendWorldInitState,
                "sendInitialStats" to lobbyBootstrap.sendInitialStats,
                "sendDefaultVarps" to lobbyBootstrap.sendDefaultVarps,
                "useForcedFallbackCandidateDefaultVarps" to lobbyBootstrap.useForcedFallbackCandidateDefaultVarps,
                "defaultVarpMinId" to lobbyBootstrap.defaultVarpMinId,
                "defaultVarpMaxId" to lobbyBootstrap.defaultVarpMaxId,
                "rebuildNormalAreaType" to lobbyBootstrap.rebuildNormalAreaType,
                "rebuildNormalHash1" to lobbyBootstrap.rebuildNormalHash1,
                "rebuildNormalHash2" to lobbyBootstrap.rebuildNormalHash2,
                "sendInterfaceBootstrapScripts" to lobbyBootstrap.sendInterfaceBootstrapScripts,
                "sendInterfaceBootstrapAnnouncementScripts" to lobbyBootstrap.sendInterfaceBootstrapAnnouncementScripts,
                "sendInterfaceBootstrapPanelScripts" to lobbyBootstrap.sendInterfaceBootstrapPanelScripts,
                "sendInterfaceBootstrapCompletionScripts" to lobbyBootstrap.sendInterfaceBootstrapCompletionScripts,
                "sendInterfaceBootstrapWidgetStateScripts" to lobbyBootstrap.sendInterfaceBootstrapWidgetStateScripts,
                "sendImmediateFollowupWorldSync" to lobbyBootstrap.sendImmediateFollowupWorldSync,
                "sendExperimentalActivePlayerOpensub" to lobbyBootstrap.sendExperimentalActivePlayerOpensub,
                "worldInterfaceSelfModelComponent" to lobbyBootstrap.worldInterfaceSelfModelComponent,
                "worldInterfaceSelfHeadComponent" to lobbyBootstrap.worldInterfaceSelfHeadComponent,
                "sendServerTickEnd" to lobbyBootstrap.sendServerTickEnd,
                "compatServerpermAckOpcode" to lobbyBootstrap.compatServerpermAckOpcode,
                "compatWorldlistFetchReplyOpcode" to lobbyBootstrap.compatWorldlistFetchReplyOpcode,
                "openRootInterface" to lobbyBootstrap.openRootInterface,
                "openSupplementalChildInterfaces" to lobbyBootstrap.openSupplementalChildInterfaces,
                "trimWorldInterfaceTail" to lobbyBootstrap.trimWorldInterfaceTail,
                "sendDeferredCompletionScripts" to lobbyBootstrap.sendDeferredCompletionScripts,
                "sendDeferredCompletionLiteScripts" to lobbyBootstrap.sendDeferredCompletionLiteScripts,
                "sendDeferredCompletion10623Batch" to lobbyBootstrap.sendDeferredCompletion10623Batch,
                "sendDeferredCompletionCoreScripts" to lobbyBootstrap.sendDeferredCompletionCoreScripts,
                "sendDeferredCompletionEventDelta" to lobbyBootstrap.sendDeferredCompletionEventDelta,
                "sendLateRootInterfaceEvents" to lobbyBootstrap.sendLateRootInterfaceEvents,
                "openPrimaryChild814" to lobbyBootstrap.openPrimaryChild814,
                "openAlternateChild1322" to lobbyBootstrap.openAlternateChild1322,
                "sendPrimaryVarcLarge2771" to lobbyBootstrap.sendPrimaryVarcLarge2771,
                "sendPrimaryVarcSmall3496" to lobbyBootstrap.sendPrimaryVarcSmall3496,
                "sendPrimaryVarcString2508" to lobbyBootstrap.sendPrimaryVarcString2508,
                "sendPrimaryClientScript10936" to lobbyBootstrap.sendPrimaryClientScript10936,
                "sendSecondaryLobbyVarcs" to lobbyBootstrap.sendSecondaryLobbyVarcs,
                "sendLobbyNewsScripts" to lobbyBootstrap.sendLobbyNewsScripts,
                "sendSocialInitPackets" to lobbyBootstrap.sendSocialInitPackets
            )
        )
    }

    override fun load(toml: Toml) {
        hostname = toml.getString("hostname", hostname)
        gameHostname = toml.getString("gameHostname", gameHostname)
        configUrl = toml.getString("configUrl", configUrl)
        build = toml.getLong("build", build.toLong()).toInt()

        val networking = toml.getTable("networking")
        if (networking != null) {
            val ports = networking.getTable("ports")
            if (ports != null) {
                this.ports.game = ports.getLong("game", this.ports.game.toLong()).toInt()
                this.ports.gameBackend = ports.getLong("gameBackend", this.ports.gameBackend.toLong()).toInt()
                this.ports.http = ports.getLong("http", this.ports.http.toLong()).toInt()
                val rawHttpAliases = ports.getList("httpAliases", emptyList<Any>())
                this.ports.httpAliases = ArrayList(
                    rawHttpAliases.map { alias ->
                        when (alias) {
                            is Number -> alias.toInt()
                            is String -> alias.trim().toInt()
                            else -> throw IllegalArgumentException("Unsupported http alias port value: $alias")
                        }
                    }
                )
                this.ports.https = ports.getLong("https", this.ports.https.toLong()).toInt()
            }
        }

        val lobby = toml.getTable("lobby")
        if (lobby != null) {
            val loginResponse = lobby.getTable("loginResponse")
            if (loginResponse != null) {
                lobbyLoginResponse.rights =
                    loginResponse.getLong("rights", lobbyLoginResponse.rights.toLong()).toInt()
                lobbyLoginResponse.ip =
                    loginResponse.getLong("ip", lobbyLoginResponse.ip.toLong()).toInt()
                lobbyLoginResponse.defaultWorldPort2 =
                    loginResponse.getLong(
                        "defaultWorldPort2",
                        lobbyLoginResponse.defaultWorldPort2.toLong()
                    ).toInt()
            }

            val bootstrap = lobby.getTable("bootstrap")
            if (bootstrap != null) {
                lobbyBootstrap.sendWorldInitState =
                    bootstrap.getBoolean("sendWorldInitState", lobbyBootstrap.sendWorldInitState)
                lobbyBootstrap.sendInitialStats =
                    bootstrap.getBoolean("sendInitialStats", lobbyBootstrap.sendInitialStats)
                lobbyBootstrap.sendDefaultVarps =
                    bootstrap.getBoolean("sendDefaultVarps", lobbyBootstrap.sendDefaultVarps)
                lobbyBootstrap.useForcedFallbackCandidateDefaultVarps =
                    bootstrap.getBoolean(
                        "useForcedFallbackCandidateDefaultVarps",
                        lobbyBootstrap.useForcedFallbackCandidateDefaultVarps
                    )
                lobbyBootstrap.defaultVarpMinId =
                    bootstrap.getLong("defaultVarpMinId", lobbyBootstrap.defaultVarpMinId.toLong()).toInt()
                lobbyBootstrap.defaultVarpMaxId =
                    bootstrap.getLong("defaultVarpMaxId", lobbyBootstrap.defaultVarpMaxId.toLong()).toInt()
                lobbyBootstrap.rebuildNormalAreaType =
                    bootstrap.getLong(
                        "rebuildNormalAreaType",
                        lobbyBootstrap.rebuildNormalAreaType.toLong()
                    ).toInt()
                lobbyBootstrap.rebuildNormalHash1 =
                    bootstrap.getLong(
                        "rebuildNormalHash1",
                        lobbyBootstrap.rebuildNormalHash1.toLong()
                    ).toInt()
                lobbyBootstrap.rebuildNormalHash2 =
                    bootstrap.getLong(
                        "rebuildNormalHash2",
                        lobbyBootstrap.rebuildNormalHash2.toLong()
                    ).toInt()
                lobbyBootstrap.sendInterfaceBootstrapScripts =
                    bootstrap.getBoolean(
                        "sendInterfaceBootstrapScripts",
                        lobbyBootstrap.sendInterfaceBootstrapScripts
                    )
                lobbyBootstrap.sendInterfaceBootstrapAnnouncementScripts =
                    bootstrap.getBoolean(
                        "sendInterfaceBootstrapAnnouncementScripts",
                        lobbyBootstrap.sendInterfaceBootstrapAnnouncementScripts
                    )
                lobbyBootstrap.sendInterfaceBootstrapPanelScripts =
                    bootstrap.getBoolean(
                        "sendInterfaceBootstrapPanelScripts",
                        lobbyBootstrap.sendInterfaceBootstrapPanelScripts
                    )
                lobbyBootstrap.sendInterfaceBootstrapCompletionScripts =
                    bootstrap.getBoolean(
                        "sendInterfaceBootstrapCompletionScripts",
                        lobbyBootstrap.sendInterfaceBootstrapCompletionScripts
                    )
                lobbyBootstrap.sendInterfaceBootstrapWidgetStateScripts =
                    bootstrap.getBoolean(
                        "sendInterfaceBootstrapWidgetStateScripts",
                        lobbyBootstrap.sendInterfaceBootstrapWidgetStateScripts
                    )
                lobbyBootstrap.sendImmediateFollowupWorldSync =
                    bootstrap.getBoolean(
                        "sendImmediateFollowupWorldSync",
                        lobbyBootstrap.sendImmediateFollowupWorldSync
                    )
                lobbyBootstrap.sendExperimentalActivePlayerOpensub =
                    bootstrap.getBoolean(
                        "sendExperimentalActivePlayerOpensub",
                        lobbyBootstrap.sendExperimentalActivePlayerOpensub
                    )
                lobbyBootstrap.worldInterfaceSelfModelComponent =
                    bootstrap.getLong(
                        "worldInterfaceSelfModelComponent",
                        lobbyBootstrap.worldInterfaceSelfModelComponent.toLong()
                    ).toInt()
                lobbyBootstrap.worldInterfaceSelfHeadComponent =
                    bootstrap.getLong(
                        "worldInterfaceSelfHeadComponent",
                        lobbyBootstrap.worldInterfaceSelfHeadComponent.toLong()
                    ).toInt()
                lobbyBootstrap.sendServerTickEnd =
                    bootstrap.getBoolean("sendServerTickEnd", lobbyBootstrap.sendServerTickEnd)
                lobbyBootstrap.compatServerpermAckOpcode =
                    bootstrap.getLong(
                        "compatServerpermAckOpcode",
                        lobbyBootstrap.compatServerpermAckOpcode.toLong()
                    ).toInt()
                lobbyBootstrap.compatWorldlistFetchReplyOpcode =
                    bootstrap.getLong(
                        "compatWorldlistFetchReplyOpcode",
                        lobbyBootstrap.compatWorldlistFetchReplyOpcode.toLong()
                    ).toInt()
                lobbyBootstrap.openRootInterface =
                    bootstrap.getBoolean("openRootInterface", lobbyBootstrap.openRootInterface)
                lobbyBootstrap.openSupplementalChildInterfaces =
                    bootstrap.getBoolean(
                        "openSupplementalChildInterfaces",
                        lobbyBootstrap.openSupplementalChildInterfaces
                    )
                lobbyBootstrap.trimWorldInterfaceTail =
                    bootstrap.getBoolean(
                        "trimWorldInterfaceTail",
                        lobbyBootstrap.trimWorldInterfaceTail
                    )
                lobbyBootstrap.sendDeferredCompletionScripts =
                    bootstrap.getBoolean(
                        "sendDeferredCompletionScripts",
                        lobbyBootstrap.sendDeferredCompletionScripts
                    )
                lobbyBootstrap.sendDeferredCompletionLiteScripts =
                    bootstrap.getBoolean(
                        "sendDeferredCompletionLiteScripts",
                        lobbyBootstrap.sendDeferredCompletionLiteScripts
                    )
                lobbyBootstrap.sendDeferredCompletion10623Batch =
                    bootstrap.getBoolean(
                        "sendDeferredCompletion10623Batch",
                        lobbyBootstrap.sendDeferredCompletion10623Batch
                    )
                lobbyBootstrap.sendDeferredCompletionCoreScripts =
                    bootstrap.getBoolean(
                        "sendDeferredCompletionCoreScripts",
                        lobbyBootstrap.sendDeferredCompletionCoreScripts
                    )
                lobbyBootstrap.sendDeferredCompletionEventDelta =
                    bootstrap.getBoolean(
                        "sendDeferredCompletionEventDelta",
                        lobbyBootstrap.sendDeferredCompletionEventDelta
                    )
                lobbyBootstrap.sendLateRootInterfaceEvents =
                    bootstrap.getBoolean(
                        "sendLateRootInterfaceEvents",
                        lobbyBootstrap.sendLateRootInterfaceEvents
                    )
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
                lobbyBootstrap.sendSecondaryLobbyVarcs =
                    bootstrap.getBoolean(
                        "sendSecondaryLobbyVarcs",
                        lobbyBootstrap.sendSecondaryLobbyVarcs
                    )
                lobbyBootstrap.sendLobbyNewsScripts =
                    bootstrap.getBoolean(
                        "sendLobbyNewsScripts",
                        lobbyBootstrap.sendLobbyNewsScripts
                    )
                lobbyBootstrap.sendSocialInitPackets =
                    bootstrap.getBoolean(
                        "sendSocialInitPackets",
                        lobbyBootstrap.sendSocialInitPackets
                    )
            }
        }
    }
}
