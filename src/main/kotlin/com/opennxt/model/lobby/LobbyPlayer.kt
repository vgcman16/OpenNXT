package com.opennxt.model.lobby

import com.opennxt.OpenNXT
import com.opennxt.api.stat.StatContainer
import com.opennxt.impl.stat.PlayerStatContainer
import com.opennxt.model.entity.BasePlayer
import com.opennxt.model.entity.player.InterfaceManager
import com.opennxt.model.worldlist.WorldFlag
import com.opennxt.model.worldlist.WorldList
import com.opennxt.model.worldlist.WorldListEntry
import com.opennxt.model.worldlist.WorldListLocation
import com.opennxt.net.ConnectedClient
import com.opennxt.net.Side
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.clientprot.ClientCheat
import com.opennxt.net.game.clientprot.WorldlistFetch
import com.opennxt.net.game.handlers.ClientCheatHandler
import com.opennxt.net.game.handlers.NoTimeoutHandler
import com.opennxt.net.game.handlers.WorldlistFetchHandler
import com.opennxt.net.game.pipeline.OpcodeWithBuffer
import com.opennxt.net.game.pipeline.GamePacketHandler
import com.opennxt.net.game.serverprot.*
import com.opennxt.net.game.serverprot.variables.ClientSetvarcLarge
import com.opennxt.net.game.serverprot.variables.ClientSetvarcSmall
import com.opennxt.net.game.serverprot.variables.ClientSetvarcstrSmall
import com.opennxt.net.game.serverprot.variables.ResetClientVarcache
import com.opennxt.net.proxy.UnidentifiedPacket
import io.netty.buffer.ByteBufUtil
import io.netty.buffer.Unpooled
import it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap
import mu.KotlinLogging
import kotlin.reflect.KClass

class LobbyPlayer(client: ConnectedClient, name: String) : BasePlayer(client, name) {
    private data class LobbyChildInterface(
        val id: Int,
        val component: Int
    )

    private data class LobbyNewsItem(
        val slot: Int,
        val imageId: Int,
        val category: Int,
        val title: String,
        val body: String,
        val slug: String,
        val date: String,
        val featured: Int
    )

