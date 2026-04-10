from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

try:
    from tools.trace_947_application_resource_gate import (
        DEFAULT_DISPATCH_RVA,
        DEFAULT_GATE_RVA,
        DEFAULT_IDLE_SELECTOR_RVA,
        DEFAULT_RECORD_FINALIZE_RVA,
        DEFAULT_RECORD_CLOSE_RVA,
        DEFAULT_RECORD_OPEN_RVA,
        DEFAULT_QUEUE_LOOP_ITEM_RVA,
        DEFAULT_QUEUE_LOOP_POST_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE0_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE2_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE3_RVA,
        DEFAULT_QUEUE_HELPER_PREPARE_RVA,
        DEFAULT_RECORD_RESET_RVA,
        DEFAULT_RECORD_STATE_RVA,
        DEFAULT_TYPE0_PREPARE_PARSER_RVA,
        DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA,
        DEFAULT_TYPE0_PREPARE_STATUS_RVA,
        DEFAULT_TYPE0_SOURCE_OBJECT_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )
except ModuleNotFoundError:
    from trace_947_application_resource_gate import (
        DEFAULT_DISPATCH_RVA,
        DEFAULT_GATE_RVA,
        DEFAULT_IDLE_SELECTOR_RVA,
        DEFAULT_RECORD_FINALIZE_RVA,
        DEFAULT_RECORD_CLOSE_RVA,
        DEFAULT_RECORD_OPEN_RVA,
        DEFAULT_QUEUE_LOOP_ITEM_RVA,
        DEFAULT_QUEUE_LOOP_POST_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE0_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE2_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE3_RVA,
        DEFAULT_QUEUE_HELPER_PREPARE_RVA,
        DEFAULT_RECORD_RESET_RVA,
        DEFAULT_RECORD_STATE_RVA,
        DEFAULT_TYPE0_PREPARE_PARSER_RVA,
        DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA,
        DEFAULT_TYPE0_PREPARE_STATUS_RVA,
        DEFAULT_TYPE0_SOURCE_OBJECT_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )


