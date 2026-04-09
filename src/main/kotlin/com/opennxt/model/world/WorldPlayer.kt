package com.opennxt.model.world

import com.opennxt.OpenNXT
import com.opennxt.api.stat.StatContainer
import com.opennxt.impl.stat.PlayerStatContainer
import com.opennxt.model.InterfaceHash
import com.opennxt.model.entity.BasePlayer
import com.opennxt.model.entity.PlayerEntity
import com.opennxt.model.entity.movement.CompassPoint
import com.opennxt.model.entity.player.InterfaceManager
import com.opennxt.model.entity.player.Viewport
import com.opennxt.model.entity.updating.NpcInfoEncoder
import com.opennxt.model.entity.updating.PlayerInfoEncoder
import com.opennxt.model.lobby.TODORefactorThisClass
import com.opennxt.model.worldlist.WorldFlag
import com.opennxt.model.worldlist.WorldList
import com.opennxt.model.worldlist.WorldListEntry
import com.opennxt.model.worldlist.WorldListLocation
import com.opennxt.net.ConnectedClient
import com.opennxt.net.GenericResponse
import com.opennxt.net.Side
import com.opennxt.net.buf.GamePacketBuilder
import com.opennxt.net.game.GamePacket
import com.opennxt.net.game.PacketRegistry
import com.opennxt.net.game.golden.GoldenPacketSupport
import com.opennxt.net.game.clientprot.ClientBootstrapBlob28
import com.opennxt.net.game.clientprot.ClientBootstrapControl50
import com.opennxt.net.game.clientprot.ClientBootstrapControl82
import com.opennxt.net.game.clientprot.ClientCheat
import com.opennxt.net.game.clientprot.ClientDisplayState106
import com.opennxt.net.game.clientprot.MapBuildComplete
import com.opennxt.net.game.handlers.ClientBootstrapBlob28Handler
import com.opennxt.net.game.handlers.ClientBootstrapControl50Handler
import com.opennxt.net.game.handlers.ClientBootstrapControl82Handler
import com.opennxt.net.game.handlers.ClientCheatHandler
import com.opennxt.net.game.handlers.ClientDisplayState106Handler
import com.opennxt.net.game.handlers.MapBuildCompleteHandler
import com.opennxt.net.game.handlers.NoTimeoutHandler
import com.opennxt.net.game.pipeline.*
import com.opennxt.net.game.pipeline.GamePacketCodec
import com.opennxt.net.game.serverprot.NoTimeout
import com.opennxt.net.game.serverprot.RebuildNormal
import com.opennxt.net.game.serverprot.RunClientScript
import com.opennxt.net.game.serverprot.ServerTickEnd
import com.opennxt.net.game.serverprot.ifaces.IfCloseSub
import com.opennxt.net.game.serverprot.ifaces.IfOpensubActivePlayer
import com.opennxt.net.game.serverprot.ifaces.IfSethide
import com.opennxt.net.game.serverprot.variables.ResetClientVarcache
import com.opennxt.net.game.serverprot.variables.ClientSetvarcSmall
import com.opennxt.net.login.LoginPacket
import com.opennxt.net.proxy.UnidentifiedPacket
import com.sun.org.apache.xpath.internal.operations.Bool
import io.netty.buffer.ByteBufUtil
import io.netty.buffer.Unpooled
import it.unimi.dsi.fastutil.objects.Object2ObjectOpenHashMap
import mu.KotlinLogging
import kotlin.reflect.KClass