    private companion object {
        val LOBBY_SUPPLEMENTAL_CHILD_INTERFACES = listOf(
            LobbyChildInterface(id = 907, component = 65),
            LobbyChildInterface(id = 910, component = 66),
            LobbyChildInterface(id = 909, component = 67),
            LobbyChildInterface(id = 912, component = 69),
            LobbyChildInterface(id = 589, component = 68),
            LobbyChildInterface(id = 911, component = 70),
            LobbyChildInterface(id = 914, component = 128),
            LobbyChildInterface(id = 915, component = 129),
            LobbyChildInterface(id = 913, component = 130),
            LobbyChildInterface(id = 815, component = 137),
            LobbyChildInterface(id = 803, component = 132),
            LobbyChildInterface(id = 822, component = 133),
            LobbyChildInterface(id = 825, component = 115),
            LobbyChildInterface(id = 821, component = 116),
            LobbyChildInterface(id = 808, component = 114),
            LobbyChildInterface(id = 820, component = 134),
            LobbyChildInterface(id = 811, component = 131),
            LobbyChildInterface(id = 826, component = 82),
            LobbyChildInterface(id = 801, component = 36)
        )

        val LOBBY_NEWS_ITEMS = listOf(
            LobbyNewsItem(
                slot = 0,
                imageId = 16302,
                category = 1,
                title = "This Week In RuneScape: Double XP LIVE & Improved Divination Training",
                body = "This Week In RuneScape we're bringing you the new and improved Divination skill! Why not test it out during Double XP LIVE?",
                slug = "this-week-in-runescape-double-xp-live--improved-divination-training",
                date = "04-May-2021",
                featured = 1
            ),
            LobbyNewsItem(
                slot = 1,
                imageId = 16301,
                category = 12,
                title = "New & Improved Divination",
                body = "A major update is coming to Divination next week. Click here to learn all about it!",
                slug = "new--improved-divination",
                date = "29-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 2,
                imageId = 16293,
                category = 1,
                title = "This Week In RuneScape: Dailies & Distractions & Diversions Week Begins!",
                body = "It's Dailies & Distractions & Diversions Week!",
                slug = "this-week-in-runescape-dailies--distractions--diversions-week-begins",
                date = "26-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 3,
                imageId = 16282,
                category = 12,
                title = "Double XP LIVE Returns Soon!",
                body = "Double XP LIVE is coming again soon!",
                slug = "double-xp-live-returns-soon",
                date = "23-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 4,
                imageId = 16291,
                category = 7,
                title = "RuneScape On Mobile This Summer - A Message From Mod Warden",
                body = "RuneScape is coming to mobile this Summer, and you can register today for free rewards!",
                slug = "runescape-on-mobile-this-summer---a-message-from-mod-warden",
                date = "22-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 5,
                imageId = 16275,
                category = 1,
                title = "This Week In RuneScape: Rex Matriarchs & Combat Week!",
                body = "This week the Rex Matriarchs come roaring into the game with a new combat challenge for experienced fighters. Which is fitting, because it's also Combat Week!",
                slug = "this-week-in-runescape-rex-matriarchs--combat-week",
                date = "19-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 6,
                imageId = 16270,
                category = 1,
                title = "This Week In RuneScape: Skilling Week Begins",
                body = "This Week In RuneScape Awesome April begins, bringing with it Skilling Week!",
                slug = "this-week-in-runescape-skilling-week-begins",
                date = "12-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 7,
                imageId = 16257,
                category = 3,
                title = "Lockout Account Returns - Updates",
                body = "Welcoming back The Returned.",
                slug = "lockout-account-returns---updates",
                date = "08-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 8,
                imageId = 16258,
                category = 1,
                title = "This Week In RuneScape: The RS20 mini-quest series continues!",
                body = "This Week In RuneScape the Ninja Team returns for Strike 21. We've also got the next part of the RS20: Once Upon a Time miniquest series!",
                slug = "this-week-in-runescape-the-rs20-mini-quest-series-continues",
                date = "05-Apr-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 9,
                imageId = 16243,
                category = 1,
                title = "This Week In RuneScape: The Spring Festival Begins!",
                body = "This Week In RuneScape marks the beginning of the Spring Festival!",
                slug = "this-week-in-runescape-the-spring-festival-begins",
                date = "29-Mar-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 10,
                imageId = 16248,
                category = 3,
                title = "Account Returning Begins & Making Things Right",
                body = "An update on the Login Lockout situation, including the first details on the return of accounts and more.",
                slug = "account-returning-begins--making-things-right",
                date = "26-Mar-2021",
                featured = 0
            ),
            LobbyNewsItem(
                slot = 11,
                imageId = 16219,
                category = 3,
                title = "Login Lockout Daily Updates",
                body = "This page is where we'll post the most recent news on the Login Lockout situation. Check back regularly for updates.",
                slug = "login-lockout-daily-updates",
                date = "26-Mar-2021",
                featured = 0
            )
        )
    }

    private val handlers =
        Object2ObjectOpenHashMap<KClass<out GamePacket>, GamePacketHandler<in BasePlayer, out GamePacket>>()
    private val logger = KotlinLogging.logger { }
    private var keepaliveTicks = 0
    private var compatServerpermAckCount = 0
    private val primedPostSocialCompatAckOpcodes = mutableSetOf<Int>()

    override val interfaces: InterfaceManager = InterfaceManager(this)
    override val stats: StatContainer = PlayerStatContainer(this)

    private fun worldHost(): String = OpenNXT.config.gameHostname

    val worldList = WorldList(
        arrayOf(
            WorldListEntry(
                id = 1,
                location = WorldListLocation(225, "Live"),
                flag = WorldFlag.createFlag(),
                activity = "Free To Play",
                host = worldHost(),
                playercount = 69
            ),
            WorldListEntry(
                id = 2,
                location = WorldListLocation(225, "Live"),
                flag = WorldFlag.createFlag(WorldFlag.MEMBERS_ONLY),
                activity = "Members only",
                host = worldHost(),
                playercount = 69
            ),
            WorldListEntry(
                id = 3,
                location = WorldListLocation(161, "Local"),
                flag = WorldFlag.createFlag(WorldFlag.VETERAN_WORLD),
                activity = "Veteran only",
                host = worldHost(),
                playercount = 69
            ),
            WorldListEntry(
                id = 4,
                location = WorldListLocation(161, "Local"),
                flag = WorldFlag.createFlag(WorldFlag.BETA_WORLD),
                activity = "Beta world",
                host = worldHost(),
                playercount = 69
            ),
            WorldListEntry(
                id = 5,
                location = WorldListLocation(161, "Local"),
                flag = WorldFlag.createFlag(WorldFlag.VIP_WORLD),
                activity = "VIP Only",
                host = worldHost(),
                playercount = 69
            ),
        )
    )