class Trace947ApplicationResourceGateTest(unittest.TestCase):
    def test_archive_paths_are_timestamped(self) -> None:
        timestamp = datetime(2026, 3, 29, 22, 40, 0)

        self.assertEqual(
            Path("root/947-application-resource-gate-20260329-224000.jsonl"),
            archive_output_path(Path("root"), timestamp),
        )
        self.assertEqual(
            Path("root/947-application-resource-gate-20260329-224000.json"),
            archive_summary_path(Path("root"), timestamp),
        )

    def test_build_script_contains_key_rvas_and_events(self) -> None:
        script = build_script(
            gate_rva=DEFAULT_GATE_RVA,
            record_reset_rva=DEFAULT_RECORD_RESET_RVA,
            dispatch_rva=DEFAULT_DISPATCH_RVA,
            queue_handler_type3_rva=DEFAULT_QUEUE_HANDLER_TYPE3_RVA,
            record_state_rva=DEFAULT_RECORD_STATE_RVA,
            record_finalize_rva=DEFAULT_RECORD_FINALIZE_RVA,
            queue_handler_type2_rva=DEFAULT_QUEUE_HANDLER_TYPE2_RVA,
            queue_handler_type0_rva=DEFAULT_QUEUE_HANDLER_TYPE0_RVA,
            queue_helper_prepare_rva=DEFAULT_QUEUE_HELPER_PREPARE_RVA,
            type0_prepare_status_rva=DEFAULT_TYPE0_PREPARE_STATUS_RVA,
            type0_descriptor_status_rva=DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA,
            type0_source_object_rva=DEFAULT_TYPE0_SOURCE_OBJECT_RVA,
            type0_prepare_parser_rva=DEFAULT_TYPE0_PREPARE_PARSER_RVA,
            queue_loop_item_rva=DEFAULT_QUEUE_LOOP_ITEM_RVA,
            queue_loop_post_rva=DEFAULT_QUEUE_LOOP_POST_RVA,
            record_open_rva=DEFAULT_RECORD_OPEN_RVA,
            record_close_rva=DEFAULT_RECORD_CLOSE_RVA,
            suppress_record_close_call_rvas=[0x5946CF],
            idle_selector_rva=DEFAULT_IDLE_SELECTOR_RVA,
            seed_dispatch_rva=0x597230,
            idle_selector_queue_check_rva=0x7B5224,
            scheduler_global_rva=0xE57B60,
            resource_count=67,
            record_stride=0x1D8,
            force_record21_on_open=True,
            force_recorde_on_open=True,
            force_recorde_on_dispatch_return=True,
            force_finalize_on_dispatch_return=True,
            force_recordd_clear_on_dispatch_return=True,
            force_owner_stage_clear_when_drained=True,
            force_record_open_on_field1c=True,
            force_seed_dispatch_on_ptr178=True,
            force_recordd_ready_on_ptr178=True,
            force_recordd_ready_on_latch_clear=True,
            force_recordd_ready_on_close_suppression=True,
            force_selector_ready_on_ptr178=True,
            force_direct_dispatch_on_state1=True,
            force_dispatch_provider_accept=True,
            force_dispatch_result_metadata_fallback=True,
            force_post_dispatch_release_callback_fallback=True,
            force_owner_stage_open_on_state1=True,
            force_prepared_selector_ready=True,
            demote_hot_donezero_queued_record=True,
            force_idle_selector_latch_clear=True,
            force_idle_selector_timer_open=True,
            force_idle_selector_queue_empty=True,
            force_post_select_flag20_on_busy=True,
            force_post_select_status_retval=22,
            force_post_select_publication_success=True,
            suppress_post_select_latch_clear=True,
            force_recordstate_from_type0=True,
            force_type0_prepare_branch=True,
            force_item_payload_from_ptr178=True,
            force_type0_descriptor_status_retval=0x64,
            force_type0_childminus1_bypass=True,
            force_type0_field18_to_2=True,
            force_type0_raw_source_from_ptr178=True,
            force_type0_zlb_source_from_ptr178=True,
            force_type0_source_object_from_side_slots=True,
            force_type3_followon_on_post_state1=True,
            force_finalize_after_type3_on_post_state1=True,
            reenter_recordstate_after_type3_on_post_state1=True,
        )

        script_lower = script.lower()
        self.assertIn("0x59671f", script_lower)
        self.assertIn("0x595370", script_lower)
        self.assertIn("0x595530", script_lower)
        self.assertIn(hex(DEFAULT_QUEUE_HANDLER_TYPE3_RVA), script_lower)
        self.assertIn("0x597d10", script_lower)
        self.assertIn(hex(DEFAULT_RECORD_FINALIZE_RVA), script_lower)
        self.assertIn(hex(DEFAULT_QUEUE_HANDLER_TYPE2_RVA), script_lower)
        self.assertIn(hex(DEFAULT_QUEUE_HANDLER_TYPE0_RVA), script_lower)
        self.assertIn(hex(DEFAULT_QUEUE_HELPER_PREPARE_RVA), script_lower)
        self.assertIn(hex(DEFAULT_QUEUE_LOOP_ITEM_RVA), script_lower)
        self.assertIn(hex(DEFAULT_QUEUE_LOOP_POST_RVA), script_lower)
        self.assertIn("0x599060", script_lower)
        self.assertIn("0x599280", script_lower)
        self.assertIn("0x594270", script_lower)
        self.assertIn("0x7b5224", script_lower)
        self.assertIn("0xe57b60", script_lower)
        self.assertIn("resource-gate-unique", script)
        self.assertIn("resource-gate-return-unique", script)
        self.assertIn("record-reset-unique", script)
        self.assertIn("resource-dispatch-unique", script)
        self.assertIn("resource-dispatch-return-unique", script)
        self.assertIn("queue-handler-type3-unique", script)
        self.assertIn("record-state-unique", script)
        self.assertIn("queue-handler-type2-unique", script)
        self.assertIn("queue-handler-type0-unique", script)
        self.assertIn("queue-helper-prepare-entry-unique", script)
        self.assertIn("queue-helper-prepare-unique", script)
        self.assertIn("queue-helper-resolver-call-unique", script)
        self.assertIn("queue-helper-post-parser-type-compare-unique", script)
        self.assertIn("queue-helper-post-parser-class-unique", script)
        self.assertIn("queue-helper-post-parser-materialize-unique", script)
        self.assertIn("queue-helper-buffer-alloc-unique", script)
        self.assertIn("queue-helper-buffer-cleanup-entry-unique", script)
        self.assertIn("queue-helper-buffer-cleanup-unique", script)
        self.assertIn("queue-helper-copy-unique", script)
        self.assertIn("type0-handler-return-bridge-unique", script)
        self.assertIn("force-type0-handler-return-slot-restore", script)
        self.assertIn("type0-post-prepare-reinit-entry-unique", script)
        self.assertIn("type0-post-prepare-state-call-entry-unique", script)
        self.assertIn("type0-post-prepare-bind-entry-unique", script)
        self.assertIn("type0-post-prepare-type2-entry-unique", script)
        self.assertIn("callerRva: this.callerRva,", script)
        self.assertIn("type0-prepare-status-entry-unique", script)
        self.assertIn("type0-prepare-parser-entry-unique", script)
        self.assertIn("queue-loop-item-unique", script)
        self.assertIn("queue-loop-post-unique", script)
        self.assertIn("record-open-unique", script)
        self.assertIn("record-close-unique", script)
        self.assertIn("record-close-call-suppression-applied", script)
        self.assertIn("shouldSuppressRecordCloseCaller", script)
        self.assertIn("suppressClose: this.suppressClose", script)
        self.assertIn("ownerBefore: this.ownerBefore", script)
        self.assertIn("afterOwnerBeforeRestore: afterOwner", script)
        self.assertIn("function nonZeroValueLost(beforeValue, afterValue)", script)
        self.assertIn("return !ptr(value).isNull();", script)
        self.assertIn("const shouldRestoreOwnerCloseCounter =", script)
        self.assertIn("const shouldRestorePreparedRecordFields =", script)
        self.assertIn('this.callerRva === "0x595433"', script)
        self.assertIn("single-dispatch-post-close", script)
        self.assertIn("const restoredOwnerField114e8 =", script)
        self.assertIn(
            "this.ownerBefore.field114e8 + 1 < 0 ? 0 : this.ownerBefore.field114e8 + 1",
            script,
        )
        self.assertIn('suppressionPayload.restoredPreparedFields.push("ptr180");', script)
        self.assertIn('suppressionPayload.restoredPreparedFields.push("ptr1c8");', script)
        self.assertIn('suppressionPayload.restoredPreparedFields.push("word190");', script)
        self.assertIn('suppressionPayload.restoredPreparedFields.push("flag191");', script)
        self.assertIn("shouldRestoreOwnerCloseCounter", script)
        self.assertIn("ptr(this.owner).add(0x114e8).writeS32(restoredOwnerField114e8);", script)
        self.assertIn("ptr(this.recordBase).add(0x180).writePointer(ptr(this.before.ptr180));", script)
        self.assertIn("ptr(this.recordBase).add(0x1c8).writePointer(ptr(this.before.ptr1c8));", script)
        self.assertIn("afterOwnerRestore = afterOwner", script)
        self.assertIn("restoredOwnerField114e8", script)
        self.assertIn("restoredPreparedFields", script)
        self.assertIn("selector-ready-on-ptr178", script)
        self.assertIn("recordd-ready-on-latch-clear", script)
        self.assertIn("recordd-ready-on-close-suppression", script)
        self.assertIn("function tryForceRecordDReadyOnLatchClear(owner, index, reason)", script)
        self.assertIn(
            "function tryForceRecordDReadyOnCloseSuppression(owner, index, reason, ownerSnapshot, recordSnapshot)",
            script,
        )
        self.assertIn("forcedRecordDReadyOnLatchClear", script)
        self.assertIn("forcedRecordDReadyOnCloseSuppression", script)
        self.assertIn("totalForcedRecordDReadyOnLatchClear", script)
        self.assertIn("totalForcedRecordDReadyOnCloseSuppression", script)
        self.assertIn("forcedRecordDReadyOnLatchClearCountsByIndex", script)
        self.assertIn("forcedRecordDReadyOnCloseSuppressionCountsByIndex", script)
        self.assertIn("lastRecordDReadyOnLatchClearState", script)
        self.assertIn("lastRecordDReadyOnCloseSuppressionState", script)
        self.assertIn("before.ptr1c8SetCount !== 0", script)
        self.assertIn("const blockingStateIndices =", script)
        self.assertIn("candidateIndices.indexOf(item.index) === -1", script)
        self.assertIn("return item.state !== 1 && item.state !== 2;", script)
        self.assertIn("blockingStateIndices.length !== 0", script)
        self.assertIn("function collectActiveEligibleDispatchIndices(ownerSnapshot)", script)
        self.assertIn('entry.selectorReason !== "eligible"', script)
        self.assertIn("const state2Indices = stateIndices", script)
        self.assertIn("const activeEligibleIndices = collectActiveEligibleDispatchIndices(before);", script)
        self.assertIn("state1Indices.concat(state2Indices, preparedIndices, activeEligibleIndices)", script)
        self.assertIn("ptr(owner).add(0x11468 + index).writeU8(0);", script)
        self.assertIn("ptr(owner).add(0x11d4a).writeU8(1);", script)
        self.assertIn("dispatchProviderAcceptCompareAddress", script)
        self.assertIn("dispatch-provider-accept-unique", script)
        self.assertIn("dispatchResultMetadataDerefAddress", script)
        self.assertIn("dispatch-result-metadata-read-unique", script)
        self.assertIn("post-dispatch-release-callback-unique", script)
        self.assertIn('dispatchCacheQueryRva: "0x595710->0x6d2730"', script)
        self.assertIn("const forceDispatchProviderAccept = true;", script)
        self.assertIn("const forceDispatchResultMetadataFallback = true;", script)
        self.assertIn("forcePostDispatchReleaseCallbackFallback", script)
        self.assertIn("syntheticDispatchResultMetadata.add(0x24).writeS32(1);", script)
        self.assertIn("syntheticPostDispatchReleaseVtable", script)
        self.assertIn("release-vfunc-8", script)
        self.assertIn("0x5946cf", script_lower)
        self.assertIn("resource-idle-selector-unique", script)
        self.assertIn("resource-idle-selector-return-unique", script)
        self.assertIn("resource-idle-selector-queue-check-unique", script)
        self.assertIn("selection-loop-entry-unique", script)
        self.assertIn("post-select-status-unique", script)
        self.assertIn("post-select-success-unique", script)
        self.assertIn("post-select-commit-unique", script)
        self.assertIn("post-select-commit-return-unique", script)
        self.assertIn("ptr1c8-open-attempt-unique", script)
        self.assertIn('const ptr1c8OpenCallerRva = "0x597d81";', script)
        self.assertIn("post-select-flag20-on-busy", script)
        self.assertIn("post-select-status-retval-forced", script)
        self.assertIn("post-select-publication-success-forced", script)
        self.assertIn('const postSelectStatusCallerRva = "0x59686b";', script)
        self.assertIn('const postSelectSuccessAddress = moduleBase.add(0x596885);', script)
        self.assertIn("this.callerRva !== postSelectStatusCallerRva", script)
        self.assertIn("function normalizePostSelectRecordBase(recordPointerLike)", script)
        self.assertIn("this.recordBase = args[3];", script)
        self.assertIn('recordArgument: hexPtr(this.recordArgument),', script)
        self.assertIn("function tryForcePostSelectPublicationSuccess(owner, recordBase, index, reason)", script)
        self.assertIn("forcedPostSelectPublicationSuccess", script)
        self.assertIn("totalForcedPostSelectPublicationSuccess", script)
        self.assertIn("lastPostSelectSuccessState", script)
        self.assertIn("lastPostSelectCommitReturnState", script)
        self.assertIn("lastForcedPostSelectPublicationSuccessState", script)
        self.assertIn("lastSelectionLatchClearReturnState", script)
        self.assertIn("const slotBase = ptr(this.context.rbx);", script)
        self.assertIn("const recordBase = slotBase.add(8);", script)
        self.assertIn("selection-latch-clear-unique", script)
        self.assertIn("selection-latch-clear-return-unique", script)
        self.assertIn("post-select-latch-clear-suppressed", script)
        self.assertIn("force-finalize-on-dispatch-return", script)
        self.assertIn("totalForcedFinalizeOnDispatchReturn", script)
        self.assertIn("uniqueForcedFinalizeOnDispatchReturnStates", script)
        self.assertIn("forcedFinalizeOnDispatchReturnCountsByIndex", script)
        self.assertIn("lastForcedFinalizeOnDispatchReturnState", script)
        self.assertIn("force-recordstate-from-type0", script)
        self.assertIn("force-recordstate-from-type0-skipped", script)
        self.assertIn("force-type0-field18-to-2", script)
        self.assertIn("force-item-payload-from-ptr178", script)
        self.assertIn("force-type3-followon-on-post-state1", script)
        self.assertIn("function retagQueueItemTypeInPlace(itemPointer, forcedType)", script)
        self.assertIn("function snapshotBlobHeader(blobPointer)", script)
        self.assertIn("function snapshotPrepareSource(pointerValue)", script)
        self.assertIn("function snapshotPrepareBufferState(pointerValue)", script)
        self.assertIn("function snapshotType0SourceCandidate(pointerValue)", script)
        self.assertIn("owner === null ||", script)
        self.assertIn("index === undefined ||", script)
        self.assertIn("recordBase === null ||", script)
        self.assertIn("recordBase: hexPtr(recordBase)", script)
        self.assertIn("function snapshotQueueHelperResolvedObject(pointerValue)", script)
        self.assertIn("function tryReadPreviewHex(pointerValue, previewLength)", script)
        self.assertIn("previewHex: tryReadPreviewHex(source, 0x20)", script)
        self.assertIn("ptr10PreviewHex: tryReadPreviewHex(ptr10, 0x20)", script)
        self.assertIn("forcedCandidateAfterReturn", script)
        self.assertIn("retvalPreviewHex: tryReadPreviewHex(naturalSourcePointer, 0x20)", script)
        self.assertIn("function itemPayloadReady(itemPointer)", script)
        self.assertIn("function bytesToHex(bytes)", script)
        self.assertIn("ptr1a0: hexPtr(safeReadPointer(record.add(0x1a0)))", script)
        self.assertIn("ptr1a8: hexPtr(safeReadPointer(record.add(0x1a8)))", script)
        self.assertIn("field18: safeReadS32(record.add(0x18))", script)
        self.assertIn("ptr1a0SetCount", script)
        self.assertIn("ptr1a8SetCount", script)
        self.assertIn("qword98: safeReadU64(source.add(0x98))", script)
        self.assertIn("qwordA0: safeReadU64(source.add(0xA0))", script)
        self.assertIn("const type0PrepareParserAddress = moduleBase.add(0x58ce70);", script)
        self.assertIn('const type0PrepareParserCallerRva = "0x5989e5";', script)
        self.assertIn("const queueHelperPrepareResolverCallAddress = moduleBase.add(0x598a1a);", script)
        self.assertIn("const queueHelperPreparePostParserTypeCompareAddress = moduleBase.add(0x598a1d);", script)
        self.assertIn("const queueHelperPrepareExpectedTypeAddress = moduleBase.add(0x0c41420);", script)
        self.assertIn("const queueHelperPreparePostParserClassAddress = moduleBase.add(0x598a54);", script)
        self.assertIn("const queueHelperPreparePostParserMaterializeReturnAddress = moduleBase.add(0x598a6f);", script)
        self.assertIn("const queueHelperPreparePreCleanupSuppressionAddress = moduleBase.add(0x598a81);", script)
        self.assertIn('const queueHelperPrepareAllocCallerRva = "0x598a9a";', script)
        self.assertIn('const queueHelperPrepareCopyCallerRva = "0x598ad1";', script)
        self.assertIn('const type0PostPrepareReinitAddress = moduleBase.add(0x69d780);', script)
        self.assertIn('const type0PostPrepareStateCallAddress = moduleBase.add(0x6842a0);', script)
        self.assertIn('const type0PostPrepareBindAddress = moduleBase.add(0x681d40);', script)
        self.assertIn('const type0PostPrepareReinitCallerRva = "0x59879e";', script)
        self.assertIn('const type0PostPrepareStateCallCallerRva = "0x69d7f8";', script)
        self.assertIn('const type0PostPrepareBindCallerRva = "0x69d822";', script)
        self.assertIn('const type0PostPrepareType2CallerRva = "0x5987f9";', script)
        self.assertIn('"0x5988d6": true,', script)
        self.assertIn('"0x598aa6": true,', script)
        self.assertIn('"0x598ab9": true,', script)
        self.assertIn('"0x598ae0": true,', script)
        self.assertIn('"0x598aea": true', script)
        self.assertIn("function pointerWithinMainModule(pointerValue)", script)
        self.assertIn("ptr80: hexPtr(ptr80)", script)
        self.assertIn("ptr80InModule: pointerWithinMainModule(ptr80)", script)
        self.assertIn("ptr90: hexPtr(ptr90)", script)
        self.assertIn("ptr148: hexPtr(ptr148)", script)
        self.assertIn("ptr278: hexPtr(ptr278)", script)
        self.assertIn("activeType0PostPrepareReinitStatesByThread", script)
        self.assertIn("uniqueType0PostPrepareStateCallEntryStates", script)
        self.assertIn("lastType0PostPrepareStateCallEntryState", script)
        self.assertIn("const forceQueueHelperResolverSyntheticSuccess =", script)
        self.assertIn("const forceQueueHelperPostParserCleanupSuppression =", script)
        self.assertIn("const forceType0HandlerReturnSlotRestore =", script)
        self.assertIn("function getQueueHelperResolverSyntheticObject()", script)
        self.assertIn("function clearPrepareBufferState(pointerValue)", script)
        self.assertIn(
            "function tryForceQueueHelperResolverSyntheticSuccessAtCallsite(",
            script,
        )
        self.assertIn("force-queue-helper-resolver-synthetic-success", script)
        self.assertIn("force-queue-helper-post-parser-cleanup-suppression", script)
        self.assertIn("uniqueQueueHelperPrepareBufferAllocStates", script)
        self.assertIn("uniqueQueueHelperPrepareBufferCleanupStates", script)
        self.assertIn("uniqueQueueHelperPrepareCopyStates", script)
        self.assertIn('instrumentation: "callsite-rip-skip"', script)
        self.assertIn("context.rip = queueHelperPreparePostParserTypeCompareAddress;", script)
        self.assertIn("state.syntheticResolverBypass =", script)
        self.assertIn("inputBuffer: snapshotPrepareBufferState(this.inputPointer)", script)
        self.assertIn("statusValue: safeReadS32(this.statusPointer)", script)
        self.assertIn("type0-prepare-parser-unique", script)
        self.assertIn("retvalPointer: ptr(retval).toString()", script)
        self.assertIn("lastType0PrepareParserState", script)
        self.assertIn("force-type0-parser-single-byte-payload-to-1", script)
        self.assertIn("const forceType0ParserSingleBytePayloadTo1 =", script)
        self.assertIn("firstByteBefore === 0", script)
        self.assertIn("forcedType0ParserSingleBytePayloadTo1", script)
        self.assertIn("lastForcedType0ParserSingleBytePayloadTo1State", script)
        self.assertIn('reason: missingSource ? "missing-source" : "suspicious-small-source"', script)
        self.assertIn("currentSourceSnapshot = snapshotPrepareSource(context.rdx)", script)
        self.assertIn("function tryForceType0RawSourceFromPtr178(context, owner, itemPointer, index, callerRva)", script)
        self.assertIn("function findZlbHeaderInPtr178Blob(blobPointer)", script)
        self.assertIn("function tryForceType0ZlbSourceFromPtr178(context, owner, itemPointer, index, callerRva)", script)
        self.assertIn('reason: missingSource ? "missing-source" : "suspicious-small-source"', script)
        self.assertIn("currentRequestedLength", script)
        self.assertIn("currentSourceSnapshot", script)
        self.assertIn("currentRequestedLength > 0 && currentRequestedLength <= 4", script)
        self.assertIn("function chooseType0SourceObjectCandidate(sideObjectPointer)", script)
        self.assertIn("selectionReason", script)
        self.assertIn("siblingDelta98ToA0", script)
        self.assertIn("alternateSource", script)
        self.assertIn("ptr98-base-preferred-over-ptrA0-plus8", script)
        self.assertIn("entry38Word8", script)
        self.assertIn("entry70Word8", script)
        self.assertIn("function tryForceRecordStateFromType0(loopState, context)", script)
        self.assertIn("function tryForceItemPayloadFromPtr178(loopState)", script)
        self.assertIn("sourceField18Before", script)
        self.assertIn("promotedField18To2", script)
        self.assertIn("function snapshotType0HandlerReturnSlot(activeContext, stackPointerOverride)", script)
        self.assertIn("const type0HandlerReturnBridgeAddress = moduleBase.add(0x59890b);", script)
        self.assertIn("activeType0HandlerReturnSlotStatesByThread", script)
        self.assertIn("totalForcedType0HandlerReturnSlotRestores", script)
        self.assertIn("lastType0HandlerReturnBridgeState", script)
        self.assertIn("lastForcedType0HandlerReturnSlotRestoreState", script)
        self.assertIn("force-type0-raw-source-from-ptr178", script)
        self.assertIn("force-type0-zlb-source-from-ptr178", script)
        self.assertIn("force-type0-requested-length-from-source-header", script)
        self.assertIn("force-type0-source-object-from-side-slots", script)
        self.assertIn("force-type0-inner-source-from-side-wrapper", script)
        self.assertIn("function tryForceType0RequestedLengthFromSourceHeader(context, owner, itemPointer, index, callerRva)", script)
        self.assertIn(
            "function tryForceType0InnerSourceFromSideWrapper(context, owner, itemPointer, index, callerRva)",
            script,
        )
        self.assertIn("computeRequestedLengthFromParserHeader", script)
        self.assertIn("function scoreParserHeaderCandidate(candidate)", script)
        self.assertIn("candidate.score = scoreParserHeaderCandidate(candidate);", script)
        self.assertIn("candidates.sort((left, right) => {", script)
        self.assertIn("const forceType0RequestedLengthFromSourceHeader =", script)
        self.assertIn("const forceType0InnerSourceFromSideWrapper =", script)
        self.assertIn("currentRequestedLength !== 0", script)
        self.assertIn("promotedRequestedLength", script)
        self.assertIn("promotedRequestedLength <= 8 || promotedRequestedLength > 0x1000000", script)
        self.assertIn("const nativeRequestedLength =", script)
        self.assertIn("requestedLengthFromBlobHeader", script)
        self.assertIn("blobHeader.length > total164", script)
        self.assertIn("queueHelperPrepareNative(ptr(loopState.owner), blobPointer, nativeRequestedLength, itemPointer)", script)
        self.assertIn("state.field1CBefore =", script)
        self.assertIn("itemPointer.add(0x1c).writeS32(total164);", script)
        self.assertIn("state.promotedField1C = true;", script)
        self.assertIn("function pointerSpanCount(startPointer, endPointer, stride)", script)
        self.assertIn("queuePending11540Count", script)
        self.assertIn("queuePending11558Count", script)
        self.assertIn("recordStateNative(ptr(loopState.owner), ptr(loopState.itemPointer));", script)
        self.assertIn('reason: "payload-not-ready"', script)
        self.assertIn("skippedRecordStateFromType0CountsByIndex", script)
        self.assertIn("lastSkippedRecordStateFromType0State", script)
        self.assertIn('const type0SourceObjectCallerRva = "0x598742";', script)
        self.assertIn("activeType0HandlerStatesByThread", script)
        self.assertIn("forcedType0SourceObjectFromSideSlotsCountsByIndex", script)
        self.assertIn("totalForcedType0SourceObjectFromSideSlots", script)
        self.assertIn("lastForcedType0SourceObjectFromSideSlotsState", script)
        self.assertIn("activeQueueHelperPrepareStatesByThread", script)
        self.assertIn("const seenQueueHelperPrepareResolverCallStates = {};", script)
        self.assertIn('probeRva: "0x598a1a"', script)
        self.assertIn("resolverFunctionPointer", script)
        self.assertIn("entryPreviewHex", script)
        self.assertIn("lastQueueHelperPrepareResolverCallState = state;", script)
        self.assertIn("uniqueQueueHelperPrepareResolverCallStates:", script)
        self.assertIn("lastQueueHelperPrepareResolverCallState: lastQueueHelperPrepareResolverCallState,", script)
        self.assertIn("typeCompareMatched", script)
        self.assertIn("willEnterMaterialize", script)
        self.assertIn("lastQueueHelperPostParserTypeCompareState", script)
        self.assertIn("lastQueueHelperPostParserClassState", script)
        self.assertIn("lastQueueHelperPostParserMaterializeState", script)
        self.assertIn("arg6SlotBefore", script)
        self.assertIn("arg6SlotAfter", script)
        self.assertIn("reenteredRecordStateAfterType3OnPostState1CountsByIndex", script)
        self.assertIn("forcedType0Field18To2CountsByIndex", script)
        self.assertIn("totalReenteredRecordStateAfterType3OnPostState1", script)
        self.assertIn("dispatchRegisterBefore", script)
        self.assertIn("dispatchRegisterAfter", script)
        self.assertIn("context.rbx = ptr(1);", script)
        self.assertIn("retaggedItemAfter", script)
        self.assertIn("loopState.rawType !== 0", script)
        self.assertIn(
            "(postLoopState !== 0 && postLoopState !== 1 && postLoopState !== 2)",
            script,
        )
        self.assertIn("function collectPreparedDispatchIndices(ownerSnapshot)", script)
        self.assertIn("function collectPreparedSelectorReadyIndices(ownerSnapshot)", script)
        self.assertIn("function collectHotDoneZeroQueuedIndices(ownerSnapshot)", script)
        self.assertIn("function tryDemoteHotDoneZeroQueuedRecord(owner, reason)", script)
        self.assertIn("(before.stateCount === 0 && preparedIndices.length === 0)", script)
        self.assertIn("field180 !== 0", script)
        self.assertIn("prepared-selector-ready", script)
        self.assertIn("hot-donezero-record-demoted", script)
        self.assertIn("totalForcedPreparedSelectorReady", script)
        self.assertIn("totalDemotedHotDoneZeroQueuedRecords", script)
        self.assertIn("forcedPreparedSelectorReadyCountsByIndex", script)
        self.assertIn("demotedHotDoneZeroQueuedRecordCountsByIndex", script)
        self.assertIn("lastPreparedSelectorReadyState", script)
        self.assertIn("lastDemotedHotDoneZeroQueuedRecordState", script)
        self.assertIn("ptr(owner).add(0x11468 + index).writeU8(0);", script)
        self.assertIn("recordBase.add(0x0d).writeU8(0);", script)
        self.assertIn("recordBase.add(0x0f).writeU8(0);", script)
        self.assertIn("ptr(owner).add(0x11468 + hotIndex).writeU8(1);", script)
        self.assertIn("Math.ceil((effectiveTotal * 5) / 100)", script)
        self.assertIn("snapshot()", script)
        self.assertIn("function safeReadU32(address)", script)
        self.assertIn("function safeReadU16(address)", script)
        self.assertIn("function parseU64String(value)", script)
        self.assertIn("function callsiteRvaTextFromReturnAddress(address)", script)
        self.assertIn("function snapshotQueueItem(itemPointer)", script)
        self.assertIn("flag11d48", script)
        self.assertIn("flag11508", script)
        self.assertIn("flag11b58", script)
        self.assertIn("flag21", script)
        self.assertIn("flag28", script)
        self.assertIn("field170", script)
        self.assertIn("flag174", script)
        self.assertIn("field180", script)
        self.assertIn("ptr180", script)
        self.assertIn("ptr188", script)
        self.assertIn("qword28", script)
        self.assertIn("ptr30", script)
        self.assertIn("word190", script)
        self.assertIn("flag191", script)
        self.assertIn("owner11bc8", script)
        self.assertIn("schedulerGlobal", script)
        self.assertIn("timerGateOpen", script)
        self.assertIn("field1cNonZeroCount", script)
        self.assertIn("ptr178SetCount", script)
        self.assertIn("ptr1c8SetCount", script)
        self.assertIn("selectorEligibleCount", script)
        self.assertIn("selectorReasonCounts", script)
        self.assertIn("selectorPtr178Details", script)
        self.assertIn("queuedCount", script)
        self.assertIn("stateCount", script)
        self.assertIn("0x597230", script_lower)
        self.assertIn("totalForcedRecord21", script)
        self.assertIn("totalForcedRecordE", script)
        self.assertIn("totalForcedRecordEDispatchReturn", script)
        self.assertIn("totalForcedRecordDDispatchReturn", script)
        self.assertIn("totalForcedOwnerStageClear", script)
        self.assertIn("totalForcedSeedDispatch", script)
        self.assertIn("totalForcedRecordDReadyOnPtr178", script)
        self.assertIn("totalForcedSelectorReadyOnPtr178", script)
        self.assertIn("totalForcedDirectDispatch", script)
        self.assertIn("totalForcedOwnerStageOpen", script)
        self.assertIn("totalForcedIdleSelectorLatchClear", script)
        self.assertIn("totalForcedIdleSelectorTimerOpen", script)
        self.assertIn("totalForcedIdleSelectorQueueEmpty", script)
        self.assertIn("totalForcedPostSelectFlag20", script)
        self.assertIn("totalForcedPostSelectStatusRetval", script)
        self.assertIn("totalSuppressedPostSelectLatchClear", script)
        self.assertIn("totalForcedRecordStateFromType0", script)
        self.assertIn("totalForcedItemPayloadFromPtr178", script)
        self.assertIn("totalForcedType3FollowonOnPostState1", script)
        self.assertIn("totalForcedFinalizeAfterType3OnPostState1", script)
        self.assertIn("totalRecordResetCalls", script)
        self.assertIn("totalRecordOpenCalls", script)
        self.assertIn("totalRecordCloseCalls", script)
        self.assertIn("totalQueueHandlerType3Calls", script)
        self.assertIn("totalQueueHandlerType2Calls", script)
        self.assertIn("totalQueueHandlerType0Calls", script)
        self.assertIn("totalQueueHelperPrepareCalls", script)
        self.assertIn("totalSelectionLoopEntryCalls", script)
        self.assertIn("totalPostSelectStatusCalls", script)
        self.assertIn("totalPostSelectCommitCalls", script)
        self.assertIn("totalPtr1c8OpenCalls", script)
        self.assertIn("totalSelectionLatchClearCalls", script)
        self.assertIn("dispatchCountsByIndex", script)
        self.assertIn("directDispatchCountsByIndex", script)
        self.assertIn("recordResetCountsByIndex", script)
        self.assertIn("recordResetCountsByCallerRva", script)
        self.assertIn("selectionLoopEntryCountsByIndex", script)
        self.assertIn("queueHandlerType3CountsByIndex", script)
        self.assertIn("recordOpenCountsByIndex", script)
        self.assertIn("recordCloseCountsByIndex", script)
        self.assertIn("recordCloseCountsByCallerRva", script)
        self.assertIn("ptr1c8OpenCountsByIndex", script)
        self.assertIn("selectionLatchClearCountsByIndex", script)
        self.assertIn("appliedRecordCloseCallSuppressions", script)
        self.assertIn("queueHandlerType2CountsByIndex", script)
        self.assertIn("queueHandlerType0CountsByIndex", script)
        self.assertIn("queueHelperPrepareCountsByIndex", script)
        self.assertIn("queueLoopCountsByIndex", script)
        self.assertIn("queueLoopCountsByRawType", script)
        self.assertIn("queueLoopCountsByPredictedHandler", script)
        self.assertIn("forcedDispatchReturnCountsByIndex", script)
        self.assertIn("forcedDirectDispatchCountsByIndex", script)
        self.assertIn("forcedRecordDReadyOnPtr178CountsByIndex", script)
        self.assertIn("forcedSelectorReadyOnPtr178CountsByIndex", script)
        self.assertIn("forcedRecordDClearCountsByIndex", script)
        self.assertIn("forcedRecordStateFromType0CountsByIndex", script)
        self.assertIn("forcedType0PrepareBranchCountsByIndex", script)
        self.assertIn("forcedItemPayloadFromPtr178CountsByIndex", script)
        self.assertIn("forcedType3FollowonOnPostState1CountsByIndex", script)
        self.assertIn("forcedFinalizeAfterType3OnPostState1CountsByIndex", script)
        self.assertIn("lastGateReturnState", script)
        self.assertIn("lastRecordResetState", script)
        self.assertIn("lastDispatchReturnState", script)
        self.assertIn("lastQueueHandlerType3State", script)
        self.assertIn("lastRecordOpenState", script)
        self.assertIn("lastRecordCloseState", script)
        self.assertIn("lastQueueHandlerType2State", script)
        self.assertIn("lastQueueHandlerType0State", script)
        self.assertIn("lastQueueHelperPrepareState", script)
        self.assertIn("lastQueueLoopItemState", script)
        self.assertIn("lastQueueLoopPostState", script)
        self.assertIn("lastIdleSelectorEntryForceState", script)
        self.assertIn("lastIdleSelectorQueueCheckState", script)
        self.assertIn("lastIdleSelectorReturnState", script)
        self.assertIn("lastSelectionLoopEntryState", script)
        self.assertIn("lastPostSelectStatusState", script)
        self.assertIn("lastPostSelectCommitState", script)
        self.assertIn("lastPtr1c8OpenState", script)
        self.assertIn("lastPostSelectFlag20State", script)
        self.assertIn("lastForcedPostSelectStatusRetvalState", script)
        self.assertIn("lastSelectionLatchClearState", script)
        self.assertIn("lastSuppressedPostSelectLatchClearState", script)
        self.assertIn("lastForcedRecordStateFromType0State", script)
        self.assertIn("lastForcedType0PrepareBranchState", script)
        self.assertIn("lastForcedItemPayloadFromPtr178State", script)
        self.assertIn("lastForcedType3FollowonOnPostState1State", script)
        self.assertIn("lastSeedDispatchForceState", script)
        self.assertIn("lastRecordDReadyOnPtr178State", script)
        self.assertIn("lastSelectorReadyOnPtr178State", script)
        self.assertIn("lastDirectDispatchForceState", script)
        self.assertIn("forcedRecord21", script)
        self.assertIn("forcedRecordE", script)
        self.assertIn("forcedRecordEOnDispatchReturn", script)
        self.assertIn("forcedRecordDOnDispatchReturn", script)
        self.assertIn("owner-stage-clear-when-drained", script)
        self.assertIn("lastOwnerStageForceState", script)
        self.assertIn("lastOwnerStageOpenState", script)
        self.assertIn("owner-seed-dispatch-on-ptr178", script)
        self.assertIn("recordd-ready-on-ptr178", script)
        self.assertIn("owner-direct-dispatch-on-state1", script)
        self.assertIn("owner-direct-dispatch-on-state1-skip", script)
        self.assertIn("owner-stage-open-on-state1", script)
        self.assertIn("idle-selector-entry-force", script)
        self.assertIn("seenDirectDispatchSkipStates", script)
        self.assertIn("retagQueueItemTypeInPlace", script)
        self.assertIn("force-type0-prepare-branch", script)
        self.assertIn("const tableSlotPointer = safeReadPointer(ptr(loopState.owner).add(0x10c10 + resourceIndex * 0x20));", script)
        self.assertIn("entryStateAddress.writeU8(0);", script)
        self.assertIn("this.forcedType0PrepareBranch = tryForceType0PrepareBranch(handlerLoopState);", script)
        self.assertIn("forcedType0PrepareBranch: this.forcedType0PrepareBranch || null,", script)
        self.assertIn("itemPayloadReady(loopState.itemPointer)", script)
        self.assertIn("payloadReadyAfter", script)
        self.assertIn("payloadReadyBefore", script)
        self.assertIn("stackReturnAddressBeforeRet", script)
        self.assertIn("entryStackPointer", script)
        self.assertIn("originalStackReturnAddress", script)
        self.assertIn("stackReturnAddressWasCorrupted", script)
        self.assertIn("finalStackReturnAddress", script)
        self.assertIn("force-queue-helper-return-slot-restore", script)
        self.assertIn("snapshotQueueHelperReturnSlot", script)
        self.assertIn("totalForcedQueueHelperReturnSlotRestores", script)
        self.assertIn("uniqueQueueHelperReturnSlotRestoreStates", script)
        self.assertIn("lastForcedQueueHelperReturnSlotRestoreState", script)
        self.assertIn("const forceQueueHelperReturnSlotRestore =", script)
        self.assertIn("uniqueQueueHelperPrepareBufferCleanupEntryStates", script)
        self.assertIn("lastQueueHelperPrepareBufferCleanupEntryState", script)
        self.assertIn("const sourceByte17 =", script)
        self.assertIn("let sourceField18 =", script)
        self.assertIn("const shouldPromoteByte17 =", script)
        self.assertIn("itemPointer.add(0x17).writeU8(1);", script)
        self.assertIn("state.promotedByte17 = true;", script)
        self.assertIn("state.sourceByte17After =", script)
        self.assertIn("state.field18Before =", script)
        self.assertIn("itemPointer.add(0x18).writeS32(2);", script)
        self.assertIn("state.promotedField18 = true;", script)
        self.assertIn("safeReadU8(ptr(loopState.itemPointer).add(0x17))", script)
        self.assertIn("safeReadS32(ptr(loopState.itemPointer).add(0x18))", script)
        self.assertIn("sourceField18 === 2", script)
        self.assertIn("(loopStateValue === 0 || loopStateValue === 1 || loopStateValue === 2)", script)
        self.assertIn("(loopState.rawType !== 0 && loopState.rawType !== 1)", script)
        self.assertIn("(postLoopState !== 0 && postLoopState !== 1 && postLoopState !== 2)", script)
        self.assertIn("syntheticType0RecordStateBridge = {", script)
        self.assertIn("synthetic-recordstate-postopen-success-skip", script)
        self.assertIn("this.context.rip = recordStatePostOpenCallAddress.add(5);", script)
        self.assertIn("const forcedItemPayload = tryForceItemPayloadFromPtr178(loopState);", script)
        self.assertIn("const retaggedItem = retagQueueItemTypeInPlace(loopState.itemPointer, 1);", script)
        self.assertIn("recordStateNative(ptr(loopState.owner), ptr(loopState.itemPointer));", script)
        self.assertIn("state.recordStateInvoked = true;", script)
        self.assertIn("state.ptr1c8Opened =", script)
        self.assertIn("const forcedRecordState = tryForceRecordStateFromType0(loopState, this.context);", script)
        self.assertIn("const handlerLoopState = {", script)
        self.assertIn("this.forcedItemPayload = tryForceItemPayloadFromPtr178(handlerLoopState);", script)
        self.assertIn("this.forcedRecordState = tryForceRecordStateFromType0(handlerLoopState, this.context);", script)
        self.assertIn("forcedItemPayload: this.forcedItemPayload || null,", script)
        self.assertIn("forcedRecordState: this.forcedRecordState || null,", script)
        self.assertIn("queueHandlerType3Native(recordBase)", script)
        self.assertIn("queueHelperPrepareNative", script)
        self.assertIn("queueHelperPrepareRva", script)
        self.assertIn("uniqueQueueHelperPrepareStates", script)
        self.assertIn("recordFinalizeNative(ptr(loopState.owner), recordBase);", script)
        self.assertIn("const queuedIndices = before && before.queuedIndices ? before.queuedIndices.slice() : [];", script)
        self.assertIn("const stateIndices = before && before.stateIndices ? before.stateIndices.slice() : [];", script)


if __name__ == "__main__":
    unittest.main()