class WorldPlayer(
    client: ConnectedClient,
    name: String,
    val entity: PlayerEntity,
    private val entryMode: EntryMode = EntryMode.FULL_LOGIN
) : BasePlayer(client, name) {
    private val handlers =
        Object2ObjectOpenHashMap<KClass<out GamePacket>, GamePacketHandler<in BasePlayer, out GamePacket>>()
    private val logger = KotlinLogging.logger { }

    val viewport = Viewport(this)
    override val interfaces: InterfaceManager = InterfaceManager(this)
    override val stats: StatContainer = PlayerStatContainer(this)
    private fun worldHost(): String = OpenNXT.config.gameHostname
    private val worldList = WorldList(
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
    var awaitingMapBuildComplete = false
    var awaitingWorldReadySignal = false
    private var deferredBootstrap: (() -> Unit)? = null
    private var mapBuildWaitTicks = 0
    private var worldReadyWaitTicks = 0
    private var playerInfoDelayTicks = 0
    private var initialWorldSyncSent = false
    private var worldSyncFramesSent = 0
    private var postInitialWorldSyncHoldTicks = 0
    private var postInitialWorldSyncHoldForcedFallback = false
    private var postInitialWorldSyncHoldSendFrames = false
    private var compatServerpermAckCount = 0
    private var deferredDefaultVarpsPending = false
    private var deferredLateWorldCompletionTailPending = false
    private var deferredForcedFallbackSupplementalChildrenPending = false
    private var deferredForcedFallbackLightInterfaceTailPending = false
    private var deferredForcedFallbackCompletionCompanionsPending = false
    private var deferredForcedFallbackCompletionStructurePending = false
    private var deferredForcedFallbackRestoredWorldPanelsPending = false
    private var deferredForcedFallbackUtilityPanelDeckPending = false
    private var deferredForcedFallbackSceneBridgePending = false
    private var forcedFallbackPreDeferredFamiliesPrimed = false
    private var deferredForcedFallbackCompletionStructureSent = false
    private var deferredForcedFallbackDeferredScriptsSent = false
    private var deferredForcedFallbackCoreScriptsPending = false
    private var deferredForcedFallbackLiteTailPending = false
    private var skipPostInitialSyncHoldForForcedFallback = false
    private var pendingForcedFallbackLoadingOverlayClose = false
    private var pendingWorldReadySignal: PendingWorldReadySignal? = null
    private var pendingServerpermDelayedReadySignal: PendingWorldReadySignal? = null
    private var compatMapBuildReadyFallbackOpcode: Int? = null
    private var forcedMapBuildFallbackPending = false
    private var forcedMapBuildFallbackActive = false
    private var forcedMinimalInterfaceBootstrap = false
    private var pendingServerpermMapBuildCompat: PendingServerpermMapBuildCompat? = null
    private var forcedFallbackRestoredWorldPanelsSent = false
    private var forcedFallbackUtilityPanelDeckSent = false
    private var forcedFallbackSceneBridgeSent = false
    private var sceneStartSyncBurstTicks = 0
    private var forcedLocalAppearanceRefreshFrames = 0
    private var deferredSceneStartEventDeltaPending = false
    private var deferredSceneStartTabbedEventDeltaPending = false
    private var deferredSceneStartLightTailScriptsPending = false
    private var deferredSceneStartFinalEventDeltaPending = false
    private var deferredLateRootInterfaceEventsPending = false
    private var deferredAnnouncementScriptsPending = false
    private var deferredForcedFallback10623BatchPending = false
    private var forcedFallbackLateReadyInterfaceReplaySent = false
    private var forcedFallbackLateReadyInterfaceReplayArmed = false
    private var deferredForcedFallbackSelfModelBindPending = false
    private var awaitingLateSceneStartReadySignal = false
    private var lateSceneStartReadySignalsAccepted = 0
    var lastClientBootstrapBlob28: ClientBootstrapBlob28? = null
        private set
    var lastClientBootstrapControl50: Int? = null
        private set
    var lastClientBootstrapControl82: Int? = null
        private set
    var lastClientDisplayState106: ClientDisplayState106? = null
        private set
    private var clientBootstrapBlob28Count = 0
    private var clientBootstrapControl50Count = 0
    private var clientBootstrapControl82Count = 0
    private var clientDisplayState106Count = 0

    companion object {
        private const val MAP_BUILD_FALLBACK_TICKS = 20
        private const val WORLD_READY_FALLBACK_TICKS = 8
        private const val PRE_READY_SYNC_PRIME_TICKS = 2
        private const val POST_INITIAL_WORLD_SYNC_HOLD_TICKS = 3
        private const val FORCED_FALLBACK_POST_INITIAL_WORLD_SYNC_HOLD_TICKS = 4
        private const val FORCED_LOCAL_APPEARANCE_FRAMES = 4
        private const val SCENE_START_SYNC_BURST_TICKS = 3
        private const val SCENE_START_LOCAL_APPEARANCE_REFRESH_FRAMES = 3
        private const val LATE_SCENE_START_CONTROL_50_MIN_VALUE = 28
        private const val LATE_SCENE_START_CONTROL_50_PHASE2_MIN_VALUE = 41
        private const val LATE_SCENE_START_CONTROL_50_PHASE3_MIN_VALUE = 125
        private const val FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_MIN_VALUE = 3
        private const val FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_PHASE2_MIN_VALUE = 4
        private const val FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_PHASE3_MIN_VALUE = 4
        private const val MAX_LATE_SCENE_START_READY_ACCEPTS = 4
        // Build 947 has shown at least one contained post-lobby path where the first
        // map-build completion signal arrives as a 3-byte opcode 30 packet instead of
        // the older control opcodes we already tolerate.
        private val MAP_BUILD_COMPAT_OPCODES = setOf(30, 50, 95, 113)
        private val WORLD_READY_COMPAT_OPCODES = setOf(17, 48, 50)
        private val INTERFACE_BOOTSTRAP_ANNOUNCEMENT_SCRIPTS = setOf(1264, 3529)
        private val INTERFACE_BOOTSTRAP_PANEL_SCRIPTS = setOf(11145, 8420)
        private val INTERFACE_BOOTSTRAP_COMPLETION_SCRIPTS = setOf(139, 14150)
        private val INTERFACE_BOOTSTRAP_WIDGET_STATE_SCRIPTS = setOf(8310)
    }

    enum class EntryMode {
        FULL_LOGIN,
        POST_LOBBY_AUTH,
    }

    private data class PendingWorldReadySignal(
        val opcode: Int,
        val payloadLength: Int,
        val preview: String,
        val source: String
    )

    private data class PendingServerpermMapBuildCompat(
        val payloadLength: Int,
        val preview: String,
        val source: String
    )

    private fun worldReadyPriority(opcode: Int): Int =
        when (opcode) {
            48 -> 3
            50 -> 2
            17 -> 1
            else -> 0
        }

    private fun armCompatMapBuildReadyFallback(opcode: Int) {
        compatMapBuildReadyFallbackOpcode = opcode
    }

    private fun clearCompatMapBuildReadyFallback() {
        compatMapBuildReadyFallbackOpcode = null
    }

    private fun latchWorldReadySignal(opcode: Int, payloadLength: Int, preview: String, source: String) {
        val existing = pendingWorldReadySignal
        val shouldReplace =
            existing == null || worldReadyPriority(opcode) > worldReadyPriority(existing.opcode)
        if (shouldReplace) {
            pendingWorldReadySignal = PendingWorldReadySignal(
                opcode = opcode,
                payloadLength = payloadLength,
                preview = preview,
                source = source
            )
            client.traceBootstrap(
                "world-ready-signal-latched name=$name opcode=$opcode bytes=$payloadLength " +
                    "preview=$preview source=$source replaced=${existing?.opcode ?: -1}"
            )
        } else {
            client.traceBootstrap(
                "world-ready-signal-latch-ignored name=$name opcode=$opcode bytes=$payloadLength " +
                    "preview=$preview source=$source retained=${existing.opcode}"
            )
        }
    }

    private fun consumePendingWorldReadySignalIfNeeded(source: String): Boolean {
        val pending = pendingWorldReadySignal ?: return false
        pendingWorldReadySignal = null
        client.traceBootstrap(
            "world-ready-signal-consume-latched name=$name opcode=${pending.opcode} " +
                "bytes=${pending.payloadLength} preview=${pending.preview} source=$source"
        )
        acceptWorldReadySignal(
            opcode = pending.opcode,
            payloadLength = pending.payloadLength,
            preview = pending.preview,
            source = source
        )
        return true
    }

    private fun logBootstrapStage(stage: String) {
        logger.info { "World bootstrap stage for $name: $stage" }
        client.traceBootstrap("world-stage name=$name stage=$stage")
    }

    private inline fun runBootstrapStage(stage: String, block: () -> Unit) {
        logBootstrapStage(stage)
        client.currentBootstrapStage = stage
        try {
            block()
            client.lastCompletedBootstrapStage = stage
            client.completedBootstrapStages += stage
        } finally {
            if (client.currentBootstrapStage == stage) {
                client.currentBootstrapStage = null
            }
        }
    }

    private fun acceptWorldReadySignal(opcode: Int, payloadLength: Int, preview: String, source: String) {
        val readyWaitPrimedByInitialSync = initialWorldSyncSent && awaitingWorldReadySignal
        if (initialWorldSyncSent && !readyWaitPrimedByInitialSync) {
            logger.info {
                "Treating unidentified opcode $opcode as late post-bootstrap world-ready signal for $name " +
                    "(payloadBytes=$payloadLength, preview=$preview, source=$source)"
            }
            client.traceBootstrap(
                "world-ready-signal-skipped name=$name opcode=$opcode bytes=$payloadLength preview=$preview source=$source"
            )
            return
        }

        logger.info {
            "Treating unidentified opcode $opcode as post-bootstrap world-ready signal for $name " +
                "(payloadBytes=$payloadLength, preview=$preview, source=$source)"
        }
        client.traceBootstrap(
            "world-ready-signal name=$name opcode=$opcode bytes=$payloadLength preview=$preview source=$source"
        )
        pendingWorldReadySignal = null
        pendingServerpermDelayedReadySignal = null
        awaitingWorldReadySignal = false
        clearCompatMapBuildReadyFallback()
        worldReadyWaitTicks = 0
        playerInfoDelayTicks = 0
        client.traceBootstrap(
            "world-ready-signal-deferred name=$name opcode=$opcode bytes=$payloadLength preview=$preview source=$source"
        )
        if (readyWaitPrimedByInitialSync) {
            client.traceBootstrap(
                "world-ready-signal-primer-accepted name=$name opcode=$opcode bytes=$payloadLength " +
                    "preview=$preview source=$source"
            )
            return
        }
        val preservePostSyncHoldDuringAcceleratedFollowup = deferredLateWorldCompletionTailPending
        val forceImmediateFollowup = deferredLateWorldCompletionTailPending
        if (forceImmediateFollowup) {
            client.traceBootstrap(
                "world-ready-signal-accelerate-followup name=$name opcode=$opcode source=$source " +
                    "reason=deferred-tail-pending preserveHold=$preservePostSyncHoldDuringAcceleratedFollowup"
            )
        }
        sendInitialWorldSyncIfNeeded(
            forceImmediateFollowup = forceImmediateFollowup,
            skipPostSyncHold = forceImmediateFollowup && !preservePostSyncHoldDuringAcceleratedFollowup
        )
    }

    private fun armSceneStartSyncBurst(reason: String, controlValue: Int) {
        val previousBurstTicks = sceneStartSyncBurstTicks
        val previousRefreshFrames = forcedLocalAppearanceRefreshFrames
        sceneStartSyncBurstTicks = maxOf(sceneStartSyncBurstTicks, SCENE_START_SYNC_BURST_TICKS)
        forcedLocalAppearanceRefreshFrames =
            maxOf(forcedLocalAppearanceRefreshFrames, SCENE_START_LOCAL_APPEARANCE_REFRESH_FRAMES)
        client.traceBootstrap(
            "world-arm-scene-start-sync-burst name=$name reason=$reason control50=$controlValue " +
                "burstTicks=$sceneStartSyncBurstTicks refreshFrames=$forcedLocalAppearanceRefreshFrames " +
                "previousBurstTicks=$previousBurstTicks previousRefreshFrames=$previousRefreshFrames"
        )
    }

    private fun sceneStartControl50ForTrace(): Int =
        lastClientBootstrapControl50 ?: LATE_SCENE_START_CONTROL_50_MIN_VALUE

    private fun effectiveSceneStartControl50(): Int =
        when {
            lastClientBootstrapControl50 != null -> lastClientBootstrapControl50!!
            forcedMapBuildFallbackActive &&
                (sceneStartSyncBurstTicks > 0 || deferredSceneStartEventDeltaPending) ->
                FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_MIN_VALUE
            else -> Int.MIN_VALUE
        }

    private fun implicitForcedFallbackSceneStartPhaseOneReached(control50: Int): Boolean =
        forcedMapBuildFallbackActive &&
            lastClientBootstrapControl50 == null &&
            lateSceneStartReadySignalsAccepted == 0 &&
            !sceneStartPhaseOneReached(control50)

    private fun sceneStartPhaseOneReleaseControl50(control50: Int): Int =
        if (implicitForcedFallbackSceneStartPhaseOneReached(control50)) {
            FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_MIN_VALUE
        } else {
            control50
        }

    private fun shouldDeferForcedFallbackPhaseOneEventDeltaUntilLateReady(control50: Int): Boolean =
        forcedMapBuildFallbackActive &&
            lateSceneStartReadySignalsAccepted == 0 &&
            sceneStartPhaseOneReleaseControl50(control50) <= FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_MIN_VALUE

    private fun deferForcedFallbackPhaseOneEventDeltaUntilLateReady(
        control50: Int,
        source: String
    ): Boolean {
        if (!shouldDeferForcedFallbackPhaseOneEventDeltaUntilLateReady(control50)) {
            return false
        }
        val phaseOneReleaseControl50 = sceneStartPhaseOneReleaseControl50(control50)
        if (!awaitingLateSceneStartReadySignal) {
            lateSceneStartReadySignalsAccepted = 0
            awaitingLateSceneStartReadySignal = true
            client.traceBootstrap(
                "world-defer-deferred-completion-event-delta-phase1-until-late-ready name=$name " +
                    "groups=1477,1430-root count=11 control50=$phaseOneReleaseControl50 source=$source"
            )
            client.traceBootstrap(
                "world-await-late-scene-ready-signal name=$name control50=$phaseOneReleaseControl50 phase=1"
            )
            forcedLocalAppearanceRefreshFrames = maxOf(forcedLocalAppearanceRefreshFrames, 1)
            if (PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null) {
                client.write(NoTimeout)
                client.traceBootstrap(
                    "world-prime-late-scene-ready-phase1-keepalive name=$name " +
                        "packet=NO_TIMEOUT control50=$phaseOneReleaseControl50 source=$source"
                )
            }
            client.traceBootstrap(
                "world-prime-late-scene-ready-phase1-followup-sync name=$name " +
                    "control50=$phaseOneReleaseControl50 source=$source"
            )
            sendWorldSyncFrame("late-scene-ready-phase1-prime")
        }
        return true
    }

    private fun sceneStartPhaseOneReached(control50: Int): Boolean =
        control50 >= LATE_SCENE_START_CONTROL_50_MIN_VALUE ||
            (forcedMapBuildFallbackActive && control50 >= FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_MIN_VALUE)

    private fun sceneStartPhaseTwoReached(control50: Int): Boolean =
        control50 >= LATE_SCENE_START_CONTROL_50_PHASE2_MIN_VALUE ||
            (forcedMapBuildFallbackActive && control50 >= FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_PHASE2_MIN_VALUE)

    private fun sceneStartPhaseThreeReached(control50: Int): Boolean =
        control50 >= LATE_SCENE_START_CONTROL_50_PHASE3_MIN_VALUE ||
            (forcedMapBuildFallbackActive && control50 >= FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_PHASE3_MIN_VALUE)

    private fun forcedFallbackTickSyncBlockReason(): String? {
        if (!forcedMapBuildFallbackActive || lateSceneStartReadySignalsAccepted > 0) {
            return null
        }
        return null
    }

    private fun isLateSceneStartReadyCompatOpcode(opcode: Int): Boolean =
        // On the contained 947 path the client no longer emits only the older 17/48-style
        // post-scene-start nudges. Once we enter the forced fallback late-world tail we now
        // consistently see a smaller readiness family (27, 66, 72, 84, 106, 114) instead.
        // Keep this scoped to the active late-scene-ready wait so we do not globally reinterpret
        // normal gameplay traffic as bootstrap progress.
        opcode in setOf(17, 27, 48, 66, 72, 83, 84, 106, 114)

    private fun acceptLateSceneStartReadySignal(opcode: Int, payloadLength: Int, preview: String, source: String) {
        lateSceneStartReadySignalsAccepted++
        awaitingLateSceneStartReadySignal =
            lateSceneStartReadySignalsAccepted < MAX_LATE_SCENE_START_READY_ACCEPTS
        val finalLateReadyAcceptance = !awaitingLateSceneStartReadySignal
        logger.info {
            "Treating unidentified opcode $opcode as late post-scene-start ready signal for $name " +
                "(payloadBytes=$payloadLength, preview=$preview, source=$source)"
        }
        client.traceBootstrap(
            "world-accept-late-scene-ready-signal name=$name opcode=$opcode bytes=$payloadLength " +
                "preview=$preview source=$source control50=${lastClientBootstrapControl50} " +
                "acceptedCount=$lateSceneStartReadySignalsAccepted keepAwaiting=$awaitingLateSceneStartReadySignal"
        )
        closeForcedFallbackLoadingOverlayIfPending(reason = "forced-map-build-fallback-after-late-ready")
        if (deferredSceneStartEventDeltaPending) {
            val phaseOneReleaseControl50 =
                lastClientBootstrapControl50 ?: FORCED_FALLBACK_LATE_SCENE_START_CONTROL_50_MIN_VALUE
            deferredSceneStartEventDeltaPending = false
            deferredSceneStartTabbedEventDeltaPending = true
            sendDeferredSceneStartEventDelta()
            client.traceBootstrap(
                "world-send-deferred-completion-event-delta-phase1-after-late-ready name=$name " +
                    "groups=1477,1430-root count=11 control50=$phaseOneReleaseControl50 " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
        }
        if (deferredSceneStartFinalEventDeltaPending) {
            deferredSceneStartFinalEventDeltaPending = false
            sendDeferredSceneStartFinalEventDelta()
            client.traceBootstrap(
                "world-send-deferred-completion-event-delta-phase3-after-late-ready name=$name " +
                    "groups=1430-extended,1465,slot-panels count=38 control50=${lastClientBootstrapControl50}"
            )
        }
        if (finalLateReadyAcceptance && deferredLateRootInterfaceEventsPending) {
            deferredLateRootInterfaceEventsPending = false
            client.traceBootstrap(
                "world-send-late-root-interface-events-after-late-ready name=$name parent=1477 count=390 " +
                    "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            sendLateRootInterfaceEventsIfConfigured()
        }
        if (finalLateReadyAcceptance && deferredForcedFallbackSceneBridgePending) {
            deferredForcedFallbackSceneBridgePending = false
            client.traceBootstrap(
                "world-send-forced-fallback-scene-bridge-after-late-ready name=$name ids=1431,568,1465,1919 " +
                    "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            openForcedFallbackSceneStartBridge(includeEvents = true)
        }
        if (finalLateReadyAcceptance && deferredForcedFallbackRestoredWorldPanelsPending) {
            deferredForcedFallbackRestoredWorldPanelsPending = false
            client.traceBootstrap(
                "world-send-forced-fallback-restored-world-panels-after-late-ready name=$name " +
                    "ids=1464,1458,1461,1884,1885,1887,1886,1460,1881,1888,1883,1449,1882,1452 " +
                    "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            openForcedFallbackRestoredWorldPanels()
        }
        if (finalLateReadyAcceptance && deferredForcedFallbackUtilityPanelDeckPending) {
            deferredForcedFallbackUtilityPanelDeckPending = false
            client.traceBootstrap(
                "world-send-forced-fallback-utility-panel-deck-after-late-ready name=$name " +
                    "ids=550,1427,1110,590,1416,1519,1588,1678,190,1854,1894 " +
                    "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            openForcedFallbackUtilityPanelDeck(includeEvents = true)
        }
        sendForcedFallbackLateReadyInterfaceReplayIfNeeded()
        if (finalLateReadyAcceptance && deferredAnnouncementScriptsPending) {
            deferredAnnouncementScriptsPending = false
            client.traceBootstrap(
                "world-send-deferred-completion-announcement-scripts-after-late-ready name=$name count=2 " +
                    "scripts=1264,3529 control50=${lastClientBootstrapControl50} " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            sendDeferredCompletionAnnouncementScripts()
        }
        if (finalLateReadyAcceptance && deferredForcedFallbackCoreScriptsPending) {
            deferredForcedFallbackCoreScriptsPending = false
            client.traceBootstrap(
                "world-send-forced-fallback-deferred-completion-scripts-after-late-ready name=$name " +
                    "scripts=8862,2651,7486,10903,8778 control50=${lastClientBootstrapControl50} " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            sendDeferredCompletionLiteScripts(includeTail = false)
        }
        if (finalLateReadyAcceptance && deferredForcedFallback10623BatchPending) {
            deferredForcedFallback10623BatchPending = false
            client.traceBootstrap(
                "world-send-forced-fallback-deferred-completion-10623-batch-after-late-ready name=$name " +
                    "scripts=10623:30522,30758,30759,30821,30828,30964,31386,31562,31918 " +
                    "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            sendDeferredCompletion10623Batch()
        }
        if (finalLateReadyAcceptance && deferredForcedFallbackLiteTailPending) {
            deferredForcedFallbackLiteTailPending = false
            client.traceBootstrap(
                "world-send-forced-fallback-deferred-completion-lite-tail-after-late-ready name=$name " +
                    "scripts=4704,4308 texts=187:7,1416:6 control50=${lastClientBootstrapControl50} " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
            sendDeferredCompletionLiteTail()
        }
        armSceneStartSyncBurst(
            reason = "late-scene-ready-signal",
            controlValue = lastClientBootstrapControl50 ?: LATE_SCENE_START_CONTROL_50_PHASE3_MIN_VALUE
        )
        if (awaitingLateSceneStartReadySignal) {
            client.traceBootstrap(
                "world-continue-await-late-scene-ready-signal name=$name " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted maxAccepts=$MAX_LATE_SCENE_START_READY_ACCEPTS"
            )
        }
        client.traceBootstrap(
            "world-send-late-scene-ready-followup name=$name opcode=$opcode source=$source"
        )
        sendWorldSyncFrame("late-scene-ready-followup")
    }

    init {
        entity.controllingPlayer = this
        handlers[NoTimeout::class] = NoTimeoutHandler
        handlers[ClientCheat::class] = ClientCheatHandler
        handlers[ClientBootstrapBlob28::class] =
            ClientBootstrapBlob28Handler as GamePacketHandler<in BasePlayer, out GamePacket>
        handlers[ClientBootstrapControl50::class] =
            ClientBootstrapControl50Handler as GamePacketHandler<in BasePlayer, out GamePacket>
        handlers[ClientBootstrapControl82::class] =
            ClientBootstrapControl82Handler as GamePacketHandler<in BasePlayer, out GamePacket>
        handlers[ClientDisplayState106::class] =
            ClientDisplayState106Handler as GamePacketHandler<in BasePlayer, out GamePacket>
        handlers[MapBuildComplete::class] = MapBuildCompleteHandler as GamePacketHandler<in BasePlayer, out GamePacket>
    }

    fun handleClientBootstrapBlob28(packet: ClientBootstrapBlob28) {
        lastClientBootstrapBlob28 = packet
        clientBootstrapBlob28Count++
        val preview = packet.payload.take(24).joinToString("") { byte ->
            (byte.toInt() and 0xFF).toString(16).padStart(2, '0')
        }
        logger.info {
            "Handled decoded client bootstrap blob opcode 28 for $name " +
                "(bytes=${packet.payload.size}, entryCount=${packet.entryCount}, count=$clientBootstrapBlob28Count)"
        }
        client.traceBootstrap(
            "world-client-bootstrap-blob name=$name opcode=28 bytes=${packet.payload.size} " +
                "entryCount=${packet.entryCount} count=$clientBootstrapBlob28Count preview=$preview " +
                "awaitingMapBuildComplete=$awaitingMapBuildComplete awaitingWorldReadySignal=$awaitingWorldReadySignal"
        )
    }

    fun handleClientBootstrapControl50(packet: ClientBootstrapControl50) {
        val value = packet.value
        val preview = value.toUInt().toString(16).padStart(Int.SIZE_BYTES * 2, '0')
        lastClientBootstrapControl50 = value
        clientBootstrapControl50Count++

        if (awaitingMapBuildComplete) {
            logger.info {
                "Treating decoded client opcode 50 as compatibility MAP_BUILD_COMPLETE for $name " +
                    "(value=$value, payloadBytes=${Int.SIZE_BYTES}, preview=$preview)"
            }
            client.traceBootstrap(
                "world-map-build-complete-compat name=$name opcode=50 bytes=${Int.SIZE_BYTES} " +
                    "value=$value preview=$preview source=decoded"
            )
            armCompatMapBuildReadyFallback(50)
            awaitingMapBuildComplete = false
            completeDeferredBootstrap()
            return
        }

        if (awaitingWorldReadySignal) {
            acceptWorldReadySignal(
                opcode = 50,
                payloadLength = Int.SIZE_BYTES,
                preview = preview,
                source = "decoded"
            )
            return
        }

        if (!initialWorldSyncSent) {
            logger.info {
                "Latching decoded client opcode 50 for $name until the live post-bootstrap world-ready wait is active " +
                    "(value=$value, payloadBytes=${Int.SIZE_BYTES}, preview=$preview, " +
                    "awaitingMapBuildComplete=$awaitingMapBuildComplete, awaitingWorldReadySignal=$awaitingWorldReadySignal)"
            }
            latchWorldReadySignal(
                opcode = 50,
                payloadLength = Int.SIZE_BYTES,
                preview = preview,
                source = "decoded-early"
            )
            return
        }

        logger.info {
            "Handled decoded client bootstrap control opcode 50 for $name " +
                "(value=$value, count=$clientBootstrapControl50Count)"
        }
        client.traceBootstrap(
            "world-client-bootstrap-control name=$name opcode=50 value=$value count=$clientBootstrapControl50Count " +
                "awaitingMapBuildComplete=$awaitingMapBuildComplete awaitingWorldReadySignal=$awaitingWorldReadySignal"
        )
        if (
            !awaitingMapBuildComplete &&
            !awaitingWorldReadySignal &&
            sceneStartPhaseOneReached(value)
        ) {
            armSceneStartSyncBurst(reason = "client-bootstrap-control-50", controlValue = value)
        }
    }

    fun handleClientBootstrapControl82(packet: ClientBootstrapControl82) {
        val value = packet.value
        val preview = value.toString(16).padStart(3 * 2, '0')
        lastClientBootstrapControl82 = value
        clientBootstrapControl82Count++
        logger.info {
            "Handled decoded client bootstrap control opcode 82 for $name " +
                "(value=$value, count=$clientBootstrapControl82Count)"
        }
        client.traceBootstrap(
            "world-client-bootstrap-control name=$name opcode=82 value=$value count=$clientBootstrapControl82Count " +
                "awaitingMapBuildComplete=$awaitingMapBuildComplete awaitingWorldReadySignal=$awaitingWorldReadySignal " +
                "preview=$preview"
        )
    }

    fun handleClientDisplayState106(packet: ClientDisplayState106) {
        lastClientDisplayState106 = packet
        clientDisplayState106Count++
        logger.info {
            "Handled decoded client display state opcode 106 for $name " +
                "(mode=${packet.mode}, width=${packet.width}, height=${packet.height}, " +
                "trailingFlag=${packet.trailingFlag}, count=$clientDisplayState106Count)"
        }
        client.traceBootstrap(
            "world-client-display-config name=$name opcode=106 mode=${packet.mode} width=${packet.width} " +
                "height=${packet.height} trailingFlag=${packet.trailingFlag} count=$clientDisplayState106Count " +
                "awaitingMapBuildComplete=$awaitingMapBuildComplete awaitingWorldReadySignal=$awaitingWorldReadySignal"
        )
        val pendingServerpermCompat = pendingServerpermMapBuildCompat
        if (awaitingMapBuildComplete && pendingServerpermCompat != null) {
            pendingServerpermMapBuildCompat = null
            logger.info {
                "Treating latched unidentified client opcode 0 for $name as compatibility MAP_BUILD_COMPLETE " +
                    "because CLIENT_DISPLAY_STATE_106 arrived after the serverperm varcs blob"
            }
            client.traceBootstrap(
                "world-map-build-complete-compat name=$name opcode=0 bytes=${pendingServerpermCompat.payloadLength} " +
                    "preview=${pendingServerpermCompat.preview} source=${pendingServerpermCompat.source}"
            )
            forcedMapBuildFallbackPending = true
            awaitingMapBuildComplete = false
            completeDeferredBootstrap()
        }
        if (awaitingLateSceneStartReadySignal) {
            acceptLateSceneStartReadySignal(
                opcode = 106,
                payloadLength = 6,
                preview =
                    "mode=${packet.mode},width=${packet.width},height=${packet.height},flag=${packet.trailingFlag}",
                source = "decoded-post-scene-start"
            )
        }
    }

    private fun handleUnidentifiedPacket(packet: UnidentifiedPacket): Boolean {
        val opcode = packet.packet.opcode
        val buf = packet.packet.buf
        val payloadLength = buf.readableBytes()
        val previewLength = minOf(24, payloadLength)
        val preview =
            if (previewLength <= 0) "<empty>"
            else ByteBufUtil.hexDump(buf, buf.readerIndex(), previewLength)
        val compatServerpermAckOpcode = OpenNXT.config.lobbyBootstrap.compatServerpermAckOpcode

        if (opcode == 0) {
            logger.info {
                "Intercepted unidentified client opcode 0 for $name " +
                    "(payloadBytes=$payloadLength, preview=$preview, compatAckOpcode=$compatServerpermAckOpcode, " +
                    "ackCount=$compatServerpermAckCount)"
            }
            client.traceBootstrap(
                "world-recv-serverperm-varcs name=$name opcode=0 bytes=$payloadLength preview=$preview " +
                    "compatAckOpcode=$compatServerpermAckOpcode ackCount=$compatServerpermAckCount"
            )
            if (compatServerpermAckOpcode >= 0) {
                client.write(UnidentifiedPacket(OpcodeWithBuffer(compatServerpermAckOpcode, Unpooled.EMPTY_BUFFER)))
                compatServerpermAckCount++
                client.traceBootstrap(
                    "world-send-serverperm-ack-candidate name=$name opcode=$compatServerpermAckOpcode " +
                        "count=$compatServerpermAckCount triggerOpcode=0"
                )
            }
            if (awaitingWorldReadySignal && !initialWorldSyncSent && lastClientDisplayState106 != null) {
                if (!skipPostInitialSyncHoldForForcedFallback) {
                    val delayedReadySignal =
                        PendingWorldReadySignal(
                            opcode = 48,
                            payloadLength = payloadLength,
                            preview = preview,
                            source =
                                if (deferredLateWorldCompletionTailPending) {
                                    "serverperm-after-display-delayed"
                                } else {
                                    "serverperm-after-display"
                                }
                        )
                    if (deferredLateWorldCompletionTailPending) {
                        pendingServerpermDelayedReadySignal = delayedReadySignal
                        client.traceBootstrap(
                            "world-defer-serverperm-ready-synthetic name=$name opcode=0 bytes=$payloadLength " +
                                "preview=$preview reason=wait-for-deferred-tail"
                        )
                    } else {
                        pendingServerpermDelayedReadySignal = delayedReadySignal
                    }
                } else {
                    client.traceBootstrap(
                        "world-skip-serverperm-ready-synthetic name=$name opcode=0 bytes=$payloadLength " +
                            "preview=$preview reason=wait-for-real-ready-or-timeout " +
                            "skipPostHold=$skipPostInitialSyncHoldForForcedFallback " +
                            "deferredTailPending=$deferredLateWorldCompletionTailPending"
                    )
                }
            }
            if (awaitingMapBuildComplete && lastClientDisplayState106 != null) {
                logger.info {
                    "Treating unidentified client opcode 0 for $name as compatibility MAP_BUILD_COMPLETE " +
                        "because CLIENT_DISPLAY_STATE_106 already arrived during rebuild"
                }
                client.traceBootstrap(
                    "world-map-build-complete-compat name=$name opcode=0 bytes=$payloadLength preview=$preview " +
                        "source=serverperm-after-display"
                )
                forcedMapBuildFallbackPending = true
                awaitingMapBuildComplete = false
                completeDeferredBootstrap()
            } else if (awaitingMapBuildComplete) {
                pendingServerpermMapBuildCompat = PendingServerpermMapBuildCompat(
                    payloadLength = payloadLength,
                    preview = preview,
                    source = "serverperm-before-display"
                )
                client.traceBootstrap(
                    "world-latch-serverperm-map-build-compat name=$name opcode=0 bytes=$payloadLength preview=$preview " +
                        "awaitingDisplayState106=true"
                )
            }
            buf.release()
            return true
        }

        if (opcode == 80 && payloadLength == 0) {
            logger.info {
                "Treating unidentified client opcode 80 as compatibility NO_TIMEOUT for $name " +
                    "(awaitingMapBuildComplete=$awaitingMapBuildComplete, awaitingWorldReadySignal=$awaitingWorldReadySignal)"
            }
            client.traceBootstrap(
                "world-client-no-timeout-compat name=$name opcode=80 bytes=0 " +
                    "awaitingMapBuildComplete=$awaitingMapBuildComplete " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal"
            )
            NoTimeoutHandler.handle(this, NoTimeout)
            buf.release()
            return true
        }

        if (opcode == 110 && payloadLength == 4) {
            val checksum = buf.getInt(buf.readerIndex())
            val compatWorldlistFetchReplyOpcode = OpenNXT.config.lobbyBootstrap.compatWorldlistFetchReplyOpcode
            logger.info {
                "Treating unidentified opcode 110 as compatibility WORLDLIST_FETCH for $name " +
                    "(checksum=$checksum, compatReplyOpcode=$compatWorldlistFetchReplyOpcode)"
            }
            client.traceBootstrap(
                "world-worldlist-fetch-compat name=$name opcode=110 checksum=$checksum " +
                    "compatReplyOpcode=$compatWorldlistFetchReplyOpcode"
            )
            if (compatWorldlistFetchReplyOpcode >= 0) {
                worldList.handleCompatRequest(checksum, client, compatWorldlistFetchReplyOpcode)
                client.traceBootstrap(
                    "world-send-worldlist-fetch-reply-compat name=$name opcode=$compatWorldlistFetchReplyOpcode " +
                        "checksum=$checksum"
                )
            }
            buf.release()
            return true
        }

        if (awaitingMapBuildComplete && opcode in MAP_BUILD_COMPAT_OPCODES) {
            logger.info {
                "Treating unidentified opcode $opcode as compatibility MAP_BUILD_COMPLETE for $name " +
                    "(payloadBytes=$payloadLength, preview=$preview)"
            }
            client.traceBootstrap(
                "world-map-build-complete-compat name=$name opcode=$opcode bytes=$payloadLength preview=$preview"
            )
            armCompatMapBuildReadyFallback(opcode)
            awaitingMapBuildComplete = false
            completeDeferredBootstrap()
            buf.release()
            return true
        }

        if (awaitingWorldReadySignal && opcode in WORLD_READY_COMPAT_OPCODES) {
            acceptWorldReadySignal(
                opcode = opcode,
                payloadLength = payloadLength,
                preview = preview,
                source = "live"
            )
            buf.release()
            return true
        }

        if (!initialWorldSyncSent && opcode in WORLD_READY_COMPAT_OPCODES) {
            logger.info {
                "Latching unidentified client opcode $opcode for $name until the live post-bootstrap world-ready wait is active " +
                    "(payloadBytes=$payloadLength, preview=$preview, awaitingMapBuildComplete=$awaitingMapBuildComplete, " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal)"
            }
            latchWorldReadySignal(
                opcode = opcode,
                payloadLength = payloadLength,
                preview = preview,
                source = "live-early"
            )
            buf.release()
            return true
        }

        if (awaitingLateSceneStartReadySignal && isLateSceneStartReadyCompatOpcode(opcode)) {
            acceptLateSceneStartReadySignal(
                opcode = opcode,
                payloadLength = payloadLength,
                preview = preview,
                source = "live-post-scene-start"
            )
            buf.release()
            return true
        }

        if (opcode == 113) {
            logger.info {
                "Ignoring unidentified client opcode 113 for $name as timed client-state traffic " +
                    "(payloadBytes=$payloadLength, preview=$preview, awaitingMapBuildComplete=$awaitingMapBuildComplete, " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal)"
            }
            client.traceBootstrap(
                "world-ignore-client-timed name=$name opcode=113 bytes=$payloadLength " +
                    "awaitingMapBuildComplete=$awaitingMapBuildComplete " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal preview=$preview"
            )
            buf.release()
            return true
        }

        if (opcode == 106) {
            logger.info {
                "Unexpected unidentified client opcode 106 for $name after explicit registration " +
                    "(payloadBytes=$payloadLength, preview=$preview, awaitingMapBuildComplete=$awaitingMapBuildComplete, " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal)"
            }
            client.traceBootstrap(
                "world-unidentified-client-display name=$name opcode=106 bytes=$payloadLength " +
                    "awaitingMapBuildComplete=$awaitingMapBuildComplete " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal preview=$preview"
            )
            buf.release()
            return true
        }

        if (opcode in setOf(17, 48, 83)) {
            logger.info {
                "Ignoring unidentified client opcode $opcode for $name " +
                    "(payloadBytes=$payloadLength, preview=$preview, awaitingMapBuildComplete=$awaitingMapBuildComplete, " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal)"
            }
            client.traceBootstrap(
                "world-ignore-client-compat name=$name opcode=$opcode bytes=$payloadLength " +
                    "awaitingMapBuildComplete=$awaitingMapBuildComplete " +
                    "awaitingWorldReadySignal=$awaitingWorldReadySignal preview=$preview"
            )
            buf.release()
            return true
        }

        logger.info {
            "Unhandled unidentified client opcode $opcode for $name " +
            "(payloadBytes=$payloadLength, preview=$preview)"
        }
        client.traceBootstrap(
            "world-unhandled-client-compat name=$name opcode=$opcode bytes=$payloadLength preview=$preview"
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

    fun completeDeferredBootstrap() {
        val continuation = deferredBootstrap ?: return
        deferredBootstrap = null
        mapBuildWaitTicks = 0
        val forcedMapBuildFallback = forcedMapBuildFallbackPending
        forcedMapBuildFallbackPending = false
        forcedMapBuildFallbackActive = forcedMapBuildFallbackActive || forcedMapBuildFallback
        skipPostInitialSyncHoldForForcedFallback = forcedMapBuildFallback
        forcedFallbackLateReadyInterfaceReplayArmed = forcedMapBuildFallback
        val previousForcedMinimalInterfaceBootstrap = forcedMinimalInterfaceBootstrap
        forcedMinimalInterfaceBootstrap = forcedMapBuildFallback
        try {
            continuation.invoke()
            worldReadyWaitTicks = 0
            playerInfoDelayTicks = 0
            if (OpenNXT.config.lobbyBootstrap.openRootInterface) {
                val compatReadyFallbackOpcode = compatMapBuildReadyFallbackOpcode
                when {
                    compatReadyFallbackOpcode == 113 -> {
                        awaitingWorldReadySignal = false
                        clearCompatMapBuildReadyFallback()
                        logger.info {
                            "Skipping post-bootstrap world-ready wait for $name because compat MAP_BUILD_COMPLETE " +
                                "opcode 113 now drives immediate initial sync"
                        }
                        client.traceBootstrap(
                            "world-skip-ready-wait name=$name reason=compat-map-build-immediate opcode=113"
                        )
                        sendInitialWorldSyncIfNeeded()
                    }

                    compatReadyFallbackOpcode != null -> {
                        awaitingWorldReadySignal = false
                        clearCompatMapBuildReadyFallback()
                        logger.info {
                            "Skipping post-bootstrap world-ready wait for $name because compat MAP_BUILD_COMPLETE " +
                                "opcode $compatReadyFallbackOpcode arrived without a later ready burst"
                        }
                        client.traceBootstrap(
                            "world-skip-ready-wait name=$name reason=compat-map-build-only opcode=$compatReadyFallbackOpcode"
                        )
                        sendInitialWorldSyncIfNeeded()
                    }

                    forcedMapBuildFallback -> {
                        awaitingWorldReadySignal = true
                        clearCompatMapBuildReadyFallback()
                        logger.info {
                            "Waiting for post-bootstrap world-ready signal for $name after forced MAP_BUILD fallback " +
                                "before sending the first world sync"
                        }
                        client.traceBootstrap(
                            "world-awaiting-ready-signal name=$name reason=forced-map-build-fallback"
                        )
                        if (pendingWorldReadySignal == null) {
                            logger.info {
                                "Synthesizing a post-bootstrap world-ready signal for $name after forced MAP_BUILD fallback " +
                                    "because no early ready burst was observed during rebuild"
                            }
                            latchWorldReadySignal(
                                opcode = 48,
                                payloadLength = 0,
                                preview = "<synthetic>",
                                source = "synthetic-forced-map-build-fallback"
                            )
                        }
                        consumePendingWorldReadySignalIfNeeded(source = "latched-post-bootstrap")
                    }

                    else -> {
                        awaitingWorldReadySignal = true
                        logger.info {
                            "Waiting for post-bootstrap world-ready signal before sending initial world sync for $name"
                        }
                        client.traceBootstrap("world-awaiting-ready-signal name=$name")
                        consumePendingWorldReadySignalIfNeeded(source = "latched-post-bootstrap")
                    }
                }
            } else {
                awaitingWorldReadySignal = false
                logger.info {
                    "Skipping post-bootstrap world-ready wait for $name because no root interface is open"
                }
                client.traceBootstrap("world-skip-ready-wait name=$name reason=no-root-interface")
                sendInitialWorldSyncIfNeeded()
            }
        } catch (e: Exception) {
            logger.error(e) { "Deferred world bootstrap failed for $name" }
            throw e
        } finally {
            forcedMinimalInterfaceBootstrap = previousForcedMinimalInterfaceBootstrap
        }
    }

    private fun sendWorldSyncFrame(reason: String) {
        val npcInfoOpcode = if (OpenNXT.protocol.serverProtNames.values.containsKey("NPC_INFO")) {
            OpenNXT.protocol.serverProtNames.values.getInt("NPC_INFO")
        } else {
            null
        }
        val playerInfoOpcode = if (OpenNXT.protocol.serverProtNames.values.containsKey("PLAYER_INFO")) {
            OpenNXT.protocol.serverProtNames.values.getInt("PLAYER_INFO")
        } else {
            null
        }
        val frameNumber = worldSyncFramesSent + 1
        val shouldTraceFrame = frameNumber <= 5 || frameNumber % 50 == 0
        if (shouldTraceFrame) {
            client.traceBootstrap(
                "world-sync-frame name=$name reason=$reason frame=$frameNumber " +
                    "npcInfoOpcode=${npcInfoOpcode ?: -1} playerInfoOpcode=${playerInfoOpcode ?: -1}"
            )
        }

        var sentFrame = false
        if (npcInfoOpcode != null) {
            val npcInfoBuffer = NpcInfoEncoder.createEmptyBuffer()
            if (shouldTraceFrame) {
                client.traceBootstrap(
                    "world-send-npc-info name=$name reason=$reason frame=$frameNumber " +
                        "opcode=$npcInfoOpcode bytes=${npcInfoBuffer.readableBytes()}"
                )
            }
            client.write(UnidentifiedPacket(OpcodeWithBuffer(npcInfoOpcode, npcInfoBuffer)))
            sentFrame = true
        }
        if (playerInfoOpcode != null) {
            val refreshAppearance = forcedLocalAppearanceRefreshFrames > 0
            if (frameNumber <= FORCED_LOCAL_APPEARANCE_FRAMES || refreshAppearance) {
                viewport.cachedAppearanceHashes[entity.index] = null
                if (refreshAppearance) {
                    forcedLocalAppearanceRefreshFrames--
                }
                client.traceBootstrap(
                    "world-force-local-appearance name=$name reason=$reason frame=$frameNumber " +
                        "maxFrames=$FORCED_LOCAL_APPEARANCE_FRAMES refreshRemaining=$forcedLocalAppearanceRefreshFrames"
                )
            }
            val playerInfoBuffer = PlayerInfoEncoder.createBufferFor(this)
            if (shouldTraceFrame) {
                client.traceBootstrap(
                    "world-send-player-info name=$name reason=$reason frame=$frameNumber " +
                        "opcode=$playerInfoOpcode bytes=${playerInfoBuffer.readableBytes()}"
                )
            }
            client.write(UnidentifiedPacket(OpcodeWithBuffer(playerInfoOpcode, playerInfoBuffer)))
            sentFrame = true
        }
        if (!sentFrame) {
            client.traceBootstrap("world-sync-frame-skipped name=$name reason=$reason frame=$frameNumber")
            return
        }

        viewport.resetForNextTransmit()
        initialWorldSyncSent = true
        worldSyncFramesSent = frameNumber
    }

    private fun sendPreReadyWorldSyncPrimeFrame(reason: String) {
        val previousInitialWorldSyncSent = initialWorldSyncSent
        sendWorldSyncFrame(reason)
        initialWorldSyncSent = previousInitialWorldSyncSent
    }

    private fun sendInitialWorldSyncIfNeeded(
        forceImmediateFollowup: Boolean = false,
        skipPostSyncHold: Boolean = false
    ) {
        if (initialWorldSyncSent) {
            client.traceBootstrap("world-sync-suppressed name=$name reason=initial-sync-already-sent")
            return
        }

        pendingWorldReadySignal = null
        pendingServerpermDelayedReadySignal = null
        val forcedFallbackBootstrap = skipPostInitialSyncHoldForForcedFallback
        postInitialWorldSyncHoldSendFrames = false
        if (interfaces.isOpened(1417) && !forcedFallbackBootstrap) {
            closeLoadingOverlay(reason = null)
        } else if (interfaces.isOpened(1417) && forcedFallbackBootstrap) {
            pendingForcedFallbackLoadingOverlayClose = true
            client.traceBootstrap(
                "world-skip-close-loading-overlay name=$name id=1417 parent=1477 component=508 " +
                    "reason=forced-map-build-fallback"
            )
        } else {
            pendingForcedFallbackLoadingOverlayClose = false
        }

        sendWorldSyncFrame("initial")
        val keepPostSyncHoldForDeferredTail = deferredLateWorldCompletionTailPending
        skipPostInitialSyncHoldForForcedFallback = false
        val sendImmediateFollowup =
            forceImmediateFollowup ||
                OpenNXT.config.lobbyBootstrap.sendImmediateFollowupWorldSync
        if (sendImmediateFollowup) {
            postInitialWorldSyncHoldForcedFallback =
                forcedFallbackBootstrap && keepPostSyncHoldForDeferredTail
            postInitialWorldSyncHoldSendFrames = keepPostSyncHoldForDeferredTail
            val source =
                if (
                    forceImmediateFollowup &&
                    !OpenNXT.config.lobbyBootstrap.sendImmediateFollowupWorldSync
                ) {
                    "explicit"
                } else {
                    "config"
                }
            client.traceBootstrap(
                "world-send-immediate-followup-sync name=$name reason=initial-sync source=$source"
            )
            sendWorldSyncFrame("initial-followup")
            if (keepPostSyncHoldForDeferredTail && !skipPostSyncHold) {
                postInitialWorldSyncHoldTicks =
                    if (forcedFallbackBootstrap) {
                        FORCED_FALLBACK_POST_INITIAL_WORLD_SYNC_HOLD_TICKS
                    } else {
                        POST_INITIAL_WORLD_SYNC_HOLD_TICKS
                    }
                client.traceBootstrap(
                    "world-keep-post-initial-sync-hold name=$name reason=deferred-tail-pending " +
                        "ticks=$postInitialWorldSyncHoldTicks source=$source"
                )
                if (forcedFallbackBootstrap) {
                    primeForcedFallbackPostInitialSyncHold(source = source)
                }
            } else {
                postInitialWorldSyncHoldTicks = 0
                postInitialWorldSyncHoldSendFrames = false
                val reason =
                    if (keepPostSyncHoldForDeferredTail && skipPostSyncHold) {
                        "ready-accepted-immediate-followup"
                    } else {
                        "immediate-followup-sync"
                    }
                client.traceBootstrap("world-skip-post-initial-sync-hold name=$name reason=$reason")
                closeForcedFallbackLoadingOverlayIfPending(reason = "forced-map-build-fallback-no-hold")
            }
        } else {
            postInitialWorldSyncHoldTicks =
                if (forcedFallbackBootstrap) {
                    FORCED_FALLBACK_POST_INITIAL_WORLD_SYNC_HOLD_TICKS
                } else {
                    POST_INITIAL_WORLD_SYNC_HOLD_TICKS
                }
            postInitialWorldSyncHoldForcedFallback = forcedFallbackBootstrap
            postInitialWorldSyncHoldSendFrames = keepPostSyncHoldForDeferredTail
            val reason =
                if (forcedFallbackBootstrap) {
                    "forced-map-build-fallback"
                } else {
                    "initial-sync"
                }
            client.traceBootstrap(
                "world-post-initial-sync-hold name=$name ticks=$postInitialWorldSyncHoldTicks reason=$reason"
            )
        }
    }

    private fun currentPostInitialSyncHoldReason(): String =
        if (postInitialWorldSyncHoldForcedFallback) {
            "forced-map-build-fallback"
        } else {
            "deferred-tail-pending"
        }

    private fun primeForcedFallbackPostInitialSyncHold(source: String) {
        if (!postInitialWorldSyncHoldForcedFallback || postInitialWorldSyncHoldTicks <= 0 || !postInitialWorldSyncHoldSendFrames) {
            return
        }

        val holdTicksRemaining = postInitialWorldSyncHoldTicks
        val holdReason = currentPostInitialSyncHoldReason()
        client.traceBootstrap(
            "world-prime-post-initial-sync-hold name=$name ticksRemaining=$holdTicksRemaining " +
                "reason=$holdReason source=$source"
        )
        if (PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null) {
            client.write(NoTimeout)
            client.traceBootstrap(
                "world-prime-post-initial-sync-hold-keepalive name=$name " +
                    "ticksRemaining=$holdTicksRemaining packet=NO_TIMEOUT reason=$holdReason source=$source"
            )
        }
        val suppressForcedFallbackHoldSync =
            postInitialWorldSyncHoldForcedFallback && deferredLateWorldCompletionTailPending
        if (client.pendingDeferredBootstrapVarpCount() == 0) {
            if (suppressForcedFallbackHoldSync) {
                client.traceBootstrap(
                    "world-skip-prime-post-initial-sync-hold-sync name=$name ticksRemaining=$holdTicksRemaining " +
                        "reason=forced-map-build-fallback-deferred-tail source=$source"
                )
            } else {
                sendWorldSyncFrame("hold-prime")
            }
            primeForcedFallbackPreDeferredFamilies(source = source)
        } else {
            client.traceBootstrap(
                "world-defer-prime-post-initial-sync-hold name=$name ticksRemaining=$holdTicksRemaining " +
                    "pendingLateDefaultVarps=${client.pendingDeferredBootstrapVarpCount()} source=$source"
            )
        }
        postInitialWorldSyncHoldTicks--
    }

    private fun primeForcedFallbackPreDeferredFamilies(source: String) {
        if (!postInitialWorldSyncHoldForcedFallback || !deferredLateWorldCompletionTailPending) {
            return
        }
        if (forcedFallbackPreDeferredFamiliesPrimed) {
            client.traceBootstrap(
                "world-skip-prime-forced-fallback-pre-deferred-families name=$name source=$source " +
                    "reason=already-primed"
            )
            return
        }
        if (!interfaces.hasRootOpen()) {
            client.traceBootstrap(
                "world-defer-prime-forced-fallback-pre-deferred-families name=$name source=$source " +
                    "reason=root-interface-not-open"
            )
            return
        }
        forcedFallbackPreDeferredFamiliesPrimed = true
        client.traceBootstrap(
            "world-prime-forced-fallback-pre-deferred-families name=$name source=$source " +
                "reason=accepted-ready-before-hold-clear"
        )
        client.traceBootstrap(
            "world-defer-forced-fallback-supplemental-children name=$name source=$source " +
                "reason=accepted-ready-before-hold-clear"
        )
        client.traceBootstrap(
            "world-defer-forced-fallback-restored-world-panels name=$name source=$source " +
                "reason=accepted-ready-before-hold-clear until=final-late-ready"
        )
        deferredForcedFallbackRestoredWorldPanelsPending = true
        client.traceBootstrap(
            "world-defer-forced-fallback-utility-panel-deck name=$name source=$source " +
                "reason=accepted-ready-before-hold-clear until=final-late-ready"
        )
        deferredForcedFallbackUtilityPanelDeckPending = true
        client.traceBootstrap(
            "world-defer-forced-fallback-scene-bridge name=$name source=$source " +
                "reason=accepted-ready-before-hold-clear until=post-ready-tail"
        )
        deferredForcedFallbackSceneBridgePending = true
        if (deferredForcedFallbackLightInterfaceTailPending) {
            client.traceBootstrap(
                "world-defer-forced-fallback-light-tail-pre-hold name=$name source=$source " +
                    "reason=accepted-ready-before-hold-clear until=post-ready-tail"
            )
        }
        if (
            deferredForcedFallbackCompletionStructurePending ||
            deferredForcedFallbackCompletionCompanionsPending ||
            !deferredForcedFallbackCompletionStructureSent
        ) {
            client.traceBootstrap(
                "world-defer-forced-fallback-completion-structure name=$name source=$source " +
                    "reason=accepted-ready-before-hold-clear until=final-late-ready"
            )
            deferredForcedFallbackCompletionStructurePending = true
        }
        if (!deferredForcedFallbackDeferredScriptsSent) {
            client.traceBootstrap(
                "world-defer-forced-fallback-deferred-completion-scripts name=$name source=$source " +
                    "reason=accepted-ready-before-hold-clear until=post-ready-tail"
            )
        }
    }

    private fun sendDeferredDefaultVarpsIfNeeded() {
        if (!deferredDefaultVarpsPending || !initialWorldSyncSent) {
            return
        }

        deferredDefaultVarpsPending = false
        runBootstrapStage("late-default-varps") {
            client.traceBootstrap("world-send-deferred-default-varps name=$name")
            val skipFullDefaultVarpReplayForContainedPostLobby =
                entryMode == EntryMode.POST_LOBBY_AUTH
            val forcedFallbackReplaySkipIds =
                if (forcedMapBuildFallbackActive) TODORefactorThisClass.FORCED_FALLBACK_CANDIDATE_DEFAULT_VARP_IDS
                else emptyList()
            if (forcedFallbackReplaySkipIds.isNotEmpty()) {
                client.traceBootstrap(
                    "world-prime-late-default-varp-replay-skip name=$name ids=${forcedFallbackReplaySkipIds.joinToString(",")}"
                )
            }
            client.withLateDefaultVarpReplaySkip(forcedFallbackReplaySkipIds) {
                if (forcedMapBuildFallbackActive) {
                    client.traceBootstrap(
                        "world-send-forced-fallback-candidate-default-varps name=$name " +
                            "ids=0,1,2,6,3,4,7,10,11,3920,8256 values=0:28,3:-1807741724,questhelp:-1,long:0"
                    )
                    TODORefactorThisClass.sendForcedFallbackCandidateDefaultVarps(client)
                }
                if (skipFullDefaultVarpReplayForContainedPostLobby) {
                    client.traceBootstrap(
                        "world-skip-full-default-varp-replay name=$name " +
                            "reason=contained-post-lobby-auth forcedFallback=$forcedMapBuildFallbackActive"
                    )
                } else {
                    TODORefactorThisClass.sendDefaultVarps(client)
                }
            }
            client.traceBootstrap(
                "world-queued-deferred-default-varps name=$name packets=${client.pendingDeferredBootstrapVarpCount()}"
            )
            if (client.pendingDeferredBootstrapVarpCount() > 0) {
                armSceneStartSyncBurst(
                    reason = "late-default-varps-prime",
                    controlValue = sceneStartControl50ForTrace()
                )
                if (PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null) {
                    client.write(NoTimeout)
                    client.traceBootstrap(
                        "world-prime-late-default-varps-keepalive name=$name " +
                            "packet=NO_TIMEOUT pendingLateDefaultVarps=${client.pendingDeferredBootstrapVarpCount()}"
                    )
                }
                client.traceBootstrap(
                    "world-prime-late-default-varps-followup-sync name=$name " +
                        "pendingLateDefaultVarps=${client.pendingDeferredBootstrapVarpCount()}"
                )
                sendWorldSyncFrame("late-default-varps-prime")
            } else {
                client.traceBootstrap(
                    "world-prime-late-default-varps-followup-sync name=$name pendingLateDefaultVarps=0"
                )
                sendWorldSyncFrame("late-default-varps-prime")
            }
        }
    }

    private fun shouldQueueDeferredDefaultVarps(reason: String): Boolean {
        val bootstrap = OpenNXT.config.lobbyBootstrap
        if (!bootstrap.sendDefaultVarps) {
            return false
        }

        val forcedMapBuildFallbackCompat = reason.startsWith("forced-map-build-fallback")
        val fullBootstrapCompatControl50Override =
            bootstrap.openRootInterface &&
                !forcedMapBuildFallbackCompat &&
                lastClientBootstrapControl50 == 1
        if (bootstrap.openRootInterface && !forcedMapBuildFallbackCompat) {
            if (fullBootstrapCompatControl50Override) {
                client.traceBootstrap(
                    "world-allow-deferred-default-varps name=$name reason=$reason " +
                        "override=compat-bootstrap-control50-1"
                )
                return true
            }
            client.traceBootstrap(
                "world-skip-deferred-default-varps name=$name reason=$reason " +
                    "compat=world-bootstrap"
            )
            return false
        }
        if (bootstrap.openRootInterface && forcedMapBuildFallbackCompat) {
            client.traceBootstrap(
                "world-allow-deferred-default-varps name=$name reason=$reason " +
                    "override=forced-map-build-fallback"
            )
        }

        return true
    }

    private fun sendConfiguredWorldInterfaceBindings() {
        val bootstrap = OpenNXT.config.lobbyBootstrap
        val parentInterfaceId = 1477
        val parentComponentId = 27
        val subInterfaceId = 1482
        val selfModelComponent = bootstrap.worldInterfaceSelfModelComponent
        val activePlayerRegistered = PacketRegistry.getRegistration(Side.SERVER, IfOpensubActivePlayer::class) != null
        val activePlayerConfigEnabled = bootstrap.sendExperimentalActivePlayerOpensub
        val activePlayerForcedByFallback = forcedMinimalInterfaceBootstrap
        val activePlayerEnabled = activePlayerConfigEnabled && !activePlayerForcedByFallback
        if (selfModelComponent >= 0) {
            val targetComponentId = InterfaceHash(subInterfaceId, selfModelComponent).hash
            if (activePlayerEnabled && activePlayerRegistered) {
                interfaces.openActivePlayer(
                    subInterfaceId = subInterfaceId,
                    component = selfModelComponent,
                    playerIndex = entity.index,
                    mode = 0
                )
                client.traceBootstrap(
                        "world-open-active-player name=$name stage=interfaces " +
                            "parentInterfaceId=$parentInterfaceId parentComponentId=$parentComponentId " +
                            "subInterfaceId=$subInterfaceId childComponentId=$selfModelComponent " +
                            "targetComponentId=$targetComponentId playerIndex=${entity.index} mode=0 " +
                            "packetRegistered=$activePlayerRegistered configEnabled=$activePlayerConfigEnabled " +
                            "forcedFallback=$activePlayerForcedByFallback effectiveEnabled=$activePlayerEnabled"
                )
            } else {
                val reason =
                    when {
                        activePlayerForcedByFallback -> "forced-map-build-fallback-disabled"
                        !activePlayerEnabled -> "experimental-opensub-disabled"
                        !activePlayerRegistered -> "packet-unmapped"
                        else -> "unknown"
                    }
                client.traceBootstrap(
                    "world-skip-active-player name=$name stage=interfaces " +
                        "parentInterfaceId=$parentInterfaceId parentComponentId=$parentComponentId " +
                        "subInterfaceId=$subInterfaceId childComponentId=$selfModelComponent " +
                        "packetRegistered=$activePlayerRegistered configEnabled=$activePlayerConfigEnabled " +
                        "forcedFallback=$activePlayerForcedByFallback effectiveEnabled=$activePlayerEnabled " +
                        "reason=$reason"
                )
            }
            if (forcedMinimalInterfaceBootstrap) {
                deferredForcedFallbackSelfModelBindPending = true
                client.traceBootstrap(
                    "world-defer-local-player-model-bind name=$name id=$subInterfaceId component=$selfModelComponent " +
                        "reason=forced-map-build-fallback-pre-late-ready"
                )
            } else {
                interfaces.setPlayerModelSelf(id = subInterfaceId, component = selfModelComponent)
                client.traceBootstrap(
                    "world-bind-local-player-model name=$name id=$subInterfaceId component=$selfModelComponent"
                )
            }
        } else {
            logger.info {
                "Skipping active player bind for $name because worldInterfaceSelfModelComponent is not configured"
            }
            client.traceBootstrap(
                "world-skip-active-player name=$name stage=interfaces " +
                    "parentInterfaceId=$parentInterfaceId parentComponentId=$parentComponentId " +
                    "subInterfaceId=$subInterfaceId childComponentId=$selfModelComponent " +
                    "packetRegistered=$activePlayerRegistered configEnabled=$activePlayerConfigEnabled " +
                    "forcedFallback=$activePlayerForcedByFallback effectiveEnabled=$activePlayerEnabled " +
                    "reason=model-component-unconfigured"
            )
        }

        val selfHeadComponent = bootstrap.worldInterfaceSelfHeadComponent
        if (selfHeadComponent >= 0) {
            interfaces.setPlayerHead(id = subInterfaceId, component = selfHeadComponent)
            client.traceBootstrap(
                "world-bind-local-player-head name=$name id=$subInterfaceId component=$selfHeadComponent"
            )
        }
    }

    private fun sendMinimalWorldVarcs() {
        client.write(ClientSetvarcSmall(id = 181, value = 0))
        client.write(ClientSetvarcSmall(id = 1027, value = 1))
        client.write(ClientSetvarcSmall(id = 1034, value = 2))
        client.write(ClientSetvarcSmall(id = 3497, value = 0))
        client.traceBootstrap("world-send-minimal-varcs name=$name ids=181,1027,1034,3497")
    }

    private fun openLoadingNotesInterfaceIfAvailable(reason: String) {
        if (PacketRegistry.getRegistration(Side.SERVER, IfSethide::class) == null) {
            logger.info {
                "Skipping loading-notes interface 1417 for $name because IF_SETHIDE is not mapped for this build"
            }
            client.traceBootstrap("world-skip-loading-notes name=$name reason=$reason")
            return
        }

        interfaces.open(id = 1417, parent = 1477, component = 508, walkable = true)
        interfaces.events(id = 1417, component = 13, from = 0, to = 29, mask = 2621470)
        interfaces.text(id = 1417, component = 5, text = "Loading notes<br>Please wait...")
        interfaces.hide(id = 1417, component = 5, hidden = false)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(11, 1))
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(12, 0))
        client.traceBootstrap("world-open-loading-notes name=$name id=1417 parent=1477 component=508 reason=$reason")
    }

    private fun openForcedFallbackSupplementalWorldChildren(includeEvents: Boolean = true) {
        interfaces.open(id = 1466, parent = 1477, component = 284, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1466, component = 7, from = 0, to = 28, mask = 30)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(0, 1))
        client.traceBootstrap("world-open-minimal-supplemental-child name=$name id=1466 parent=1477 component=284")

        interfaces.open(id = 1473, parent = 1477, component = 98, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1473, component = 7, from = 65535, to = 65535, mask = 2097152)
            interfaces.events(id = 1473, component = 7, from = 0, to = 27, mask = 15302030)
            interfaces.events(id = 1473, component = 25, from = 0, to = 16, mask = 1422)
            interfaces.events(id = 1473, component = 1, from = 0, to = 5, mask = 2099198)
            interfaces.events(id = 1473, component = 28, from = 0, to = 5, mask = 2099198)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(2, 1))
        client.traceBootstrap("world-open-minimal-supplemental-child name=$name id=1473 parent=1477 component=98")
        if (!includeEvents) {
            client.traceBootstrap(
                "world-skip-forced-fallback-supplemental-events name=$name count=6 reason=forced-map-build-fallback"
            )
        }
    }

    private fun queueMinimalWorldFollowupIfNeeded(
        reason: String,
        queueDeferredCompletionTail: Boolean = true
    ) {
        if (shouldQueueDeferredDefaultVarps(reason) && !deferredDefaultVarpsPending) {
            deferredDefaultVarpsPending = true
            client.traceBootstrap("world-defer-default-varps name=$name reason=$reason")
        }
        if (queueDeferredCompletionTail) {
            queueDeferredWorldCompletionTailIfNeeded(reason)
        } else {
            client.traceBootstrap("world-skip-deferred-completion-tail name=$name reason=$reason")
        }
    }

    private fun queueDeferredWorldCompletionTailIfNeeded(reason: String) {
        if (!deferredLateWorldCompletionTailPending) {
            deferredLateWorldCompletionTailPending = true
            client.traceBootstrap("world-queue-deferred-completion-tail name=$name reason=$reason")
        }
    }

    private fun deferForcedFallbackInterfaceTail(reason: String) {
        if (!deferredForcedFallbackSupplementalChildrenPending) {
            deferredForcedFallbackSupplementalChildrenPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-supplemental-children name=$name reason=$reason"
            )
        }
        if (!deferredForcedFallbackLightInterfaceTailPending) {
            deferredForcedFallbackLightInterfaceTailPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-light-tail name=$name reason=$reason"
            )
        }
        if (!deferredForcedFallbackCompletionCompanionsPending) {
            deferredForcedFallbackCompletionCompanionsPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-completion-companions name=$name " +
                    "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                    "reason=$reason"
            )
        }
    }

    private fun sendInterfaceBootstrapScript(script: Int, args: Array<Any> = emptyArray()) {
        val bootstrap = OpenNXT.config.lobbyBootstrap
        val skipReason =
            when {
                !bootstrap.sendInterfaceBootstrapScripts -> "global-disabled"
                script in INTERFACE_BOOTSTRAP_PANEL_SCRIPTS &&
                    !bootstrap.sendInterfaceBootstrapPanelScripts -> "panel-disabled"
                script in INTERFACE_BOOTSTRAP_ANNOUNCEMENT_SCRIPTS &&
                    !bootstrap.sendInterfaceBootstrapAnnouncementScripts -> "announcement-disabled"
                script in INTERFACE_BOOTSTRAP_COMPLETION_SCRIPTS &&
                    !bootstrap.sendInterfaceBootstrapCompletionScripts -> "completion-disabled"
                script in INTERFACE_BOOTSTRAP_WIDGET_STATE_SCRIPTS &&
                    !bootstrap.sendInterfaceBootstrapWidgetStateScripts -> "widget-state-disabled"
                else -> null
            }
        if (skipReason != null) {
            client.traceBootstrap(
                "world-skip-interface-bootstrap-script name=$name script=$script reason=$skipReason"
            )
            return
        }
        client.write(RunClientScript(script = script, args = args))
    }

    private fun sendLightLateWorldInterfaceTail(includeEvents: Boolean = true, includeScripts: Boolean = true) {
        interfaces.open(id = 634, parent = 1477, component = 739, walkable = true)
        if (includeScripts) {
            sendInterfaceBootstrapScript(script = 11145, args = arrayOf(1067, 600, 0, 0, 96797408))
            sendInterfaceBootstrapScript(script = 8420, args = arrayOf(-1, 96797410, 96797411, -1, "", 21259, 1007))
        }
        interfaces.hide(id = 634, component = 259, hidden = true)
        interfaces.hide(id = 634, component = 0, hidden = false)
        if (includeEvents) {
            interfaces.events(id = 634, component = 152, from = 65535, to = 65535, mask = 1022)
            interfaces.events(id = 634, component = 265, from = 65535, to = 65535, mask = 2)
            interfaces.events(id = 634, component = 67, from = 65535, to = 65535, mask = 2)
            interfaces.events(id = 634, component = 68, from = 65535, to = 65535, mask = 2)
            interfaces.events(id = 634, component = 138, from = 65535, to = 65535, mask = 2)
            interfaces.events(id = 634, component = 139, from = 65535, to = 65535, mask = 2)
            interfaces.events(id = 634, component = 2, from = 65535, to = 65535, mask = 2)
        }

        interfaces.open(id = 653, parent = 1477, component = 744, walkable = true)
        if (includeScripts) {
            sendInterfaceBootstrapScript(script = 11145, args = arrayOf(1067, 600, 0, 0, 96797413))
            sendInterfaceBootstrapScript(script = 8420, args = arrayOf(-1, 96797415, 96797416, -1, "", 21259, 1007))
        }
        interfaces.hide(id = 653, component = 71, hidden = true)
        interfaces.hide(id = 653, component = 0, hidden = false)
        if (includeEvents) {
            interfaces.events(id = 653, component = 155, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 166, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 177, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 188, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 199, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 210, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 221, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 232, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 243, from = 0, to = 500, mask = 62)
            interfaces.events(id = 653, component = 254, from = 0, to = 500, mask = 62)
        }

        interfaces.open(id = 1430, parent = 1477, component = 65, walkable = true)
        interfaces.open(id = 1670, parent = 1477, component = 70, walkable = true)
        if (includeScripts) {
            sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1032))
        }
        interfaces.open(id = 1671, parent = 1477, component = 75, walkable = true)
        if (includeScripts) {
            sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1033))
        }
        interfaces.open(id = 1673, parent = 1477, component = 85, walkable = true)
        if (includeScripts) {
            sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1035))
        }

        client.traceBootstrap("world-send-light-interface-tail name=$name ids=634,653,1430,1670,1671,1673")
        if (!includeEvents) {
            client.traceBootstrap(
                "world-skip-forced-fallback-light-tail-events name=$name count=17 reason=forced-map-build-fallback"
            )
        }
        if (!includeScripts) {
            client.traceBootstrap(
                "world-skip-forced-fallback-light-tail-scripts name=$name count=7 scripts=11145,8420,8310 reason=forced-map-build-fallback"
            )
        }
    }

    private fun sendDeferredForcedFallbackInterfaceTailIfNeeded(
        includeEvents: Boolean = true,
        includeScripts: Boolean = true
    ) {
        if (!deferredForcedFallbackSupplementalChildrenPending && !deferredForcedFallbackLightInterfaceTailPending) {
            return
        }
        if (deferredForcedFallbackSupplementalChildrenPending) {
            deferredForcedFallbackSupplementalChildrenPending = false
            openForcedFallbackSupplementalWorldChildren(includeEvents = includeEvents)
        }
        if (deferredForcedFallbackLightInterfaceTailPending) {
            deferredForcedFallbackLightInterfaceTailPending = false
            sendLightLateWorldInterfaceTail(includeEvents = includeEvents, includeScripts = includeScripts)
        }
    }

    private fun openForcedFallbackRestoredWorldPanels(includeEvents: Boolean = true) {
        if (forcedFallbackRestoredWorldPanelsSent) {
            return
        }
        forcedFallbackRestoredWorldPanelsSent = true
        interfaces.open(id = 1464, parent = 1477, component = 109, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1464, component = 15, from = 0, to = 18, mask = 15302654)
            interfaces.events(id = 1464, component = 24, from = 0, to = 6, mask = 2046)
            interfaces.events(id = 1464, component = 19, from = 0, to = 6, mask = 2046)
            interfaces.events(id = 1464, component = 15, from = 0, to = 18, mask = 10749950)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(3, 1))
        client.write(ClientSetvarcSmall(id = 181, value = 0))

        interfaces.open(id = 1458, parent = 1477, component = 131, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1458, component = 39, from = 0, to = 38, mask = 8388610)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(4, 1))

        interfaces.open(id = 1461, parent = 1477, component = 186, walkable = true)
        interfaces.open(id = 1884, parent = 1477, component = 197, walkable = true)
        interfaces.open(id = 1885, parent = 1477, component = 208, walkable = true)
        interfaces.open(id = 1887, parent = 1477, component = 219, walkable = true)
        interfaces.open(id = 1886, parent = 1477, component = 230, walkable = true)
        interfaces.open(id = 1460, parent = 1477, component = 142, walkable = true)
        interfaces.open(id = 1881, parent = 1477, component = 153, walkable = true)
        interfaces.open(id = 1888, parent = 1477, component = 164, walkable = true)
        interfaces.open(id = 1883, parent = 1477, component = 241, walkable = true)
        interfaces.open(id = 1449, parent = 1477, component = 252, walkable = true)
        interfaces.open(id = 1882, parent = 1477, component = 263, walkable = true)
        interfaces.open(id = 1452, parent = 1477, component = 175, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1461, component = 1, from = 0, to = 211, mask = 10320974)
            interfaces.events(id = 1884, component = 1, from = 0, to = 211, mask = 10320974)
            interfaces.events(id = 1885, component = 1, from = 0, to = 211, mask = 10320974)
            interfaces.events(id = 1886, component = 1, from = 0, to = 211, mask = 10320974)
            interfaces.events(id = 1461, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1461, component = 7, from = 7, to = 10, mask = 10319874)
            interfaces.events(id = 1460, component = 5, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1460, component = 5, from = 7, to = 10, mask = 10319874)
            interfaces.events(id = 1452, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1883, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1883, component = 7, from = 7, to = 10, mask = 10319874)
            interfaces.events(id = 1881, component = 5, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1888, component = 5, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1449, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1882, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1884, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1885, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1886, component = 7, from = 7, to = 16, mask = 2)
            interfaces.events(id = 1460, component = 1, from = 0, to = 211, mask = 10320902)
            interfaces.events(id = 1881, component = 1, from = 0, to = 211, mask = 10320902)
            interfaces.events(id = 1888, component = 1, from = 0, to = 211, mask = 10320902)
            interfaces.events(id = 1452, component = 1, from = 0, to = 211, mask = 10320902)
            interfaces.events(id = 1883, component = 1, from = 0, to = 211, mask = 10320902)
            interfaces.events(id = 1449, component = 1, from = 0, to = 211, mask = 10320902)
            interfaces.events(id = 1882, component = 1, from = 0, to = 211, mask = 10320902)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(5, 1))
        client.traceBootstrap("world-open-restored-interface name=$name id=1887 parent=1477 component=219")
        client.traceBootstrap(
            "world-send-forced-fallback-restored-world-panels name=$name " +
                "ids=1464,1458,1461,1884,1885,1887,1886,1460,1881,1888,1883,1449,1882,1452 scripts=8862:3,4,5"
        )
    }

    private fun openForcedFallbackUtilityPanelDeck(includeEvents: Boolean = true) {
        if (forcedFallbackUtilityPanelDeckSent) {
            return
        }
        forcedFallbackUtilityPanelDeckSent = true
        interfaces.open(id = 550, parent = 1477, component = 475, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(14, 1))
        if (includeEvents) {
            interfaces.events(id = 550, component = 7, from = 0, to = 500, mask = 2046)
            interfaces.events(id = 550, component = 60, from = 0, to = 500, mask = 6)
        }

        interfaces.open(id = 1427, parent = 1477, component = 519, walkable = true)
        client.write(ClientSetvarcSmall(id = 1027, value = 1))
        client.write(ClientSetvarcSmall(id = 1034, value = 2))
        if (includeEvents) {
            interfaces.events(id = 1427, component = 30, from = 0, to = 600, mask = 1040)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(15, 1))

        interfaces.open(id = 1110, parent = 1477, component = 486, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(16, 1))
        if (includeEvents) {
            interfaces.events(id = 1110, component = 31, from = 0, to = 200, mask = 2)
            interfaces.events(id = 1110, component = 85, from = 0, to = 600, mask = 2)
            interfaces.events(id = 1110, component = 83, from = 0, to = 600, mask = 1040)
            interfaces.events(id = 1110, component = 38, from = 0, to = 600, mask = 1040)
        }

        interfaces.open(id = 590, parent = 1477, component = 393, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 590, component = 8, from = 0, to = 223, mask = 8388614)
            interfaces.events(id = 590, component = 1, from = 0, to = 43, mask = 8388622)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(9, 1))

        interfaces.open(id = 1416, parent = 1477, component = 295, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1416, component = 3, from = 0, to = 3087, mask = 62)
            interfaces.events(id = 1416, component = 11, from = 0, to = 99, mask = 2359334)
            interfaces.events(id = 1416, component = 11, from = 100, to = 199, mask = 4)
            interfaces.events(id = 1416, component = 11, from = 200, to = 200, mask = 2097152)
        }
        interfaces.text(id = 1416, component = 6, text = "Adventure")
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(10, 1))
        client.write(ClientSetvarcSmall(id = 3497, value = 0))

        interfaces.open(id = 1519, parent = 1477, component = 497, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(27, 1))
        interfaces.open(id = 1588, parent = 1477, component = 327, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(28, 1))
        interfaces.open(id = 1678, parent = 1477, component = 338, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(29, 1))
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(30, 0))

        interfaces.open(id = 190, parent = 1477, component = 360, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 190, component = 5, from = 0, to = 312, mask = 14)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(31, 1))

        interfaces.open(id = 1854, parent = 1477, component = 371, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(32, 1))
        if (includeEvents) {
            interfaces.events(id = 1854, component = 6, from = 0, to = 4, mask = 66)
            interfaces.events(id = 1854, component = 5, from = 0, to = 1, mask = 2)
        }

        interfaces.open(id = 1894, parent = 1477, component = 382, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1894, component = 16, from = 0, to = 2, mask = 2)
            interfaces.events(id = 1894, component = 18, from = 0, to = 3, mask = 6)
            interfaces.events(id = 1894, component = 19, from = 0, to = 3, mask = 6)
        }
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(41, 1))

        client.traceBootstrap(
            "world-send-forced-fallback-utility-panel-deck name=$name " +
                "ids=550,1427,1110,590,1416,1519,1588,1678,190,1854,1894 " +
                "scripts=8862:14,15,16,9,10,27,28,29,30,31,32,41 varcs=1027,1034,3497"
        )
        if (!includeEvents) {
            client.traceBootstrap(
                "world-skip-forced-fallback-utility-panel-events name=$name count=19 reason=forced-map-build-fallback"
            )
        }
    }

    private fun openForcedFallbackSceneStartBridge(includeEvents: Boolean = true) {
        if (forcedFallbackSceneBridgeSent) {
            return
        }
        forcedFallbackSceneBridgeSent = true
        interfaces.open(id = 1431, parent = 1477, component = 59, walkable = true)
        interfaces.open(id = 568, parent = 1477, component = 638, walkable = true)
        interfaces.open(id = 1465, parent = 1477, component = 90, walkable = true)
        interfaces.open(id = 1919, parent = 1477, component = 91, walkable = true)
        client.traceBootstrap(
            "world-open-forced-fallback-scene-bridge name=$name ids=1431,568,1465,1919"
        )
        if (includeEvents) {
            interfaces.events(id = 1477, component = 60, from = 1, to = 1, mask = 2)
            interfaces.events(id = 1431, component = 0, from = 0, to = 46, mask = 6)
            interfaces.events(id = 568, component = 5, from = 0, to = 46, mask = 6)
            interfaces.events(id = 1477, component = 94, from = 1, to = 1, mask = 6)
        }
    }

    private fun sendForcedFallbackCompletionCompanions() {
        if (forcedMinimalInterfaceBootstrap) {
            client.traceBootstrap(
                "world-skip-forced-fallback-completion-companions name=$name " +
                    "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                    "reason=forced-map-build-fallback-minimal-bootstrap-active-guard"
            )
            return
        }

        interfaces.open(id = 1484, parent = 1477, component = 767, walkable = true)
        interfaces.hide(id = 1477, component = 593, hidden = false)
        interfaces.open(id = 1483, parent = 1477, component = 576, walkable = true)
        interfaces.open(id = 745, parent = 1477, component = 589, walkable = true)
        interfaces.open(id = 284, parent = 1477, component = 572, walkable = true)
        interfaces.open(id = 1213, parent = 1477, component = 619, walkable = true)
        interfaces.open(id = 1448, parent = 1477, component = 662, walkable = true)
        interfaces.open(id = 291, parent = 1477, component = 568, walkable = true)
        interfaces.events(id = 1477, component = 22, from = 65535, to = 65535, mask = 2097152)
        sendInterfaceBootstrapScript(script = 139, args = arrayOf(96796695))

        interfaces.open(id = 1488, parent = 1477, component = 760, walkable = true)
        interfaces.open(id = 1680, parent = 1477, component = 39, walkable = true)
        sendInterfaceBootstrapScript(script = 14150, args = arrayOf(5))
        interfaces.events(id = 1477, component = 15, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 1477, component = 15, from = 0, to = 41, mask = 2)
        interfaces.events(id = 1477, component = 840, from = 0, to = 1000, mask = 2)

        interfaces.open(id = 1847, parent = 1477, component = 856, walkable = true)
        interfaces.events(id = 1477, component = 856, from = 0, to = 0, mask = 2)

        interfaces.open(id = 635, parent = 1477, component = 615, walkable = true)
        interfaces.open(id = 1639, parent = 1477, component = 627, walkable = true)
        client.traceBootstrap(
            "world-send-forced-fallback-completion-companions name=$name " +
                "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150"
        )
    }

    private fun sendDeferredForcedFallbackCompletionCompanionsIfPending(
        reason: String,
        includeEvents: Boolean
    ): Boolean {
        if (!deferredForcedFallbackCompletionCompanionsPending) {
            return false
        }
        deferredForcedFallbackCompletionCompanionsPending = false
        interfaces.open(id = 1484, parent = 1477, component = 767, walkable = true)
        interfaces.hide(id = 1477, component = 593, hidden = false)
        interfaces.open(id = 1483, parent = 1477, component = 576, walkable = true)
        interfaces.open(id = 745, parent = 1477, component = 589, walkable = true)
        interfaces.open(id = 284, parent = 1477, component = 572, walkable = true)
        interfaces.open(id = 1213, parent = 1477, component = 619, walkable = true)
        interfaces.open(id = 1448, parent = 1477, component = 662, walkable = true)
        interfaces.open(id = 291, parent = 1477, component = 568, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1477, component = 22, from = 65535, to = 65535, mask = 2097152)
        }
        sendInterfaceBootstrapScript(script = 139, args = arrayOf(96796695))

        interfaces.open(id = 1488, parent = 1477, component = 760, walkable = true)
        interfaces.open(id = 1680, parent = 1477, component = 39, walkable = true)
        sendInterfaceBootstrapScript(script = 14150, args = arrayOf(5))
        if (includeEvents) {
            interfaces.events(id = 1477, component = 15, from = 65535, to = 65535, mask = 2)
            interfaces.events(id = 1477, component = 15, from = 0, to = 41, mask = 2)
            interfaces.events(id = 1477, component = 840, from = 0, to = 1000, mask = 2)
        }

        interfaces.open(id = 1847, parent = 1477, component = 856, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1477, component = 856, from = 0, to = 0, mask = 2)
        }

        interfaces.open(id = 635, parent = 1477, component = 615, walkable = true)
        interfaces.open(id = 1639, parent = 1477, component = 627, walkable = true)
        client.traceBootstrap(
            "world-send-deferred-forced-fallback-completion-companions name=$name " +
                "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                "reason=$reason"
        )
        return true
    }

    private fun sendDeferredForcedFallbackCompletionStructureIfNeeded(
        reason: String,
        includeEvents: Boolean
    ): Boolean {
        if (deferredForcedFallbackCompletionStructureSent) {
            if (!deferredForcedFallbackCompletionCompanionsPending) {
                client.traceBootstrap(
                    "world-skip-forced-fallback-completion-companions-duplicate name=$name " +
                        "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                        "reason=already-sent-pre-ready"
                )
            }
            return false
        }
        deferredForcedFallbackCompletionStructureSent = true

        interfaces.open(id = 1433, parent = 1477, component = 751, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1433, component = 6, from = 0, to = 6, mask = 2)
        }

        interfaces.open(id = 137, parent = 1477, component = 404, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 137, component = 85, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 137, component = 62, from = 0, to = 11, mask = 126)
            interfaces.events(id = 137, component = 65, from = 0, to = 8, mask = 126)
            interfaces.events(id = 137, component = 59, from = 0, to = 2, mask = 2)
        }

        interfaces.open(id = 1467, parent = 1477, component = 415, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1467, component = 192, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 1467, component = 179, from = 0, to = 11, mask = 126)
            interfaces.events(id = 1467, component = 183, from = 0, to = 8, mask = 126)
            interfaces.events(id = 1467, component = 185, from = 0, to = 2, mask = 2)
        }

        interfaces.open(id = 1472, parent = 1477, component = 425, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1472, component = 193, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 1472, component = 186, from = 0, to = 11, mask = 126)
            interfaces.events(id = 1472, component = 190, from = 0, to = 8, mask = 126)
            interfaces.events(id = 1472, component = 192, from = 0, to = 2, mask = 2)
        }

        interfaces.open(id = 1471, parent = 1477, component = 435, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1471, component = 193, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 1471, component = 180, from = 0, to = 11, mask = 126)
            interfaces.events(id = 1471, component = 184, from = 0, to = 8, mask = 126)
            interfaces.events(id = 1471, component = 186, from = 0, to = 2, mask = 2)
        }

        interfaces.open(id = 1470, parent = 1477, component = 445, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1470, component = 193, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 1470, component = 180, from = 0, to = 11, mask = 126)
            interfaces.events(id = 1470, component = 184, from = 0, to = 8, mask = 126)
            interfaces.events(id = 1470, component = 186, from = 0, to = 2, mask = 2)
        }

        interfaces.open(id = 464, parent = 1477, component = 455, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 464, component = 193, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 464, component = 180, from = 0, to = 11, mask = 126)
            interfaces.events(id = 464, component = 184, from = 0, to = 8, mask = 126)
            interfaces.events(id = 464, component = 186, from = 0, to = 2, mask = 2)
        }

        interfaces.open(id = 1529, parent = 1477, component = 465, walkable = true)
        if (includeEvents) {
            interfaces.events(id = 1529, component = 192, from = 0, to = 99, mask = 1792)
            interfaces.events(id = 1529, component = 179, from = 0, to = 11, mask = 126)
            interfaces.events(id = 1529, component = 183, from = 0, to = 8, mask = 126)
            interfaces.events(id = 1529, component = 185, from = 0, to = 2, mask = 2)
        }

        if (sendDeferredForcedFallbackCompletionCompanionsIfPending(reason = reason, includeEvents = includeEvents)) {
            client.traceBootstrap(
                "world-send-deferred-completion-structure name=$name " +
                    "ids=1433,137,1467,1472,1471,1470,464,1529,1431,568,1465,1919,1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639"
            )
        } else {
            client.traceBootstrap(
                "world-skip-forced-fallback-completion-companions-duplicate name=$name " +
                    "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                    "reason=already-sent-pre-ready"
            )
            client.traceBootstrap(
                "world-send-deferred-completion-structure name=$name " +
                    "ids=1433,137,1467,1472,1471,1470,464,1529,1431,568,1465,1919"
            )
        }
        return true
    }

    private fun sendForcedFallbackDeferredCompletionScriptsIfNeeded(): Boolean {
        if (deferredForcedFallbackDeferredScriptsSent) {
            return false
        }
        deferredForcedFallbackDeferredScriptsSent = true

        if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionScripts) {
            deferredForcedFallbackCoreScriptsPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-deferred-completion-scripts name=$name " +
                    "scripts=8862,2651,7486,10903,8778 reason=forced-map-build-fallback until=final-late-ready"
            )
            deferredForcedFallbackLiteTailPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-deferred-completion-lite-tail name=$name " +
                    "scripts=4704,4308 texts=187:7,1416:6 reason=forced-map-build-fallback until=final-late-ready"
            )
            deferredForcedFallback10623BatchPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-deferred-completion-10623-batch name=$name " +
                    "scripts=10623:30522,30758,30759,30821,30828,30964,31386,31562,31918 " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
            return true
        }
        if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionLiteScripts) {
            deferredForcedFallbackCoreScriptsPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-deferred-completion-scripts name=$name " +
                    "scripts=8862,2651,7486,10903,8778 reason=forced-map-build-fallback until=final-late-ready"
            )
            deferredForcedFallbackLiteTailPending = true
            client.traceBootstrap(
                "world-defer-forced-fallback-deferred-completion-lite-tail name=$name " +
                    "scripts=4704,4308 texts=187:7,1416:6 reason=forced-map-build-fallback until=final-late-ready"
            )
            return true
        }
        if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletion10623Batch) {
            client.traceBootstrap(
                "world-skip-forced-fallback-deferred-completion-scripts name=$name count=10 " +
                    "scripts=10623 reason=forced-map-build-fallback"
            )
            return false
        }
        if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionCoreScripts) {
            client.traceBootstrap(
                "world-skip-forced-fallback-deferred-completion-scripts name=$name count=5 " +
                    "scripts=8862,2651,8778 reason=forced-map-build-fallback"
            )
            return false
        }
        client.traceBootstrap("world-skip-deferred-completion-scripts name=$name")
        return false
    }

    private fun sendDeferredLateWorldCompletionTail() {
        val forcedFallbackDeferredTail =
            deferredForcedFallbackSupplementalChildrenPending || deferredForcedFallbackLightInterfaceTailPending
        val includeForcedFallbackEvents = !forcedFallbackDeferredTail
        if (deferredForcedFallbackSupplementalChildrenPending) {
            client.traceBootstrap(
                "world-keep-forced-fallback-supplemental-children-deferred name=$name " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        }
        if (deferredForcedFallbackLightInterfaceTailPending) {
            client.traceBootstrap(
                "world-keep-forced-fallback-light-tail-deferred name=$name " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        }
        if (deferredForcedFallbackRestoredWorldPanelsPending) {
            client.traceBootstrap(
                "world-keep-forced-fallback-restored-world-panels-deferred name=$name " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        } else {
            openForcedFallbackRestoredWorldPanels()
        }
        if (deferredForcedFallbackUtilityPanelDeckPending) {
            client.traceBootstrap(
                "world-keep-forced-fallback-utility-panel-deck-deferred name=$name " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        } else {
            openForcedFallbackUtilityPanelDeck(includeEvents = includeForcedFallbackEvents)
        }
        if (deferredForcedFallbackSceneBridgePending) {
            client.traceBootstrap(
                "world-keep-forced-fallback-scene-bridge-deferred name=$name " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        } else {
            openForcedFallbackSceneStartBridge(includeEvents = includeForcedFallbackEvents)
        }
        if (deferredForcedFallbackCompletionStructurePending) {
            client.traceBootstrap(
                "world-keep-forced-fallback-completion-structure-deferred name=$name " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        } else {
            sendDeferredForcedFallbackCompletionStructureIfNeeded(
                reason = "forced-map-build-fallback-post-ready",
                includeEvents = includeForcedFallbackEvents
            )
        }
        if (forcedFallbackDeferredTail) {
            sendForcedFallbackDeferredCompletionScriptsIfNeeded()
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionScripts) {
            client.traceBootstrap(
                "world-send-deferred-completion-scripts name=$name " +
                    "scripts=8862,2651,7486,10903,8778,4704,4308,10623"
            )
            sendDeferredCompletionLiteScripts()
            for (scriptArg in listOf(30522, 30758, 30759, 30821, 30828, 30964, 31386, 31562, 31918, 39392)) {
                client.write(RunClientScript(script = 10623, args = arrayOf(scriptArg, 0)))
            }
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionLiteScripts) {
            client.traceBootstrap(
                "world-send-deferred-completion-lite-scripts name=$name " +
                    "scripts=8862,2651,7486,10903,8778,4704,4308"
            )
            sendDeferredCompletionLiteScripts()
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletion10623Batch) {
            client.traceBootstrap(
                "world-send-deferred-completion-10623-batch name=$name " +
                    "scripts=10623:30522,30758,30759,30821,30828,30964,31386,31562,31918,39392"
            )
            for (scriptArg in listOf(30522, 30758, 30759, 30821, 30828, 30964, 31386, 31562, 31918, 39392)) {
                client.write(RunClientScript(script = 10623, args = arrayOf(scriptArg, 0)))
            }
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionCoreScripts) {
            client.traceBootstrap(
                "world-send-deferred-completion-core-scripts name=$name " +
                    "scripts=8862:1025,2651:1025,8862:1031,2651:1031,8778"
            )
            client.write(RunClientScript(script = 8862, args = arrayOf(1025, 1)))
            client.write(RunClientScript(script = 2651, args = arrayOf(1025, 0)))
            client.write(RunClientScript(script = 8862, args = arrayOf(1031, 1)))
            client.write(RunClientScript(script = 2651, args = arrayOf(1031, 0)))
            client.write(RunClientScript(script = 8778))
        } else {
            client.traceBootstrap("world-skip-deferred-completion-scripts name=$name")
        }

        if (forcedFallbackDeferredTail && OpenNXT.config.lobbyBootstrap.sendLateRootInterfaceEvents) {
            deferredLateRootInterfaceEventsPending = true
            client.traceBootstrap(
                "world-defer-late-root-interface-events name=$name parent=1477 count=390 " +
                    "reason=forced-map-build-fallback until=final-late-ready"
            )
        } else {
            sendLateRootInterfaceEventsIfConfigured()
        }

        if (forcedFallbackDeferredTail && OpenNXT.config.lobbyBootstrap.sendInterfaceBootstrapAnnouncementScripts) {
            deferredAnnouncementScriptsPending = true
            client.traceBootstrap(
                "world-defer-deferred-completion-announcement-scripts name=$name count=2 " +
                    "scripts=1264,3529 reason=forced-map-build-fallback until=final-late-ready"
            )
        } else {
            sendDeferredCompletionAnnouncementScripts()
        }

        if (forcedFallbackDeferredTail) {
            client.traceBootstrap(
                "world-skip-forced-fallback-deferred-completion-events name=$name count=34 reason=forced-map-build-fallback"
            )
            if (OpenNXT.config.lobbyBootstrap.sendSocialInitPackets) {
                deferredSceneStartEventDeltaPending = true
                deferredSceneStartLightTailScriptsPending = true
                deferredSceneStartFinalEventDeltaPending = true
                client.traceBootstrap(
                    "world-defer-deferred-completion-event-delta name=$name " +
                        "reason=forced-map-build-fallback until=scene-start-control-50"
                )
            } else {
                client.traceBootstrap(
                    "world-skip-deferred-completion-event-delta name=$name reason=social-init-disabled"
                )
            }
        } else if (OpenNXT.config.lobbyBootstrap.sendSocialInitPackets) {
            sendDeferredLateWorldCompletionEventDelta()
            client.traceBootstrap(
                "world-send-deferred-completion-event-delta name=$name " +
                    "groups=1430,1670,1671,1673,slot-panels count=133"
            )
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionEventDelta) {
            client.traceBootstrap(
                "world-skip-deferred-completion-event-delta name=$name reason=social-init-disabled"
            )
        }

        client.traceBootstrap(
            "world-send-deferred-completion-tail name=$name " +
                "ids=1433,137,1467,1472,1471,1470,464,1529,1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639"
        )
    }

    private fun sendDeferredCompletionLiteScripts(includeTail: Boolean = true) {
        client.write(RunClientScript(script = 8862, args = arrayOf(1025, 1)))
        client.write(RunClientScript(script = 2651, args = arrayOf(1025, 0)))
        client.write(RunClientScript(script = 7486, args = arrayOf(27066179, 41615368)))
        client.write(RunClientScript(script = 10903))
        client.write(RunClientScript(script = 8862, args = arrayOf(1031, 1)))
        client.write(RunClientScript(script = 2651, args = arrayOf(1031, 0)))
        client.write(RunClientScript(script = 8778))
        if (includeTail) {
            sendDeferredCompletionLiteTail()
        }
    }

    private fun sendDeferredCompletionLiteTail() {
        interfaces.text(id = 187, component = 7, text = "")
        interfaces.text(id = 1416, component = 6, text = "")
        client.write(RunClientScript(script = 4704))
        client.write(RunClientScript(script = 4308, args = arrayOf(18, 0)))
    }

    private fun sendDeferredCompletion10623Batch() {
        for (scriptArg in listOf(30522, 30758, 30759, 30821, 30828, 30964, 31386, 31562, 31918)) {
            client.write(RunClientScript(script = 10623, args = arrayOf(scriptArg, 0)))
        }
    }

    private fun sendDeferredCompletionFinalMiniTail() {
        interfaces.hide(id = 1477, component = 555, hidden = false)
        interfaces.hide(id = 745, component = 5, hidden = true)
        client.write(RunClientScript(script = 5559, args = arrayOf(0)))
        client.write(RunClientScript(script = 10623, args = arrayOf(39392, 0)))
        client.write(RunClientScript(script = 3957))
        interfaces.text(id = 187, component = 7, text = "Harmony")
        interfaces.text(id = 1416, component = 6, text = "Harmony")
    }

    private fun sendDeferredCompletionFullScripts() {
        sendDeferredCompletionLiteScripts()
        sendDeferredCompletion10623Batch()
        sendDeferredCompletionFinalMiniTail()
    }

    private fun sendLateRootInterfaceEventsIfConfigured(): Boolean {
        val bootstrap = OpenNXT.config.lobbyBootstrap
        if (!bootstrap.sendLateRootInterfaceEvents) {
            client.traceBootstrap("world-skip-late-root-interface-events name=$name parent=1477")
            return false
        }

        val tripleRangeComponents = intArrayOf(58, 64, 69, 74, 79, 84)
        val quadRangeComponents = intArrayOf(
            47, 93, 101, 112, 123, 134, 145, 156, 167, 178, 189, 200, 211, 222, 233, 244, 255,
            266, 276, 287, 298, 309, 320, 330, 341, 352, 363, 374, 385, 396, 407, 417, 427, 437,
            447, 457, 467, 478, 489, 500, 511, 522, 569, 573, 596, 604, 612, 643, 653
        )
        val singleActionComponents = intArrayOf(
            102, 113, 124, 135, 146, 157, 168, 179, 190, 201, 212, 223, 234, 245, 256, 267, 278,
            288, 299, 310, 335, 346, 357, 368, 379, 390, 397, 408, 418, 428, 438, 448, 458, 468,
            479, 490, 501, 512, 523, 664, 689
        )
        val pairedRangeComponents = intArrayOf(
            532, 540, 544, 548, 552, 556, 561, 565, 577, 582, 586, 590, 600, 608, 616, 620, 624,
            628, 632, 659, 668, 674, 678, 683, 698, 768
        )
        val rootMaskComponents = intArrayOf(
            24, 56, 62, 67, 72, 77, 82, 87, 96, 107, 118, 129, 140, 151, 162, 173, 184, 195, 206,
            217, 228, 239, 250, 261, 272, 282, 293, 304, 315, 325, 336, 347, 358, 369, 380, 391,
            402, 413, 423, 433, 443, 453, 463, 473, 484, 495, 506, 517, 655, 684
        )

        tripleRangeComponents.forEach { component ->
            interfaces.events(id = 1477, component = component, from = 1, to = 7, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 11, to = 13, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 0, to = 0, mask = 9175040)
        }

        rootMaskComponents.forEach { component ->
            interfaces.events(id = 1477, component = component, from = 65535, to = 65535, mask = 2097152)
        }

        quadRangeComponents.forEach { component ->
            interfaces.events(id = 1477, component = component, from = 1, to = 7, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 11, to = 13, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 0, to = 0, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 3, to = 4, mask = 9175040)
        }

        singleActionComponents.forEach { component ->
            interfaces.events(id = 1477, component = component, from = 1, to = 1, mask = 2)
        }

        pairedRangeComponents.forEach { component ->
            interfaces.events(id = 1477, component = component, from = 1, to = 2, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 0, to = 0, mask = 9175040)
            interfaces.events(id = 1477, component = component, from = 3, to = 4, mask = 9175040)
        }

        interfaces.events(id = 1477, component = 688, from = 0, to = 0, mask = 9175040)
        interfaces.events(id = 1477, component = 648, from = 1, to = 2, mask = 9175040)
        interfaces.events(id = 1477, component = 648, from = 6, to = 7, mask = 9175040)
        interfaces.events(id = 1477, component = 648, from = 11, to = 11, mask = 9175040)
        interfaces.events(id = 1477, component = 648, from = 13, to = 13, mask = 9175040)
        interfaces.events(id = 1477, component = 648, from = 0, to = 0, mask = 9175040)
        interfaces.events(id = 1477, component = 648, from = 3, to = 4, mask = 9175040)

        client.traceBootstrap("world-send-late-root-interface-events name=$name parent=1477 count=390")
        return true
    }

    private fun sendDeferredCompletionAnnouncementScripts() {
        val bootstrap = OpenNXT.config.lobbyBootstrap
        if (!bootstrap.sendInterfaceBootstrapAnnouncementScripts) {
            client.traceBootstrap("world-skip-deferred-completion-announcement-scripts name=$name reason=announcement-disabled")
            return
        }
        sendInterfaceBootstrapScript(
            script = 1264,
            args = arrayOf(
                "PMod PvM Event",
                "Friday 18th June, 20:00 Game Time",
                "Nex: Angel of Death boss mass",
                "",
                "Nex lobby, God Wars Dungeon",
                "w88",
                "Pippyspot & Boss Guild",
                "Boss Guild",
                "",
                "",
                1321
            )
        )
        sendInterfaceBootstrapScript(script = 3529)
        client.traceBootstrap("world-send-deferred-completion-announcement-scripts name=$name scripts=1264,3529")
    }

    private fun sendDeferredLateWorldCompletionEventDelta() {
        interfaces.events(id = 1477, component = 66, from = 1, to = 1, mask = 4)

        listOf(64, 69).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 11239422)
        }
        listOf(77, 82, 90, 95, 103, 108, 116, 121, 129, 134, 142, 147, 155, 160, 168, 173, 181, 186, 194, 199, 207, 212, 233, 238).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 2098176)
        }
        listOf(220, 225).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 11239422)
        }
        listOf(17, 22).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 8388608)
        }
        interfaces.events(id = 1430, component = 11, from = 65535, to = 65535, mask = 8650758)
        listOf(16, 254).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 2046)
        }
        interfaces.events(id = 1430, component = 253, from = 65535, to = 65535, mask = 0)
        interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 0)
        interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 1465, component = 15, from = 65535, to = 65535, mask = 8388608)

        listOf(
            18, 23, 31, 36, 44, 49, 57, 62, 70, 75, 83, 88, 96, 101,
            109, 114, 122, 127, 135, 140, 148, 153, 161, 166, 174, 179, 187, 192
        ).forEach { component ->
            interfaces.events(id = 1670, component = component, from = 65535, to = 65535, mask = 2098176)
        }
        listOf(
            13, 18, 26, 31, 39, 44, 52, 57, 65, 70, 78, 83, 91, 96,
            104, 109, 117, 122, 130, 135, 143, 148, 156, 161, 169, 174, 182, 187
        ).forEach { component ->
            interfaces.events(id = 1671, component = component, from = 65535, to = 65535, mask = 2098176)
            interfaces.events(id = 1673, component = component, from = 65535, to = 65535, mask = 2098176)
        }

        listOf(1460, 1881, 1888).forEach { id ->
            interfaces.events(id = id, component = 1, from = 0, to = 211, mask = 8592390)
        }
        listOf(1452, 1883, 1449, 1882).forEach { id ->
            interfaces.events(id = id, component = 1, from = 0, to = 211, mask = 8616966)
        }
        listOf(1461, 1884, 1885, 1886).forEach { id ->
            interfaces.events(id = id, component = 1, from = 0, to = 211, mask = 8617038)
        }
    }

    private fun sendDeferredSceneStartEventDelta() {
        interfaces.events(id = 1477, component = 66, from = 1, to = 1, mask = 4)
        listOf(64, 69).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 11239422)
        }
        listOf(17, 22).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 8388608)
        }
        interfaces.events(id = 1430, component = 11, from = 65535, to = 65535, mask = 8650758)
        listOf(16, 254).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 2046)
        }
        interfaces.events(id = 1430, component = 253, from = 65535, to = 65535, mask = 0)
        interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 0)
        interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 2)
    }

    private fun sendDeferredSceneStartTabbedEventDelta() {
        listOf(
            18, 23, 31, 36, 44, 49, 57, 62, 70, 75, 83, 88, 96, 101,
            109, 114, 122, 127, 135, 140, 148, 153, 161, 166, 174, 179, 187, 192
        ).forEach { component ->
            interfaces.events(id = 1670, component = component, from = 65535, to = 65535, mask = 2098176)
        }
        listOf(
            13, 18, 26, 31, 39, 44, 52, 57, 65, 70, 78, 83, 91, 96,
            104, 109, 117, 122, 130, 135, 143, 148, 156, 161, 169, 174, 182, 187
        ).forEach { component ->
            interfaces.events(id = 1671, component = component, from = 65535, to = 65535, mask = 2098176)
            interfaces.events(id = 1673, component = component, from = 65535, to = 65535, mask = 2098176)
        }
    }

    private fun sendDeferredSceneStartLightTailScripts() {
        sendInterfaceBootstrapScript(script = 11145, args = arrayOf(1067, 600, 0, 0, 96797408))
        sendInterfaceBootstrapScript(script = 8420, args = arrayOf(-1, 96797410, 96797411, -1, "", 21259, 1007))
        sendInterfaceBootstrapScript(script = 11145, args = arrayOf(1067, 600, 0, 0, 96797413))
        sendInterfaceBootstrapScript(script = 8420, args = arrayOf(-1, 96797415, 96797416, -1, "", 21259, 1007))
        sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1032))
        sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1033))
        sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1035))
    }

    private fun sendDeferredSceneStartFinalEventDelta() {
        listOf(77, 82, 90, 95, 103, 108, 116, 121, 129, 134, 142, 147, 155, 160, 168, 173, 181, 186, 194, 199, 207, 212, 233, 238).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 2098176)
        }
        listOf(220, 225).forEach { component ->
            interfaces.events(id = 1430, component = component, from = 65535, to = 65535, mask = 11239422)
        }
        interfaces.events(id = 1465, component = 15, from = 65535, to = 65535, mask = 8388608)

        listOf(1460, 1881, 1888).forEach { id ->
            interfaces.events(id = id, component = 1, from = 0, to = 211, mask = 8592390)
        }
        listOf(1452, 1883, 1449, 1882).forEach { id ->
            interfaces.events(id = id, component = 1, from = 0, to = 211, mask = 8616966)
        }
        listOf(1461, 1884, 1885, 1886).forEach { id ->
            interfaces.events(id = id, component = 1, from = 0, to = 211, mask = 8617038)
        }
    }

    private fun sendForcedFallbackSupplementalInterfaceEvents() {
        interfaces.events(id = 1466, component = 7, from = 0, to = 28, mask = 30)
        interfaces.events(id = 1473, component = 7, from = 65535, to = 65535, mask = 2097152)
        interfaces.events(id = 1473, component = 7, from = 0, to = 27, mask = 15302030)
        interfaces.events(id = 1473, component = 25, from = 0, to = 16, mask = 1422)
        interfaces.events(id = 1473, component = 1, from = 0, to = 5, mask = 2099198)
        interfaces.events(id = 1473, component = 28, from = 0, to = 5, mask = 2099198)
    }

    private fun sendForcedFallbackLightTailEvents() {
        interfaces.events(id = 634, component = 152, from = 65535, to = 65535, mask = 1022)
        interfaces.events(id = 634, component = 265, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 634, component = 67, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 634, component = 68, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 634, component = 138, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 634, component = 139, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 634, component = 2, from = 65535, to = 65535, mask = 2)

        interfaces.events(id = 653, component = 155, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 166, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 177, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 188, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 199, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 210, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 221, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 232, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 243, from = 0, to = 500, mask = 62)
        interfaces.events(id = 653, component = 254, from = 0, to = 500, mask = 62)
    }

    private fun sendForcedFallbackCompletionCompanionEvents() {
        interfaces.events(id = 1477, component = 22, from = 65535, to = 65535, mask = 2097152)
        interfaces.events(id = 1477, component = 15, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 1477, component = 15, from = 0, to = 41, mask = 2)
        interfaces.events(id = 1477, component = 840, from = 0, to = 1000, mask = 2)
        interfaces.events(id = 1477, component = 856, from = 0, to = 0, mask = 2)
    }

    private fun sendForcedFallbackCompletionStructureEvents() {
        interfaces.events(id = 1433, component = 6, from = 0, to = 6, mask = 2)

        interfaces.events(id = 137, component = 85, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 137, component = 62, from = 0, to = 11, mask = 126)
        interfaces.events(id = 137, component = 65, from = 0, to = 8, mask = 126)
        interfaces.events(id = 137, component = 59, from = 0, to = 2, mask = 2)

        interfaces.events(id = 1467, component = 192, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 1467, component = 179, from = 0, to = 11, mask = 126)
        interfaces.events(id = 1467, component = 183, from = 0, to = 8, mask = 126)
        interfaces.events(id = 1467, component = 185, from = 0, to = 2, mask = 2)

        interfaces.events(id = 1472, component = 193, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 1472, component = 186, from = 0, to = 11, mask = 126)
        interfaces.events(id = 1472, component = 190, from = 0, to = 8, mask = 126)
        interfaces.events(id = 1472, component = 192, from = 0, to = 2, mask = 2)

        interfaces.events(id = 1471, component = 193, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 1471, component = 180, from = 0, to = 11, mask = 126)
        interfaces.events(id = 1471, component = 184, from = 0, to = 8, mask = 126)
        interfaces.events(id = 1471, component = 186, from = 0, to = 2, mask = 2)

        interfaces.events(id = 1470, component = 193, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 1470, component = 180, from = 0, to = 11, mask = 126)
        interfaces.events(id = 1470, component = 184, from = 0, to = 8, mask = 126)
        interfaces.events(id = 1470, component = 186, from = 0, to = 2, mask = 2)

        interfaces.events(id = 464, component = 193, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 464, component = 180, from = 0, to = 11, mask = 126)
        interfaces.events(id = 464, component = 184, from = 0, to = 8, mask = 126)
        interfaces.events(id = 464, component = 186, from = 0, to = 2, mask = 2)

        interfaces.events(id = 1529, component = 192, from = 0, to = 99, mask = 1792)
        interfaces.events(id = 1529, component = 179, from = 0, to = 11, mask = 126)
        interfaces.events(id = 1529, component = 183, from = 0, to = 8, mask = 126)
        interfaces.events(id = 1529, component = 185, from = 0, to = 2, mask = 2)
    }

    private fun sendForcedFallbackCompletionCompanionReplayAfterLateReady() {
        interfaces.open(id = 1484, parent = 1477, component = 767, walkable = true)
        interfaces.hide(id = 1477, component = 593, hidden = false)
        interfaces.open(id = 1483, parent = 1477, component = 576, walkable = true)
        interfaces.open(id = 745, parent = 1477, component = 589, walkable = true)
        interfaces.open(id = 284, parent = 1477, component = 572, walkable = true)
        interfaces.open(id = 1213, parent = 1477, component = 619, walkable = true)
        interfaces.open(id = 1448, parent = 1477, component = 662, walkable = true)
        interfaces.open(id = 291, parent = 1477, component = 568, walkable = true)
        interfaces.events(id = 1477, component = 22, from = 65535, to = 65535, mask = 2097152)
        sendInterfaceBootstrapScript(script = 139, args = arrayOf(96796695))

        interfaces.open(id = 1488, parent = 1477, component = 760, walkable = true)
        interfaces.open(id = 1680, parent = 1477, component = 39, walkable = true)
        sendInterfaceBootstrapScript(script = 14150, args = arrayOf(5))
        interfaces.events(id = 1477, component = 15, from = 65535, to = 65535, mask = 2)
        interfaces.events(id = 1477, component = 15, from = 0, to = 41, mask = 2)
        interfaces.events(id = 1477, component = 840, from = 0, to = 1000, mask = 2)

        interfaces.open(id = 1847, parent = 1477, component = 856, walkable = true)
        interfaces.events(id = 1477, component = 856, from = 0, to = 0, mask = 2)

        interfaces.open(id = 635, parent = 1477, component = 615, walkable = true)
        interfaces.open(id = 1639, parent = 1477, component = 627, walkable = true)
        client.traceBootstrap(
            "world-send-forced-fallback-completion-companion-replay-after-late-ready name=$name " +
                "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
        )
    }

    private fun sendForcedFallbackLateReadyInterfaceReplayIfNeeded() {
        val forcedFallbackLateReadyReplayActive =
            forcedMinimalInterfaceBootstrap || forcedFallbackLateReadyInterfaceReplayArmed
        if (!forcedFallbackLateReadyReplayActive || forcedFallbackLateReadyInterfaceReplaySent) {
            return
        }
        forcedFallbackLateReadyInterfaceReplaySent = true
        forcedFallbackLateReadyInterfaceReplayArmed = false
        if (deferredForcedFallbackSelfModelBindPending) {
            deferredForcedFallbackSelfModelBindPending = false
            val selfModelComponent = OpenNXT.config.lobbyBootstrap.worldInterfaceSelfModelComponent
            if (selfModelComponent >= 0) {
                interfaces.setPlayerModelSelf(id = 1482, component = selfModelComponent)
                client.traceBootstrap(
                    "world-bind-local-player-model-after-late-ready name=$name id=1482 component=$selfModelComponent " +
                        "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
                )
            }
        }
        if (deferredForcedFallbackSupplementalChildrenPending) {
            deferredForcedFallbackSupplementalChildrenPending = false
            openForcedFallbackSupplementalWorldChildren(includeEvents = false)
            client.traceBootstrap(
                "world-send-forced-fallback-supplemental-children-after-late-ready name=$name " +
                    "ids=1466,1473 control50=${lastClientBootstrapControl50} " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
        }
        if (deferredForcedFallbackCompletionStructurePending) {
            if (!deferredForcedFallbackCompletionCompanionsPending) {
                deferredForcedFallbackCompletionCompanionsPending = true
            }
            deferredForcedFallbackCompletionStructurePending = false
            sendDeferredForcedFallbackCompletionStructureIfNeeded(
                reason = "forced-map-build-fallback-after-late-ready",
                includeEvents = false
            )
        }
        if (deferredForcedFallbackLightInterfaceTailPending) {
            deferredForcedFallbackLightInterfaceTailPending = false
            sendLightLateWorldInterfaceTail(includeEvents = false, includeScripts = false)
            client.traceBootstrap(
                "world-send-forced-fallback-light-tail-after-late-ready name=$name " +
                    "ids=634,653,1430,1670,1671,1673 " +
                    "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
        }
        sendForcedFallbackSupplementalInterfaceEvents()
        client.traceBootstrap(
            "world-send-forced-fallback-supplemental-events-after-late-ready name=$name count=6 " +
                "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
        )
        sendForcedFallbackLightTailEvents()
        client.traceBootstrap(
            "world-send-forced-fallback-light-tail-events-after-late-ready name=$name count=17 " +
                "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
        )
        sendForcedFallbackCompletionStructureEvents()
        client.traceBootstrap(
            "world-send-forced-fallback-completion-structure-events-after-late-ready name=$name " +
                "components=1433,137,1467,1472,1471,1470,464,1529 count=29 " +
                "control50=${lastClientBootstrapControl50} acceptedCount=$lateSceneStartReadySignalsAccepted"
        )
        if (
            deferredForcedFallbackCompletionStructurePending ||
            deferredForcedFallbackCompletionCompanionsPending ||
            !deferredForcedFallbackCompletionStructureSent
        ) {
            sendForcedFallbackCompletionCompanionReplayAfterLateReady()
        } else {
            client.traceBootstrap(
                "world-skip-forced-fallback-completion-companion-replay-after-late-ready name=$name " +
                    "reason=already-sent-in-deferred-tail control50=${lastClientBootstrapControl50} " +
                    "acceptedCount=$lateSceneStartReadySignalsAccepted"
            )
        }
    }

    private fun sendDeferredLateWorldCompletionTailIfNeeded(): Boolean {
        if (!deferredLateWorldCompletionTailPending || !initialWorldSyncSent || postInitialWorldSyncHoldTicks > 0) {
            return false
        }
        closeForcedFallbackLoadingOverlayIfPending(reason = "forced-map-build-fallback-before-deferred-tail")
        deferredLateWorldCompletionTailPending = false
        client.traceBootstrap("world-send-deferred-completion-tail-after-sync name=$name reason=post-sync-hold-cleared")
        sendDeferredLateWorldCompletionTail()
        sendDeferredDefaultVarpsIfNeeded()
        return true
    }

    private fun closeLoadingOverlay(reason: String?) {
        interfaces.close(id = 1477, component = 508)
        val suffix = if (reason == null) "" else " reason=$reason"
        client.traceBootstrap("world-close-loading-overlay name=$name id=1417 parent=1477 component=508$suffix")
    }

    private fun closeForcedFallbackLoadingOverlayIfPending(reason: String): Boolean {
        if (!pendingForcedFallbackLoadingOverlayClose) {
            return false
        }
        if (lateSceneStartReadySignalsAccepted == 0 && deferredLateWorldCompletionTailPending) {
            client.traceBootstrap(
                "world-keep-loading-overlay-deferred name=$name id=1417 parent=1477 component=508 " +
                    "reason=$reason"
            )
            return false
        }
        pendingForcedFallbackLoadingOverlayClose = false
        if (!interfaces.isOpened(1417)) {
            client.write(IfCloseSub(InterfaceHash(1477, 508)))
            client.traceBootstrap(
                "world-force-close-loading-overlay name=$name id=1417 parent=1477 component=508 " +
                    "reason=$reason tracked=false"
            )
            return true
        }
        closeLoadingOverlay(reason = reason)
        return true
    }

    fun added() {
        logger.info { "Bootstrapping world player $name" }
        client.traceBootstrap("world-added name=$name")
        client.processUnidentifiedPackets = true
        client.currentBootstrapStage = null
        client.lastCompletedBootstrapStage = null
        client.completedBootstrapStages.clear()
        pendingWorldReadySignal = null
        pendingServerpermDelayedReadySignal = null
        awaitingWorldReadySignal = false
        worldReadyWaitTicks = 0
        playerInfoDelayTicks = 0
        initialWorldSyncSent = false
        worldSyncFramesSent = 0
        sceneStartSyncBurstTicks = 0
        forcedLocalAppearanceRefreshFrames = 0
        deferredSceneStartEventDeltaPending = false
        deferredSceneStartTabbedEventDeltaPending = false
        deferredSceneStartLightTailScriptsPending = false
        deferredSceneStartFinalEventDeltaPending = false
        deferredLateRootInterfaceEventsPending = false
        deferredAnnouncementScriptsPending = false
        deferredForcedFallback10623BatchPending = false
        forcedFallbackLateReadyInterfaceReplaySent = false
        forcedFallbackLateReadyInterfaceReplayArmed = false
        deferredForcedFallbackSelfModelBindPending = false
        awaitingLateSceneStartReadySignal = false
        lateSceneStartReadySignalsAccepted = 0
        postInitialWorldSyncHoldTicks = 0
        postInitialWorldSyncHoldForcedFallback = false
        postInitialWorldSyncHoldSendFrames = false
        compatServerpermAckCount = 0
        deferredDefaultVarpsPending = false
        deferredLateWorldCompletionTailPending = false
        deferredForcedFallbackSupplementalChildrenPending = false
        deferredForcedFallbackLightInterfaceTailPending = false
        deferredForcedFallbackCompletionCompanionsPending = false
        deferredForcedFallbackCompletionStructurePending = false
        deferredForcedFallbackRestoredWorldPanelsPending = false
        deferredForcedFallbackUtilityPanelDeckPending = false
        deferredForcedFallbackSceneBridgePending = false
        forcedFallbackPreDeferredFamiliesPrimed = false
        deferredForcedFallbackCompletionStructureSent = false
        deferredForcedFallbackDeferredScriptsSent = false
        deferredForcedFallbackCoreScriptsPending = false
        deferredForcedFallbackLiteTailPending = false
        skipPostInitialSyncHoldForForcedFallback = false
        pendingForcedFallbackLoadingOverlayClose = false
        forcedMapBuildFallbackPending = false
        forcedMapBuildFallbackActive = false
        pendingServerpermMapBuildCompat = null
        forcedFallbackRestoredWorldPanelsSent = false
        forcedFallbackUtilityPanelDeckSent = false
        forcedFallbackSceneBridgeSent = false
        lastClientDisplayState106 = null
        clearCompatMapBuildReadyFallback()
        var stage = "appearance"
        try {
        runBootstrapStage(stage) {
            entity.model.refresh()
        }

        if (entryMode == EntryMode.FULL_LOGIN) {
            stage = "login-response"
            runBootstrapStage(stage) {
                client.channel.write(Unpooled.buffer(1).writeByte(GenericResponse.SUCCESSFUL.id))
                client.channel.writeAndFlush(
                    LoginPacket.GameLoginResponse(
                        byte0 = 0,
                        rights = 0,
                        byte2 = 0,
                        byte3 = 0,
                        byte4 = 0,
                        byte5 = 0,
                        byte6 = 0,
                        playerIndex = entity.index,
                        byte8 = 1,
                        medium9 = 0,
                        isMember = 1,
                        username = name,
                        short12 = 0,
                        int13 = 0
                    )
                )
            }

            stage = "pipeline-switch"
            runBootstrapStage(stage) {
                val pipeline = client.channel.pipeline()

                if (pipeline.context("game-decoder") == null) {
                    if (pipeline.context("login-decoder") != null) {
                        pipeline.replace("login-decoder", "game-decoder", GamePacketFraming())
                    } else {
                        logger.warn { "Game decoder missing during world pipeline switch for $name; adding it directly" }
                        if (pipeline.context("transport-sniffer") != null) {
                            pipeline.addAfter("transport-sniffer", "game-decoder", GamePacketFraming())
                        } else {
                            pipeline.addLast("game-decoder", GamePacketFraming())
                        }
                    }
                }

                if (pipeline.context("game-encoder") == null) {
                    if (pipeline.context("login-encoder") != null) {
                        pipeline.replace("login-encoder", "game-encoder", GamePacketEncoder())
                    } else {
                        logger.warn { "Game encoder missing during world pipeline switch for $name; adding it directly" }
                        pipeline.addLast("game-encoder", GamePacketEncoder())
                    }
                }

                if (pipeline.context("game-handler") == null) {
                    if (pipeline.context("login-handler") != null) {
                        pipeline.replace("login-handler", "game-handler", DynamicPacketHandler())
                    } else {
                        logger.warn { "Game handler missing during world pipeline switch for $name; adding it directly" }
                        pipeline.addLast("game-handler", DynamicPacketHandler())
                    }
                }
            }
        } else {
            client.traceBootstrap("world-skip-login-response name=$name reason=post-lobby-auth")
            client.traceBootstrap("world-skip-pipeline-switch name=$name reason=post-lobby-auth")
        }

        stage = "rebuild"
        runBootstrapStage(stage) {
            val rebuildRegistration = PacketRegistry.getRegistration(Side.SERVER, RebuildNormal::class)
            if (rebuildRegistration == null) {
                logger.warn {
                    "Skipping REBUILD_NORMAL for ${this.name}: packet is not mapped for build ${OpenNXT.config.build}"
                }
                awaitingMapBuildComplete = true
            } else {
                val rebuildPayload = Unpooled.buffer(5140)
                val rebuildBuilder = GamePacketBuilder(rebuildPayload)
                viewport.init(rebuildBuilder)
                val rebuildPacket = viewport.createPacket()
                client.traceBootstrap(
                    "world-send-rebuild-tail name=$name chunkX=${rebuildPacket.chunkX} " +
                        "chunkY=${rebuildPacket.chunkY} npcBits=${rebuildPacket.npcBits} " +
                        "mapSize=${rebuildPacket.mapSize} areaType=${rebuildPacket.areaType} " +
                        "hash1=${rebuildPacket.hash1} hash2=${rebuildPacket.hash2}"
                )
                @Suppress("UNCHECKED_CAST")
                (rebuildRegistration.codec as GamePacketCodec<GamePacket>).encode(rebuildPacket, rebuildBuilder)
                GoldenPacketSupport.traceSend(
                    channel = client.channel,
                    localSide = Side.SERVER,
                    registration = rebuildRegistration,
                    payload = ByteBufUtil.getBytes(rebuildPayload, 0, rebuildPayload.writerIndex(), false),
                    packet = rebuildPacket
                )
                client.write(UnidentifiedPacket(OpcodeWithBuffer(rebuildRegistration.opcode, rebuildPayload)))
                awaitingMapBuildComplete = PacketRegistry.getRegistration(Side.CLIENT, MapBuildComplete::class) != null
                if (entryMode == EntryMode.POST_LOBBY_AUTH && awaitingMapBuildComplete) {
                    logger.info {
                        "Allowing the contained post-lobby world bootstrap for $name to wait for the normal " +
                            "MAP_BUILD_COMPLETE/compat path after REBUILD_NORMAL before using the timed fallback"
                    }
                    client.traceBootstrap(
                        "world-allow-map-build-complete-wait name=$name reason=post-lobby-auth-normal-bootstrap"
                    )
                }
            }
        }

        val player = this
        val bootstrap = OpenNXT.config.lobbyBootstrap
        deferredBootstrap = {
        stage = "stats"
        runBootstrapStage(stage) {
            if (forcedMinimalInterfaceBootstrap) {
                logger.info {
                    "Skipping world stats init for $name because forced MAP_BUILD fallback is using the minimal interface bootstrap"
                }
                client.traceBootstrap(
                    "world-skip-stats name=$name reason=forced-map-build-fallback-minimal-bootstrap"
                )
                return@runBootstrapStage
            }
            if (!bootstrap.sendWorldInitState) {
                logger.info { "Skipping world stats init for $name because sendWorldInitState=false" }
                client.traceBootstrap("world-skip-stats name=$name")
                return@runBootstrapStage
            }
            client.traceBootstrap("world-init-stats name=$name")
            stats.init()
        }
        stage = "default-state"
        runBootstrapStage(stage) {
            if (forcedMinimalInterfaceBootstrap) {
                if (!bootstrap.sendWorldInitState) {
                    logger.info {
                        "Forced MAP_BUILD fallback is overriding sendWorldInitState=false for $name " +
                            "to preserve ResetClientVarcache/default-varp scene bootstrap"
                    }
                    client.traceBootstrap(
                        "world-force-init-state-reset name=$name reason=forced-map-build-fallback-minimal-bootstrap " +
                            "override=sendWorldInitState=false"
                    )
                }
                // Keep the compat fallback narrow, but still restore the client-state reset
                // and deferred varp burst that the stable world path expects.
                client.write(ResetClientVarcache)
                client.traceBootstrap(
                    "world-send-reset-client-varcache name=$name reason=forced-map-build-fallback-minimal-bootstrap"
                )
                if (bootstrap.sendDefaultVarps) {
                    deferredDefaultVarpsPending = true
                    client.traceBootstrap(
                        "world-defer-default-varps name=$name reason=forced-map-build-fallback-minimal-bootstrap"
                    )
                } else {
                    logger.info { "Skipping world default varps for $name because sendDefaultVarps=false" }
                    client.traceBootstrap(
                        "world-skip-deferred-default-varps name=$name reason=forced-map-build-fallback-minimal-bootstrap"
                    )
                }
                client.traceBootstrap(
                    "world-skip-bootstrap-script name=$name script=671 stage=default-state " +
                        "reason=forced-map-build-fallback-minimal-bootstrap"
                )
                return@runBootstrapStage
            }
            if (!bootstrap.sendWorldInitState) {
                logger.info { "Skipping world init state for $name because sendWorldInitState=false" }
                client.traceBootstrap("world-skip-init-state name=$name")
                return@runBootstrapStage
            }
            client.write(ResetClientVarcache)
            client.traceBootstrap("world-send-reset-client-varcache name=$name")
            if (shouldQueueDeferredDefaultVarps("default-state")) {
                deferredDefaultVarpsPending = true
                client.traceBootstrap("world-defer-default-varps name=$name")
            } else {
                logger.info { "Skipping world default varps for $name due to bootstrap config" }
            }
            if (bootstrap.sendInterfaceBootstrapScripts) {
                client.write(RunClientScript(script = 671, args = arrayOf(0)))
            } else {
                client.traceBootstrap("world-skip-bootstrap-script name=$name script=671 stage=default-state")
            }
        }
        stage = "interfaces"
        runBootstrapStage(stage) {
            if (!bootstrap.openRootInterface) {
                logger.info { "Skipping world root/child interfaces for $name because openRootInterface=false" }
                return@runBootstrapStage
            }
            player.interfaces.openTop(id = 1477)
            if (forcedMinimalInterfaceBootstrap) {
                logger.info {
                    "Opening only the primary world child interface for $name because forced MAP_BUILD fallback " +
                        "is using the minimal interface bootstrap"
                }
                client.traceBootstrap(
                    "world-force-minimal-interface-bootstrap name=$name reason=forced-map-build-fallback"
                )
                player.interfaces.open(id = 1482, parent = 1477, component = 27, walkable = true)
                sendConfiguredWorldInterfaceBindings()
                sendMinimalWorldVarcs()
                client.traceBootstrap(
                    "world-send-forced-fallback-immediate-gate-varps name=$name " +
                        "ids=0,1,2,6,3,4,7,10,11,3920,8256 values=0:28,3:-1807741724,questhelp:-1,long:0"
                )
                TODORefactorThisClass.sendForcedFallbackCandidateDefaultVarps(client)
                client.primeLateDefaultVarpReplaySkip(TODORefactorThisClass.FORCED_FALLBACK_CANDIDATE_DEFAULT_VARP_IDS)
                client.traceBootstrap(
                    "world-skip-loading-notes name=$name reason=forced-map-build-fallback-minimal-bootstrap"
                )
                client.traceBootstrap(
                    "world-skip-forced-fallback-completion-companions name=$name " +
                        "ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 " +
                        "reason=forced-map-build-fallback-minimal-bootstrap"
                )
                deferForcedFallbackInterfaceTail(reason = "forced-map-build-fallback-pre-ready")
                queueMinimalWorldFollowupIfNeeded(
                    reason = "forced-map-build-fallback-minimal-child",
                    queueDeferredCompletionTail = true
                )
                client.traceBootstrap("world-open-minimal-child name=$name id=1482 parent=1477 component=27")
                return@runBootstrapStage
            }
            if (!bootstrap.openSupplementalChildInterfaces) {
                logger.info {
                    "Opening only the primary world child interface for $name because " +
                        "openSupplementalChildInterfaces=false"
                }
                // Keep the stripped-down world bootstrap stable, but restore the first
                // scene child so we can test whether the client needs it to leave the
                // loading screen.
                player.interfaces.open(id = 1482, parent = 1477, component = 27, walkable = true)
                sendConfiguredWorldInterfaceBindings()
                sendMinimalWorldVarcs()
                queueMinimalWorldFollowupIfNeeded("minimal-child")
                client.traceBootstrap("world-open-minimal-child name=$name id=1482 parent=1477 component=27")
                return@runBootstrapStage
            }
        player.interfaces.open(id = 1482, parent = 1477, component = 27, walkable = true)
        sendConfiguredWorldInterfaceBindings()
        player.interfaces.open(id = 1466, parent = 1477, component = 284, walkable = true)
        player.interfaces.events(id = 1466, component = 7, from = 0, to = 28, mask = 30)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(0, 1))
        player.interfaces.open(id = 1473, parent = 1477, component = 98, walkable = true)
        player.interfaces.events(id = 1473, component = 7, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1473, component = 7, from = 0, to = 27, mask = 15302030)
        player.interfaces.events(id = 1473, component = 25, from = 0, to = 16, mask = 1422)
        player.interfaces.events(id = 1473, component = 1, from = 0, to = 5, mask = 2099198)
        player.interfaces.events(id = 1473, component = 28, from = 0, to = 5, mask = 2099198)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(2, 1))
        player.interfaces.open(id = 1464, parent = 1477, component = 109, walkable = true)
        player.interfaces.events(id = 1464, component = 15, from = 0, to = 18, mask = 15302654)
        player.interfaces.events(id = 1464, component = 24, from = 0, to = 6, mask = 2046)
        player.interfaces.events(id = 1464, component = 19, from = 0, to = 6, mask = 2046)
        player.interfaces.events(id = 1464, component = 15, from = 0, to = 18, mask = 10749950)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(3, 1))
        client.write(ClientSetvarcSmall(id = 181, value = 0))
        player.interfaces.open(id = 1458, parent = 1477, component = 131, walkable = true)
        player.interfaces.events(id = 1458, component = 39, from = 0, to = 38, mask = 8388610)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(4, 1))
        player.interfaces.open(id = 1461, parent = 1477, component = 186, walkable = true)
        player.interfaces.open(id = 1884, parent = 1477, component = 197, walkable = true)
        player.interfaces.open(id = 1885, parent = 1477, component = 208, walkable = true)
        player.interfaces.open(id = 1887, parent = 1477, component = 219, walkable = true)
        client.traceBootstrap("world-open-restored-interface name=$name id=1887 parent=1477 component=219")
        player.interfaces.open(id = 1886, parent = 1477, component = 230, walkable = true)
        player.interfaces.open(id = 1460, parent = 1477, component = 142, walkable = true)
        player.interfaces.open(id = 1881, parent = 1477, component = 153, walkable = true)
        player.interfaces.open(id = 1888, parent = 1477, component = 164, walkable = true)
        player.interfaces.open(id = 1883, parent = 1477, component = 241, walkable = true)
        player.interfaces.open(id = 1449, parent = 1477, component = 252, walkable = true)
        player.interfaces.open(id = 1882, parent = 1477, component = 263, walkable = true)
        player.interfaces.open(id = 1452, parent = 1477, component = 175, walkable = true)
        player.interfaces.events(id = 1461, component = 1, from = 0, to = 211, mask = 10320974)
        player.interfaces.events(id = 1884, component = 1, from = 0, to = 211, mask = 10320974)
        player.interfaces.events(id = 1885, component = 1, from = 0, to = 211, mask = 10320974)
        player.interfaces.events(id = 1886, component = 1, from = 0, to = 211, mask = 10320974)
        player.interfaces.events(id = 1461, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1461, component = 7, from = 7, to = 10, mask = 10319874)
        player.interfaces.events(id = 1460, component = 5, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1460, component = 5, from = 7, to = 10, mask = 10319874)
        player.interfaces.events(id = 1452, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1883, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1883, component = 7, from = 7, to = 10, mask = 10319874)
        player.interfaces.events(id = 1881, component = 5, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1888, component = 5, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1449, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1882, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1884, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1885, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1886, component = 7, from = 7, to = 16, mask = 2)
        player.interfaces.events(id = 1460, component = 1, from = 0, to = 211, mask = 10320902)
        player.interfaces.events(id = 1881, component = 1, from = 0, to = 211, mask = 10320902)
        player.interfaces.events(id = 1888, component = 1, from = 0, to = 211, mask = 10320902)
        player.interfaces.events(id = 1452, component = 1, from = 0, to = 211, mask = 10320902)
        player.interfaces.events(id = 1883, component = 1, from = 0, to = 211, mask = 10320902)
        player.interfaces.events(id = 1449, component = 1, from = 0, to = 211, mask = 10320902)
        player.interfaces.events(id = 1882, component = 1, from = 0, to = 211, mask = 10320902)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(5, 1))
        player.interfaces.open(id = 550, parent = 1477, component = 475, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(14, 1))
        player.interfaces.events(id = 550, component = 7, from = 0, to = 500, mask = 2046)
        player.interfaces.events(id = 550, component = 60, from = 0, to = 500, mask = 6)
        player.interfaces.open(id = 1427, parent = 1477, component = 519, walkable = true)
        client.write(ClientSetvarcSmall(id = 1027, value = 1))
        client.write(ClientSetvarcSmall(id = 1034, value = 2))
        player.interfaces.events(id = 1427, component = 30, from = 0, to = 600, mask = 1040)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(15, 1))
        player.interfaces.open(id = 1110, parent = 1477, component = 486, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(16, 1))
        player.interfaces.events(id = 1110, component = 31, from = 0, to = 200, mask = 2)
        player.interfaces.events(id = 1110, component = 85, from = 0, to = 600, mask = 2)
        player.interfaces.events(id = 1110, component = 83, from = 0, to = 600, mask = 1040)
        player.interfaces.events(id = 1110, component = 38, from = 0, to = 600, mask = 1040)
        player.interfaces.open(id = 590, parent = 1477, component = 393, walkable = true)
        player.interfaces.events(id = 590, component = 8, from = 0, to = 223, mask = 8388614)
        player.interfaces.events(id = 590, component = 1, from = 0, to = 43, mask = 8388622)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(9, 1))
        player.interfaces.open(id = 1416, parent = 1477, component = 295, walkable = true)
        player.interfaces.events(id = 1416, component = 3, from = 0, to = 3087, mask = 62)
        player.interfaces.events(id = 1416, component = 11, from = 0, to = 99, mask = 2359334)
        player.interfaces.events(id = 1416, component = 11, from = 100, to = 199, mask = 4)
        player.interfaces.events(id = 1416, component = 11, from = 200, to = 200, mask = 2097152)
        player.interfaces.text(id = 1416, component = 6, text = "Adventure")
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(10, 1))
        client.write(ClientSetvarcSmall(id = 3497, value = 0))
        openLoadingNotesInterfaceIfAvailable(reason = "full-bootstrap")
        player.interfaces.open(id = 1519, parent = 1477, component = 497, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(27, 1))
        player.interfaces.open(id = 1588, parent = 1477, component = 327, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(28, 1))
        player.interfaces.open(id = 1678, parent = 1477, component = 338, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(29, 1))
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(30, 0))
        player.interfaces.open(id = 190, parent = 1477, component = 360, walkable = true)
        player.interfaces.events(id = 190, component = 5, from = 0, to = 312, mask = 14)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(31, 1))
        player.interfaces.open(id = 1854, parent = 1477, component = 371, walkable = true)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(32, 1))
        player.interfaces.events(id = 1854, component = 6, from = 0, to = 4, mask = 66)
        player.interfaces.events(id = 1854, component = 5, from = 0, to = 1, mask = 2)
        player.interfaces.open(id = 1894, parent = 1477, component = 382, walkable = true)
        player.interfaces.events(id = 1894, component = 16, from = 0, to = 2, mask = 2)
        player.interfaces.events(id = 1894, component = 18, from = 0, to = 3, mask = 6)
        player.interfaces.events(id = 1894, component = 19, from = 0, to = 3, mask = 6)
        sendInterfaceBootstrapScript(script = 8862, args = arrayOf(41, 1))
        player.interfaces.open(id = 1431, parent = 1477, component = 59, walkable = true)
        player.interfaces.open(id = 568, parent = 1477, component = 638, walkable = true)
        player.interfaces.events(id = 1477, component = 60, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1431, component = 0, from = 0, to = 46, mask = 6)
        player.interfaces.events(id = 568, component = 5, from = 0, to = 46, mask = 6)
        player.interfaces.open(id = 1465, parent = 1477, component = 90, walkable = true)
        player.interfaces.open(id = 1919, parent = 1477, component = 91, walkable = true)
        player.interfaces.events(id = 1477, component = 94, from = 1, to = 1, mask = 6)
        if (bootstrap.trimWorldInterfaceTail) {
            deferredLateWorldCompletionTailPending = true
            sendLightLateWorldInterfaceTail()
            logger.info {
                "Skipping heavy late world interface tail for $name after light late-tail bootstrap " +
                    "because trimWorldInterfaceTail=true"
            }
            client.traceBootstrap("world-trimmed-interface-tail name=$name mode=light")
            return@runBootstrapStage
        }
        val deferFullWorldInterfaceTail = bootstrap.openRootInterface && !bootstrap.trimWorldInterfaceTail
        client.traceBootstrap(
            "world-evaluate-interface-tail name=$name " +
                "openRoot=${bootstrap.openRootInterface} " +
                "openSupplemental=${bootstrap.openSupplementalChildInterfaces} " +
                "trim=${bootstrap.trimWorldInterfaceTail} defer=$deferFullWorldInterfaceTail"
        )
        if (deferFullWorldInterfaceTail) {
            queueDeferredWorldCompletionTailIfNeeded("full-interface")
            sendLightLateWorldInterfaceTail()
            client.traceBootstrap("world-deferred-interface-tail name=$name mode=light reason=full-interface")
            return@runBootstrapStage
        }
        player.interfaces.open(id = 634, parent = 1477, component = 739, walkable = true)
        sendInterfaceBootstrapScript(script = 11145, args = arrayOf(1067, 600, 0, 0, 96797408))
        sendInterfaceBootstrapScript(script = 8420, args = arrayOf(-1, 96797410, 96797411, -1, "", 21259, 1007))
        player.interfaces.hide(id = 634, component = 259, hidden = true)
        player.interfaces.hide(id = 634, component = 0, hidden = false)
        player.interfaces.events(id = 634, component = 152, from = 65535, to = 65535, mask = 1022)
        player.interfaces.events(id = 634, component = 265, from = 65535, to = 65535, mask = 2)
        player.interfaces.events(id = 634, component = 67, from = 65535, to = 65535, mask = 2)
        player.interfaces.events(id = 634, component = 68, from = 65535, to = 65535, mask = 2)
        player.interfaces.events(id = 634, component = 138, from = 65535, to = 65535, mask = 2)
        player.interfaces.events(id = 634, component = 139, from = 65535, to = 65535, mask = 2)
        player.interfaces.events(id = 634, component = 2, from = 65535, to = 65535, mask = 2)
        player.interfaces.open(id = 653, parent = 1477, component = 744, walkable = true)
        sendInterfaceBootstrapScript(script = 11145, args = arrayOf(1067, 600, 0, 0, 96797413))
        sendInterfaceBootstrapScript(script = 8420, args = arrayOf(-1, 96797415, 96797416, -1, "", 21259, 1007))
        player.interfaces.hide(id = 653, component = 71, hidden = true)
        player.interfaces.hide(id = 653, component = 0, hidden = false)
        player.interfaces.events(id = 653, component = 155, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 166, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 177, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 188, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 199, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 210, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 221, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 232, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 243, from = 0, to = 500, mask = 62)
        player.interfaces.events(id = 653, component = 254, from = 0, to = 500, mask = 62)
        player.interfaces.open(id = 1430, parent = 1477, component = 65, walkable = true)
        player.interfaces.open(id = 1670, parent = 1477, component = 70, walkable = true)
        sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1032))
        player.interfaces.open(id = 1671, parent = 1477, component = 75, walkable = true)
        sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1033))
        player.interfaces.open(id = 1673, parent = 1477, component = 85, walkable = true)
        sendInterfaceBootstrapScript(script = 8310, args = arrayOf(1035))
        if (bootstrap.sendSocialInitPackets) {
            player.interfaces.events(id = 1477, component = 66, from = 1, to = 1, mask = 4)
            player.interfaces.events(id = 1430, component = 64, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 69, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 77, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 82, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 90, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 95, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 103, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 108, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 116, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 121, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 129, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 134, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 142, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 147, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 155, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 160, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 168, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 173, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 181, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 186, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 194, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 199, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 207, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 212, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 220, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 225, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 233, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 238, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 18, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 23, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 31, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 36, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 44, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 49, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 57, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 62, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 70, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 75, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 83, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 88, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 96, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 101, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 109, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 114, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 122, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 127, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 135, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 140, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 148, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 153, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 161, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 166, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 174, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 179, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 187, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 192, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 13, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 18, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 26, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 31, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 39, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 44, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 52, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 57, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 65, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 70, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 78, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 83, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 91, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 96, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 104, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 109, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 117, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 122, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 130, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 135, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 143, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 148, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 156, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 161, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 169, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 174, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 182, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 187, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 13, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 18, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 26, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 31, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 39, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 44, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 52, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 57, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 65, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 70, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 78, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 83, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 91, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 96, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 104, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 109, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 117, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 122, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 130, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 135, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 143, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 148, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 156, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 161, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 169, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 174, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 182, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 187, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1458, component = 39, from = 0, to = 38, mask = 8388610)
            player.interfaces.events(id = 1430, component = 17, from = 65535, to = 65535, mask = 8388608)
            player.interfaces.events(id = 1465, component = 15, from = 65535, to = 65535, mask = 8388608)
            player.interfaces.events(id = 1430, component = 11, from = 65535, to = 65535, mask = 8650758)
            player.interfaces.events(id = 1430, component = 22, from = 65535, to = 65535, mask = 8388608)
            player.interfaces.events(id = 1430, component = 16, from = 65535, to = 65535, mask = 2046)
            player.interfaces.events(id = 1460, component = 1, from = 0, to = 211, mask = 8592390)
            player.interfaces.events(id = 1881, component = 1, from = 0, to = 211, mask = 8592390)
            player.interfaces.events(id = 1888, component = 1, from = 0, to = 211, mask = 8592390)
            player.interfaces.events(id = 1452, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 1461, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1884, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1885, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1886, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1883, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 1449, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 1882, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 590, component = 8, from = 0, to = 223, mask = 8388614)
            player.interfaces.events(id = 1430, component = 254, from = 65535, to = 65535, mask = 2046)
            player.interfaces.events(id = 1430, component = 253, from = 65535, to = 65535, mask = 0)
            player.interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 0)
            player.interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 2)
        } else {
            logger.info { "Skipping world social interface event flood for $name due to bootstrap config" }
            client.traceBootstrap("world-skip-social-interface-events name=$name ids=1430,1458,1460,1461,1670,1671,1673,1881,1882,1883,1884,1885,1886,1888,590")
        }