    init {
        handlers[NoTimeout::class] = NoTimeoutHandler
        handlers[ClientCheat::class] = ClientCheatHandler
        handlers[WorldlistFetch::class] = WorldlistFetchHandler as GamePacketHandler<in BasePlayer, out GamePacket>
    }

    private fun sendLobbyCompatServerpermAck(triggerOpcode: Int, reason: String) {
        val compatAckOpcode = OpenNXT.config.lobbyBootstrap.compatServerpermAckOpcode
        if (compatAckOpcode < 0) {
            client.traceBootstrap(
                "lobby-skip-serverperm-ack-candidate name=$name triggerOpcode=$triggerOpcode reason=$reason " +
                    "compatAckOpcode=$compatAckOpcode"
            )
            return
        }

        client.write(UnidentifiedPacket(OpcodeWithBuffer(compatAckOpcode, Unpooled.EMPTY_BUFFER)))
        compatServerpermAckCount++
        client.traceBootstrap(
            "lobby-send-serverperm-ack-candidate name=$name opcode=$compatAckOpcode count=$compatServerpermAckCount " +
                "triggerOpcode=$triggerOpcode reason=$reason"
        )
    }

    private fun primePostSocialCompatAck(opcode: Int, payloadSize: Int, previewHex: String, reason: String) {
        if (!primedPostSocialCompatAckOpcodes.add(opcode)) {
            return
        }

        logger.info {
            "Priming post-social lobby compatibility ack for $name from opcode $opcode " +
                "(payloadBytes=$payloadSize, preview=$previewHex, reason=$reason)"
        }
        client.traceBootstrap(
            "lobby-prime-post-social-compat name=$name opcode=$opcode bytes=$payloadSize " +
                "preview=$previewHex reason=$reason"
        )
        sendLobbyCompatServerpermAck(triggerOpcode = opcode, reason = reason)
    }

    private fun shouldPrimePostSocialCompatAck(opcode: Int, payloadSize: Int, bootstrapStage: String): Boolean {
        if (bootstrapStage != "social-state" || payloadSize <= 0) {
            return false
        }

        return when (opcode) {
            0, 80, 110 -> false
            12, 118, 122 -> false
            else -> true
        }
    }