// ClientSetvarcSmall(id=1436, value=1)
        player.interfaces.open(id = 1433, parent = 1477, component = 751, walkable = true)
        player.interfaces.events(id = 1433, component = 6, from = 0, to = 6, mask = 2)
        player.interfaces.open(id = 137, parent = 1477, component = 404, walkable = true)
        player.interfaces.events(id = 137, component = 85, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 137, component = 62, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 137, component = 65, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 137, component = 59, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 1467, parent = 1477, component = 415, walkable = true)
        player.interfaces.events(id = 1467, component = 192, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 1467, component = 179, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 1467, component = 183, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 1467, component = 185, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 1472, parent = 1477, component = 425, walkable = true)
        player.interfaces.events(id = 1472, component = 193, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 1472, component = 186, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 1472, component = 190, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 1472, component = 192, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 1471, parent = 1477, component = 435, walkable = true)
        player.interfaces.events(id = 1471, component = 193, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 1471, component = 180, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 1471, component = 184, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 1471, component = 186, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 1470, parent = 1477, component = 445, walkable = true)
        player.interfaces.events(id = 1470, component = 193, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 1470, component = 180, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 1470, component = 184, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 1470, component = 186, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 464, parent = 1477, component = 455, walkable = true)
        player.interfaces.events(id = 464, component = 193, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 464, component = 180, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 464, component = 184, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 464, component = 186, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 1529, parent = 1477, component = 465, walkable = true)
        player.interfaces.events(id = 1529, component = 192, from = 0, to = 99, mask = 1792)
        player.interfaces.events(id = 1529, component = 179, from = 0, to = 11, mask = 126)
        player.interfaces.events(id = 1529, component = 183, from = 0, to = 8, mask = 126)
        player.interfaces.events(id = 1529, component = 185, from = 0, to = 2, mask = 2)
        player.interfaces.open(id = 1484, parent = 1477, component = 767, walkable = true)
        player.interfaces.hide(id = 1477, component = 593, hidden = false)
        player.interfaces.open(id = 1483, parent = 1477, component = 576, walkable = true)
        player.interfaces.open(id = 745, parent = 1477, component = 589, walkable = true)
        player.interfaces.open(id = 284, parent = 1477, component = 572, walkable = true)
        player.interfaces.open(id = 1213, parent = 1477, component = 619, walkable = true)
        player.interfaces.open(id = 1448, parent = 1477, component = 662, walkable = true)
        player.interfaces.open(id = 291, parent = 1477, component = 568, walkable = true)