    private fun handleUnidentifiedPacket(packet: UnidentifiedPacket): Boolean {
        val opcode = packet.packet.opcode
        val buf = packet.packet.buf
        val payloadSize = buf.readableBytes()
        val payloadHex =
            if (payloadSize <= 0) ""
            else ByteBufUtil.hexDump(buf, buf.readerIndex(), payloadSize)
        val previewHex =
            if (payloadSize <= 0) "<empty>"
            else ByteBufUtil.hexDump(buf, buf.readerIndex(), minOf(32, payloadSize))
        val bootstrapStage = client.currentBootstrapStage ?: client.lastCompletedBootstrapStage ?: "none"
        val probableFamily =
            when (opcode) {
                12, 118, 122 -> "possible-if-button"
                0 -> "serverperm-varcs"
                80 -> "no-timeout-compat"
                110 -> "worldlist-fetch-compat"
                27, 44, 48, 56, 57, 62, 89, 94, 109, 30625, 30398 -> "post-login-compat"
                else -> "unknown"
            }

        if (opcode == 0) {
            logger.info {
                "Intercepted unidentified lobby opcode 0 for $name " +
                    "(payloadBytes=$payloadSize, preview=$previewHex, compatAckCount=$compatServerpermAckCount)"
            }
            client.traceBootstrap(
                "lobby-recv-serverperm-varcs name=$name opcode=0 bytes=$payloadSize preview=$previewHex " +
                    "ackCount=$compatServerpermAckCount"
            )
            sendLobbyCompatServerpermAck(triggerOpcode = 0, reason = "serverperm-varcs")
            buf.release()
            return true
        }

        if (opcode == 80 && payloadSize == 0) {
            logger.info {
                "Treating unidentified lobby opcode 80 as compatibility NO_TIMEOUT for $name"
            }
            client.traceBootstrap("lobby-client-no-timeout-compat name=$name opcode=80 bytes=0")
            NoTimeoutHandler.handle(this, NoTimeout)
            buf.release()
            return true
        }

        if (opcode == 110 && payloadSize == 4) {
            val checksum = buf.getInt(buf.readerIndex())
            val compatReplyOpcode = OpenNXT.config.lobbyBootstrap.compatWorldlistFetchReplyOpcode
            logger.info {
                "Treating unidentified lobby opcode 110 as compatibility WORLDLIST_FETCH for $name " +
                    "(checksum=$checksum, compatReplyOpcode=$compatReplyOpcode)"
            }
            client.traceBootstrap(
                "lobby-worldlist-fetch-compat name=$name opcode=110 checksum=$checksum compatReplyOpcode=$compatReplyOpcode"
            )
            if (compatReplyOpcode >= 0) {
                worldList.handleCompatRequest(checksum, client, compatReplyOpcode)
                client.traceBootstrap(
                    "lobby-send-worldlist-fetch-reply-compat name=$name opcode=$compatReplyOpcode checksum=$checksum"
                )
            }
            buf.release()
            return true
        }

        if (shouldPrimePostSocialCompatAck(opcode = opcode, payloadSize = payloadSize, bootstrapStage = bootstrapStage)) {
            val reason =
                when {
                    opcode == 27 && payloadSize in setOf(12, 13, 14) -> "post-social-prime"
                    opcode in setOf(62, 109) -> "post-social-followup"
                    probableFamily == "post-login-compat" -> "post-social-compat-family"
                    else -> "post-social-generic"
                }
            primePostSocialCompatAck(
                opcode = opcode,
                payloadSize = payloadSize,
                previewHex = previewHex,
                reason = reason
            )
        }

        logger.info {
            "Unhandled unidentified lobby packet for $name " +
                "(opcode=$opcode, payloadBytes=$payloadSize, family=$probableFamily, preview=$previewHex)"
        }
        client.traceBootstrap(
            "lobby-unidentified-client name=$name opcode=$opcode bytes=$payloadSize " +
                "family=$probableFamily stage=$bootstrapStage preview=$previewHex"
        )
        LobbyPacketForensics.recordClientPacket(
            username = name,
            remoteAddress = client.channel.remoteAddress()?.toString().orEmpty(),
            localAddress = client.channel.localAddress()?.toString().orEmpty(),
            opcode = opcode,
            payloadHex = payloadHex,
            previewHex = previewHex,
            bootstrapStage = bootstrapStage,
        )
        buf.release()
        return true
    }

    fun handleIncomingPackets() {
        val queue = client.incomingQueue
        while (true) {
            val packet = queue.poll() ?: return

            if (packet is UnidentifiedPacket) {
                if (handleUnidentifiedPacket(packet)) {
                    continue
                }
            }

            val handler = handlers[packet::class] as? GamePacketHandler<in BasePlayer, GamePacket>
            if (handler != null) {
                handler.handle(this, packet)
            } else {
                logger.info { "TODO: Handle incoming $packet" }
            }
        }
    }