// ClientSetvarcSmall(id=2834, value=1)
        player.interfaces.events(id = 1477, component = 22, from = 65535, to = 65535, mask = 2097152)
        sendInterfaceBootstrapScript(script = 139, args = arrayOf(96796695))
        player.interfaces.open(id = 1488, parent = 1477, component = 760, walkable = true)
        player.interfaces.open(id = 1680, parent = 1477, component = 39, walkable = true)
        sendInterfaceBootstrapScript(script = 14150, args = arrayOf(5))
        player.interfaces.events(id = 1477, component = 15, from = 65535, to = 65535, mask = 2)
        player.interfaces.events(id = 1477, component = 15, from = 0, to = 41, mask = 2)
        player.interfaces.events(id = 1477, component = 840, from = 0, to = 1000, mask = 2)
        player.interfaces.open(id = 1847, parent = 1477, component = 856, walkable = true)
        player.interfaces.events(id = 1477, component = 856, from = 0, to = 0, mask = 2)
        player.interfaces.open(id = 635, parent = 1477, component = 615, walkable = true)
        player.interfaces.open(id = 1639, parent = 1477, component = 627, walkable = true)
        client.traceBootstrap(
            "world-send-deferred-completion-structure-template name=$name " +
                "ids=1433,137,1467,1472,1471,1470,464,1529,1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639"
        )
        if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionScripts) {
            client.traceBootstrap(
                "world-send-deferred-completion-scripts-template name=$name " +
                    "scripts=8862,2651,7486,10903,8778,4704,4308,10623,5559,3957"
            )
            sendDeferredCompletionFullScripts()
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionLiteScripts) {
            client.traceBootstrap(
                "world-send-deferred-completion-lite-scripts-template name=$name " +
                    "scripts=8862,2651,7486,10903,8778,4704,4308"
            )
            player.client.write(RunClientScript(script = 8862, args = arrayOf(1025, 1)))
            player.client.write(RunClientScript(script = 2651, args = arrayOf(1025, 0)))
            player.client.write(RunClientScript(script = 7486, args = arrayOf(27066179, 41615368)))
            player.client.write(RunClientScript(script = 10903))
            player.client.write(RunClientScript(script = 8862, args = arrayOf(1031, 1)))
            player.client.write(RunClientScript(script = 2651, args = arrayOf(1031, 0)))
            player.client.write(RunClientScript(script = 8778))
            player.interfaces.text(id = 187, component = 7, text = "")
            player.interfaces.text(id = 1416, component = 6, text = "")
            player.client.write(RunClientScript(script = 4704))
            player.client.write(RunClientScript(script = 4308, args = arrayOf(18, 0)))
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletion10623Batch) {
            client.traceBootstrap(
                "world-send-deferred-completion-10623-batch-template name=$name " +
                    "scripts=10623:30522,30758,30759,30821,30828,30964,31386,31562,31918,39392"
            )
            for (scriptArg in listOf(30522, 30758, 30759, 30821, 30828, 30964, 31386, 31562, 31918, 39392)) {
                player.client.write(RunClientScript(script = 10623, args = arrayOf(scriptArg, 0)))
            }
        } else if (OpenNXT.config.lobbyBootstrap.sendDeferredCompletionCoreScripts) {
            client.traceBootstrap(
                "world-send-deferred-completion-core-scripts-template name=$name " +
                    "scripts=8862:1025,2651:1025,8862:1031,2651:1031,8778"
            )
            player.client.write(RunClientScript(script = 8862, args = arrayOf(1025, 1)))
            player.client.write(RunClientScript(script = 2651, args = arrayOf(1025, 0)))
            player.client.write(RunClientScript(script = 8862, args = arrayOf(1031, 1)))
            player.client.write(RunClientScript(script = 2651, args = arrayOf(1031, 0)))
            player.client.write(RunClientScript(script = 8778))
        } else {
            client.traceBootstrap("world-skip-deferred-completion-scripts-template name=$name")
        }
        if (bootstrap.sendLateRootInterfaceEvents) {
        player.interfaces.events(id = 1477, component = 58, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 58, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 58, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 56, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 64, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 64, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 64, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 62, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 93, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 93, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 93, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 93, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 87, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 407, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 407, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 407, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 407, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 402, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 408, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 417, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 417, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 417, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 417, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 413, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 418, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 427, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 427, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 427, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 427, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 423, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 428, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 437, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 437, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 437, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 437, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 433, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 438, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 447, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 447, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 447, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 447, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 443, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 448, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 457, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 457, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 457, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 457, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 453, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 458, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 467, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 467, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 467, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 467, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 463, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 468, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 396, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 396, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 396, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 396, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 391, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 397, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 101, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 101, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 101, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 101, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 96, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 102, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 145, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 145, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 145, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 145, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 140, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 146, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 156, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 156, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 156, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 156, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 151, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 157, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 167, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 167, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 167, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 167, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 162, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 168, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 178, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 178, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 178, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 178, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 173, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 179, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 189, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 189, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 189, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 189, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 184, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 190, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 200, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 200, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 200, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 200, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 195, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 201, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 211, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 211, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 211, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 211, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 206, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 212, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 222, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 222, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 222, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 222, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 217, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 223, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 233, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 233, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 233, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 233, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 228, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 234, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 244, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 244, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 244, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 244, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 239, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 245, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 255, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 255, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 255, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 255, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 250, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 256, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 266, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 266, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 266, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 266, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 261, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 267, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 112, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 112, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 112, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 112, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 107, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 113, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 123, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 123, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 123, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 123, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 118, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 124, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 276, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 276, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 276, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 276, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 272, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 278, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 287, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 287, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 287, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 287, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 282, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 288, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 134, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 134, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 134, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 134, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 129, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 135, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 298, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 298, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 298, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 298, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 293, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 299, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 511, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 511, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 511, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 511, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 506, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 512, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 478, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 478, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 478, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 478, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 473, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 479, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 489, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 489, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 489, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 489, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 484, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 490, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 522, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 522, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 522, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 522, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 517, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 523, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 596, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 596, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 596, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 596, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 698, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 698, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 698, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 683, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 683, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 683, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 674, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 674, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 674, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 688, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 684, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 689, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 573, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 573, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 573, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 573, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 552, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 552, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 552, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 577, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 577, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 577, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 582, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 582, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 582, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 565, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 565, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 565, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 590, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 590, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 590, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 556, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 556, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 556, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 768, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 768, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 768, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 643, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 643, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 643, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 643, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 586, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 586, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 586, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 604, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 604, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 604, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 604, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 659, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 659, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 659, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 655, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 664, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 47, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 47, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 47, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 47, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 24, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 608, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 608, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 608, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 309, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 309, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 309, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 309, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 304, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 310, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 320, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 320, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 320, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 320, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 315, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 668, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 668, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 668, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 500, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 500, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 500, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 500, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 495, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 501, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 648, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 648, from = 6, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 648, from = 11, to = 11, mask = 9175040)
        player.interfaces.events(id = 1477, component = 648, from = 13, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 648, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 648, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 616, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 616, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 616, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 620, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 620, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 620, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 330, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 330, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 330, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 330, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 325, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 335, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 624, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 624, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 624, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 561, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 561, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 561, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 653, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 653, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 653, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 653, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 632, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 632, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 632, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 628, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 628, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 628, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 69, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 69, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 69, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 67, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 74, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 74, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 74, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 72, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 79, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 79, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 79, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 77, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 84, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 84, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 84, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 82, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 341, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 341, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 341, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 341, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 336, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 346, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 600, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 600, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 600, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 352, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 352, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 352, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 352, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 347, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 357, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 548, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 548, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 548, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 363, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 363, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 363, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 363, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 358, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 368, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 569, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 569, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 569, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 569, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 374, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 374, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 374, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 374, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 369, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 379, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 385, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 385, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 385, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 385, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 380, from = 65535, to = 65535, mask = 2097152)
        player.interfaces.events(id = 1477, component = 390, from = 1, to = 1, mask = 2)
        player.interfaces.events(id = 1477, component = 678, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 678, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 678, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 544, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 544, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 544, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 540, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 540, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 540, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 612, from = 1, to = 7, mask = 9175040)
        player.interfaces.events(id = 1477, component = 612, from = 11, to = 13, mask = 9175040)
        player.interfaces.events(id = 1477, component = 612, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 612, from = 3, to = 4, mask = 9175040)
        player.interfaces.events(id = 1477, component = 532, from = 1, to = 2, mask = 9175040)
        player.interfaces.events(id = 1477, component = 532, from = 0, to = 0, mask = 9175040)
        player.interfaces.events(id = 1477, component = 532, from = 3, to = 4, mask = 9175040)
        client.traceBootstrap("world-send-late-root-interface-events name=$name parent=1477")
        } else {
            client.traceBootstrap("world-skip-late-root-interface-events name=$name parent=1477")
        }
        sendInterfaceBootstrapScript(
            script = 1264,
            args = arrayOf(
                "PMod PvM Event",
                "Friday 18th June, 20:00 Game Time",
                "Nex: Angel of Death boss mass",
                "",
                "Nex lobby, God Wars Dungeon",
                "w88",
                "Pippyspot & Boss Guild",
                "Boss Guild",
                "",
                "",
                1321
            )
        )
        sendInterfaceBootstrapScript(script = 3529)
        if (bootstrap.sendSocialInitPackets) {
            player.interfaces.events(id = 1430, component = 64, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 69, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 77, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 82, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 90, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 95, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 103, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 108, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 116, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 121, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 129, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 134, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 142, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 147, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 155, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 160, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 168, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 173, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 181, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 186, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 194, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 199, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 207, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 212, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 220, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 225, from = 65535, to = 65535, mask = 11239422)
            player.interfaces.events(id = 1430, component = 233, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1430, component = 238, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 18, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 23, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 31, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 36, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 44, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 49, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 57, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 62, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 70, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 75, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 83, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 88, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 96, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 101, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 109, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 114, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 122, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 127, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 135, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 140, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 148, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 153, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 161, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 166, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 174, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 179, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 187, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1670, component = 192, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 13, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 18, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 26, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 31, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 39, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 44, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 52, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 57, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 65, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 70, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 78, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 83, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 91, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 96, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 104, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 109, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 117, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 122, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 130, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 135, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 143, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 148, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 156, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 161, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 169, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 174, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 182, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1671, component = 187, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 13, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 18, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 26, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 31, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 39, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 44, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 52, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 57, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 65, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 70, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 78, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 83, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 91, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 96, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 104, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 109, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 117, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 122, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 130, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 135, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 143, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 148, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 156, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 161, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 169, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 174, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 182, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1673, component = 187, from = 65535, to = 65535, mask = 2098176)
            player.interfaces.events(id = 1458, component = 39, from = 0, to = 38, mask = 8388610)
            player.interfaces.events(id = 1430, component = 17, from = 65535, to = 65535, mask = 8388608)
            player.interfaces.events(id = 1465, component = 15, from = 65535, to = 65535, mask = 8388608)
            player.interfaces.events(id = 1430, component = 11, from = 65535, to = 65535, mask = 8650758)
            player.interfaces.events(id = 1430, component = 22, from = 65535, to = 65535, mask = 8388608)
            player.interfaces.events(id = 1430, component = 16, from = 65535, to = 65535, mask = 2046)
            player.interfaces.events(id = 1460, component = 1, from = 0, to = 211, mask = 8592390)
            player.interfaces.events(id = 1881, component = 1, from = 0, to = 211, mask = 8592390)
            player.interfaces.events(id = 1888, component = 1, from = 0, to = 211, mask = 8592390)
            player.interfaces.events(id = 1452, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 1461, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1884, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1885, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1886, component = 1, from = 0, to = 211, mask = 8617038)
            player.interfaces.events(id = 1883, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 1449, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 1882, component = 1, from = 0, to = 211, mask = 8616966)
            player.interfaces.events(id = 590, component = 8, from = 0, to = 223, mask = 8388614)
            player.interfaces.events(id = 1430, component = 254, from = 65535, to = 65535, mask = 2046)
            player.interfaces.events(id = 1430, component = 253, from = 65535, to = 65535, mask = 0)
            player.interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 0)
            player.interfaces.events(id = 1430, component = 35, from = 65535, to = 65535, mask = 2)
        } else {
            client.traceBootstrap(
                "world-skip-social-interface-events-template name=$name " +
                    "ids=1430,1458,1460,1461,1670,1671,1673,1881,1882,1883,1884,1885,1886,1888,590"
            )
        }

        // TODO Rebuild [region | dynamic] packet
        }
        logger.info { "Finished world bootstrap for $name after stages ${client.completedBootstrapStages.joinToString()}" }
        }

        if (awaitingMapBuildComplete) {
            logger.info { "Waiting for MAP_BUILD_COMPLETE before continuing world bootstrap for $name" }
            client.traceBootstrap("world-waiting-map-build-complete name=$name")
            return
        }

        completeDeferredBootstrap()
        } catch (e: Exception) {
            logger.error(e) { "World bootstrap failed for $name at stage $stage" }
            throw e
        }
    }

    override fun tick() {
        if (awaitingMapBuildComplete) {
            mapBuildWaitTicks++
            if (mapBuildWaitTicks == MAP_BUILD_FALLBACK_TICKS && deferredBootstrap != null) {
                logger.warn {
                    "MAP_BUILD_COMPLETE not received for $name after $mapBuildWaitTicks ticks; " +
                        "forcing deferred world bootstrap continuation"
                }
                client.traceBootstrap(
                    "world-force-map-build-fallback name=$name ticks=$mapBuildWaitTicks"
                )
                forcedMapBuildFallbackPending = true
                awaitingMapBuildComplete = false
                completeDeferredBootstrap()
            }
        }

        if (awaitingWorldReadySignal) {
            worldReadyWaitTicks++
            if (PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null) {
                client.write(NoTimeout)
                client.traceBootstrap(
                    "world-ready-wait-keepalive name=$name ticks=$worldReadyWaitTicks packet=NO_TIMEOUT"
                )
            }
            val pendingServerpermDelayedReady = pendingServerpermDelayedReadySignal
            if (
                pendingWorldReadySignal == null &&
                pendingServerpermDelayedReady != null &&
                !initialWorldSyncSent &&
                !skipPostInitialSyncHoldForForcedFallback &&
                lastClientDisplayState106 != null
            ) {
                if (deferredLateWorldCompletionTailPending) {
                    client.traceBootstrap(
                        "world-promote-serverperm-ready-synthetic name=$name " +
                            "opcode=${pendingServerpermDelayedReady.opcode} " +
                            "bytes=${pendingServerpermDelayedReady.payloadLength} " +
                            "preview=${pendingServerpermDelayedReady.preview} " +
                            "source=${pendingServerpermDelayedReady.source} waitTicks=$worldReadyWaitTicks"
                    )
                }
                pendingServerpermDelayedReadySignal = null
                latchWorldReadySignal(
                    opcode = pendingServerpermDelayedReady.opcode,
                    payloadLength = pendingServerpermDelayedReady.payloadLength,
                    preview = pendingServerpermDelayedReady.preview,
                    source = pendingServerpermDelayedReady.source
                )
            }
            val pendingReadySignal = pendingWorldReadySignal
            if (
                pendingReadySignal != null &&
                pendingReadySignal.source != "synthetic-forced-map-build-fallback"
            ) {
                client.traceBootstrap(
                    "world-ready-signal-consume-delayed name=$name opcode=${pendingReadySignal.opcode} " +
                        "bytes=${pendingReadySignal.payloadLength} preview=${pendingReadySignal.preview} " +
                        "pendingSource=${pendingReadySignal.source} waitTicks=$worldReadyWaitTicks"
                )
                consumePendingWorldReadySignalIfNeeded(source = "delayed-ready-wait")
                return
            }
            if (
                !initialWorldSyncSent &&
                !skipPostInitialSyncHoldForForcedFallback &&
                deferredLateWorldCompletionTailPending &&
                lastClientDisplayState106 != null &&
                worldReadyWaitTicks <= PRE_READY_SYNC_PRIME_TICKS
            ) {
                client.traceBootstrap(
                    "world-ready-wait-prime-sync name=$name ticks=$worldReadyWaitTicks " +
                        "reason=full-interface-display-ready"
                )
                if (client.pendingDeferredBootstrapVarpCount() == 0) {
                    sendPreReadyWorldSyncPrimeFrame("ready-prime")
                } else {
                    client.traceBootstrap(
                        "world-defer-ready-wait-prime-sync name=$name ticks=$worldReadyWaitTicks " +
                            "pendingLateDefaultVarps=${client.pendingDeferredBootstrapVarpCount()}"
                    )
                }
            }
            if (worldReadyWaitTicks == WORLD_READY_FALLBACK_TICKS) {
                logger.warn {
                    "World-ready signal not received for $name after $worldReadyWaitTicks ticks; " +
                        "allowing PLAYER_INFO fallback with immediate followup sync"
                }
                client.traceBootstrap(
                    "world-ready-signal-fallback name=$name ticks=$worldReadyWaitTicks"
                )
                awaitingWorldReadySignal = false
                clearCompatMapBuildReadyFallback()
                playerInfoDelayTicks = 0
                if (!initialWorldSyncSent) {
                    sendInitialWorldSyncIfNeeded(forceImmediateFollowup = true)
                }
            }
        }

        if (!awaitingMapBuildComplete && !awaitingWorldReadySignal) {
            if (playerInfoDelayTicks > 0) {
                playerInfoDelayTicks--
            } else if (!initialWorldSyncSent) {
                sendInitialWorldSyncIfNeeded()
            } else {
                if (sendDeferredLateWorldCompletionTailIfNeeded()) {
                    return
                }
                if (postInitialWorldSyncHoldTicks > 0) {
                    val holdTicksRemaining = postInitialWorldSyncHoldTicks
                    val holdReason = currentPostInitialSyncHoldReason()
                    if (postInitialWorldSyncHoldForcedFallback && deferredLateWorldCompletionTailPending) {
                        primeForcedFallbackPreDeferredFamilies(source = "hold")
                    }
                    client.traceBootstrap(
                        "world-hold-post-initial-sync name=$name ticksRemaining=$holdTicksRemaining"
                    )
                    if (
                        postInitialWorldSyncHoldSendFrames &&
                        PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null
                    ) {
                        client.write(NoTimeout)
                        client.traceBootstrap(
                            "world-hold-keepalive name=$name ticksRemaining=$holdTicksRemaining " +
                                "packet=NO_TIMEOUT reason=$holdReason"
                        )
                    }
                    val suppressForcedFallbackHoldSync =
                        postInitialWorldSyncHoldForcedFallback &&
                            deferredLateWorldCompletionTailPending
                    if (postInitialWorldSyncHoldSendFrames) {
                        if (suppressForcedFallbackHoldSync) {
                            client.traceBootstrap(
                                "world-skip-hold-sync name=$name ticksRemaining=$holdTicksRemaining " +
                                    "reason=forced-map-build-fallback-post-prime"
                            )
                        } else if (client.pendingDeferredBootstrapVarpCount() == 0) {
                            sendWorldSyncFrame("hold")
                        } else {
                            client.traceBootstrap(
                                "world-defer-hold-sync name=$name ticksRemaining=$holdTicksRemaining " +
                                "pendingLateDefaultVarps=${client.pendingDeferredBootstrapVarpCount()}"
                            )
                        }
                    }
                    if (suppressForcedFallbackHoldSync && postInitialWorldSyncHoldTicks > 1) {
                        client.traceBootstrap(
                            "world-accelerate-post-initial-sync-hold-clear name=$name " +
                                "ticksRemaining=$holdTicksRemaining reason=forced-map-build-fallback-deferred-tail"
                        )
                        postInitialWorldSyncHoldTicks = 1
                    }
                    postInitialWorldSyncHoldTicks--
                    if (postInitialWorldSyncHoldTicks == 0) {
                        postInitialWorldSyncHoldForcedFallback = false
                        postInitialWorldSyncHoldSendFrames = false
                        closeForcedFallbackLoadingOverlayIfPending(reason = "forced-map-build-fallback-post-hold")
                        if (deferredLateWorldCompletionTailPending) {
                            client.traceBootstrap(
                                "world-clear-post-initial-sync-hold name=$name " +
                                    "reason=$holdReason continue=deferred-tail"
                            )
                            if (sendDeferredLateWorldCompletionTailIfNeeded()) {
                                return
                            }
                        } else {
                            client.traceBootstrap(
                                "world-clear-post-initial-sync-hold name=$name " +
                                    "reason=$holdReason continue=tick-sync"
                            )
                        }
                    } else {
                        return
                    }
                }
                sendDeferredDefaultVarpsIfNeeded()
                val pendingLateDefaultVarps = client.pendingDeferredBootstrapVarpCount()
                if (pendingLateDefaultVarps == 0) {
                    val sceneStartControl50 = effectiveSceneStartControl50()
                    if (sceneStartSyncBurstTicks > 0) {
                        client.traceBootstrap(
                            "world-send-scene-start-sync-burst name=$name ticksRemaining=$sceneStartSyncBurstTicks"
                        )
                        sceneStartSyncBurstTicks--
                        sendWorldSyncFrame("scene-start-nudge")
                        val phaseOneReleaseControl50 = sceneStartPhaseOneReleaseControl50(sceneStartControl50)
                        if (
                            sceneStartSyncBurstTicks == 0 &&
                            deferredSceneStartEventDeltaPending &&
                            (
                                sceneStartPhaseOneReached(sceneStartControl50) ||
                                    implicitForcedFallbackSceneStartPhaseOneReached(sceneStartControl50)
                                )
                        ) {
                            if (
                                deferForcedFallbackPhaseOneEventDeltaUntilLateReady(
                                    control50 = sceneStartControl50,
                                    source =
                                        if (sceneStartPhaseOneReached(sceneStartControl50)) {
                                            "scene-start-burst-drain"
                                        } else {
                                            "forced-fallback-scene-start-burst-drain-no-control50"
                                        }
                                )
                            ) {
                                return
                            }
                            deferredSceneStartEventDeltaPending = false
                            deferredSceneStartTabbedEventDeltaPending = true
                            sendDeferredSceneStartEventDelta()
                            client.traceBootstrap(
                                "world-send-deferred-completion-event-delta-after-scene-start name=$name " +
                                    "groups=1477,1430-root count=11 control50=$phaseOneReleaseControl50 " +
                                    "source=${
                                        if (sceneStartPhaseOneReached(sceneStartControl50)) {
                                            "scene-start-burst-drain"
                                        } else {
                                            "forced-fallback-scene-start-burst-drain-no-control50"
                                        }
                                    }"
                            )
                        }
                        return
                    }
                    val phaseOneReleaseControl50 = sceneStartPhaseOneReleaseControl50(sceneStartControl50)
                    if (
                        deferredSceneStartEventDeltaPending &&
                        (
                            sceneStartPhaseOneReached(sceneStartControl50) ||
                                implicitForcedFallbackSceneStartPhaseOneReached(sceneStartControl50)
                            )
                    ) {
                        if (
                            deferForcedFallbackPhaseOneEventDeltaUntilLateReady(
                                control50 = sceneStartControl50,
                                source =
                                    if (sceneStartPhaseOneReached(sceneStartControl50)) {
                                        "scene-start-direct"
                                    } else {
                                        "forced-fallback-scene-start-direct-no-control50"
                                    }
                            )
                        ) {
                            return
                        }
                        deferredSceneStartEventDeltaPending = false
                        deferredSceneStartTabbedEventDeltaPending = true
                        sendDeferredSceneStartEventDelta()
                        client.traceBootstrap(
                            "world-send-deferred-completion-event-delta-after-scene-start name=$name " +
                                "groups=1477,1430-root count=11 control50=$phaseOneReleaseControl50 " +
                                "source=${
                                    if (sceneStartPhaseOneReached(sceneStartControl50)) {
                                        "scene-start-direct"
                                    } else {
                                        "forced-fallback-scene-start-direct-no-control50"
                                    }
                                }"
                        )
                        return
                    }
                    if (
                        deferredSceneStartTabbedEventDeltaPending &&
                        sceneStartPhaseTwoReached(sceneStartControl50)
                    ) {
                        deferredSceneStartTabbedEventDeltaPending = false
                        sendDeferredSceneStartTabbedEventDelta()
                        client.traceBootstrap(
                            "world-send-deferred-completion-event-delta-phase2-after-scene-start name=$name " +
                                "groups=1670,1671,1673 count=84 control50=$sceneStartControl50"
                        )
                        return
                    }
                    if (
                        deferredSceneStartLightTailScriptsPending &&
                        sceneStartPhaseThreeReached(sceneStartControl50)
                    ) {
                        deferredSceneStartLightTailScriptsPending = false
                        sendDeferredSceneStartLightTailScripts()
                        client.traceBootstrap(
                            "world-send-deferred-light-tail-scripts-after-scene-start name=$name " +
                                "scripts=11145,8420,8310 count=7 control50=$sceneStartControl50"
                        )
                        return
                    }
                    if (
                        deferredSceneStartFinalEventDeltaPending &&
                        !awaitingLateSceneStartReadySignal &&
                        sceneStartPhaseThreeReached(sceneStartControl50)
                    ) {
                        lateSceneStartReadySignalsAccepted = 0
                        awaitingLateSceneStartReadySignal = true
                        client.traceBootstrap(
                            "world-defer-deferred-completion-event-delta-phase3-until-late-ready name=$name " +
                                "groups=1430-extended,1465,slot-panels count=38 control50=$sceneStartControl50"
                        )
                        client.traceBootstrap(
                            "world-await-late-scene-ready-signal name=$name control50=$sceneStartControl50"
                        )
                        return
                    }
                    val forcedFallbackTickBlockReason = forcedFallbackTickSyncBlockReason()
                    if (forcedFallbackTickBlockReason != null) {
                        if (PacketRegistry.getRegistration(Side.SERVER, NoTimeout::class) != null) {
                            client.write(NoTimeout)
                            client.traceBootstrap(
                                "world-defer-tick-sync-keepalive name=$name packet=NO_TIMEOUT " +
                                    "reason=$forcedFallbackTickBlockReason"
                            )
                        }
                        client.traceBootstrap(
                            "world-defer-tick-sync name=$name reason=$forcedFallbackTickBlockReason"
                        )
                        return
                    }
                }
                if (pendingLateDefaultVarps > 0) {
                    client.traceBootstrap(
                        "world-allow-tick-sync name=$name pendingLateDefaultVarps=$pendingLateDefaultVarps"
                    )
                }
                sendWorldSyncFrame("tick")
            }
        }

        if (
            initialWorldSyncSent &&
            postInitialWorldSyncHoldTicks == 0 &&
            !awaitingMapBuildComplete &&
            !awaitingWorldReadySignal &&
            OpenNXT.config.lobbyBootstrap.sendServerTickEnd &&
            PacketRegistry.getRegistration(Side.SERVER, ServerTickEnd::class) != null
        ) {
            client.write(ServerTickEnd)
        }
    }
}