    fun added() {
        logger.info { "Bootstrapping lobby player $name" }
        client.processUnidentifiedPackets = true
        val bootstrap = OpenNXT.config.lobbyBootstrap
        val stageTracker = LobbyBootstrapStageTracker(client, name)

        logger.info {
                "Lobby bootstrap toggles for $name: " +
                "initialStats=${bootstrap.sendInitialStats}, " +
                "defaultVarps=${bootstrap.sendDefaultVarps}, " +
                "forcedFallbackCandidateVarps=${bootstrap.useForcedFallbackCandidateDefaultVarps}, " +
                "defaultVarpRange=${bootstrap.defaultVarpMinId}..${bootstrap.defaultVarpMaxId}, " +
                "root=${bootstrap.openRootInterface}, " +
                "supplementalChildren=${bootstrap.openSupplementalChildInterfaces}, " +
                "child814=${bootstrap.openPrimaryChild814}, " +
                "child1322=${bootstrap.openAlternateChild1322}, " +
                "varcLarge2771=${bootstrap.sendPrimaryVarcLarge2771}, " +
                "varcSmall3496=${bootstrap.sendPrimaryVarcSmall3496}, " +
                "varcString2508=${bootstrap.sendPrimaryVarcString2508}, " +
                "script10936=${bootstrap.sendPrimaryClientScript10936}, " +
                "secondaryVarcs=${bootstrap.sendSecondaryLobbyVarcs}, " +
                "newsScripts=${bootstrap.sendLobbyNewsScripts}, " +
                "socialInit=${bootstrap.sendSocialInitPackets}"
        }

        if (bootstrap.sendInitialStats) {
            stats.init()
        } else {
            logger.info { "Skipping initial stat burst for $name due to bootstrap config" }
        }

        stageTracker.run(LobbyBootstrapStage.RESET) {
            client.write(ResetClientVarcache)
        }

        stageTracker.run(LobbyBootstrapStage.DEFAULT_VARPS) {
            if (bootstrap.sendDefaultVarps) {
                if (bootstrap.useForcedFallbackCandidateDefaultVarps) {
                    logger.info {
                        "Sending forced fallback candidate lobby varps for $name " +
                            "(count=${TODORefactorThisClass.FORCED_FALLBACK_CANDIDATE_DEFAULT_VARP_IDS.size})"
                    }
                    TODORefactorThisClass.sendForcedFallbackCandidateDefaultVarps(client)
                } else {
                    TODORefactorThisClass.sendDefaultVarps(client)
                }
            } else {
                logger.info { "Skipping default lobby varps for $name while isolating the 946 crash" }
            }
        }

        stageTracker.run(LobbyBootstrapStage.VARCS) {
            if (bootstrap.sendPrimaryVarcLarge2771) {
                client.write(ClientSetvarcLarge(2771, 55004971))
            }
            if (bootstrap.sendPrimaryVarcSmall3496) {
                client.write(ClientSetvarcSmall(3496, 0))
            }
            if (bootstrap.sendPrimaryVarcString2508) {
                client.write(ClientSetvarcstrSmall(2508, ""))
            }
            if (
                !bootstrap.sendPrimaryVarcLarge2771 &&
                !bootstrap.sendPrimaryVarcSmall3496 &&
                !bootstrap.sendPrimaryVarcString2508
            ) {
                logger.info { "Skipping lobby varc bootstrap for $name due to bootstrap config" }
            }
        }

        stageTracker.run(LobbyBootstrapStage.SECONDARY_VARCS) {
            if (bootstrap.sendSecondaryLobbyVarcs) {
                client.write(ClientSetvarcSmall(4659, 0))
                client.write(ClientSetvarcLarge(4660, 500))
                client.write(ClientSetvarcSmall(1800, 0))
                client.write(ClientSetvarcLarge(1648, 500))
                client.write(ClientSetvarcSmall(4968, 0))
                client.write(ClientSetvarcSmall(4969, 0))
                client.write(ClientSetvarcSmall(3905, 0))
                client.write(ClientSetvarcSmall(4266, 1))
                client.write(ClientSetvarcSmall(4267, 110))
                client.write(ClientSetvarcSmall(4263, -1))
                client.write(ClientSetvarcSmall(4264, -1))
                client.write(ClientSetvarcSmall(4265, -1))
            } else {
                logger.info { "Skipping secondary lobby varc bootstrap for $name due to bootstrap config" }
            }
        }

        stageTracker.run(LobbyBootstrapStage.RUNCLIENTSCRIPT) {
            if (bootstrap.sendPrimaryClientScript10936) {
                client.write(RunClientScript(script = 10936, args = emptyArray()))
            } else {
                logger.info { "Skipping lobby bootstrap clientscript stage for $name due to bootstrap config" }
            }
        }

        if (!bootstrap.openRootInterface) {
            logger.info { "Skipping lobby root interface for $name due to bootstrap config" }
            logger.info { "Finished lobby bootstrap for $name after stages ${client.completedBootstrapStages.joinToString()}" }
            return
        }

        stageTracker.run(LobbyBootstrapStage.ROOT_INTERFACE) {
            interfaces.openTop(id = 906)
        }

        stageTracker.run(LobbyBootstrapStage.CHILD_INTERFACES) {
            if (bootstrap.openSupplementalChildInterfaces) {
                for (child in LOBBY_SUPPLEMENTAL_CHILD_INTERFACES) {
                    interfaces.open(id = child.id, parent = 906, component = child.component, walkable = true)
                }
            }
            if (bootstrap.openPrimaryChild814) {
                interfaces.open(id = 814, parent = 906, component = 37, walkable = true)
            }
            if (bootstrap.openAlternateChild1322) {
                interfaces.open(id = 1322, parent = 906, component = 151, walkable = true)
            }
            if (
                !bootstrap.openSupplementalChildInterfaces &&
                !bootstrap.openPrimaryChild814 &&
                !bootstrap.openAlternateChild1322
            ) {
                logger.info { "Skipping all lobby child interfaces for $name due to bootstrap config" }
            }
        }

        stageTracker.run(LobbyBootstrapStage.NEWS_SCRIPTS) {
            if (bootstrap.sendLobbyNewsScripts) {
                sendLobbyNewsFeed()
            } else {
                logger.info { "Skipping lobby news bootstrap for $name due to bootstrap config" }
            }
        }

        stageTracker.run(LobbyBootstrapStage.SOCIAL_STATE) {
            if (bootstrap.sendSocialInitPackets) {
                val canSendPrivateChatFilter =
                    PacketRegistry.getRegistration(Side.SERVER, ChatFilterSettingsPrivatechat::class) != null
                if (canSendPrivateChatFilter) {
                    client.write(ChatFilterSettingsPrivatechat(0))
                } else {
                    logger.info {
                        "Skipping CHAT_FILTER_SETTINGS_PRIVATECHAT for $name: " +
                            "build ${OpenNXT.config.build} has no server opcode mapping"
                    }
                }

                val canSendFriendlistLoaded =
                    PacketRegistry.getRegistration(Side.SERVER, FriendlistLoaded::class) != null
                if (canSendFriendlistLoaded) {
                    client.write(FriendlistLoaded)
                } else {
                    logger.info {
                        "Skipping FRIENDLIST_LOADED for $name: " +
                            "build ${OpenNXT.config.build} has no server opcode mapping"
                    }
                }
            } else {
                logger.info { "Skipping lobby social bootstrap for $name due to bootstrap config" }
            }
        }

        logger.info { "Finished lobby bootstrap for $name after stages ${client.completedBootstrapStages.joinToString()}" }

//        client.write(ClientSetvarcSmall(id = 4659, value = 0))
//        client.write(ClientSetvarcLarge(id = 4660, value = 500))
//        client.write(ClientSetvarcSmall(id = 1800, value = 0))
//        client.write(ClientSetvarcLarge(id = 1648, value = 500))
//        client.write(ClientSetvarcSmall(id = 4968, value = 0))
//        client.write(ClientSetvarcSmall(id = 4969, value = 0))
//
//        client.write(ClientSetvarcSmall(id = 3905, value = 0))
//        client.write(ClientSetvarcSmall(id = 4266, value = 1))
//        client.write(ClientSetvarcSmall(id = 4267, value = 110))
//        client.write(ClientSetvarcLarge(id = 4660, value = 500))
//        client.write(ClientSetvarcSmall(id = 4659, value = 0))
//
//        // TODO http image
//        client.write(ClientSetvarcSmall(id = 4263, value = -1))
//        // TODO http image
//        client.write(ClientSetvarcSmall(id = 4264, value = -1))
//        // TODO http image
//        client.write(ClientSetvarcSmall(id = 4265, value = -1))
//
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    0,
//                    16302,
//                    1,
//                    -1,
//                    "This Week In RuneScape: Double XP LIVE & Improved Divination Training",
//                    "This Week In RuneScape we're bringing you the new and improved Divination skill! Why not test it out during Double XP LIVE?",
//                    "this-week-in-runescape-double-xp-live--improved-divination-training",
//                    "04-May-2021",
//                    1
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    1,
//                    16301,
//                    12,
//                    -1,
//                    "New & Improved Divination",
//                    "A major update is coming to Divination next week. Click here to learn all about it!",
//                    "new--improved-divination",
//                    "29-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    2,
//                    16293,
//                    1,
//                    -1,
//                    "This Week In RuneScape: Dailies & Distractions & Diversions Week Begins!",
//                    "It�s Dailies & Distractions & Diversions Week!",
//                    "this-week-in-runescape-dailies--distractions--diversions-week-begins",
//                    "26-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    3,
//                    16282,
//                    12,
//                    -1,
//                    "Double XP LIVE Returns Soon!",
//                    "Double XP LIVE is coming again soon!",
//                    "double-xp-live-returns-soon",
//                    "23-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    4,
//                    16291,
//                    7,
//                    -1,
//                    "RuneScape On Mobile This Summer - A Message From Mod Warden",
//                    "RuneScape is coming to mobile this Summer, and you can register today for free rewards!",
//                    "runescape-on-mobile-this-summer---a-message-from-mod-warden",
//                    "22-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    5,
//                    16275,
//                    1,
//                    -1,
//                    "This Week In RuneScape: Rex Matriarchs & Combat Week!",
//                    "This week the Rex Matriarchs come roaring into the game with a new combat challenge for experienced fighters. Which is fitting, because it�s also Combat Week!",
//                    "this-week-in-runescape-rex-matriarchs--combat-week",
//                    "19-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    6,
//                    16270,
//                    1,
//                    -1,
//                    "This Week In RuneScape: Skilling Week Begins",
//                    "This Week In RuneScape Awesome April begins, bringing with it Skilling Week!",
//                    "this-week-in-runescape-skilling-week-begins",
//                    "12-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    7,
//                    16257,
//                    3,
//                    -1,
//                    "Lockout Account Returns - Updates",
//                    "Welcoming back The Returned.",
//                    "lockout-account-returns---updates",
//                    "08-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    8,
//                    16258,
//                    1,
//                    -1,
//                    "This Week In RuneScape: The RS20 mini-quest series continues!",
//                    "This Week In RuneScape the Ninja Team returns for Strike 21. We've also got the next part of the RS20: Once Upon a Time miniquest series!",
//                    "this-week-in-runescape-the-rs20-mini-quest-series-continues",
//                    "05-Apr-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    9,
//                    16243,
//                    1,
//                    -1,
//                    "This Week In RuneScape: The Spring Festival Begins!",
//                    "This Week In RuneScape marks the beginning of the Spring Festival!",
//                    "this-week-in-runescape-the-spring-festival-begins",
//                    "29-Mar-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    10,
//                    16248,
//                    3,
//                    -1,
//                    "Account Returning Begins & Making Things Right",
//                    "An update on the Login Lockout situation, including the first details on the return of accounts and more.",
//                    "account-returning-begins--making-things-right",
//                    "26-Mar-2021",
//                    0
//                )
//            )
//        )
//        client.write(
//            RunClientScript(
//                script = 10931,
//                args = arrayOf(
//                    11,
//                    16219,
//                    3,
//                    -1,
//                    "Login Lockout Daily Updates",
//                    "This page is where we'll post the most recent news on the Login Lockout situation. Check back regularly for updates.",
//                    "login-lockout-daily-updates",
//                    "26-Mar-2021",
//                    0
//                )
//            )
//        )
//        client.write(RunClientScript(script = 10936, args = emptyArray()))
//
//        client.write(ChatFilterSettingsPrivatechat(0))
//        client.write(FriendlistLoaded)
        logger.info { "Finished lobby bootstrap for $name" }
    }

    private fun sendLobbyNewsFeed() {
        for (item in LOBBY_NEWS_ITEMS) {
            client.write(
                RunClientScript(
                    script = 10931,
                    args = arrayOf(
                        item.slot,
                        item.imageId,
                        item.category,
                        -1,
                        item.title,
                        item.body,
                        item.slug,
                        item.date,
                        item.featured
                    )
                )
            )
        }
    }

    override fun tick() {
        keepaliveTicks++
        if (keepaliveTicks % 5 == 0) {
            val canSendNoTimeout = PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null
            if (canSendNoTimeout) {
                client.write(NoTimeout)
            }
        }
        if (
            OpenNXT.config.lobbyBootstrap.sendServerTickEnd &&
            PacketRegistry.getRegistration(Side.SERVER, ServerTickEnd::class) != null
        ) {
            client.write(ServerTickEnd)
        }
    }
}
