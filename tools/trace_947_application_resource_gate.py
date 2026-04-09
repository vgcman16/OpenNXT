from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import frida
    FRIDA_IMPORT_ERROR = None
except Exception as frida_import_error:  # pragma: no cover - exercised on locked-down Windows hosts
    frida = None
    FRIDA_IMPORT_ERROR = frida_import_error


DEFAULT_OUTPUT_ROOT = Path(
    r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm\data\debug\application-resource-gate-947"
)
DEFAULT_GATE_RVA = 0x59671F
DEFAULT_RECORD_RESET_RVA = 0x595370
DEFAULT_DISPATCH_RVA = 0x595530
DEFAULT_QUEUE_HANDLER_TYPE3_RVA = 0x597070
DEFAULT_RECORD_STATE_RVA = 0x597D10
DEFAULT_RECORD_FINALIZE_RVA = 0x597FD0
DEFAULT_QUEUE_HANDLER_TYPE2_RVA = 0x598DE0
DEFAULT_QUEUE_HANDLER_TYPE0_RVA = 0x598370
DEFAULT_QUEUE_HELPER_PREPARE_RVA = 0x598930
DEFAULT_TYPE0_PREPARE_STATUS_RVA = 0x6A0430
DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA = 0x69FDD0
DEFAULT_TYPE0_SOURCE_OBJECT_RVA = 0x6A0120
DEFAULT_TYPE0_PREPARE_PARSER_RVA = 0x58CE70
DEFAULT_QUEUE_LOOP_ITEM_RVA = 0x59660A
DEFAULT_QUEUE_LOOP_POST_RVA = 0x5966BA
DEFAULT_RECORD_OPEN_RVA = 0x599060
DEFAULT_RECORD_CLOSE_RVA = 0x599280
DEFAULT_IDLE_SELECTOR_RVA = 0x594270
DEFAULT_IDLE_SELECTOR_QUEUE_CHECK_RVA = 0x7B5224
DEFAULT_POST_SELECT_STATUS_RVA = 0x6CC2B0
DEFAULT_POST_SELECT_COMMIT_RVA = 0x596896
DEFAULT_POST_SELECT_LATCH_CLEAR_RVA = 0x596554
DEFAULT_SEED_DISPATCH_RVA = 0x597230
DEFAULT_SCHEDULER_GLOBAL_RVA = 0xE57B60
DEFAULT_RESOURCE_COUNT = 67
DEFAULT_RECORD_STRIDE = 0x1D8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Trace the 947 application-resource splash loop with Frida."
    )
    parser.add_argument("--pid", type=int, help="Target rs2client.exe PID")
    parser.add_argument(
        "--process-name",
        default=None,
        help="Wait for the newest process with this name and attach to it",
    )
    parser.add_argument(
        "--wait-timeout-seconds",
        type=float,
        default=30.0,
        help="How long to wait for --process-name before failing",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=0.5,
        help="Polling interval for --process-name mode",
    )
    parser.add_argument(
        "--ignore-existing-processes",
        action="store_true",
        help="Only attach to a process that appears after this tracer starts",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=15.0,
        help="How long to keep the hooks attached",
    )
    parser.add_argument(
        "--gate-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_GATE_RVA,
        help="Outer splash resource gate RVA (default: 0x59671f)",
    )
    parser.add_argument(
        "--record-reset-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_RESET_RVA,
        help="Record reset/refresh helper RVA (default: 0x595370)",
    )
    parser.add_argument(
        "--dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_DISPATCH_RVA,
        help="Per-resource dispatch RVA (default: 0x595530)",
    )
    parser.add_argument(
        "--record-state-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_STATE_RVA,
        help="Per-record state transition RVA (default: 0x597d10)",
    )
    parser.add_argument(
        "--record-finalize-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_FINALIZE_RVA,
        help="Post-state finalize RVA (default: 0x597fd0)",
    )
    parser.add_argument(
        "--queue-handler-type3-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_QUEUE_HANDLER_TYPE3_RVA,
        help="Queue type-3 handler RVA (default: 0x597070)",
    )
    parser.add_argument(
        "--queue-handler-type2-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_QUEUE_HANDLER_TYPE2_RVA,
        help="Queue type-2 handler RVA (default: 0x598de0)",
    )
    parser.add_argument(
        "--queue-handler-type0-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_QUEUE_HANDLER_TYPE0_RVA,
        help="Queue type-0 handler RVA (default: 0x598370)",
    )
    parser.add_argument(
        "--queue-helper-prepare-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_QUEUE_HELPER_PREPARE_RVA,
        help="Queue payload-prepare helper RVA (default: 0x598930)",
    )
    parser.add_argument(
        "--type0-prepare-status-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_TYPE0_PREPARE_STATUS_RVA,
        help="Type-0 handler status helper RVA before 0x598930 (default: 0x6a0430)",
    )
    parser.add_argument(
        "--type0-descriptor-status-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA,
        help="Type-0 descriptor/status helper RVA before 0x598930 (default: 0x69fdd0)",
    )
    parser.add_argument(
        "--type0-source-object-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_TYPE0_SOURCE_OBJECT_RVA,
        help="Type-0 source-object helper RVA passed into 0x598930 (default: 0x6a0120)",
    )
    parser.add_argument(
        "--type0-prepare-parser-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_TYPE0_PREPARE_PARSER_RVA,
        help="Type-0 payload parser RVA called by 0x598930 (default: 0x58ce70)",
    )
    parser.add_argument(
        "--queue-loop-item-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_QUEUE_LOOP_ITEM_RVA,
        help="Queue-loop pre-reset snapshot RVA (default: 0x59660a)",
    )
    parser.add_argument(
        "--queue-loop-post-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_QUEUE_LOOP_POST_RVA,
        help="Queue-loop post-handler snapshot RVA (default: 0x5966ba)",
    )
    parser.add_argument(
        "--record-open-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_OPEN_RVA,
        help="Record DB-open helper RVA (default: 0x599060)",
    )
    parser.add_argument(
        "--record-close-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_CLOSE_RVA,
        help="Record DB-close helper RVA (default: 0x599280)",
    )
    parser.add_argument(
        "--suppress-record-close-call-rva",
        dest="suppress_record_close_call_rvas",
        type=lambda value: int(value, 0),
        action="append",
        default=[],
        help="NOP a specific caller-side call instruction that invokes the record-close helper as a late-attach smoke test (repeatable)",
    )
    parser.add_argument(
        "--idle-selector-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_IDLE_SELECTOR_RVA,
        help="Owner idle-selector RVA (default: 0x594270)",
    )
    parser.add_argument(
        "--seed-dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_SEED_DISPATCH_RVA,
        help="Owner queue/state seed RVA (default: 0x597230)",
    )
    parser.add_argument(
        "--idle-selector-queue-check-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_IDLE_SELECTOR_QUEUE_CHECK_RVA,
        help="Idle-selector owner+0x11bc8 queue check RVA (default: 0x7b5224)",
    )
    parser.add_argument(
        "--scheduler-global-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_SCHEDULER_GLOBAL_RVA,
        help="Global scheduler qword RVA used by the idle-selector timer gate (default: 0xe57b60)",
    )
    parser.add_argument(
        "--resource-count",
        type=int,
        default=DEFAULT_RESOURCE_COUNT,
        help="Number of resource records in the splash loop",
    )
    parser.add_argument(
        "--record-stride",
        type=lambda value: int(value, 0),
        default=DEFAULT_RECORD_STRIDE,
        help="Stride between resource records (default: 0x1d8)",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directory for JSON artifacts",
    )
    parser.add_argument(
        "--skip-snapshot",
        action="store_true",
        help="Do not call script.exports_sync.snapshot() at the end of the trace window",
    )
    parser.add_argument(
        "--force-record21-on-open",
        action="store_true",
        help="When a record opens ptr1c8 but leaves +0x20/+0x21 unset, force +0x21=1 as a smoke test",
    )
    parser.add_argument(
        "--force-recorde-on-open",
        action="store_true",
        help="When a record has ptr1c8 and still looks stalled, force +0x0e=1 to suppress redispatch as a smoke test",
    )
    parser.add_argument(
        "--force-recorde-on-dispatch-return",
        action="store_true",
        help="When a dispatched record returns with ptr1c8 but still has +0x0e unset, force +0x0e=1 on dispatch return as a smoke test",
    )
    parser.add_argument(
        "--force-finalize-on-dispatch-return",
        action="store_true",
        help="When a dispatched ptr178-backed hot record stalls with field170=0/1 and no ptr180/ptr188 yet, invoke the native 0x597fd0 finalize helper as a smoke test",
    )
    parser.add_argument(
        "--force-recordd-clear-on-dispatch-return",
        action="store_true",
        help="When a dispatched record returns complete (+0x0e != 0), clear +0x0d so owner+0x11d4a can drain as a smoke test",
    )
    parser.add_argument(
        "--force-owner-stage-clear-when-drained",
        action="store_true",
        help="When active and inflight record sets are both empty, clear owner+0x11b58, owner+0x11d49, and owner+0x11d4a as a smoke test",
    )
    parser.add_argument(
        "--force-record-open-on-field1c",
        action="store_true",
        help="When the first gate sees configured records but zero ptr178/ptr1c8/state, invoke the native 0x599060 record-open helper for those field1c-backed records as a smoke test",
    )
    parser.add_argument(
        "--force-seed-dispatch-on-ptr178",
        action="store_true",
        help="When the splash loop is stuck on ptr178-backed records with no ptr1c8/state bridge yet, invoke the native 0x597230 seed path as a smoke test, preferring the hot queued/active record",
    )
    parser.add_argument(
        "--force-recordd-ready-on-ptr178",
        action="store_true",
        help="When ptr178-backed records never get the outer-scan +0x0d ready byte, set +0x0d=1 and owner+0x11d4a=1 as a smoke test",
    )
    parser.add_argument(
        "--force-recordd-ready-on-latch-clear",
        action="store_true",
        help="When the late hot selected record hits 0x596554 with ptr178 ready but still never carries into the next scan, clear owner+0x11468[index] and set +0x0d there as a smoke test",
    )
    parser.add_argument(
        "--force-recordd-ready-on-close-suppression",
        action="store_true",
        help="When bulk-close suppression preserves the hot ptr178 record but it still never re-enters dispatch, set +0x0d there as a smoke test",
    )
    parser.add_argument(
        "--force-selector-ready-on-ptr178",
        action="store_true",
        help="When ptr178-backed records are stuck only because done168/pct are still below the selector threshold, satisfy that 5 percent gate as a smoke test",
    )
    parser.add_argument(
        "--force-direct-dispatch-on-state1",
        action="store_true",
        help="When loop-state=1/2 or already-active selector-eligible records are stalled before ptr1c8/state publication, re-enter the native 0x595530 dispatch path for those indices as a smoke test",
    )
    parser.add_argument(
        "--force-dispatch-provider-accept",
        action="store_true",
        help="When the 0x595530 provider-accept compare rejects the cache worker before it reaches the ptr178 SQL query, force the expected provider token as a smoke test",
    )
    parser.add_argument(
        "--force-dispatch-result-metadata-fallback",
        action="store_true",
        help="When the 0x595530 cache worker reaches 0x5957b1 with a null metadata pointer at [rsp+0x170], inject a synthetic metadata descriptor as a smoke test",
    )
    parser.add_argument(
        "--force-post-dispatch-release-callback-fallback",
        action="store_true",
        help="When the 0x5966de/0x5966f8 post-dispatch release callbacks resolve to null or tiny targets, swap in a synthetic no-op vtable as a smoke test",
    )
    parser.add_argument(
        "--force-owner-stage-open-on-state1",
        action="store_true",
        help="When loop-state=1 entries exist but owner+0x11b48/0x11d49 are still closed, set both bytes to 1 as a smoke test",
    )
    parser.add_argument(
        "--force-prepared-selector-ready",
        action="store_true",
        help="When ptr1c8+ptr180 prepared records are stuck behind done=0 or owner+0x11468[index], satisfy the selector-ready gate and clear the per-index latch as a smoke test",
    )
    parser.add_argument(
        "--demote-hot-donezero-queued-record",
        action="store_true",
        help="When one queued ptr178-backed record is still done=0 while sibling records are already selector-eligible, clear its +0x0d/+0x0f bytes so the owner scan can advance as a smoke test",
    )
    parser.add_argument(
        "--force-idle-selector-latch-clear",
        action="store_true",
        help="Before 0x594270 runs, clear owner+0x11b58 so the selector cannot short-circuit on its closed latch",
    )
    parser.add_argument(
        "--force-idle-selector-timer-open",
        action="store_true",
        help="Before 0x594270 runs, clear owner+0x11b50 so the selector timer gate stays open",
    )
    parser.add_argument(
        "--force-idle-selector-queue-empty",
        action="store_true",
        help="When 0x594270 checks owner+0x11bc8, force the queue-check helper to return empty as a smoke test",
    )
    parser.add_argument(
        "--force-post-select-flag20-on-busy",
        action="store_true",
        help="When the selected record falls into the busy branch with ptr178 still present, set +0x20=1 and clear +0x16c as a smoke test",
    )
    parser.add_argument(
        "--force-post-select-status-retval",
        type=lambda value: int(value, 0),
        default=None,
        help="Late-attach smoke test: override the filtered 0x59686b helper-status retval for valid selected records",
    )
    parser.add_argument(
        "--force-post-select-publication-success",
        action="store_true",
        help="When a selected record reaches post-select with ptr178+ptr180 but never publishes, force +0x170=0/+0x174=1 and clear +0x16c as a smoke test",
    )
    parser.add_argument(
        "--suppress-post-select-latch-clear",
        action="store_true",
        help="Late-attach smoke test: skip the 0x596554 owner+0x11468[index]=0 clear so a selected record stays queued after post-select commit",
    )
    parser.add_argument(
        "--force-recordstate-from-type0",
        action="store_true",
        help="When a live queue type-0 item targets a ptr178-backed record lacking ptr1c8, retag the real queue item to type 1 so the native queue dispatch reaches record-state as a smoke test",
    )
    parser.add_argument(
        "--force-type0-prepare-branch",
        action="store_true",
        help="When a live queue type-0 item is already ptr178-backed but skips the native 0x598742 prepare path because its old entry-state byte is nonzero, zero that entry-state byte before the handler reads it as a smoke test",
    )
    parser.add_argument(
        "--force-item-payload-from-ptr178",
        action="store_true",
        help="When a live queue item has byte17=1 and a ptr178-backed record but no payload buffer yet, invoke the native 0x598930 payload-prepare helper on the current item as a smoke test",
    )
    parser.add_argument(
        "--force-type0-descriptor-status-retval",
        type=lambda value: int(value, 0),
        default=None,
        help="Late-attach smoke test: override the filtered 0x69fdd0 descriptor/status helper retval at the natural 0x598565 caller site",
    )
    parser.add_argument(
        "--force-type0-childminus1-bypass",
        action="store_true",
        help="Late-attach smoke test: at the 0x5986a4 compare gate, set item byte17=1 for child=-1 type-0 items so the natural mismatch bypass can survive",
    )
    parser.add_argument(
        "--force-type0-field18-to-2",
        action="store_true",
        help="Late-attach smoke test: when a live ptr178-backed type-0 item already has byte17=1 but field18 is still 1, promote field18 to 2 before the synthetic record-state bridge gate",
    )
    parser.add_argument(
        "--force-type0-raw-source-from-ptr178",
        action="store_true",
        help="When the natural type-0 prepare helper arrives with source=NULL and len=0, feed the raw ptr178 blob and its container length directly into 0x598930 as a smoke test",
    )
    parser.add_argument(
        "--force-type0-zlb-source-from-ptr178",
        action="store_true",
        help="When the natural type-0 prepare helper arrives with source=NULL and len=0, scan the ptr178 blob for an inlined ZLB1 header and feed that slice into 0x598930 as a smoke test",
    )
    parser.add_argument(
        "--force-type0-requested-length-from-source-header",
        action="store_true",
        help="When the natural 0x598930 type-0 prepare helper arrives with a non-null source but len=0, promote the requested length from source+0x4 as a smoke test",
    )
    parser.add_argument(
        "--force-type0-source-object-from-side-slots",
        action="store_true",
        help="When the natural 0x6a0120 type-0 source-object helper returns NULL at the 0x598742 caller site, seed side+0x88 from side+0xa0 or side+0x98 and return that candidate as a smoke test",
    )
    parser.add_argument(
        "--force-type0-inner-source-from-side-wrapper",
        action="store_true",
        help="When 0x598930 arrives with source NULL or a suspicious string-like source, pull the parser container from the record ptr1a8 side-wrapper inner pointer (+0x98->+0x18 or +0xa0->+0x10) as a smoke test",
    )
    parser.add_argument(
        "--force-type0-parser-single-byte-payload-to-1",
        action="store_true",
        help="When the natural 0x58ce70 parser produces a single-byte payload equal to 0 at the 0x5989e5 caller site, rewrite that payload byte to 1 as a type-selection smoke test",
    )
    parser.add_argument(
        "--force-queue-helper-resolver-synthetic-success",
        action="store_true",
        help="When 0x598930 reaches the virtual resolver call at 0x598a1a, skip the native resolver call, seed a minimal resolved object, and resume at the compare site as a smoke test",
    )
    parser.add_argument(
        "--force-queue-helper-post-parser-cleanup-suppression",
        action="store_true",
        help="When 0x598930 reaches the post-materialize copy point at 0x598a81, clear the temporary parser buffers so the trailing 0x02dcb0 cleanup calls become no-ops as a smoke test",
    )
    parser.add_argument(
        "--force-queue-helper-return-slot-restore",
        action="store_true",
        help="When 0x598930 is about to return and its original entry-time stack return slot has been clobbered, restore the saved return address as a smoke test",
    )
    parser.add_argument(
        "--force-type0-handler-return-slot-restore",
        action="store_true",
        help="When the type-0 handler is about to execute its final ret at 0x59890b and its entry-time return slot has been clobbered, restore the saved return address as a smoke test",
    )
    parser.add_argument(
        "--force-type3-followon-on-post-state1",
        action="store_true",
        help="When queue-loop post state shows flag21=1 with ptr1c8 set but flag20 still clear, invoke the native 0x597070 follow-on helper as a smoke test",
    )
    parser.add_argument(
        "--force-finalize-after-type3-on-post-state1",
        action="store_true",
        help="After forcing the native 0x597070 follow-on helper on a queue-loop post state, invoke 0x597fd0 when it returns true as a smoke test",
    )
    parser.add_argument(
        "--reenter-recordstate-after-type3-on-post-state1",
        action="store_true",
        help="After forcing the native 0x597070 follow-on helper and optional 0x597fd0 finalize step, re-enter the native 0x597d10 record-state consumer with the same queue item as a smoke test",
    )
    args = parser.parse_args()
    if args.pid is None and not args.process_name:
        parser.error("Either --pid or --process-name is required")
    return args


def query_process_ids(process_name: str | None) -> set[int]:
    if not process_name:
        return set()
    command = (
        f"Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue | "
        "Sort-Object StartTime -Descending | Select-Object Id | ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    if not stdout or stdout == "null":
        return set()
    payload = json.loads(stdout)
    if isinstance(payload, dict):
        return {int(payload["Id"])}
    if isinstance(payload, list):
        return {int(item["Id"]) for item in payload if isinstance(item, dict) and "Id" in item}
    return set()


def resolve_pid(args: argparse.Namespace) -> int:
    if args.pid is not None:
        return args.pid
    ignored_pids: set[int] = set()
    if args.ignore_existing_processes:
        ignored_pids = query_process_ids(args.process_name)
    deadline = time.time() + args.wait_timeout_seconds
    while time.time() < deadline:
        current_pids = query_process_ids(args.process_name)
        attachable_pids = [pid for pid in current_pids if pid not in ignored_pids]
        if attachable_pids:
            return attachable_pids[0]
        time.sleep(args.poll_interval_seconds)
    raise RuntimeError(
        f"Timed out waiting for process {args.process_name!r} after {args.wait_timeout_seconds:.1f}s"
    )


def build_script(
    *,
    gate_rva: int,
    record_reset_rva: int,
    dispatch_rva: int,
    queue_handler_type3_rva: int,
    record_state_rva: int,
    record_finalize_rva: int,
    queue_handler_type2_rva: int,
    queue_handler_type0_rva: int,
    queue_helper_prepare_rva: int,
    type0_prepare_status_rva: int,
    type0_descriptor_status_rva: int,
    type0_source_object_rva: int,
    type0_prepare_parser_rva: int,
    queue_loop_item_rva: int,
    queue_loop_post_rva: int,
    record_open_rva: int,
    record_close_rva: int,
    suppress_record_close_call_rvas: list[int],
    idle_selector_rva: int,
    seed_dispatch_rva: int,
    idle_selector_queue_check_rva: int,
    scheduler_global_rva: int,
    resource_count: int,
    record_stride: int,
    force_record21_on_open: bool,
    force_recorde_on_open: bool,
    force_recorde_on_dispatch_return: bool,
    force_finalize_on_dispatch_return: bool,
    force_recordd_clear_on_dispatch_return: bool,
    force_owner_stage_clear_when_drained: bool,
    force_record_open_on_field1c: bool,
    force_seed_dispatch_on_ptr178: bool,
    force_recordd_ready_on_ptr178: bool,
    force_recordd_ready_on_latch_clear: bool,
    force_recordd_ready_on_close_suppression: bool,
    force_selector_ready_on_ptr178: bool,
    force_direct_dispatch_on_state1: bool,
    force_dispatch_provider_accept: bool,
    force_dispatch_result_metadata_fallback: bool,
    force_post_dispatch_release_callback_fallback: bool,
    force_owner_stage_open_on_state1: bool,
    force_prepared_selector_ready: bool,
    demote_hot_donezero_queued_record: bool,
    force_idle_selector_latch_clear: bool,
    force_idle_selector_timer_open: bool,
    force_idle_selector_queue_empty: bool,
    force_post_select_flag20_on_busy: bool,
    force_post_select_status_retval: int | None,
    force_post_select_publication_success: bool,
    suppress_post_select_latch_clear: bool,
    force_recordstate_from_type0: bool,
    force_type0_prepare_branch: bool,
    force_item_payload_from_ptr178: bool,
    force_type0_descriptor_status_retval: int | None,
    force_type0_childminus1_bypass: bool,
    force_type0_field18_to_2: bool,
    force_type3_followon_on_post_state1: bool,
    force_finalize_after_type3_on_post_state1: bool,
    force_type0_raw_source_from_ptr178: bool = False,
    force_type0_zlb_source_from_ptr178: bool = False,
    force_type0_requested_length_from_source_header: bool = False,
    force_type0_source_object_from_side_slots: bool = False,
    force_type0_inner_source_from_side_wrapper: bool = False,
    force_type0_parser_single_byte_payload_to_1: bool = False,
    force_queue_helper_resolver_synthetic_success: bool = False,
    force_queue_helper_post_parser_cleanup_suppression: bool = False,
    force_queue_helper_return_slot_restore: bool = False,
    force_type0_handler_return_slot_restore: bool = False,
    reenter_recordstate_after_type3_on_post_state1: bool = False,
) -> str:
    return (
        r"""
const mainModule = Process.enumerateModules()[0];
const moduleBase = mainModule.base;
const moduleEnd = moduleBase.add(mainModule.size);
const gateAddress = moduleBase.add(__GATE_RVA__);
const recordResetAddress = moduleBase.add(__RECORD_RESET_RVA__);
const dispatchAddress = moduleBase.add(__DISPATCH_RVA__);
const queueHandlerType3Address = moduleBase.add(__QUEUE_HANDLER_TYPE3_RVA__);
const recordStateAddress = moduleBase.add(__RECORD_STATE_RVA__);
const recordFinalizeAddress = moduleBase.add(__RECORD_FINALIZE_RVA__);
const queueHandlerType2Address = moduleBase.add(__QUEUE_HANDLER_TYPE2_RVA__);
const queueHandlerType0Address = moduleBase.add(__QUEUE_HANDLER_TYPE0_RVA__);
const queueHelperPrepareAddress = moduleBase.add(__QUEUE_HELPER_PREPARE_RVA__);
const type0PrepareStatusAddress = moduleBase.add(__TYPE0_PREPARE_STATUS_RVA__);
const type0DescriptorStatusAddress = moduleBase.add(__TYPE0_DESCRIPTOR_STATUS_RVA__);
const type0SourceObjectAddress = moduleBase.add(__TYPE0_SOURCE_OBJECT_RVA__);
const type0PrepareParserAddress = moduleBase.add(__TYPE0_PREPARE_PARSER_RVA__);
const queueHelperPrepareResolverCallAddress = moduleBase.add(0x598a1a);
const queueHelperPreparePostParserTypeCompareAddress = moduleBase.add(0x598a1d);
const queueHelperPrepareExpectedTypeAddress = moduleBase.add(0x0c41420);
const dispatchProviderAcceptCompareAddress = moduleBase.add(0x59566b);
const dispatchProviderAcceptExpectedAddress = moduleBase.add(0x0c41420);
const dispatchResultMetadataDerefAddress = moduleBase.add(0x5957b1);
const postDispatchReleaseCallbackAddress = moduleBase.add(0x5966de);
const postDispatchReleaseCleanupCallbackAddress = moduleBase.add(0x5966f8);
const queueHelperPreparePostParserClassAddress = moduleBase.add(0x598a54);
const queueHelperPreparePostParserMaterializeReturnAddress = moduleBase.add(0x598a6f);
const queueHelperPreparePreCleanupSuppressionAddress = moduleBase.add(0x598a81);
const queueHelperPrepareBufferAllocAddress = moduleBase.add(0x793b40);
const queueHelperPrepareBufferCleanupAddress = moduleBase.add(0x2dcb0);
const queueHelperPrepareCopyAddress = moduleBase.add(0x7b9c90);
const queueHelperPrepareReturnBridgeAddress = moduleBase.add(0x598c99);
const type0HandlerReturnBridgeAddress = moduleBase.add(0x59890b);
const type0PostPrepareReinitAddress = moduleBase.add(0x69d780);
const type0PostPrepareStateCallAddress = moduleBase.add(0x6842a0);
const type0PostPrepareBindAddress = moduleBase.add(0x681d40);
const queueLoopItemAddress = moduleBase.add(__QUEUE_LOOP_ITEM_RVA__);
const queueLoopPostAddress = moduleBase.add(__QUEUE_LOOP_POST_RVA__);
const recordOpenAddress = moduleBase.add(__RECORD_OPEN_RVA__);
const recordCloseAddress = moduleBase.add(__RECORD_CLOSE_RVA__);
const idleSelectorAddress = moduleBase.add(__IDLE_SELECTOR_RVA__);
const seedDispatchAddress = moduleBase.add(__SEED_DISPATCH_RVA__);
const idleSelectorQueueCheckAddress = moduleBase.add(__IDLE_SELECTOR_QUEUE_CHECK_RVA__);
const schedulerGlobalAddress = moduleBase.add(__SCHEDULER_GLOBAL_RVA__);
const selectionLoopEntryAddress = moduleBase.add(0x596110);
const postSelectStatusAddress = moduleBase.add(0x6cc2b0);
const postSelectStatusCallerRva = "0x59686b";
const postSelectSuccessAddress = moduleBase.add(0x596885);
const ptr1c8OpenAddress = moduleBase.add(0x6d2730);
const dispatchCacheQueryOpenCallerRva = "0x595710";
const ptr1c8OpenCallerRva = "0x597d81";
const type0DescriptorStatusCallerRva = "0x598565";
const type0CompareGateAddress = moduleBase.add(0x5986a4);
const recordStatePostOpenCallAddress = moduleBase.add(0x597dbe);
const postSelectCommitAddress = moduleBase.add(0x596896);
const postSelectLatchClearAddress = moduleBase.add(0x596554);
const postSelectLatchClearSkipAddress = moduleBase.add(0x59655f);
const directDispatch = new NativeFunction(dispatchAddress, 'void', ['pointer', 'int']);
const seedDispatch = new NativeFunction(seedDispatchAddress, 'void', ['pointer', 'int']);
const recordOpenNative = new NativeFunction(recordOpenAddress, 'bool', ['pointer']);
const queueHandlerType3Native = new NativeFunction(queueHandlerType3Address, 'uint8', ['pointer']);
const recordStateNative = new NativeFunction(recordStateAddress, 'void', ['pointer', 'pointer']);
const recordFinalizeNative = new NativeFunction(recordFinalizeAddress, 'void', ['pointer', 'pointer']);
const queueHelperPrepareNative = new NativeFunction(queueHelperPrepareAddress, 'bool', ['pointer', 'pointer', 'int', 'pointer']);
const resourceCount = __RESOURCE_COUNT__;
const recordStride = __RECORD_STRIDE__;
const suppressRecordCloseCallRvas = __SUPPRESS_RECORD_CLOSE_CALL_RVAS__;
const suppressRecordCloseCallerRvaSet = {};
const forcedPostSelectStatusRetval = __FORCE_POST_SELECT_STATUS_RETVAL__;
const forcedType0DescriptorStatusRetval = __FORCE_TYPE0_DESCRIPTOR_STATUS_RETVAL__;
const forceDispatchProviderAccept = __FORCE_DISPATCH_PROVIDER_ACCEPT__;
const forceDispatchResultMetadataFallback = __FORCE_DISPATCH_RESULT_METADATA_FALLBACK__;
const forcePostDispatchReleaseCallbackFallback =
  __FORCE_POST_DISPATCH_RELEASE_CALLBACK_FALLBACK__;
const forceType0RawSourceFromPtr178 = __FORCE_TYPE0_RAW_SOURCE_FROM_PTR178__;
const forceType0ZlbSourceFromPtr178 = __FORCE_TYPE0_ZLB_SOURCE_FROM_PTR178__;
const forceType0RequestedLengthFromSourceHeader = __FORCE_TYPE0_REQUESTED_LENGTH_FROM_SOURCE_HEADER__;
const forceType0SourceObjectFromSideSlots = __FORCE_TYPE0_SOURCE_OBJECT_FROM_SIDE_SLOTS__;
const forceType0InnerSourceFromSideWrapper = __FORCE_TYPE0_INNER_SOURCE_FROM_SIDE_WRAPPER__;
const forceType0ParserSingleBytePayloadTo1 = __FORCE_TYPE0_PARSER_SINGLE_BYTE_PAYLOAD_TO_1__;
const forceQueueHelperResolverSyntheticSuccess =
  __FORCE_QUEUE_HELPER_RESOLVER_SYNTHETIC_SUCCESS__;
const forceQueueHelperPostParserCleanupSuppression =
  __FORCE_QUEUE_HELPER_POST_PARSER_CLEANUP_SUPPRESSION__;
const forceQueueHelperReturnSlotRestore =
  __FORCE_QUEUE_HELPER_RETURN_SLOT_RESTORE__;
const forceType0HandlerReturnSlotRestore =
  __FORCE_TYPE0_HANDLER_RETURN_SLOT_RESTORE__;
const forceType0Field18To2 = __FORCE_TYPE0_FIELD18_TO_2__;
const forceFinalizeOnDispatchReturn = __FORCE_FINALIZE_ON_DISPATCH_RETURN__;
const TYPE0_PREPARE_CALLER_RVA = "0x598755";
const type0SourceObjectCallerRva = "0x598742";
const type0PrepareParserCallerRva = "0x5989e5";
const type0PostPrepareReinitCallerRva = "0x59879e";
const type0PostPrepareStateCallCallerRva = "0x69d7f8";
const type0PostPrepareBindCallerRva = "0x69d822";
const type0PostPrepareType2CallerRva = "0x5987f9";
const queueHelperPrepareAllocCallerRva = "0x598a9a";
const queueHelperPrepareCopyCallerRva = "0x598ad1";
const queueHelperPrepareCleanupCallerRvaSet = {
  "0x5988d6": true,
  "0x598aa6": true,
  "0x598ab9": true,
  "0x598ae0": true,
  "0x598aea": true
};
const TYPE0_ZLB_MAGIC = 0x01424c5a;
for (const callerRva of suppressRecordCloseCallRvas) {
  suppressRecordCloseCallerRvaSet["0x" + callerRva.toString(16)] = 1;
}

const seenGateStates = {};
const seenGateReturnStates = {};
const seenRecordResetStates = {};
const seenDispatchStates = {};
const seenDispatchReturnStates = {};
const seenQueueHandlerType3States = {};
const seenRecordStates = {};
const seenQueueHandlerType2States = {};
const seenQueueHandlerType0States = {};
const seenQueueHelperPrepareEntryStates = {};
const seenQueueHelperPrepareStates = {};
const seenQueueHelperPrepareResolverCallStates = {};
const seenQueueHelperResolverSyntheticSuccessStates = {};
const seenQueueHelperPostParserCleanupSuppressionStates = {};
const seenQueueHelperReturnSlotRestoreStates = {};
const seenQueueHelperPostParserTypeCompareStates = {};
const seenQueueHelperPostParserClassStates = {};
const seenQueueHelperPostParserMaterializeStates = {};
const seenQueueHelperPrepareBufferAllocStates = {};
const seenQueueHelperPrepareBufferCleanupEntryStates = {};
const seenQueueHelperPrepareBufferCleanupStates = {};
const seenQueueHelperPrepareCopyStates = {};
const seenType0HandlerReturnBridgeStates = {};
const seenType0HandlerReturnSlotRestoreStates = {};
const seenType0PostPrepareReinitEntryStates = {};
const seenType0PostPrepareReinitReturnStates = {};
const seenType0PostPrepareStateCallEntryStates = {};
const seenType0PostPrepareStateCallReturnStates = {};
const seenType0PostPrepareBindEntryStates = {};
const seenType0PostPrepareBindReturnStates = {};
const seenType0PostPrepareType2EntryStates = {};
const seenType0MaterializeStates = {};
const seenType0PrepareStatusEntryStates = {};
const seenType0PrepareStatusStates = {};
const seenType0DescriptorStatusStates = {};
const seenType0CompareGateStates = {};
const seenType0SourceObjectStates = {};
const seenType0PrepareParserEntryStates = {};
const seenType0PrepareParserStates = {};
const seenQueueLoopItemStates = {};
const seenQueueLoopPostStates = {};
const seenRecordOpenStates = {};
const seenRecordCloseStates = {};
const seenIdleSelectorStates = {};
const seenIdleSelectorReturnStates = {};
const seenIdleSelectorQueueCheckStates = {};
const seenHotDoneZeroQueuedDemotionStates = {};
const seenSelectionLoopEntryStates = {};
const seenPostSelectStatusStates = {};
const seenPostSelectSuccessStates = {};
const seenPostSelectCommitStates = {};
const seenPostSelectCommitReturnStates = {};
const seenPtr1c8OpenStates = {};
const seenDispatchProviderAcceptStates = {};
const seenDispatchResultMetadataStates = {};
const seenPostDispatchReleaseCallbackStates = {};
const seenDispatchCacheQueryStates = {};
const seenSelectionLatchClearStates = {};
const seenSelectionLatchClearReturnStates = {};
const seenForcedFinalizeOnDispatchReturnStates = {};
const seenDirectDispatchSkipStates = {};
let totalGateCalls = 0;
let totalRecordResetCalls = 0;
let totalDispatchCalls = 0;
let totalQueueHandlerType3Calls = 0;
let totalRecordStateCalls = 0;
let totalQueueHandlerType2Calls = 0;
let totalQueueHandlerType0Calls = 0;
let totalQueueHelperPrepareCalls = 0;
let totalType0MaterializeCalls = 0;
let totalType0PrepareStatusCalls = 0;
let totalType0DescriptorStatusCalls = 0;
let totalType0CompareGateCalls = 0;
let totalType0SourceObjectCalls = 0;
let totalQueueLoopItemCalls = 0;
let totalQueueLoopPostCalls = 0;
let totalRecordOpenCalls = 0;
let totalRecordCloseCalls = 0;
let totalIdleSelectorCalls = 0;
let totalSelectionLoopEntryCalls = 0;
let totalPostSelectStatusCalls = 0;
let totalPostSelectSuccessCalls = 0;
let totalPostSelectCommitCalls = 0;
let totalPtr1c8OpenCalls = 0;
let totalDispatchProviderAcceptCalls = 0;
let totalForcedDispatchProviderAccept = 0;
let totalDispatchResultMetadataReads = 0;
let totalForcedDispatchResultMetadataFallback = 0;
let totalPostDispatchReleaseCallbackCalls = 0;
let totalForcedPostDispatchReleaseCallbackFallback = 0;
let totalDispatchCacheQueryCalls = 0;
let totalSelectionLatchClearCalls = 0;
let totalForcedRecord21 = 0;
let totalForcedRecordE = 0;
let totalForcedRecordEDispatchReturn = 0;
let totalForcedFinalizeOnDispatchReturn = 0;
let totalForcedRecordDDispatchReturn = 0;
let totalForcedOwnerStageClear = 0;
let totalForcedRecordOpen = 0;
let totalForcedSeedDispatch = 0;
let totalForcedRecordDReadyOnPtr178 = 0;
let totalForcedRecordDReadyOnLatchClear = 0;
let totalForcedRecordDReadyOnCloseSuppression = 0;
let totalForcedSelectorReadyOnPtr178 = 0;
let totalForcedDirectDispatch = 0;
let totalForcedOwnerStageOpen = 0;
let totalForcedPreparedSelectorReady = 0;
let totalDemotedHotDoneZeroQueuedRecords = 0;
let totalForcedIdleSelectorLatchClear = 0;
let totalForcedIdleSelectorTimerOpen = 0;
let totalForcedIdleSelectorQueueEmpty = 0;
let totalForcedPostSelectFlag20 = 0;
let totalForcedPostSelectStatusRetval = 0;
let totalForcedPostSelectPublicationSuccess = 0;
let totalSuppressedPostSelectLatchClear = 0;
let totalForcedRecordStateFromType0 = 0;
let totalForcedType0PrepareBranch = 0;
let totalForcedItemPayloadFromPtr178 = 0;
let totalForcedType0ChildMinus1Bypass = 0;
let totalForcedType0Field18To2 = 0;
let totalForcedType0RawSourceFromPtr178 = 0;
let totalForcedType0ZlbSourceFromPtr178 = 0;
let totalForcedType0RequestedLengthFromSourceHeader = 0;
let totalForcedType0SourceObjectFromSideSlots = 0;
let totalForcedType0InnerSourceFromSideWrapper = 0;
let totalForcedType0ParserSingleBytePayloadTo1 = 0;
let totalForcedQueueHelperResolverSyntheticSuccess = 0;
let totalForcedQueueHelperPostParserCleanupSuppressions = 0;
let totalForcedQueueHelperReturnSlotRestores = 0;
let totalForcedType0HandlerReturnSlotRestores = 0;
let totalForcedType3FollowonOnPostState1 = 0;
let totalForcedFinalizeAfterType3OnPostState1 = 0;
let totalReenteredRecordStateAfterType3OnPostState1 = 0;
let lastGateState = null;
let lastGateReturnState = null;
let lastRecordResetState = null;
let lastDispatchState = null;
let lastDispatchReturnState = null;
let lastQueueHandlerType3State = null;
let lastRecordState = null;
let lastQueueHandlerType2State = null;
let lastQueueHandlerType0State = null;
let lastQueueHelperPrepareEntryState = null;
let lastQueueHelperPrepareState = null;
let lastQueueHelperPrepareResolverCallState = null;
let lastForcedQueueHelperResolverSyntheticSuccessState = null;
let lastForcedQueueHelperPostParserCleanupSuppressionState = null;
let lastForcedQueueHelperReturnSlotRestoreState = null;
let lastType0HandlerReturnBridgeState = null;
let lastForcedType0HandlerReturnSlotRestoreState = null;
let lastQueueHelperPostParserTypeCompareState = null;
let lastQueueHelperPostParserClassState = null;
let lastQueueHelperPostParserMaterializeState = null;
let lastType0MaterializeState = null;
let lastType0PrepareStatusEntryState = null;
let lastType0PrepareStatusState = null;
let lastType0DescriptorStatusState = null;
let lastType0CompareGateState = null;
let lastType0SourceObjectState = null;
let lastType0PrepareParserEntryState = null;
let lastType0PrepareParserState = null;
let lastQueueLoopItemState = null;
let lastQueueLoopPostState = null;
let lastRecordOpenState = null;
let lastRecordCloseState = null;
let lastOwnerStageForceState = null;
let lastRecordOpenForceState = null;
let lastSeedDispatchForceState = null;
let lastRecordDReadyOnPtr178State = null;
let lastRecordDReadyOnLatchClearState = null;
let lastRecordDReadyOnCloseSuppressionState = null;
let lastSelectorReadyOnPtr178State = null;
let lastDirectDispatchForceState = null;
let lastOwnerStageOpenState = null;
let lastPreparedSelectorReadyState = null;
let lastDemotedHotDoneZeroQueuedRecordState = null;
let lastIdleSelectorState = null;
let lastIdleSelectorReturnState = null;
let lastIdleSelectorEntryForceState = null;
let lastIdleSelectorQueueCheckState = null;
let lastSelectionLoopEntryState = null;
let lastPostSelectStatusState = null;
let lastPostSelectSuccessState = null;
let lastPostSelectCommitState = null;
let lastPostSelectCommitReturnState = null;
let lastPtr1c8OpenState = null;
let lastDispatchProviderAcceptState = null;
let lastDispatchResultMetadataState = null;
let lastPostDispatchReleaseCallbackState = null;
let lastDispatchCacheQueryState = null;
let lastPostSelectFlag20State = null;
let lastForcedPostSelectStatusRetvalState = null;
let lastForcedPostSelectPublicationSuccessState = null;
let lastSelectionLatchClearState = null;
let lastSelectionLatchClearReturnState = null;
let lastSuppressedPostSelectLatchClearState = null;
let lastForcedRecordStateFromType0State = null;
let lastSkippedRecordStateFromType0State = null;
let lastForcedType0PrepareBranchState = null;
let lastForcedItemPayloadFromPtr178State = null;
let lastForcedType0Field18To2State = null;
let lastForcedType0RawSourceFromPtr178State = null;
let lastForcedType0ZlbSourceFromPtr178State = null;
let lastForcedType0RequestedLengthFromSourceHeaderState = null;
let lastForcedType0SourceObjectFromSideSlotsState = null;
let lastForcedType0InnerSourceFromSideWrapperState = null;
let lastForcedType0ParserSingleBytePayloadTo1State = null;
let lastQueueHelperPrepareBufferAllocState = null;
let lastQueueHelperPrepareBufferCleanupEntryState = null;
let lastQueueHelperPrepareBufferCleanupState = null;
let lastQueueHelperPrepareCopyState = null;
let lastType0PostPrepareReinitEntryState = null;
let lastType0PostPrepareReinitReturnState = null;
let lastType0PostPrepareStateCallEntryState = null;
let lastType0PostPrepareStateCallReturnState = null;
let lastType0PostPrepareBindEntryState = null;
let lastType0PostPrepareBindReturnState = null;
let lastType0PostPrepareType2EntryState = null;
let lastForcedType3FollowonOnPostState1State = null;
let lastForcedFinalizeOnDispatchReturnState = null;
let lastReenteredRecordStateAfterType3OnPostState1State = null;
let syntheticType0RecordStateBridge = null;
const syntheticDispatchResultMetadata = Memory.alloc(0x100);
syntheticDispatchResultMetadata.writeByteArray(new Uint8Array(0x100));
syntheticDispatchResultMetadata.add(0x24).writeS32(1);
syntheticDispatchResultMetadata.add(0x84).writeS32(0);
const syntheticPostDispatchReleaseVtable = Memory.alloc(Process.pointerSize * 4);
syntheticPostDispatchReleaseVtable.writeByteArray(
  new Uint8Array(Process.pointerSize * 4),
);
const syntheticPostDispatchReleaseNoop = new NativeCallback(
  function (_objectPointer) {
    return;
  },
  'void',
  ['pointer'],
);
syntheticPostDispatchReleaseVtable
  .add(Process.pointerSize)
  .writePointer(syntheticPostDispatchReleaseNoop);
syntheticPostDispatchReleaseVtable
  .add(Process.pointerSize * 2)
  .writePointer(syntheticPostDispatchReleaseNoop);
let recordOpenForcedOnce = false;
let seedDispatchForcedOnce = false;
let recordOpenForceInProgress = false;
let seedDispatchInProgress = false;
let directDispatchInProgress = false;
const idleSelectorThreadStates = {};
const activeType0HandlerStatesByThread = {};
const activeType0HandlerReturnSlotStatesByThread = {};
const activeType0PostPrepareReinitStatesByThread = {};
const activeQueueHelperPrepareStatesByThread = {};
const dispatchCountsByIndex = {};
const directDispatchCountsByIndex = {};
const recordResetCountsByIndex = {};
const recordResetCountsByCallerRva = {};
const queueHandlerType3CountsByIndex = {};
const recordStateCountsByIndex = {};
const queueHandlerType2CountsByIndex = {};
const queueHandlerType0CountsByIndex = {};
const queueHelperPrepareCountsByIndex = {};
const queueLoopCountsByIndex = {};
const queueLoopCountsByRawType = {};
const queueLoopCountsByPredictedHandler = {};
const recordOpenCountsByIndex = {};
const recordCloseCountsByIndex = {};
const recordCloseCountsByCallerRva = {};
const selectionLoopEntryCountsByIndex = {};
const ptr1c8OpenCountsByIndex = {};
const selectionLatchClearCountsByIndex = {};
const forcedDispatchReturnCountsByIndex = {};
const forcedFinalizeOnDispatchReturnCountsByIndex = {};
const forcedRecordDClearCountsByIndex = {};
const forcedDirectDispatchCountsByIndex = {};
const forcedRecordDReadyOnPtr178CountsByIndex = {};
const forcedRecordDReadyOnLatchClearCountsByIndex = {};
const forcedRecordDReadyOnCloseSuppressionCountsByIndex = {};
const forcedSelectorReadyOnPtr178CountsByIndex = {};
const forcedPreparedSelectorReadyCountsByIndex = {};
const demotedHotDoneZeroQueuedRecordCountsByIndex = {};
const forcedRecordOpenCountsByIndex = {};
const forcedRecordStateFromType0CountsByIndex = {};
const skippedRecordStateFromType0CountsByIndex = {};
const forcedType0PrepareBranchCountsByIndex = {};
const forcedItemPayloadFromPtr178CountsByIndex = {};
const forcedType0ChildMinus1BypassCountsByIndex = {};
const forcedType0Field18To2CountsByIndex = {};
let queueHelperResolverSyntheticObject = null;
const forcedType0RawSourceFromPtr178CountsByIndex = {};
const forcedType0ZlbSourceFromPtr178CountsByIndex = {};
const forcedType0RequestedLengthFromSourceHeaderCountsByIndex = {};
const forcedType0SourceObjectFromSideSlotsCountsByIndex = {};
const forcedType0InnerSourceFromSideWrapperCountsByIndex = {};
const forcedType0ParserSingleBytePayloadTo1CountsByIndex = {};
const forcedType3FollowonOnPostState1CountsByIndex = {};
const forcedFinalizeAfterType3OnPostState1CountsByIndex = {};
const reenteredRecordStateAfterType3OnPostState1CountsByIndex = {};
const appliedRecordCloseCallSuppressions = [];

function hexPtr(value) {
  if (value === null || value === undefined) {
    return null;
  }
  try {
    return ptr(value).toString();
  } catch (_error) {
    return null;
  }
}

function bytesToHex(bytes) {
  if (bytes === null || bytes === undefined) {
    return '';
  }
  return Array.from(new Uint8Array(bytes)).map(function (value) {
    return value.toString(16).padStart(2, '0');
  }).join('');
}

function safeReadU8(address) {
  try {
    return ptr(address).readU8();
  } catch (_error) {
    return null;
  }
}

function safeReadS32(address) {
  try {
    return ptr(address).readS32();
  } catch (_error) {
    return null;
  }
}

function safeReadU32(address) {
  try {
    return ptr(address).readU32();
  } catch (_error) {
    return null;
  }
}

function safeReadU16(address) {
  try {
    return ptr(address).readU16();
  } catch (_error) {
    return null;
  }
}

function safeReadU64(address) {
  try {
    return ptr(address).readU64().toString();
  } catch (_error) {
    return null;
  }
}

function safeReadPointer(address) {
  try {
    return ptr(address).readPointer();
  } catch (_error) {
    return null;
  }
}

function pointerLooksSet(value) {
  if (value === null || value === undefined) {
    return false;
  }
  try {
    return !ptr(value).isNull();
  } catch (_error) {
    const text = String(value).trim().toLowerCase();
    return text !== "0x0" && text !== "0";
  }
}

function nonZeroValueLost(beforeValue, afterValue) {
  return (
    beforeValue !== null &&
    beforeValue !== undefined &&
    beforeValue !== 0 &&
    (afterValue === null || afterValue === undefined || afterValue === 0)
  );
}

function parseU64String(value) {
  if (value === null || value === undefined) {
    return null;
  }
  try {
    return BigInt(String(value));
  } catch (_error) {
    return null;
  }
}

function tryReadPreviewHex(pointerValue, previewLength) {
  if (
    !pointerLooksSet(pointerValue) ||
    previewLength === null ||
    previewLength === undefined
  ) {
    return null;
  }
  const parsedLength = Number(previewLength);
  if (!Number.isFinite(parsedLength) || parsedLength <= 0) {
    return null;
  }
  try {
    return bytesToHex(Memory.readByteArray(ptr(pointerValue), Math.min(Math.trunc(parsedLength), 0x20)));
  } catch (_error) {
    return "<unreadable>";
  }
}

function tryReadCString(pointerValue, maxLength) {
  if (!pointerLooksSet(pointerValue)) {
    return null;
  }
  const parsedLength = Number(maxLength);
  const limit = Number.isFinite(parsedLength) && parsedLength > 0 ? Math.trunc(parsedLength) : 0x100;
  try {
    return ptr(pointerValue).readUtf8String(limit);
  } catch (_error) {
    return "<unreadable>";
  }
}

function getQueueHelperResolverSyntheticObject() {
  if (queueHelperResolverSyntheticObject !== null) {
    return queueHelperResolverSyntheticObject;
  }
  const objectPointer = Memory.alloc(0x100);
  objectPointer.add(0x24).writeU8(1);
  objectPointer.add(0x28).writeU32(2);
  objectPointer.add(0xe0).writeU64(0);
  objectPointer.add(0xe8).writePointer(ptr(0));
  queueHelperResolverSyntheticObject = objectPointer;
  return queueHelperResolverSyntheticObject;
}

function clearPrepareBufferState(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return false;
  }
  try {
    const buffer = ptr(pointerValue);
    buffer.add(0x08).writeU64(0);
    buffer.add(0x10).writePointer(ptr(0));
    buffer.add(0x18).writeU64(0);
    return true;
  } catch (_error) {
    return false;
  }
}

function tryForceQueueHelperResolverSyntheticSuccessAtCallsite(
  context,
  activeQueueHelperPrepareContext,
) {
  if (
    !forceQueueHelperResolverSyntheticSuccess ||
    activeQueueHelperPrepareContext === null
  ) {
    return {
      forced: false,
      state: null
    };
  }
  const serviceObjectPointer = ptr(context.rcx);
  const serviceVtablePointer = safeReadPointer(serviceObjectPointer);
  const resolverFunctionPointer = pointerLooksSet(serviceVtablePointer)
    ? safeReadPointer(ptr(serviceVtablePointer).add(0x18))
    : null;
  const outPointerSlot = ptr(context.rdx);
  const entryPointer = ptr(context.r8);
  const outPointerBefore = hexPtr(safeReadPointer(outPointerSlot));
  const syntheticResolvedObjectPointer = getQueueHelperResolverSyntheticObject();
  ptr(outPointerSlot).writePointer(syntheticResolvedObjectPointer);
  context.rax = queueHelperPrepareExpectedTypeAddress;
  context.rip = queueHelperPreparePostParserTypeCompareAddress;
  const state = {
    queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
    probeRva: "0x598a1a",
    instrumentation: "callsite-rip-skip",
    activeQueueHelperPrepareContext: activeQueueHelperPrepareContext,
    serviceObjectPointer: hexPtr(serviceObjectPointer),
    serviceVtablePointer: hexPtr(serviceVtablePointer),
    resolverFunctionPointer: hexPtr(resolverFunctionPointer),
    outPointerSlot: hexPtr(outPointerSlot),
    outPointerBefore: outPointerBefore,
    outPointerAfter: hexPtr(safeReadPointer(outPointerSlot)),
    entryPointer: hexPtr(entryPointer),
    entryDword0: safeReadU32(entryPointer),
    entryDword4: safeReadU32(entryPointer.add(0x4)),
    entryQword0: safeReadU64(entryPointer),
    entryQword8: safeReadU64(entryPointer.add(0x8)),
    entryPreviewHex: tryReadPreviewHex(entryPointer, 0x20),
    syntheticResolvedObjectPointer: hexPtr(syntheticResolvedObjectPointer),
    syntheticResolvedObject:
      snapshotQueueHelperResolvedObject(syntheticResolvedObjectPointer),
    forcedReturnTypePointer: hexPtr(queueHelperPrepareExpectedTypeAddress),
    forcedNextRip: hexPtr(queueHelperPreparePostParserTypeCompareAddress),
    timestamp: Date.now() / 1000
  };
  totalForcedQueueHelperResolverSyntheticSuccess += 1;
  lastForcedQueueHelperResolverSyntheticSuccessState = state;
  sendUnique(
    seenQueueHelperResolverSyntheticSuccessStates,
    "force-queue-helper-resolver-synthetic-success",
    state,
  );
  return {
    forced: true,
    state: state
  };
}

function pointerSpanCount(startPointer, endPointer, stride) {
  const start = parseU64String(hexPtr(startPointer));
  const end = parseU64String(hexPtr(endPointer));
  if (start === null || end === null || end < start) {
    return null;
  }
  const width = BigInt(stride);
  if (width <= 0n) {
    return null;
  }
  const span = end - start;
  if (span % width !== 0n) {
    return null;
  }
  return Number(span / width);
}

function addressToRvaText(address) {
  if (address === null || address === undefined) {
    return null;
  }
  try {
    return ptr(address).sub(moduleBase).toString();
  } catch (_error) {
    return null;
  }
}

function pointerWithinMainModule(pointerValue) {
  if (pointerValue === null || pointerValue === undefined) {
    return false;
  }
  try {
    const pointer = ptr(pointerValue);
    return pointer.compare(moduleBase) >= 0 && pointer.compare(moduleEnd) < 0;
  } catch (_error) {
    return false;
  }
}

function pointerBelowThreshold(pointerValue, thresholdValue) {
  if (pointerValue === null || pointerValue === undefined) {
    return true;
  }
  try {
    return ptr(pointerValue).compare(ptr(thresholdValue)) < 0;
  } catch (_error) {
    return true;
  }
}

function shouldFallbackReleaseCallbackTarget(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return true;
  }
  return pointerBelowThreshold(pointerValue, 0x10000);
}

function callsiteRvaTextFromReturnAddress(address) {
  if (address === null || address === undefined) {
    return null;
  }
  try {
    const returnAddress = ptr(address);
    const callsite = returnAddress.sub(5);
    if (callsite.readU8() === 0xe8) {
      return callsite.sub(moduleBase).toString();
    }
    return returnAddress.sub(moduleBase).toString();
  } catch (_error) {
    return addressToRvaText(address);
  }
}

function rvaTextToInt(callsiteRva) {
  if (callsiteRva === null || callsiteRva === undefined) {
    return null;
  }
  try {
    return parseInt(String(callsiteRva), 16);
  } catch (_error) {
    return null;
  }
}

function callsiteWithinType0Handler(callsiteRva) {
  const value = rvaTextToInt(callsiteRva);
  return value !== null && value >= 0x598370 && value < 0x598930;
}

function describeRecordResetCaller(callsiteRva) {
  switch (callsiteRva) {
    case "0x5955aa":
      return "single-dispatch-pre-reset-flag20";
    case "0x596617":
      return "dispatch-pre-handler-flag20";
    case "0x596642":
      return "dispatch-pre-base-handler-secondary-reset";
    case "0x5966b5":
      return "dispatch-post-handler-flag28";
    default:
      return null;
  }
}

function describeQueueHandlerCaller(callsiteRva) {
  switch (callsiteRva) {
    case "0x59665d":
      return "queue-handler-type3";
    case "0x59666f":
      return "queue-handler-type2";
    case "0x59667e":
      return "queue-handler-type1";
    case "0x5966a3":
      return "queue-handler-type0";
    default:
      return null;
  }
}

function describeQueueLoopHandlerFromRawType(rawType) {
  switch (rawType) {
    case 0:
      return "queue-handler-type0";
    case 1:
      return "queue-handler-type1";
    case 2:
      return "queue-handler-type2";
    case 3:
      return "queue-handler-type3";
    default:
      return "queue-handler-unknown";
  }
}

function describeRecordCloseCaller(callsiteRva) {
  switch (callsiteRva) {
    case "0x595433":
      return "record-reset-close-path";
    case "0x595be3":
      return "single-dispatch-post-close";
    case "0x5946cf":
      return "owner-bulk-close-pass-a";
    case "0x594700":
      return "owner-bulk-close-pass-b";
    default:
      return null;
  }
}

function shouldSuppressRecordCloseCaller(callsiteRva) {
  return callsiteRva !== null && suppressRecordCloseCallerRvaSet[callsiteRva] === 1;
}

function snapshotQueueItem(itemPointer) {
  if (itemPointer === null || itemPointer === undefined) {
    return null;
  }
  try {
    const item = ptr(itemPointer);
    return {
      pointer: hexPtr(item),
      itemType: safeReadS32(item),
      index: safeReadS32(item.add(4)),
      field8: safeReadS32(item.add(8)),
      fieldC: safeReadS32(item.add(0x0c)),
      field10: safeReadS32(item.add(0x10)),
      byte14: safeReadU8(item.add(0x14)),
      byte15: safeReadU8(item.add(0x15)),
      byte16: safeReadU8(item.add(0x16)),
      byte17: safeReadU8(item.add(0x17)),
      field18: safeReadS32(item.add(0x18)),
      field1C: safeReadS32(item.add(0x1c)),
      ptr20: hexPtr(safeReadPointer(item.add(0x20))),
      ptr28: hexPtr(safeReadPointer(item.add(0x28))),
      qword28: safeReadU64(item.add(0x28)),
      ptr30: hexPtr(safeReadPointer(item.add(0x30)))
    };
  } catch (_error) {
    return {
      pointer: hexPtr(itemPointer),
      unreadable: true
    };
  }
}

function snapshotBlobHeader(blobPointer) {
  if (blobPointer === null || blobPointer === undefined) {
    return null;
  }
  try {
    const blob = ptr(blobPointer);
    return {
      pointer: hexPtr(blob),
      magic: safeReadU32(blob),
      length: safeReadU32(blob.add(4)),
      qword0: safeReadU64(blob),
      qword1: safeReadU64(blob.add(8))
    };
  } catch (_error) {
    return {
      pointer: hexPtr(blobPointer),
      unreadable: true
    };
  }
}

function snapshotPrepareSource(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return null;
  }
  try {
    const source = ptr(pointerValue);
    const ptr8 = safeReadPointer(source.add(0x8));
    const ptr10 = safeReadPointer(source.add(0x10));
    return {
      pointer: hexPtr(source),
      dword0: safeReadU32(source),
      dword4: safeReadU32(source.add(0x4)),
      qword0: safeReadU64(source),
      qword8: safeReadU64(source.add(0x8)),
      qword10: safeReadU64(source.add(0x10)),
      ptr8: hexPtr(ptr8),
      ptr10: hexPtr(ptr10),
      previewHex: tryReadPreviewHex(source, 0x20),
      ptr8PreviewHex: tryReadPreviewHex(ptr8, 0x20),
      ptr10PreviewHex: tryReadPreviewHex(ptr10, 0x20),
      blobHeader: snapshotBlobHeader(source)
    };
  } catch (_error) {
    return {
      pointer: hexPtr(pointerValue),
      error: String(_error)
    };
  }
}

function snapshotType0SourceCandidate(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return null;
  }
  try {
    const source = ptr(pointerValue);
    const ptr10 = safeReadPointer(source.add(0x10));
    const ptr18 = safeReadPointer(source.add(0x18));
    const ptr20 = safeReadPointer(source.add(0x20));
    const ptr28 = safeReadPointer(source.add(0x28));
    return {
      pointer: hexPtr(source),
      qword0: safeReadU64(source),
      word8: safeReadU16(source.add(0x08)),
      byteA: safeReadU8(source.add(0x0a)),
      dwordC: safeReadU32(source.add(0x0c)),
      qword10: safeReadU64(source.add(0x10)),
      qword18: safeReadU64(source.add(0x18)),
      dword20: safeReadU32(source.add(0x20)),
      qword20: safeReadU64(source.add(0x20)),
      ptr10: hexPtr(ptr10),
      ptr18: hexPtr(ptr18),
      ptr20: hexPtr(ptr20),
      ptr28: hexPtr(ptr28),
      qword28: safeReadU64(source.add(0x28)),
      previewHex: tryReadPreviewHex(source, 0x20),
      ptr10PreviewHex: tryReadPreviewHex(ptr10, 0x20),
      ptr18PreviewHex: tryReadPreviewHex(ptr18, 0x20),
      ptr20PreviewHex: tryReadPreviewHex(ptr20, 0x20),
      ptr28PreviewHex: tryReadPreviewHex(ptr28, 0x20),
      entry38Qword0: safeReadU64(source.add(0x38)),
      entry38Word8: safeReadU16(source.add(0x40)),
      entry38ByteA: safeReadU8(source.add(0x42)),
      entry38Qword10: safeReadU64(source.add(0x48)),
      entry70Qword0: safeReadU64(source.add(0x70)),
      entry70Word8: safeReadU16(source.add(0x78)),
      entry70ByteA: safeReadU8(source.add(0x7a)),
      entry70Qword10: safeReadU64(source.add(0x80)),
      blobHeader: snapshotBlobHeader(source)
    };
  } catch (_error) {
    return {
      pointer: hexPtr(pointerValue),
      error: String(_error)
    };
  }
}

function snapshotPrepareBufferState(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return null;
  }
  try {
    const buffer = ptr(pointerValue);
    const dataPointer = safeReadPointer(buffer.add(0x10));
    const sizeLengthRaw = safeReadU64(buffer.add(0x08));
    const previewLengthRaw = safeReadU64(buffer.add(0x18));
    let previewLength = 0;
    for (const rawLength of [previewLengthRaw, sizeLengthRaw]) {
      if (rawLength !== null) {
        const parsedLength = Number(parseU64String(rawLength));
        if (Number.isFinite(parsedLength) && parsedLength > 0) {
          previewLength = Math.min(parsedLength, 0x20);
          break;
        }
      }
    }
    const previewHex = tryReadPreviewHex(dataPointer, previewLength);
    return {
      pointer: hexPtr(buffer),
      qword0: safeReadU64(buffer),
      previewLength: previewLength,
      qword8: safeReadU64(buffer.add(0x08)),
      ptr10: hexPtr(dataPointer),
      qword10: safeReadU64(buffer.add(0x10)),
      qword18: safeReadU64(buffer.add(0x18)),
      previewHex: previewHex
    };
  } catch (_error) {
    return {
      pointer: hexPtr(pointerValue),
      error: String(_error)
    };
  }
}

function snapshotType0SideObject(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return null;
  }
  try {
    const source = ptr(pointerValue);
    const ptr0 = safeReadPointer(source);
    const ptr80 = safeReadPointer(source.add(0x80));
    const ptr88 = safeReadPointer(source.add(0x88));
    const ptr90 = safeReadPointer(source.add(0x90));
    const ptr98 = safeReadPointer(source.add(0x98));
    const ptrA0 = safeReadPointer(source.add(0xA0));
    const ptr148 = safeReadPointer(source.add(0x148));
    const ptr278 = safeReadPointer(source.add(0x278));
    return {
      pointer: hexPtr(source),
      ptr0: hexPtr(ptr0),
      qword0: safeReadU64(source),
      qword0SelfMatches: hexPtr(ptr0) === hexPtr(source),
      word8: safeReadU16(source.add(0x08)),
      byteA: safeReadU8(source.add(0x0a)),
      dwordC: safeReadU32(source.add(0x0c)),
      qword10: safeReadU64(source.add(0x10)),
      qword18: safeReadU64(source.add(0x18)),
      dword20: safeReadU32(source.add(0x20)),
      dword24: safeReadU32(source.add(0x24)),
      qword28: safeReadU64(source.add(0x28)),
      dword30: safeReadU32(source.add(0x30)),
      qword30: safeReadU64(source.add(0x30)),
      dword34: safeReadU32(source.add(0x34)),
      dword38: safeReadU32(source.add(0x38)),
      ptr80: hexPtr(ptr80),
      qword80: safeReadU64(source.add(0x80)),
      ptr80Rva: pointerWithinMainModule(ptr80) ? addressToRvaText(ptr80) : null,
      ptr80InModule: pointerWithinMainModule(ptr80),
      ptr88: hexPtr(ptr88),
      qword88: safeReadU64(source.add(0x88)),
      ptr90: hexPtr(ptr90),
      qword90: safeReadU64(source.add(0x90)),
      ptr90Rva: pointerWithinMainModule(ptr90) ? addressToRvaText(ptr90) : null,
      ptr90InModule: pointerWithinMainModule(ptr90),
      ptr98: hexPtr(ptr98),
      qword98: safeReadU64(source.add(0x98)),
      ptrA0: hexPtr(ptrA0),
      qwordA0: safeReadU64(source.add(0xA0)),
      ptr148: hexPtr(ptr148),
      qword148: safeReadU64(source.add(0x148)),
      ptr148Rva: pointerWithinMainModule(ptr148) ? addressToRvaText(ptr148) : null,
      ptr148InModule: pointerWithinMainModule(ptr148),
      ptr278: hexPtr(ptr278),
      qword278: safeReadU64(source.add(0x278)),
      ptr278Rva: pointerWithinMainModule(ptr278) ? addressToRvaText(ptr278) : null,
      ptr278InModule: pointerWithinMainModule(ptr278),
      wordB4: safeReadU16(source.add(0xB4)),
      byte61: safeReadU8(source.add(0x61))
    };
  } catch (_error) {
    return {
      pointer: hexPtr(pointerValue),
      error: String(_error)
    };
  }
}

function snapshotQueueHelperResolvedObject(pointerValue) {
  if (!pointerLooksSet(pointerValue)) {
    return null;
  }
  try {
    const object = ptr(pointerValue);
    const ptrE8 = safeReadPointer(object.add(0xe8));
    return {
      pointer: hexPtr(object),
      vtable: hexPtr(safeReadPointer(object)),
      byte24: safeReadU8(object.add(0x24)),
      dword28: safeReadS32(object.add(0x28)),
      qwordE0: safeReadU64(object.add(0xe0)),
      ptrE8: hexPtr(ptrE8),
      wordE8_0: safeReadU16(ptrE8),
      wordE8_1: pointerLooksSet(ptrE8) ? safeReadU16(ptr(ptrE8).add(0x2)) : null,
      wordE8_2: pointerLooksSet(ptrE8) ? safeReadU16(ptr(ptrE8).add(0x4)) : null,
      previewHex: tryReadPreviewHex(object, 0x30),
      ptrE8PreviewHex: tryReadPreviewHex(ptrE8, 0x20)
    };
  } catch (_error) {
    return {
      pointer: hexPtr(pointerValue),
      error: String(_error)
    };
  }
}

function snapshotQueueHelperReturnSlot(activeContext) {
  if (
    activeContext === null ||
    activeContext === undefined ||
    !pointerLooksSet(activeContext.entryStackPointer)
  ) {
    return null;
  }
  try {
    const entryStackPointer = ptr(activeContext.entryStackPointer);
    const currentReturnAddress = safeReadPointer(entryStackPointer);
    const originalReturnAddress = pointerLooksSet(activeContext.originalStackReturnAddress)
      ? ptr(activeContext.originalStackReturnAddress)
      : null;
    return {
      entryStackPointer: hexPtr(entryStackPointer),
      originalReturnAddress: hexPtr(originalReturnAddress),
      currentReturnAddress: hexPtr(currentReturnAddress),
      currentMatchesOriginal:
        hexPtr(currentReturnAddress) === hexPtr(originalReturnAddress),
    };
  } catch (_error) {
    return {
      entryStackPointer: hexPtr(activeContext.entryStackPointer),
      originalReturnAddress: hexPtr(activeContext.originalStackReturnAddress),
      error: String(_error),
    };
  }
}

function snapshotType0HandlerReturnSlot(activeContext, stackPointerOverride) {
  if (
    activeContext === null ||
    activeContext === undefined ||
    (
      !pointerLooksSet(stackPointerOverride) &&
      !pointerLooksSet(activeContext.entryStackPointer)
    )
  ) {
    return null;
  }
  try {
    const currentStackPointer = pointerLooksSet(stackPointerOverride)
      ? ptr(stackPointerOverride)
      : ptr(activeContext.entryStackPointer);
    const currentReturnAddress = safeReadPointer(currentStackPointer);
    const originalReturnAddress = pointerLooksSet(activeContext.originalStackReturnAddress)
      ? ptr(activeContext.originalStackReturnAddress)
      : null;
    return {
      entryStackPointer: hexPtr(activeContext.entryStackPointer),
      currentStackPointer: hexPtr(currentStackPointer),
      originalReturnAddress: hexPtr(originalReturnAddress),
      currentReturnAddress: hexPtr(currentReturnAddress),
      currentMatchesOriginal:
        hexPtr(currentReturnAddress) === hexPtr(originalReturnAddress),
    };
  } catch (_error) {
    return {
      entryStackPointer: hexPtr(activeContext.entryStackPointer),
      currentStackPointer: hexPtr(stackPointerOverride),
      originalReturnAddress: hexPtr(activeContext.originalStackReturnAddress),
      error: String(_error),
    };
  }
}

function byteSwapU32(value) {
  const word = value >>> 0;
  return (
    ((word & 0x000000ff) << 24) |
    ((word & 0x0000ff00) << 8) |
    ((word & 0x00ff0000) >>> 8) |
    ((word & 0xff000000) >>> 24)
  ) >>> 0;
}

function normalizeParserLength(rawValue) {
  if (rawValue === null || rawValue === undefined) {
    return null;
  }
  const littleEndian = rawValue >>> 0;
  const swapped = byteSwapU32(littleEndian);
  const candidates = [];
  if (littleEndian > 0 && littleEndian <= 0x1000000) {
    candidates.push(littleEndian);
  }
  if (swapped > 0 && swapped <= 0x1000000) {
    candidates.push(swapped);
  }
  if (candidates.length === 0) {
    return null;
  }
  return Math.min.apply(null, candidates);
}

function computeRequestedLengthFromParserHeader(sourcePointer) {
  if (!pointerLooksSet(sourcePointer)) {
    return null;
  }
  try {
    const source = ptr(sourcePointer);
    const typeByte = safeReadU8(source);
    const primaryLengthRaw = safeReadU32(source.add(0x1));
    const secondaryLengthRaw = safeReadU32(source.add(0x5));
    const primaryLength = normalizeParserLength(primaryLengthRaw);
    const secondaryLength = normalizeParserLength(secondaryLengthRaw);
    let requestedLength = null;
    if (typeByte === 0) {
      if (primaryLength === null) {
        return null;
      }
      requestedLength = 5 + primaryLength;
    } else if (typeByte === 1 || typeByte === 2 || typeByte === 3) {
      if (primaryLength === null || secondaryLength === null) {
        return null;
      }
      requestedLength = 9 + primaryLength;
    } else {
      return null;
    }
    if (requestedLength === null || requestedLength <= 4 || requestedLength > 0x1000000) {
      return null;
    }
    return {
      sourcePointer: hexPtr(source),
      typeByte: typeByte,
      primaryLengthRaw: primaryLengthRaw,
      primaryLength: primaryLength,
      secondaryLengthRaw: secondaryLengthRaw,
      secondaryLength: secondaryLength,
      requestedLength: requestedLength
    };
  } catch (_error) {
    return null;
  }
}

function scoreParserHeaderCandidate(candidate) {
  if (candidate === null || candidate === undefined) {
    return -0x100000;
  }
  let score = 0;
  if (candidate.typeByte === 0) {
    score += 8;
  } else if (candidate.typeByte === 1 || candidate.typeByte === 2 || candidate.typeByte === 3) {
    score += 4;
  }
  if (
    candidate.primaryLengthRaw !== null &&
    candidate.primaryLength !== null &&
    candidate.primaryLengthRaw === candidate.primaryLength
  ) {
    score += 10;
  }
  if (
    candidate.typeByte !== 0 &&
    candidate.secondaryLengthRaw !== null &&
    candidate.secondaryLength !== null &&
    candidate.secondaryLengthRaw === candidate.secondaryLength
  ) {
    score += 4;
  } else if (candidate.typeByte !== 0 && (candidate.secondaryLength === null || candidate.secondaryLength === 0)) {
    score += 2;
  }
  if (candidate.requestedLength !== null && candidate.requestedLength >= 0x20) {
    score += 6;
  } else if (candidate.requestedLength !== null && candidate.requestedLength >= 0x10) {
    score += 2;
  } else if (candidate.requestedLength !== null && candidate.requestedLength < 8) {
    score -= 12;
  }
  if (
    candidate.primaryLength !== null &&
    candidate.primaryLength >= 0x20 &&
    candidate.primaryLength <= 0x4000
  ) {
    score += 4;
  }
  if (candidate.requestedLength !== null && candidate.requestedLength > 0x400) {
    score -= 4;
  }
  if (candidate.sourceOffset !== null && candidate.sourceOffset >= 0x20) {
    score += 2;
  }
  if (
    candidate.previewHex !== null &&
    candidate.previewHex !== undefined &&
    !String(candidate.previewHex).startsWith("<unreadable>")
  ) {
    score += 3;
  }
  return score;
}

function itemPayloadReady(itemPointer) {
  if (itemPointer === null || itemPointer === undefined) {
    return false;
  }
  const item = ptr(itemPointer);
  const payloadSize = parseU64String(safeReadU64(item.add(0x28)));
  const payloadBuffer = hexPtr(safeReadPointer(item.add(0x30)));
  return payloadSize !== null && payloadSize > 0n && pointerLooksSet(payloadBuffer);
}

function findParserHeaderInPtr178Blob(blobPointer) {
  if (!pointerLooksSet(blobPointer)) {
    return null;
  }
  try {
    const blob = ptr(blobPointer);
    const containerLength = safeReadU32(blob.add(0x4));
    if (containerLength === null || containerLength <= 8) {
      return null;
    }
    const scanLength = Math.min(containerLength, 0x4000);
    const candidates = [];
    for (let offset = 0; offset + 5 <= scanLength; offset += 1) {
      const sourcePointer = blob.add(offset);
      const header = computeRequestedLengthFromParserHeader(sourcePointer);
      if (
        header === null ||
        header.requestedLength === null ||
        header.requestedLength <= 4 ||
        offset + header.requestedLength > scanLength
      ) {
        continue;
      }
      const candidate = {
        sourcePointer: hexPtr(sourcePointer),
        sourceOffset: offset,
        typeByte: header.typeByte,
        primaryLengthRaw: header.primaryLengthRaw,
        primaryLength: header.primaryLength,
        secondaryLengthRaw: header.secondaryLengthRaw,
        secondaryLength: header.secondaryLength,
        requestedLength: header.requestedLength,
        previewHex: tryReadPreviewHex(sourcePointer, Math.min(header.requestedLength, 0x20))
      };
      candidate.score = scoreParserHeaderCandidate(candidate);
      candidates.push(candidate);
      if (candidates.length >= 8) {
        break;
      }
    }
    candidates.sort((left, right) => {
      if (right.score !== left.score) {
        return right.score - left.score;
      }
      if (left.requestedLength !== right.requestedLength) {
        return left.requestedLength - right.requestedLength;
      }
      return left.sourceOffset - right.sourceOffset;
    });
    return {
      blobPointer: hexPtr(blob),
      containerLength: containerLength,
      scanLength: scanLength,
      found: candidates.length !== 0,
      candidates: candidates,
      selected: candidates.length !== 0 ? candidates[0] : null
    };
  } catch (_error) {
    return {
      blobPointer: hexPtr(blobPointer),
      found: false,
      error: String(_error)
    };
  }
}

function findZlbHeaderInPtr178Blob(blobPointer) {
  if (!pointerLooksSet(blobPointer)) {
    return null;
  }
  try {
    const blob = ptr(blobPointer);
    const containerLength = safeReadU32(blob.add(0x4));
    if (containerLength === null || containerLength <= 8) {
      return null;
    }
    const scanLength = Math.min(containerLength, 0x4000);
    const matches = Memory.scanSync(blob, scanLength, "5a 4c 42 01");
    if (!matches || matches.length === 0) {
      return {
        blobPointer: hexPtr(blob),
        containerLength: containerLength,
        found: false
      };
    }
    const sourcePointer = matches[0].address;
    const sourceOffsetBig =
      parseU64String(sourcePointer.toString()) - parseU64String(blob.toString());
    const sourceOffset = Number(sourceOffsetBig);
    if (!Number.isFinite(sourceOffset) || sourceOffset < 0 || sourceOffset + 8 > scanLength) {
      return {
        blobPointer: hexPtr(blob),
        containerLength: containerLength,
        found: false
      };
    }
    const remainingLength = Math.max(0, containerLength - sourceOffset);
    return {
      blobPointer: hexPtr(blob),
      containerLength: containerLength,
      found: true,
      sourcePointer: hexPtr(sourcePointer),
      sourceOffset: sourceOffset,
      remainingLength: remainingLength,
      zlbMagic: safeReadU32(sourcePointer),
      zlbLength: safeReadU32(sourcePointer.add(0x4))
    };
  } catch (_error) {
    return {
      blobPointer: hexPtr(blobPointer),
      found: false,
      error: String(_error)
    };
  }
}

function tryForceType0ZlbSourceFromPtr178(context, owner, itemPointer, index, callerRva) {
  const currentSourcePointer = hexPtr(context.rdx);
  const currentRequestedLength = ptr(context.r8).toInt32();
  const currentSourceSnapshot = snapshotPrepareSource(context.rdx);
  const missingSource = currentSourcePointer === "0x0" || currentRequestedLength === 0;
  const suspiciousSource =
    !missingSource &&
    (
      (currentRequestedLength > 0 && currentRequestedLength <= 4) ||
      (currentSourceSnapshot !== null &&
        currentSourceSnapshot.dword4 !== null &&
        currentSourceSnapshot.dword4 <= 4)
    );
  if (
    !forceType0ZlbSourceFromPtr178 ||
    callerRva !== TYPE0_PREPARE_CALLER_RVA ||
    owner === null ||
    itemPointer === null ||
    index === null ||
    index < 0 ||
    index >= resourceCount ||
    (!missingSource && !suspiciousSource)
  ) {
    return { forced: false, state: null };
  }
  const record = snapshotRecord(owner, index);
  if (!record || !record.validIndex || !pointerLooksSet(record.ptr178)) {
    return { forced: false, state: null };
  }
  const zlbSource = findZlbHeaderInPtr178Blob(record.ptr178);
  if (!zlbSource || zlbSource.found !== true || !pointerLooksSet(zlbSource.sourcePointer)) {
    return { forced: false, state: zlbSource };
  }
  const requestedLength = zlbSource.remainingLength;
  if (requestedLength === null || requestedLength <= 8) {
    return { forced: false, state: zlbSource };
  }
  const sourcePointer = ptr(zlbSource.sourcePointer);
  context.rdx = sourcePointer;
  context.r8 = ptr(requestedLength);
  totalForcedType0ZlbSourceFromPtr178 += 1;
  forcedType0ZlbSourceFromPtr178CountsByIndex[index] =
    (forcedType0ZlbSourceFromPtr178CountsByIndex[index] || 0) + 1;
  const state = {
    event: "force-type0-zlb-source-from-ptr178",
    timestamp: Date.now() / 1000.0,
    callerRva: callerRva,
    reason: missingSource ? "missing-source" : "suspicious-small-source",
    owner: hexPtr(owner),
    itemPointer: hexPtr(itemPointer),
    index: index,
    record: record,
    currentSourcePointer: currentSourcePointer,
    currentRequestedLength: currentRequestedLength,
    currentSourceSnapshot: currentSourceSnapshot,
    zlbSource: zlbSource,
    forcedSourcePointer: hexPtr(sourcePointer),
    forcedRequestedLength: requestedLength,
    forcedSourceSnapshot: snapshotPrepareSource(sourcePointer)
  };
  lastForcedType0ZlbSourceFromPtr178State = state;
  send(state);
  return {
    forced: true,
    state: state
  };
}

function tryForceType0RawSourceFromPtr178(context, owner, itemPointer, index, callerRva) {
  const currentSourcePointer = hexPtr(context.rdx);
  const currentRequestedLength = ptr(context.r8).toInt32();
  const currentSourceSnapshot = snapshotPrepareSource(context.rdx);
  const missingSource = currentSourcePointer === "0x0" || currentRequestedLength === 0;
  const suspiciousSource =
    !missingSource &&
    (
      (currentRequestedLength > 0 && currentRequestedLength <= 4) ||
      (currentSourceSnapshot !== null &&
        currentSourceSnapshot.dword4 !== null &&
        currentSourceSnapshot.dword4 <= 4)
    );
  if (
    !forceType0RawSourceFromPtr178 ||
    callerRva !== TYPE0_PREPARE_CALLER_RVA ||
    owner === null ||
    itemPointer === null ||
    index === null ||
    index < 0 ||
    index >= resourceCount ||
    (!missingSource && !suspiciousSource)
  ) {
    return { forced: false, state: null };
  }
  const record = snapshotRecord(owner, index);
  if (!record || !record.validIndex || !pointerLooksSet(record.ptr178)) {
    return { forced: false, state: null };
  }
  const item = snapshotQueueItem(itemPointer);
  const rawBlob = snapshotBlobHeader(record.ptr178);
  if (!rawBlob || !pointerLooksSet(rawBlob.pointer)) {
    return { forced: false, state: rawBlob };
  }
  const parserSourceScan = findParserHeaderInPtr178Blob(record.ptr178);
  let sourcePointer = ptr(record.ptr178);
  let requestedLength = rawBlob.length;
  if (
    parserSourceScan &&
    parserSourceScan.found === true &&
    parserSourceScan.selected &&
    pointerLooksSet(parserSourceScan.selected.sourcePointer)
  ) {
    sourcePointer = ptr(parserSourceScan.selected.sourcePointer);
    requestedLength = parserSourceScan.selected.requestedLength;
  }
  if (requestedLength === null || requestedLength <= 4) {
    return { forced: false, state: parserSourceScan || rawBlob };
  }
  context.rdx = sourcePointer;
  context.r8 = ptr(requestedLength);
  totalForcedType0RawSourceFromPtr178 += 1;
  forcedType0RawSourceFromPtr178CountsByIndex[index] =
    (forcedType0RawSourceFromPtr178CountsByIndex[index] || 0) + 1;
  const state = {
    event: "force-type0-raw-source-from-ptr178",
    timestamp: Date.now() / 1000.0,
    callerRva: callerRva,
    reason: missingSource ? "missing-source" : "suspicious-small-source",
    owner: hexPtr(owner),
    itemPointer: hexPtr(itemPointer),
    item: item,
    index: index,
    record: record,
    currentSourcePointer: currentSourcePointer,
    currentRequestedLength: currentRequestedLength,
    currentSourceSnapshot: currentSourceSnapshot,
    rawBlob: rawBlob,
    parserSourceScan: parserSourceScan,
    forcedSourcePointer: hexPtr(sourcePointer),
    forcedRequestedLength: requestedLength,
    forcedSourceSnapshot: snapshotPrepareSource(sourcePointer)
  };
  lastForcedType0RawSourceFromPtr178State = state;
  send(state);
  return {
    forced: true,
    state: state
  };
}

function tryForceType0RequestedLengthFromSourceHeader(context, owner, itemPointer, index, callerRva) {
  const currentSourcePointer = hexPtr(context.rdx);
  const currentRequestedLength = ptr(context.r8).toInt32();
  const currentSourceSnapshot = snapshotPrepareSource(context.rdx);
  if (
    !forceType0RequestedLengthFromSourceHeader ||
    callerRva !== TYPE0_PREPARE_CALLER_RVA ||
    owner === null ||
    itemPointer === null ||
    index === null ||
    index < 0 ||
    index >= resourceCount ||
    !pointerLooksSet(currentSourcePointer) ||
    currentRequestedLength !== 0 ||
    currentSourceSnapshot === null ||
    currentSourceSnapshot.dword4 === null
  ) {
    return { forced: false, state: null };
  }
  const promotedRequestedLength = currentSourceSnapshot.dword4;
  if (promotedRequestedLength <= 8 || promotedRequestedLength > 0x1000000) {
    return { forced: false, state: null };
  }
  const record = snapshotRecord(owner, index);
  const item = snapshotQueueItem(itemPointer);
  context.r8 = ptr(promotedRequestedLength);
  totalForcedType0RequestedLengthFromSourceHeader += 1;
  forcedType0RequestedLengthFromSourceHeaderCountsByIndex[index] =
    (forcedType0RequestedLengthFromSourceHeaderCountsByIndex[index] || 0) + 1;
  const state = {
    event: "force-type0-requested-length-from-source-header",
    timestamp: Date.now() / 1000.0,
    callerRva: callerRva,
    owner: hexPtr(owner),
    itemPointer: hexPtr(itemPointer),
    item: item,
    index: index,
    record: record,
    currentSourcePointer: currentSourcePointer,
    currentRequestedLength: currentRequestedLength,
    currentSourceSnapshot: currentSourceSnapshot,
    promotedRequestedLength: promotedRequestedLength,
    promotedSourceSnapshot: snapshotPrepareSource(context.rdx)
  };
  lastForcedType0RequestedLengthFromSourceHeaderState = state;
  send(state);
  return {
    forced: true,
    state: state
  };
}

function tryForceType0InnerSourceFromSideWrapper(context, owner, itemPointer, index, callerRva) {
  const currentSourcePointer = hexPtr(context.rdx);
  const currentRequestedLength = ptr(context.r8).toInt32();
  const currentSourceSnapshot = snapshotPrepareSource(context.rdx);
  const missingSource = currentSourcePointer === "0x0" || currentRequestedLength === 0;
  const suspiciousSmallRequestedLength =
    currentRequestedLength > 0 && currentRequestedLength <= 8;
  const suspiciousSource =
    !missingSource &&
    currentSourceSnapshot !== null &&
    (
      currentSourceSnapshot.dword0 === 0x302e30 ||
      (
        suspiciousSmallRequestedLength &&
        currentSourceSnapshot.dword4 !== null &&
        currentSourceSnapshot.dword4 <= 4
      )
    );
  if (
    !forceType0InnerSourceFromSideWrapper ||
    callerRva !== TYPE0_PREPARE_CALLER_RVA ||
    owner === null ||
    itemPointer === null ||
    index === null ||
    index < 0 ||
    index >= resourceCount ||
    (!missingSource && !suspiciousSource)
  ) {
    return { forced: false, state: null };
  }
  const record = snapshotRecord(owner, index);
  if (!record || !record.validIndex || !pointerLooksSet(record.ptr1a8)) {
    return { forced: false, state: record };
  }
  const sideObject = ptr(record.ptr1a8);
  const wrapper98 = safeReadPointer(sideObject.add(0x98));
  const wrapperA0 = safeReadPointer(sideObject.add(0xA0));
  const candidateStates = [];
  const candidates = [
    {
      slot: "ptr98+0x18",
      wrapperPointer: hexPtr(wrapper98),
      innerPointer: pointerLooksSet(wrapper98) ? safeReadPointer(ptr(wrapper98).add(0x18)) : null
    },
    {
      slot: "ptrA0+0x10",
      wrapperPointer: hexPtr(wrapperA0),
      innerPointer: pointerLooksSet(wrapperA0) ? safeReadPointer(ptr(wrapperA0).add(0x10)) : null
    }
  ];
  for (const candidate of candidates) {
    const parserHeader = computeRequestedLengthFromParserHeader(candidate.innerPointer);
    let effectiveRequestedLength =
      parserHeader !== null ? parserHeader.requestedLength : null;
    let promotedRequestedLengthFromSecondary = false;
    if (
      parserHeader !== null &&
      parserHeader.typeByte === 0 &&
      parserHeader.primaryLength === 1 &&
      parserHeader.secondaryLength === 4 &&
      effectiveRequestedLength !== null &&
      effectiveRequestedLength < 13
    ) {
      effectiveRequestedLength = 9 + parserHeader.secondaryLength;
      promotedRequestedLengthFromSecondary = true;
    }
    const candidateState = {
      slot: candidate.slot,
      wrapperPointer: candidate.wrapperPointer,
      wrapperSnapshot: snapshotType0SourceCandidate(candidate.wrapperPointer),
      innerPointer: hexPtr(candidate.innerPointer),
      innerSourceSnapshot: snapshotPrepareSource(candidate.innerPointer),
      parserHeader: parserHeader,
      effectiveRequestedLength: effectiveRequestedLength,
      promotedRequestedLengthFromSecondary: promotedRequestedLengthFromSecondary
    };
    candidateStates.push(candidateState);
    if (parserHeader === null || !pointerLooksSet(candidate.innerPointer)) {
      continue;
    }
    context.rdx = ptr(candidate.innerPointer);
    context.r8 = ptr(effectiveRequestedLength);
    totalForcedType0InnerSourceFromSideWrapper += 1;
    forcedType0InnerSourceFromSideWrapperCountsByIndex[index] =
      (forcedType0InnerSourceFromSideWrapperCountsByIndex[index] || 0) + 1;
    const state = {
      event: "force-type0-inner-source-from-side-wrapper",
      timestamp: Date.now() / 1000.0,
      callerRva: callerRva,
      reason: missingSource ? "missing-source" : "suspicious-small-source",
      owner: hexPtr(owner),
      itemPointer: hexPtr(itemPointer),
      item: snapshotQueueItem(itemPointer),
      index: index,
      record: record,
      currentSourcePointer: currentSourcePointer,
      currentRequestedLength: currentRequestedLength,
      currentSourceSnapshot: currentSourceSnapshot,
      sideObjectPointer: record.ptr1a8,
      candidateStates: candidateStates,
      selectedSlot: candidate.slot,
      forcedSourcePointer: hexPtr(candidate.innerPointer),
      forcedRequestedLength: effectiveRequestedLength,
      forcedSourceSnapshot: snapshotPrepareSource(candidate.innerPointer),
      parserHeader: parserHeader,
      promotedRequestedLengthFromSecondary: promotedRequestedLengthFromSecondary
    };
    lastForcedType0InnerSourceFromSideWrapperState = state;
    send(state);
    return {
      forced: true,
      state: state
    };
  }
  const state = {
    event: "force-type0-inner-source-from-side-wrapper-skipped",
    timestamp: Date.now() / 1000.0,
    callerRva: callerRva,
    reason: missingSource ? "missing-source" : "suspicious-small-source",
    owner: hexPtr(owner),
    itemPointer: hexPtr(itemPointer),
    index: index,
    record: record,
    currentSourcePointer: currentSourcePointer,
    currentRequestedLength: currentRequestedLength,
    currentSourceSnapshot: currentSourceSnapshot,
    sideObjectPointer: record.ptr1a8,
    candidateStates: candidateStates
  };
  lastForcedType0InnerSourceFromSideWrapperState = state;
  send(state);
  return {
    forced: false,
    state: state
  };
}

function chooseType0SourceObjectCandidate(sideObjectPointer) {
  if (!pointerLooksSet(sideObjectPointer)) {
    return null;
  }
  try {
    const sideObject = ptr(sideObjectPointer);
    const ptr88 = safeReadPointer(sideObject.add(0x88));
    const ptrA0 = safeReadPointer(sideObject.add(0xA0));
    const ptr98 = safeReadPointer(sideObject.add(0x98));
    const current88 = hexPtr(ptr88);
    if (pointerLooksSet(current88)) {
      return {
        slot: "ptr88",
        pointer: current88,
        seededPtr88: false,
        siblingPointer: null,
        alternateSlot: null,
        alternatePointer: null,
        selectionReason: "ptr88-already-set",
        siblingDelta98ToA0: null
      };
    }
    const p98Text = hexPtr(ptr98);
    const a0Text = hexPtr(ptrA0);
    if (pointerLooksSet(p98Text) && pointerLooksSet(a0Text)) {
      const p98Value = parseU64String(p98Text);
      const a0Value = parseU64String(a0Text);
      const siblingDelta98ToA0 =
        p98Value === null || a0Value === null ? null : a0Value - p98Value;
      return {
        slot: "ptr98",
        pointer: p98Text,
        seededPtr88: true,
        siblingPointer: p98Text,
        alternateSlot: "ptrA0",
        alternatePointer: a0Text,
        selectionReason:
          siblingDelta98ToA0 === 8n
            ? "ptr98-base-preferred-over-ptrA0-plus8"
            : "ptr98-preferred-over-ptrA0",
        siblingDelta98ToA0:
          siblingDelta98ToA0 === null ? null : siblingDelta98ToA0.toString()
      };
    }
    if (pointerLooksSet(p98Text)) {
      return {
        slot: "ptr98",
        pointer: p98Text,
        seededPtr88: true,
        siblingPointer: p98Text,
        alternateSlot: null,
        alternatePointer: null,
        selectionReason: "ptr98-only",
        siblingDelta98ToA0: null
      };
    }
    if (pointerLooksSet(a0Text)) {
      return {
        slot: "ptrA0",
        pointer: a0Text,
        seededPtr88: true,
        siblingPointer: a0Text,
        alternateSlot: null,
        alternatePointer: null,
        selectionReason: "ptrA0-only",
        siblingDelta98ToA0: null
      };
    }
    return null;
  } catch (_error) {
    return null;
  }
}

function resourceRecordBase(owner, index) {
  if (
    owner === null ||
    owner === undefined ||
    index === null ||
    index === undefined ||
    index < 0 ||
    index >= resourceCount
  ) {
    return null;
  }
  try {
    return ptr(owner).add(8).add(index * recordStride);
  } catch (_error) {
    return null;
  }
}

function snapshotRecordFromBase(owner, index, recordBase) {
  if (
    owner === null ||
    owner === undefined ||
    index === null ||
    index === undefined ||
    index < 0 ||
    index >= resourceCount ||
    recordBase === null ||
    recordBase === undefined
  ) {
    return {
      index: index,
      validIndex: false,
      recordBase: hexPtr(recordBase)
    };
  }
  try {
    const record = ptr(recordBase);
    const ownerPointer = ptr(owner);
    return {
      index: index,
      validIndex: true,
      recordBase: hexPtr(record),
      recordIndex: safeReadS32(record.add(8)),
      flagD: safeReadU8(record.add(0x0d)),
      flagE: safeReadU8(record.add(0x0e)),
      flagF: safeReadU8(record.add(0x0f)),
      flag20: safeReadU8(record.add(0x20)),
      flag21: safeReadU8(record.add(0x21)),
      flag28: safeReadU8(record.add(0x28)),
      flag29: safeReadU8(record.add(0x29)),
      field10: safeReadS32(record.add(0x10)),
      field18: safeReadS32(record.add(0x18)),
      field1c: safeReadS32(record.add(0x1c)),
      total164: safeReadU32(record.add(0x164)),
      done168: safeReadU32(record.add(0x168)),
      busy16c: safeReadU8(record.add(0x16c)),
      field170: safeReadU32(record.add(0x170)),
      flag174: safeReadU8(record.add(0x174)),
      ptr178: hexPtr(safeReadPointer(record.add(0x178))),
      field180: safeReadU32(record.add(0x180)),
      ptr180: hexPtr(safeReadPointer(record.add(0x180))),
      ptr188: hexPtr(safeReadPointer(record.add(0x188))),
      word190: safeReadU16(record.add(0x190)),
      flag191: safeReadU8(record.add(0x191)),
      ptr1a0: hexPtr(safeReadPointer(record.add(0x1a0))),
      ptr1a8: hexPtr(safeReadPointer(record.add(0x1a8))),
      ptr1c8: hexPtr(safeReadPointer(record.add(0x1c8))),
      queueFlag11468: safeReadU8(ownerPointer.add(0x11468 + index)),
      loopState119e4: safeReadS32(ownerPointer.add(0x119e4 + index * 4)),
    };
  } catch (_error) {
    return {
      index: index,
      validIndex: false,
      recordBase: hexPtr(recordBase)
    };
  }
}

function snapshotRecord(owner, index) {
  return snapshotRecordFromBase(owner, index, resourceRecordBase(owner, index));
}

function queueLoopSecondaryRecordBase(owner, index) {
  if (owner === null || owner === undefined || index === null || index < 0 || index >= resourceCount) {
    return null;
  }
  return ptr(owner).add(0x7b90).add(index * recordStride);
}

function snapshotQueueLoopState(context) {
  try {
    const owner = ptr(context.rdi);
    const primaryRecordBase = ptr(context.rbp);
    const primaryIndex = safeReadS32(primaryRecordBase.add(8));
    const itemPointer = ptr(context.rsp).add(0x40);
    const item = snapshotQueueItem(itemPointer);
    const rawType =
      item && item.itemType !== null && item.itemType !== undefined ? item.itemType : context.rbx.toInt32();
    const predictedHandler = describeQueueLoopHandlerFromRawType(rawType);
    const selectorByte15 = safeReadU8(ptr(context.rsp).add(0x57));
    const secondaryRecordBase = queueLoopSecondaryRecordBase(owner, primaryIndex);
    const chosenType0RecordBase =
      selectorByte15 !== 0 && secondaryRecordBase !== null ? secondaryRecordBase : primaryRecordBase;
    return {
      owner: hexPtr(owner),
      primaryRecordBase: hexPtr(primaryRecordBase),
      secondaryRecordBase: hexPtr(secondaryRecordBase),
      chosenType0RecordBase: hexPtr(chosenType0RecordBase),
      index: primaryIndex,
      rawType: rawType,
      predictedHandler: predictedHandler,
      selectorByte15: selectorByte15,
      primaryRecord: snapshotRecordFromBase(owner, primaryIndex, primaryRecordBase),
      secondaryRecord:
        secondaryRecordBase === null
          ? null
          : snapshotRecordFromBase(owner, primaryIndex, secondaryRecordBase),
      itemPointer: hexPtr(itemPointer),
      item: item
    };
  } catch (_error) {
    return {
      unreadable: true,
      error: String(_error)
    };
  }
}

function retagQueueItemTypeInPlace(itemPointer, forcedType) {
  const source = ptr(itemPointer);
  const before = snapshotQueueItem(source);
  source.writeS32(forcedType);
  const after = snapshotQueueItem(source);
  return {
    before: before,
    after: after
  };
}

function syntheticType0RecordStateBridgeMatches(owner, itemPointer, recordBase) {
  if (!syntheticType0RecordStateBridge) {
    return false;
  }
  if (
    syntheticType0RecordStateBridge.owner !== hexPtr(owner) ||
    syntheticType0RecordStateBridge.itemPointer !== hexPtr(itemPointer)
  ) {
    return false;
  }
  const recordIndex = safeReadS32(ptr(recordBase).add(8));
  if (
    recordIndex === null ||
    recordIndex !== syntheticType0RecordStateBridge.index
  ) {
    return false;
  }
  const recordSnapshot = snapshotRecordFromBase(owner, recordIndex, recordBase);
  return recordSnapshot && recordSnapshot.validIndex && pointerLooksSet(recordSnapshot.ptr1c8);
}

function tryForceType0PrepareBranch(loopState) {
  if (!__FORCE_TYPE0_PREPARE_BRANCH__) {
    return {
      forced: false
    };
  }
  const primaryRecord = loopState ? loopState.primaryRecord : null;
  const loopStateValue =
    primaryRecord && primaryRecord.loopState119e4 !== undefined
      ? primaryRecord.loopState119e4
      : null;
  const total164 =
    primaryRecord && primaryRecord.total164 !== undefined ? primaryRecord.total164 : null;
  if (
    !loopState ||
    loopState.unreadable ||
    loopState.rawType !== 0 ||
    loopState.index === null ||
    !primaryRecord ||
    !primaryRecord.validIndex ||
    !pointerLooksSet(primaryRecord.ptr178) ||
    pointerLooksSet(primaryRecord.ptr1c8) ||
    total164 === null ||
    total164 <= 0 ||
    (loopStateValue !== 0 && loopStateValue !== 1 && loopStateValue !== 2) ||
    forcedType0PrepareBranchCountsByIndex[loopState.index]
  ) {
    return {
      forced: false
    };
  }
  try {
    const itemPointer = ptr(loopState.itemPointer);
    const resourceIndex = safeReadS32(itemPointer.add(4));
    const secondaryIndex = safeReadS32(itemPointer.add(8));
    if (resourceIndex === null || secondaryIndex === null) {
      return {
        forced: false
      };
    }
    const tableSlotPointer = safeReadPointer(ptr(loopState.owner).add(0x10c10 + resourceIndex * 0x20));
    if (!pointerLooksSet(hexPtr(tableSlotPointer))) {
      return {
        forced: false
      };
    }
    const entryStateAddress = ptr(tableSlotPointer).add(secondaryIndex + 1);
    const entryStateBefore = safeReadU8(entryStateAddress);
    if (entryStateBefore === null || entryStateBefore === 0) {
      return {
        forced: false
      };
    }
    entryStateAddress.writeU8(0);
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      resourceIndex: resourceIndex,
      secondaryIndex: secondaryIndex,
      tableSlotPointer: hexPtr(tableSlotPointer),
      entryStateAddress: hexPtr(entryStateAddress),
      entryStateBefore: entryStateBefore,
      entryStateAfter: safeReadU8(entryStateAddress),
      beforePrimaryRecord: primaryRecord
    };
    forcedType0PrepareBranchCountsByIndex[loopState.index] = 1;
    totalForcedType0PrepareBranch += 1;
    lastForcedType0PrepareBranchState = state;
    send({
      event: "force-type0-prepare-branch",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      state: state
    };
  } catch (_error) {
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      beforePrimaryRecord: primaryRecord,
      error: String(_error)
    };
    lastForcedType0PrepareBranchState = state;
    send({
      event: "force-type0-prepare-branch-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      state: state,
      error: String(_error)
    };
  }
}

function tryForceType0ChildMinus1Bypass(loopState) {
  if (!__FORCE_TYPE0_CHILDMINUS1_BYPASS__) {
    return { forced: false };
  }
  if (!loopState || !loopState.primaryRecord || !loopState.itemPointer) {
    return { forced: false };
  }
  const itemPointer = ptr(loopState.itemPointer);
  const field8 = safeReadS32(itemPointer.add(8));
  const byte17Before = safeReadU8(itemPointer.add(0x17));
  if (field8 !== -1 || byte17Before !== 0 || !loopState.primaryRecord.ptr178 || loopState.primaryRecord.ptr178 === "0x0") {
    return { forced: false };
  }
  try {
    itemPointer.add(0x17).writeU8(1);
    const byte17After = safeReadU8(itemPointer.add(0x17));
    if (byte17After !== 1) {
      return {
        forced: false,
        state: {
          index: loopState.index,
          owner: loopState.owner,
          itemPointer: loopState.itemPointer,
          field8: field8,
          byte17Before: byte17Before,
          byte17After: byte17After
        }
      };
    }
    totalForcedType0ChildMinus1Bypass += 1;
    if (loopState.index !== null && loopState.index !== undefined) {
      forcedType0ChildMinus1BypassCountsByIndex[loopState.index] =
        (forcedType0ChildMinus1BypassCountsByIndex[loopState.index] || 0) + 1;
    }
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      itemPointer: loopState.itemPointer,
      field8: field8,
      byte17Before: byte17Before,
      byte17After: byte17After,
      primaryRecord: loopState.primaryRecord
    };
    send({
      event: "force-type0-childminus1-bypass",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return { forced: true, state: state };
  } catch (error) {
    return {
      forced: false,
      error: String(error),
      state: {
        index: loopState.index,
        owner: loopState.owner,
        itemPointer: loopState.itemPointer,
        field8: field8,
        byte17Before: byte17Before
      }
    };
  }
}

function tryForceItemPayloadFromPtr178(loopState) {
  if (!__FORCE_ITEM_PAYLOAD_FROM_PTR178__) {
    return {
      forced: false
    };
  }
  const primaryRecord = loopState ? loopState.primaryRecord : null;
  const sourceItem = loopState ? loopState.item : null;
  const loopStateValue =
    primaryRecord && primaryRecord.loopState119e4 !== undefined
      ? primaryRecord.loopState119e4
      : null;
  const total164 =
    primaryRecord && primaryRecord.total164 !== undefined ? primaryRecord.total164 : null;
  const blobPointerValue = primaryRecord ? primaryRecord.ptr178 : null;
  const sourceByte17 =
    sourceItem && sourceItem.byte17 !== undefined ? sourceItem.byte17 : null;
  const shouldPromoteByte17 =
    loopState &&
    loopState.rawType === 0 &&
    sourceItem &&
    sourceItem.itemType === 0 &&
    sourceByte17 === 0 &&
    (loopStateValue === 0 || loopStateValue === 1 || loopStateValue === 2);
  if (
    !loopState ||
    loopState.unreadable ||
    loopState.index === null ||
    !primaryRecord ||
    !primaryRecord.validIndex ||
    !pointerLooksSet(blobPointerValue) ||
    total164 === null ||
    total164 <= 0 ||
    !sourceItem ||
    (sourceByte17 !== 1 && !shouldPromoteByte17) ||
    itemPayloadReady(loopState.itemPointer) ||
    forcedItemPayloadFromPtr178CountsByIndex[loopState.index]
  ) {
    return {
      forced: false
    };
  }
  try {
    const blobPointer = ptr(blobPointerValue);
    const itemPointer = ptr(loopState.itemPointer);
    const blobHeader = snapshotBlobHeader(blobPointer);
    const nativeRequestedLength =
      blobHeader &&
      typeof blobHeader.length === "number" &&
      blobHeader.length > total164
        ? blobHeader.length
        : total164;
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      blobHeader: blobHeader,
      requestedLength: nativeRequestedLength,
      requestedLengthFromBlobHeader: nativeRequestedLength !== total164,
      sourceByte17Before: sourceByte17,
      payloadReadyBefore: itemPayloadReady(itemPointer),
      beforeItem: snapshotQueueItem(itemPointer),
      beforePrimaryRecord: primaryRecord
    };
    state.field18Before =
      state.beforeItem && state.beforeItem.field18 !== undefined ? state.beforeItem.field18 : null;
    state.field1CBefore =
      state.beforeItem && state.beforeItem.field1C !== undefined ? state.beforeItem.field1C : null;
    if (shouldPromoteByte17) {
      itemPointer.add(0x17).writeU8(1);
      state.promotedByte17 = true;
    } else {
      state.promotedByte17 = false;
    }
    if (state.field18Before !== 2) {
      itemPointer.add(0x18).writeS32(2);
      state.promotedField18 = true;
    } else {
      state.promotedField18 = false;
    }
    if (
      total164 !== null &&
      total164 > 0 &&
      (state.field1CBefore === null || state.field1CBefore === undefined || state.field1CBefore <= 0)
    ) {
      itemPointer.add(0x1c).writeS32(total164);
      state.promotedField1C = true;
    } else {
      state.promotedField1C = false;
    }
    state.prepareResult =
      queueHelperPrepareNative(ptr(loopState.owner), blobPointer, nativeRequestedLength, itemPointer) === true;
    state.afterItem = snapshotQueueItem(itemPointer);
    state.afterPrimaryRecord = snapshotRecord(ptr(loopState.owner), loopState.index);
    state.payloadReadyAfter = itemPayloadReady(itemPointer);
    state.sourceByte17After =
      state.afterItem && state.afterItem.byte17 !== undefined ? state.afterItem.byte17 : null;
    if (state.payloadReadyAfter) {
      forcedItemPayloadFromPtr178CountsByIndex[loopState.index] = 1;
      totalForcedItemPayloadFromPtr178 += 1;
    }
    lastForcedItemPayloadFromPtr178State = state;
    send({
      event: "force-item-payload-from-ptr178",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: state.payloadReadyAfter === true,
      state: state
    };
  } catch (_error) {
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      sourceItem: sourceItem,
      beforePrimaryRecord: primaryRecord,
      error: String(_error)
    };
    lastForcedItemPayloadFromPtr178State = state;
    send({
      event: "force-item-payload-from-ptr178-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      state: state,
      error: String(_error)
    };
  }
}

function tryForceRecordStateFromType0(loopState, context) {
  if (!__FORCE_RECORDSTATE_FROM_TYPE0__) {
    return {
      forced: false
    };
  }
  const primaryRecord = loopState ? loopState.primaryRecord : null;
  const sourceItem = loopState ? loopState.item : null;
  const loopStateValue =
    primaryRecord && primaryRecord.loopState119e4 !== undefined
      ? primaryRecord.loopState119e4
      : null;
  const total164 =
    primaryRecord && primaryRecord.total164 !== undefined ? primaryRecord.total164 : null;
  const sourceByte17 =
    loopState && loopState.itemPointer
      ? safeReadU8(ptr(loopState.itemPointer).add(0x17))
      : sourceItem && sourceItem.byte17 !== undefined
        ? sourceItem.byte17
        : null;
  let sourceField18 =
    loopState && loopState.itemPointer
      ? safeReadS32(ptr(loopState.itemPointer).add(0x18))
      : sourceItem && sourceItem.field18 !== undefined
        ? sourceItem.field18
        : null;
  const sourceField18Before = sourceField18;
  let promotedField18To2 = false;
  if (
    forceType0Field18To2 &&
    loopState &&
    loopState.rawType === 0 &&
    loopState.itemPointer &&
    sourceByte17 === 1 &&
    sourceField18 === 1 &&
    total164 !== null &&
    total164 > 0 &&
    pointerLooksSet(primaryRecord ? primaryRecord.ptr178 : null) &&
    !pointerLooksSet(primaryRecord ? primaryRecord.ptr1c8 : null) &&
    (loopStateValue === 0 || loopStateValue === 1 || loopStateValue === 2)
  ) {
    try {
      ptr(loopState.itemPointer).add(0x18).writeS32(2);
      sourceField18 = safeReadS32(ptr(loopState.itemPointer).add(0x18));
      promotedField18To2 = sourceField18 === 2;
      const state = {
        index: loopState.index,
        owner: loopState.owner,
        itemPointer: loopState.itemPointer,
        sourceByte17: sourceByte17,
        sourceField18Before: sourceField18Before,
        sourceField18After: sourceField18,
        total164: total164,
        beforePrimaryRecord: primaryRecord
      };
      if (promotedField18To2) {
        totalForcedType0Field18To2 += 1;
        if (loopState.index !== null && loopState.index !== undefined) {
          forcedType0Field18To2CountsByIndex[loopState.index] =
            (forcedType0Field18To2CountsByIndex[loopState.index] || 0) + 1;
        }
        lastForcedType0Field18To2State = state;
        send({
          event: "force-type0-field18-to-2",
          timestamp: Date.now() / 1000.0,
          ...state
        });
      }
    } catch (_error) {
      const state = {
        index: loopState.index,
        owner: loopState.owner,
        itemPointer: loopState.itemPointer,
        sourceByte17: sourceByte17,
        sourceField18Before: sourceField18Before,
        total164: total164,
        beforePrimaryRecord: primaryRecord,
        error: String(_error)
      };
      lastForcedType0Field18To2State = state;
      send({
        event: "force-type0-field18-to-2-error",
        timestamp: Date.now() / 1000.0,
        ...state
      });
    }
  }
  const payloadReady = loopState ? itemPayloadReady(loopState.itemPointer) : false;
  const looksLikeType0RecordStateSource =
    sourceByte17 === 1 &&
    sourceField18 === 2 &&
    total164 !== null &&
    total164 > 0 &&
    pointerLooksSet(primaryRecord ? primaryRecord.ptr178 : null) &&
    !pointerLooksSet(primaryRecord ? primaryRecord.ptr1c8 : null) &&
    (loopStateValue === 0 || loopStateValue === 1 || loopStateValue === 2);
  if (
    loopState &&
    !loopState.unreadable &&
    loopState.rawType === 0 &&
    loopState.index !== null &&
    primaryRecord &&
    primaryRecord.validIndex &&
    looksLikeType0RecordStateSource &&
    !payloadReady &&
    !forcedRecordStateFromType0CountsByIndex[loopState.index] &&
    !skippedRecordStateFromType0CountsByIndex[loopState.index]
  ) {
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      sourceItem: loopState.item,
      sourceByte17: sourceByte17,
      sourceField18Before: sourceField18Before,
      sourceField18: sourceField18,
      promotedField18To2: promotedField18To2,
      payloadReadyBefore: payloadReady,
      beforePrimaryRecord: loopState.primaryRecord,
      reason: "payload-not-ready"
    };
    skippedRecordStateFromType0CountsByIndex[loopState.index] = 1;
    lastSkippedRecordStateFromType0State = state;
    send({
      event: "force-recordstate-from-type0-skipped",
      timestamp: Date.now() / 1000.0,
      ...state
    });
  }
  if (
    !loopState ||
    loopState.unreadable ||
    loopState.rawType !== 0 ||
    loopState.index === null ||
    !primaryRecord ||
    !primaryRecord.validIndex ||
    !looksLikeType0RecordStateSource ||
    !payloadReady ||
    forcedRecordStateFromType0CountsByIndex[loopState.index]
  ) {
    return {
      forced: false
    };
  }
  try {
    const dispatchRegisterBefore =
      context && context.rbx !== undefined && context.rbx !== null ? hexPtr(context.rbx) : null;
    const retaggedItem = retagQueueItemTypeInPlace(loopState.itemPointer, 1);
    if (context && context.rbx !== undefined && context.rbx !== null) {
      context.rbx = ptr(1);
    }
    const dispatchRegisterAfter =
      context && context.rbx !== undefined && context.rbx !== null ? hexPtr(context.rbx) : null;
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      sourceItem: loopState.item,
      sourceByte17: sourceByte17,
      sourceField18Before: sourceField18Before,
      sourceField18: sourceField18,
      promotedField18To2: promotedField18To2,
      payloadReadyBefore: payloadReady,
      dispatchRegisterBefore: dispatchRegisterBefore,
      dispatchRegisterAfter: dispatchRegisterAfter,
      retaggedItemBefore: retaggedItem.before,
      retaggedItemAfter: retaggedItem.after,
      beforePrimaryRecord: loopState.primaryRecord
    };
    forcedRecordStateFromType0CountsByIndex[loopState.index] = 1;
    totalForcedRecordStateFromType0 += 1;
    const previousSyntheticType0RecordStateBridge = syntheticType0RecordStateBridge;
    syntheticType0RecordStateBridge = {
      owner: loopState.owner,
      itemPointer: loopState.itemPointer,
      index: loopState.index
    };
    try {
      recordStateNative(ptr(loopState.owner), ptr(loopState.itemPointer));
    } finally {
      syntheticType0RecordStateBridge = previousSyntheticType0RecordStateBridge;
    }
    state.recordStateInvoked = true;
    state.afterPrimaryRecord = snapshotRecord(ptr(loopState.owner), loopState.index);
    state.afterOwnerSnapshot = snapshotOwner(ptr(loopState.owner));
    state.payloadReadyAfter = itemPayloadReady(loopState.itemPointer);
    state.ptr1c8Opened =
      state.afterPrimaryRecord && state.afterPrimaryRecord.validIndex
        ? pointerLooksSet(state.afterPrimaryRecord.ptr1c8)
        : false;
    lastForcedRecordStateFromType0State = state;
    send({
      event: "force-recordstate-from-type0",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: state.ptr1c8Opened === true,
      state: state
    };
  } catch (_error) {
    const state = {
      index: loopState.index,
      owner: loopState.owner,
      sourceItemPointer: loopState.itemPointer,
      sourceItem: loopState.item,
      sourceByte17: sourceByte17,
      sourceField18Before: sourceField18Before,
      sourceField18: sourceField18,
      promotedField18To2: promotedField18To2,
      payloadReadyBefore: payloadReady,
      beforePrimaryRecord: loopState.primaryRecord,
      error: String(_error)
    };
    lastForcedRecordStateFromType0State = state;
    send({
      event: "force-recordstate-from-type0-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      state: state,
      error: String(_error)
    };
  }
}

function tryForceType3FollowonOnPostState1(loopState) {
  if (!__FORCE_TYPE3_FOLLOWON_ON_POST_STATE1__) {
    return {
      forced: false
    };
  }
  const postRecord = loopState ? loopState.primaryRecord : null;
  const postLoopState = postRecord ? postRecord.loopState119e4 : null;
  if (
    !loopState ||
    loopState.unreadable ||
    (loopState.rawType !== 0 && loopState.rawType !== 1) ||
    loopState.index === null ||
    !postRecord ||
    !postRecord.validIndex ||
    (postLoopState !== 0 && postLoopState !== 1 && postLoopState !== 2) ||
    postRecord.flag21 !== 1 ||
    postRecord.flag20 !== 0 ||
    !pointerLooksSet(postRecord.ptr178) ||
    !pointerLooksSet(postRecord.ptr1c8) ||
    forcedType3FollowonOnPostState1CountsByIndex[loopState.index]
  ) {
    return {
      forced: false
    };
  }
  const recordBase = ptr(loopState.primaryRecord.recordBase);
  const state = {
    index: loopState.index,
    owner: loopState.owner,
    rawType: loopState.rawType,
    sourceItemPointer: loopState.itemPointer,
    sourceItem: loopState.item,
    beforePrimaryRecord: loopState.primaryRecord
  };
  try {
    const type3ReturnU8 = queueHandlerType3Native(recordBase) & 0xff;
    const type3ReturnBool = type3ReturnU8 !== 0;
    totalForcedType3FollowonOnPostState1 += 1;
    forcedType3FollowonOnPostState1CountsByIndex[loopState.index] = 1;
    state.type3ReturnU8 = type3ReturnU8;
    state.type3ReturnBool = type3ReturnBool;
    state.afterType3PrimaryRecord = snapshotRecord(ptr(loopState.owner), loopState.index);
    state.afterType3OwnerSnapshot = snapshotOwner(ptr(loopState.owner));
    let forcedFinalize = false;
    if (__FORCE_FINALIZE_AFTER_TYPE3_ON_POST_STATE1__ && type3ReturnBool) {
      recordFinalizeNative(ptr(loopState.owner), recordBase);
      forcedFinalize = true;
      totalForcedFinalizeAfterType3OnPostState1 += 1;
      forcedFinalizeAfterType3OnPostState1CountsByIndex[loopState.index] = 1;
    }
    state.forcedFinalize = forcedFinalize;
    state.afterFinalizePrimaryRecord = snapshotRecord(ptr(loopState.owner), loopState.index);
    state.afterFinalizeOwnerSnapshot = snapshotOwner(ptr(loopState.owner));
    const preparedSelectorReadyForce = tryForcePreparedSelectorReady(
      ptr(loopState.owner),
      "queue-post-type3-followon"
    );
    state.forcedPreparedSelectorReady = preparedSelectorReadyForce.forced === true;
    state.preparedSelectorReadyBefore = preparedSelectorReadyForce.before || null;
    state.preparedSelectorReadyAfter = preparedSelectorReadyForce.after || null;
    state.preparedSelectorReadyIndices = preparedSelectorReadyForce.preparedIndices || [];
    const directDispatchForce = tryForceDirectDispatchOnState1(
      ptr(loopState.owner),
      "queue-post-type3-followon"
    );
    state.forcedDirectDispatch = directDispatchForce.forced === true;
    state.directDispatchBefore = directDispatchForce.before || null;
    state.directDispatchAfter = directDispatchForce.after || null;
    state.directlyDispatchedIndices = directDispatchForce.dispatchedIndices || [];
    let reenteredRecordState = false;
    if (
      __REENTER_RECORDSTATE_AFTER_TYPE3_ON_POST_STATE1__ &&
      type3ReturnBool &&
      loopState.itemPointer &&
      !reenteredRecordStateAfterType3OnPostState1CountsByIndex[loopState.index]
    ) {
      try {
        recordStateNative(ptr(loopState.owner), ptr(loopState.itemPointer));
        reenteredRecordState = true;
        totalReenteredRecordStateAfterType3OnPostState1 += 1;
        reenteredRecordStateAfterType3OnPostState1CountsByIndex[loopState.index] = 1;
      } catch (_error) {
        state.reenterRecordStateError = String(_error);
      }
    }
    state.reenteredRecordState = reenteredRecordState;
    state.afterReenterPrimaryRecord = snapshotRecord(ptr(loopState.owner), loopState.index);
    state.afterReenterOwnerSnapshot = snapshotOwner(ptr(loopState.owner));
    if (reenteredRecordState || state.reenterRecordStateError) {
      lastReenteredRecordStateAfterType3OnPostState1State = state;
    }
    lastForcedType3FollowonOnPostState1State = state;
    send({
      event: "force-type3-followon-on-post-state1",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      state: state
    };
  } catch (_error) {
    state.error = String(_error);
    state.afterErrorPrimaryRecord = snapshotRecord(ptr(loopState.owner), loopState.index);
    state.afterErrorOwnerSnapshot = snapshotOwner(ptr(loopState.owner));
    lastForcedType3FollowonOnPostState1State = state;
    send({
      event: "force-type3-followon-on-post-state1-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      state: state,
      error: String(_error)
    };
  }
}

function tryForceFinalizeOnDispatchReturn(owner, index, beforeRecord, afterRecord) {
  if (!forceFinalizeOnDispatchReturn) {
    return {
      forced: false
    };
  }
  if (
    owner === null ||
    owner === undefined ||
    index === null ||
    index === undefined ||
    index < 0 ||
    index >= resourceCount ||
    !afterRecord ||
    afterRecord.validIndex !== true ||
    forcedFinalizeOnDispatchReturnCountsByIndex[index]
  ) {
    return {
      forced: false
    };
  }
  const hot =
    (typeof afterRecord.flagF === "number" && afterRecord.flagF !== 0) ||
    (typeof afterRecord.flagD === "number" && afterRecord.flagD !== 0) ||
    (typeof afterRecord.queueFlag11468 === "number" && afterRecord.queueFlag11468 !== 0);
  if (
    !hot ||
    !pointerLooksSet(afterRecord.ptr178) ||
    pointerLooksSet(afterRecord.ptr1c8) ||
    pointerLooksSet(afterRecord.ptr180) ||
    pointerLooksSet(afterRecord.ptr188) ||
    (typeof afterRecord.field170 === "number" && afterRecord.field170 !== 0 && afterRecord.field170 !== 1)
  ) {
    return {
      forced: false
    };
  }
  const recordBase = ptr(afterRecord.recordBase);
  const state = {
    index: index,
    owner: hexPtr(owner),
    beforeRecord: beforeRecord,
    afterRecordBeforeFinalize: afterRecord
  };
  try {
    recordFinalizeNative(ptr(owner), recordBase);
    forcedFinalizeOnDispatchReturnCountsByIndex[index] =
      (forcedFinalizeOnDispatchReturnCountsByIndex[index] || 0) + 1;
    totalForcedFinalizeOnDispatchReturn += 1;
    state.afterRecord = snapshotRecord(ptr(owner), index);
    state.afterOwnerSnapshot = snapshotOwner(ptr(owner));
    lastForcedFinalizeOnDispatchReturnState = state;
    sendUnique(
      seenForcedFinalizeOnDispatchReturnStates,
      "force-finalize-on-dispatch-return",
      state
    );
    return {
      forced: true,
      state: state
    };
  } catch (_error) {
    state.error = String(_error);
    state.afterErrorRecord = snapshotRecord(ptr(owner), index);
    state.afterErrorOwnerSnapshot = snapshotOwner(ptr(owner));
    lastForcedFinalizeOnDispatchReturnState = state;
    send({
      event: "force-finalize-on-dispatch-return-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      state: state,
      error: String(_error)
    };
  }
}

function inferOwnerFromRecordBase(recordBase) {
  if (recordBase === null || recordBase === undefined) {
    return null;
  }
  try {
    const record = ptr(recordBase);
    const index = safeReadS32(record.add(8));
    if (index === null || index < 0 || index >= resourceCount) {
      return null;
    }
    return record.sub(8).sub(index * recordStride);
  } catch (_error) {
    return null;
  }
}

function normalizePostSelectRecordBase(recordPointerLike) {
  if (recordPointerLike === null || recordPointerLike === undefined) {
    return null;
  }
  try {
    return ptr(recordPointerLike).sub(8);
  } catch (_error) {
    return null;
  }
}

function snapshotOwner(owner) {
  if (!pointerLooksSet(owner)) {
    return null;
  }
  try {
    owner = ptr(owner);
    if (owner.isNull()) {
      return null;
    }
  } catch (_error) {
    return null;
  }
  const activeIndices = [];
  const completedIndices = [];
  const flagged20Indices = [];
  const flagged21Indices = [];
  const flagged28Indices = [];
  const inflightIndices = [];
  const queuedIndices = [];
  const stateIndices = [];
  const field1cNonZeroIndices = [];
  const ptr178SetIndices = [];
  const ptr1a0SetIndices = [];
  const ptr1a8SetIndices = [];
  const ptr1c8SetIndices = [];
  const selectorEligibleIndices = [];
  const selectorPtr178Details = [];
  const selectorReasonCounts = {
    ptr178Missing: 0,
    busy: 0,
    totalZero: 0,
    doneZero: 0,
    pctBelow5: 0,
    eligible: 0
  };
  for (let index = 0; index < resourceCount; index++) {
    const record = resourceRecordBase(owner, index);
    const flagD = safeReadU8(record.add(0x0d));
    const flagE = safeReadU8(record.add(0x0e));
    const flagF = safeReadU8(record.add(0x0f));
    const flag20 = safeReadU8(record.add(0x20));
    const flag21 = safeReadU8(record.add(0x21));
    const flag28 = safeReadU8(record.add(0x28));
    const flag29 = safeReadU8(record.add(0x29));
    const field1c = safeReadS32(record.add(0x1c));
    const total164 = safeReadU32(record.add(0x164));
    const done168 = safeReadU32(record.add(0x168));
    const busy16c = safeReadU8(record.add(0x16c));
    const field170 = safeReadU32(record.add(0x170));
    const flag174 = safeReadU8(record.add(0x174));
    const ptr178 = hexPtr(safeReadPointer(record.add(0x178)));
    const field180 = safeReadU32(record.add(0x180));
    const ptr180 = hexPtr(safeReadPointer(record.add(0x180)));
    const ptr188 = hexPtr(safeReadPointer(record.add(0x188)));
    const word190 = safeReadU16(record.add(0x190));
    const flag191 = safeReadU8(record.add(0x191));
    const ptr1a0 = hexPtr(safeReadPointer(record.add(0x1a0)));
    const ptr1a8 = hexPtr(safeReadPointer(record.add(0x1a8)));
    const ptr1c8 = hexPtr(safeReadPointer(record.add(0x1c8)));
    const inflight = safeReadU8(ptr(owner).add(0x11468 + index));
    const stateValue = safeReadS32(ptr(owner).add(0x119e4 + index * 4));
    const recordIndexField = safeReadS32(record.add(8));
    const hasPtr178 = ptr178 && ptr178 !== "0x0";
    let selectorPct = null;
    if (total164 !== null && total164 !== 0 && done168 !== null) {
      selectorPct = Math.floor((done168 * 100) / total164);
    }
    let selectorReason = "eligible";
    if (!hasPtr178) {
      selectorReason = "ptr178Missing";
    } else if (busy16c !== 0) {
      selectorReason = "busy";
    } else if (total164 === null || total164 === 0) {
      selectorReason = "totalZero";
    } else if (done168 === null || done168 === 0) {
      selectorReason = "doneZero";
    } else if (selectorPct === null || selectorPct < 5) {
      selectorReason = "pctBelow5";
    }
    if (flagD) {
      activeIndices.push(index);
    }
    if (flagE) {
      completedIndices.push(index);
    }
    if (flag20) {
      flagged20Indices.push(index);
    }
    if (flag21) {
      flagged21Indices.push(index);
    }
    if (flag28) {
      flagged28Indices.push(index);
    }
    if (field1c) {
      field1cNonZeroIndices.push(index);
    }
    if (hasPtr178) {
      ptr178SetIndices.push(index);
      selectorPtr178Details.push({
        index: index,
        recordIndexField: recordIndexField,
        state: stateValue,
        total164: total164,
        done168: done168,
        pct: selectorPct,
        busy16c: busy16c,
        field170: field170,
        flag174: flag174,
        field180: field180,
        ptr180: ptr180,
        ptr188: ptr188,
        word190: word190,
        flag191: flag191,
        ptr1a0: ptr1a0,
        ptr1a8: ptr1a8,
        flagD: flagD,
        flagE: flagE,
        flagF: flagF,
        flag28: flag28,
        flag29: flag29,
        queued: inflight,
        selectorReason: selectorReason
      });
      selectorReasonCounts[selectorReason] += 1;
      if (selectorReason === "eligible") {
        selectorEligibleIndices.push(index);
      }
    } else {
      selectorReasonCounts.ptr178Missing += 1;
    }
    if (ptr1a0 && ptr1a0 !== "0x0") {
      ptr1a0SetIndices.push(index);
    }
    if (ptr1a8 && ptr1a8 !== "0x0") {
      ptr1a8SetIndices.push(index);
    }
    if (ptr1c8 && ptr1c8 !== "0x0") {
      ptr1c8SetIndices.push(index);
    }
    if (inflight) {
      inflightIndices.push(index);
      queuedIndices.push(index);
    }
    if (stateValue) {
      stateIndices.push({
        index: index,
        state: stateValue
      });
    }
  }
  const schedulerGlobal = safeReadU64(schedulerGlobalAddress);
  const timer11b50 = safeReadU64(ptr(owner).add(0x11b50));
  const schedulerGlobalBig = parseU64String(schedulerGlobal);
  const timer11b50Big = parseU64String(timer11b50);
  const queueHead11540Ptr = safeReadPointer(ptr(owner).add(0x11540));
  const queueCursor11548Ptr = safeReadPointer(ptr(owner).add(0x11548));
  const queueEnd11550Ptr = safeReadPointer(ptr(owner).add(0x11550));
  const queueHead11558Ptr = safeReadPointer(ptr(owner).add(0x11558));
  const queueCursor11560Ptr = safeReadPointer(ptr(owner).add(0x11560));
  const queueEnd11568Ptr = safeReadPointer(ptr(owner).add(0x11568));
  const timerGateOpen =
    schedulerGlobalBig !== null && timer11b50Big !== null
      ? schedulerGlobalBig >= timer11b50Big
      : null;
  return {
    owner: hexPtr(owner),
    owner11bc8: hexPtr(ptr(owner).add(0x11bc8)),
    flag11b48: safeReadU8(ptr(owner).add(0x11b48)),
    flag11b58: safeReadU8(ptr(owner).add(0x11b58)),
    flag11d48: safeReadU8(ptr(owner).add(0x11d48)),
    flag11d49: safeReadU8(ptr(owner).add(0x11d49)),
    flag11d4a: safeReadU8(ptr(owner).add(0x11d4a)),
    flag11508: safeReadU8(ptr(owner).add(0x11508)),
    flag114e0: safeReadU8(ptr(owner).add(0x114e0)),
    field114e8: safeReadS32(ptr(owner).add(0x114e8)),
    field114ec: safeReadS32(ptr(owner).add(0x114ec)),
    field114f0: safeReadS32(ptr(owner).add(0x114f0)),
    queueHead11540: hexPtr(queueHead11540Ptr),
    queueCursor11548: hexPtr(queueCursor11548Ptr),
    queueEnd11550: hexPtr(queueEnd11550Ptr),
    queuePending11540Count: pointerSpanCount(queueHead11540Ptr, queueCursor11548Ptr, 0x30),
    queueHead11558: hexPtr(queueHead11558Ptr),
    queueCursor11560: hexPtr(queueCursor11560Ptr),
    queueEnd11568: hexPtr(queueEnd11568Ptr),
    queuePending11558Count: pointerSpanCount(queueHead11558Ptr, queueCursor11560Ptr, 0x30),
    schedulerGlobal: schedulerGlobal,
    timer11b50: timer11b50,
    timerGateOpen: timerGateOpen,
    field1cNonZeroCount: field1cNonZeroIndices.length,
    field1cNonZeroIndices: field1cNonZeroIndices,
    ptr178SetCount: ptr178SetIndices.length,
    ptr178SetIndices: ptr178SetIndices,
    ptr1a0SetCount: ptr1a0SetIndices.length,
    ptr1a0SetIndices: ptr1a0SetIndices,
    ptr1a8SetCount: ptr1a8SetIndices.length,
    ptr1a8SetIndices: ptr1a8SetIndices,
    ptr1c8SetCount: ptr1c8SetIndices.length,
    ptr1c8SetIndices: ptr1c8SetIndices,
    selectorEligibleCount: selectorEligibleIndices.length,
    selectorEligibleIndices: selectorEligibleIndices,
    selectorReasonCounts: selectorReasonCounts,
    selectorPtr178Details: selectorPtr178Details,
    queuedCount: queuedIndices.length,
    queuedIndices: queuedIndices,
    stateCount: stateIndices.length,
    stateIndices: stateIndices,
    activeIndices: activeIndices,
    completedIndices: completedIndices,
    flagged20Indices: flagged20Indices,
    flagged21Indices: flagged21Indices,
    flagged28Indices: flagged28Indices,
    inflightIndices: inflightIndices,
  };
}

function tryForceOwnerStageClear(owner, reason) {
  if (!__FORCE_OWNER_STAGE_CLEAR_WHEN_DRAINED__) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  if (
    !before ||
    before.activeIndices.length !== 0 ||
    before.inflightIndices.length !== 0 ||
    (before.flag11b58 === 0 && before.flag11d49 === 0 && before.flag11d4a === 0)
  ) {
    return {
      forced: false,
      before: before
    };
  }
  try {
    ptr(owner).add(0x11b58).writeU8(0);
    ptr(owner).add(0x11d49).writeU8(0);
    ptr(owner).add(0x11d4a).writeU8(0);
    totalForcedOwnerStageClear += 1;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      before: before,
      after: after
    };
    lastOwnerStageForceState = state;
    send({
      event: "owner-stage-clear-when-drained",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after
    };
  } catch (_error) {
    const state = {
      reason: reason,
      before: before,
      error: String(_error)
    };
    lastOwnerStageForceState = state;
    send({
      event: "owner-stage-clear-when-drained-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      error: String(_error)
    };
  }
}

function tryForceRecordOpenOnField1c(owner, reason) {
  if (!__FORCE_RECORD_OPEN_ON_FIELD1C__ || recordOpenForcedOnce || recordOpenForceInProgress) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const candidateRecords = [];
  if (before && before.field1cNonZeroIndices) {
    for (const index of before.field1cNonZeroIndices) {
      const record = snapshotRecord(owner, index);
      if (
        !record ||
        record.validIndex !== true ||
        typeof record.recordIndex !== "number" ||
        record.recordIndex < 0 ||
        typeof record.field1c !== "number" ||
        record.field1c <= 1 ||
        pointerLooksSet(record.ptr178) ||
        pointerLooksSet(record.ptr1c8)
      ) {
        continue;
      }
      candidateRecords.push(record);
    }
  }
  const candidateIndices = candidateRecords.map((record) => record.index);
  if (
    !before ||
    candidateRecords.length === 0 ||
    before.ptr178SetCount !== 0 ||
    before.ptr1c8SetCount !== 0 ||
    before.stateCount !== 0 ||
    before.activeIndices.length !== 0 ||
    before.completedIndices.length !== 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  recordOpenForceInProgress = true;
  try {
    const openedIndices = [];
    const errors = [];
    for (const record of candidateRecords) {
      try {
        const opened = recordOpenNative(ptr(record.recordBase));
        const afterRecord = snapshotRecord(owner, record.index);
        if (opened === true || pointerLooksSet(afterRecord ? afterRecord.ptr178 : null)) {
          openedIndices.push(record.index);
          forcedRecordOpenCountsByIndex[record.index] =
            (forcedRecordOpenCountsByIndex[record.index] || 0) + 1;
        }
      } catch (_error) {
        errors.push({
          index: record.index,
          recordIndex: record.recordIndex,
          error: String(_error)
        });
      }
    }
    if (openedIndices.length === 0) {
      return {
        forced: false,
        before: before,
        openedIndices: openedIndices,
        candidateIndices: candidateIndices,
        errors: errors
      };
    }
    recordOpenForcedOnce = true;
    totalForcedRecordOpen += openedIndices.length;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      openedIndices: openedIndices,
      before: before,
      after: after,
      errors: errors
    };
    lastRecordOpenForceState = state;
    send({
      event: "owner-record-open-on-field1c",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after,
      openedIndices: openedIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      before: before,
      error: String(_error)
    };
    lastRecordOpenForceState = state;
    send({
      event: "owner-record-open-on-field1c-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      openedIndices: candidateIndices,
      error: String(_error)
    };
  } finally {
    recordOpenForceInProgress = false;
  }
}

function tryForceSeedDispatchOnPtr178(owner, reason) {
  if (!__FORCE_SEED_DISPATCH_ON_PTR178__ || seedDispatchForcedOnce || seedDispatchInProgress) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const seedableIndices =
    before && before.ptr178SetIndices
      ? before.ptr178SetIndices.filter((index) => {
          const record = snapshotRecord(owner, index);
          return (
            record &&
            record.validIndex === true &&
            typeof record.recordIndex === "number" &&
            record.recordIndex >= 0 &&
            pointerLooksSet(record.ptr178)
          );
        })
      : [];
  const queuedIndices = before && before.queuedIndices ? before.queuedIndices.slice() : [];
  const stateIndices = before && before.stateIndices ? before.stateIndices.slice() : [];
  const activeIndices = before && before.activeIndices ? before.activeIndices.slice() : [];
  const completedRecordIndices =
    before && before.completedIndices ? before.completedIndices.slice() : [];
  const ptr1c8Indices = before && before.ptr1c8SetIndices ? before.ptr1c8SetIndices.slice() : [];
  const candidateIndices = [];
  function addCandidate(index) {
    if (candidateIndices.indexOf(index) !== -1) {
      return;
    }
    if (seedableIndices.indexOf(index) === -1) {
      return;
    }
    const record = snapshotRecord(owner, index);
    if (
      !record ||
      record.validIndex !== true ||
      !pointerLooksSet(record.ptr178) ||
      pointerLooksSet(record.ptr1c8) ||
      (typeof record.field180 === "number" && record.field180 !== 0) ||
      (typeof record.flagE === "number" && record.flagE !== 0)
    ) {
      return;
    }
    candidateIndices.push(index);
  }
  for (const index of queuedIndices) {
    addCandidate(index);
  }
  for (const index of activeIndices) {
    addCandidate(index);
  }
  for (const index of seedableIndices) {
    addCandidate(index);
  }
  const selectedSeedIndex = candidateIndices.length === 0 ? null : candidateIndices[0];
  const selectedCandidateIndices = selectedSeedIndex === null ? [] : [selectedSeedIndex];
  if (
    !before ||
    seedableIndices.length === 0 ||
    stateIndices.length !== 0 ||
    ptr1c8Indices.length !== 0 ||
    selectedCandidateIndices.length === 0
  ) {
    return {
      forced: false,
      before: before
    };
  }
  seedDispatchInProgress = true;
  try {
    const completedIndices = [];
    const errors = [];
    for (const index of selectedCandidateIndices) {
      try {
        seedDispatch(ptr(owner), index);
        completedIndices.push(index);
      } catch (_error) {
        errors.push({
          index: index,
          error: String(_error)
        });
      }
    }
    if (completedIndices.length === 0) {
      return {
        forced: false,
        before: before,
        consideredIndices: candidateIndices,
        seededIndices: selectedCandidateIndices,
        error: errors.length === 0 ? null : JSON.stringify(errors)
      };
    }
    seedDispatchForcedOnce = true;
    totalForcedSeedDispatch += completedIndices.length;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      mode:
        queuedIndices.length !== 0 || activeIndices.length !== 0
          ? "queued-active-fallback"
          : "cold-bootstrap",
      consideredIndices: candidateIndices,
      queuedIndices: queuedIndices,
      activeIndices: activeIndices,
      completedIndicesBefore: completedRecordIndices,
      seededIndices: completedIndices,
      before: before,
      after: after,
      errors: errors
    };
    lastSeedDispatchForceState = state;
    send({
      event: "owner-seed-dispatch-on-ptr178",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after,
      seededIndices: completedIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      mode:
        queuedIndices.length !== 0 || activeIndices.length !== 0
          ? "queued-active-fallback"
          : "cold-bootstrap",
      consideredIndices: candidateIndices,
      queuedIndices: queuedIndices,
      activeIndices: activeIndices,
      completedIndicesBefore: completedRecordIndices,
      seededIndices: selectedCandidateIndices,
      before: before,
      error: String(_error)
    };
    lastSeedDispatchForceState = state;
    send({
      event: "owner-seed-dispatch-on-ptr178-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      consideredIndices: candidateIndices,
      seededIndices: selectedCandidateIndices,
      error: String(_error)
    };
  } finally {
    seedDispatchInProgress = false;
  }
}

function collectPtr178DispatchReadyIndices(ownerSnapshot) {
  if (!ownerSnapshot) {
    return [];
  }
  const candidateIndices = [];
  for (const entry of ownerSnapshot.selectorPtr178Details || []) {
    if (!entry || entry.index === null || entry.index === undefined) {
      continue;
    }
    const totalKnown = typeof entry.total164 === "number" && entry.total164 > 0;
    const configured = typeof entry.recordIndexField === "number" && entry.recordIndexField >= 0;
    const alreadyQueued = typeof entry.queued === "number" && entry.queued !== 0;
    const alreadyReady = typeof entry.flagD === "number" && entry.flagD !== 0;
    const completed = typeof entry.flagE === "number" && entry.flagE !== 0;
    const busy = typeof entry.busy16c === "number" && entry.busy16c !== 0;
    if (
      !totalKnown ||
      !configured ||
      alreadyQueued ||
      alreadyReady ||
      completed ||
      busy
    ) {
      continue;
    }
    candidateIndices.push(entry.index);
  }
  return candidateIndices;
}

function tryForceRecordDReadyOnPtr178(owner, reason) {
  if (!__FORCE_RECORDD_READY_ON_PTR178__) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const candidateIndices = collectPtr178DispatchReadyIndices(before).filter(
    (index) => !(index in forcedRecordDReadyOnPtr178CountsByIndex)
  );
  if (!before || candidateIndices.length === 0) {
    return {
      forced: false,
      before: before
    };
  }
  try {
    for (const index of candidateIndices) {
      const recordBase = ptr(owner).add(8 + (index * recordStride));
      recordBase.add(0x0d).writeU8(1);
      recordBase.add(0x0e).writeU8(0);
      ptr(owner).add(0x11d4a).writeU8(1);
      forcedRecordDReadyOnPtr178CountsByIndex[index] =
        (forcedRecordDReadyOnPtr178CountsByIndex[index] || 0) + 1;
    }
    totalForcedRecordDReadyOnPtr178 += candidateIndices.length;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      before: before,
      after: after
    };
    lastRecordDReadyOnPtr178State = state;
    send({
      event: "recordd-ready-on-ptr178",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after,
      candidateIndices: candidateIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      before: before,
      error: String(_error)
    };
    lastRecordDReadyOnPtr178State = state;
    send({
      event: "recordd-ready-on-ptr178-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error)
    };
  }
}

function tryForceRecordDReadyOnLatchClear(owner, index, reason) {
  if (!__FORCE_RECORDD_READY_ON_LATCH_CLEAR__) {
    return {
      forced: false
    };
  }
  const beforeOwner = snapshotOwner(owner);
  const beforeRecord = snapshotRecord(owner, index);
  const latchClearCount =
    index !== null && index !== undefined && (index in selectionLatchClearCountsByIndex)
      ? selectionLatchClearCountsByIndex[index]
      : 0;
  const inflightIndices =
    beforeOwner && beforeOwner.inflightIndices ? beforeOwner.inflightIndices.slice() : [];
  if (
    !beforeOwner ||
    !beforeRecord ||
    !beforeRecord.validIndex ||
    index === null ||
    index < 0 ||
    index >= resourceCount ||
    (index in forcedRecordDReadyOnLatchClearCountsByIndex) ||
    beforeOwner.flag11b48 === 0 ||
    beforeOwner.flag11d49 === 0 ||
    beforeOwner.flag11d48 !== 0 ||
    beforeOwner.flag11508 !== 0 ||
    beforeOwner.timerGateOpen !== true ||
    beforeOwner.queuedCount !== 1 ||
    beforeOwner.ptr178SetCount < 10 ||
    latchClearCount < 2 ||
    inflightIndices.length !== 1 ||
    inflightIndices[0] !== index ||
    !pointerLooksSet(beforeRecord.ptr178) ||
    pointerLooksSet(beforeRecord.ptr1c8) ||
    pointerLooksSet(beforeRecord.ptr180) ||
    pointerLooksSet(beforeRecord.ptr188) ||
    beforeRecord.queueFlag11468 === 0 ||
    beforeRecord.flagD !== 0 ||
    beforeRecord.flagE !== 0 ||
    beforeRecord.flag20 !== 0 ||
    beforeRecord.busy16c !== 0 ||
    beforeRecord.field1c === 0 ||
    beforeRecord.loopState119e4 !== 2
  ) {
    return {
      forced: false,
      beforeOwner: beforeOwner,
      beforeRecord: beforeRecord,
      latchClearCount: latchClearCount
    };
  }
  try {
    const recordBase = ptr(beforeRecord.recordBase);
    recordBase.add(0x0d).writeU8(1);
    recordBase.add(0x0e).writeU8(0);
    ptr(owner).add(0x11468 + index).writeU8(0);
    ptr(owner).add(0x11d4a).writeU8(1);
    forcedRecordDReadyOnLatchClearCountsByIndex[index] =
      (forcedRecordDReadyOnLatchClearCountsByIndex[index] || 0) + 1;
    totalForcedRecordDReadyOnLatchClear += 1;
    const afterRecord = snapshotRecord(owner, index);
    const afterOwner = snapshotOwner(owner);
    const state = {
      reason: reason,
      index: index,
      latchClearCount: latchClearCount,
      beforeRecord: beforeRecord,
      afterRecord: afterRecord,
      beforeOwner: beforeOwner,
      afterOwner: afterOwner
    };
    lastRecordDReadyOnLatchClearState = state;
    send({
      event: "recordd-ready-on-latch-clear",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      beforeOwner: beforeOwner,
      afterOwner: afterOwner,
      beforeRecord: beforeRecord,
      afterRecord: afterRecord,
      latchClearCount: latchClearCount
    };
  } catch (_error) {
    const state = {
      reason: reason,
      index: index,
      latchClearCount: latchClearCount,
      beforeOwner: beforeOwner,
      beforeRecord: beforeRecord,
      error: String(_error)
    };
    lastRecordDReadyOnLatchClearState = state;
    send({
      event: "recordd-ready-on-latch-clear-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      beforeOwner: beforeOwner,
      beforeRecord: beforeRecord,
      latchClearCount: latchClearCount,
      error: String(_error)
    };
  }
}

function tryForceRecordDReadyOnCloseSuppression(owner, index, reason, ownerSnapshot, recordSnapshot) {
  if (!__FORCE_RECORDD_READY_ON_CLOSE_SUPPRESSION__) {
    return {
      forced: false
    };
  }
  const beforeOwner = ownerSnapshot || snapshotOwner(owner);
  const beforeRecord = recordSnapshot || snapshotRecord(owner, index);
  const firstPtr178Index =
    beforeOwner &&
    beforeOwner.ptr178SetIndices &&
    beforeOwner.ptr178SetIndices.length !== 0
      ? beforeOwner.ptr178SetIndices[0]
      : null;
  if (
    !beforeOwner ||
    !beforeRecord ||
    !beforeRecord.validIndex ||
    index === null ||
    index < 0 ||
    index >= resourceCount ||
    (index in forcedRecordDReadyOnCloseSuppressionCountsByIndex) ||
    firstPtr178Index === null ||
    index !== firstPtr178Index ||
    beforeOwner.flag11b48 === 0 ||
    beforeOwner.flag11d49 === 0 ||
    beforeOwner.flag11d48 !== 0 ||
    beforeOwner.flag11508 !== 0 ||
    beforeOwner.ptr178SetCount < 10 ||
    !pointerLooksSet(beforeRecord.ptr178) ||
    pointerLooksSet(beforeRecord.ptr1c8) ||
    pointerLooksSet(beforeRecord.ptr180) ||
    pointerLooksSet(beforeRecord.ptr188) ||
    beforeRecord.queueFlag11468 !== 0 ||
    beforeRecord.flagD !== 0 ||
    beforeRecord.flagE !== 0 ||
    beforeRecord.flag20 !== 0 ||
    beforeRecord.busy16c !== 0 ||
    beforeRecord.field1c === 0 ||
    beforeRecord.loopState119e4 !== 2
  ) {
    return {
      forced: false,
      beforeOwner: beforeOwner,
      beforeRecord: beforeRecord,
      firstPtr178Index: firstPtr178Index
    };
  }
  try {
    const recordBase = ptr(beforeRecord.recordBase);
    recordBase.add(0x0d).writeU8(1);
    recordBase.add(0x0e).writeU8(0);
    ptr(owner).add(0x11468 + index).writeU8(0);
    ptr(owner).add(0x11d4a).writeU8(1);
    forcedRecordDReadyOnCloseSuppressionCountsByIndex[index] =
      (forcedRecordDReadyOnCloseSuppressionCountsByIndex[index] || 0) + 1;
    totalForcedRecordDReadyOnCloseSuppression += 1;
    const afterRecord = snapshotRecord(owner, index);
    const afterOwner = snapshotOwner(owner);
    const state = {
      reason: reason,
      index: index,
      firstPtr178Index: firstPtr178Index,
      beforeRecord: beforeRecord,
      afterRecord: afterRecord,
      beforeOwner: beforeOwner,
      afterOwner: afterOwner
    };
    lastRecordDReadyOnCloseSuppressionState = state;
    send({
      event: "recordd-ready-on-close-suppression",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      beforeOwner: beforeOwner,
      afterOwner: afterOwner,
      beforeRecord: beforeRecord,
      afterRecord: afterRecord,
      firstPtr178Index: firstPtr178Index
    };
  } catch (_error) {
    const state = {
      reason: reason,
      index: index,
      firstPtr178Index: firstPtr178Index,
      beforeOwner: beforeOwner,
      beforeRecord: beforeRecord,
      error: String(_error)
    };
    lastRecordDReadyOnCloseSuppressionState = state;
    send({
      event: "recordd-ready-on-close-suppression-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      beforeOwner: beforeOwner,
      beforeRecord: beforeRecord,
      firstPtr178Index: firstPtr178Index,
      error: String(_error)
    };
  }
}

function collectPtr178SelectorReadyIndices(ownerSnapshot) {
  if (!ownerSnapshot) {
    return [];
  }
  const candidateIndices = [];
  for (const entry of ownerSnapshot.selectorPtr178Details || []) {
    if (!entry || entry.index === null || entry.index === undefined) {
      continue;
    }
    const totalKnown = typeof entry.total164 === "number" && entry.total164 > 0;
    const busy = typeof entry.busy16c === "number" && entry.busy16c !== 0;
    const pctReady = typeof entry.pct === "number" && entry.pct >= 5;
    if (
      !totalKnown ||
      busy ||
      entry.selectorReason === "ptr178Missing" ||
      entry.selectorReason === "totalZero" ||
      pctReady
    ) {
      continue;
    }
    candidateIndices.push(entry.index);
  }
  return candidateIndices;
}

function tryForceSelectorReadyOnPtr178(owner, reason) {
  if (!__FORCE_SELECTOR_READY_ON_PTR178__) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const candidateIndices = collectPtr178SelectorReadyIndices(before).filter(
    (index) => !(index in forcedSelectorReadyOnPtr178CountsByIndex)
  );
  const blockingStateIndices =
    before && before.stateIndices
      ? before.stateIndices.filter(item => {
          if (!item || typeof item.index !== "number") {
            return true;
          }
          if (candidateIndices.indexOf(item.index) === -1) {
            return true;
          }
          return item.state !== 1 && item.state !== 2;
        })
      : [];
  if (
    !before ||
    before.ptr1c8SetCount !== 0 ||
    blockingStateIndices.length !== 0 ||
    candidateIndices.length === 0
  ) {
    return {
      forced: false,
      before: before,
      blockingStateIndices: blockingStateIndices
    };
  }
  try {
    for (const index of candidateIndices) {
      const recordBase = ptr(owner).add(8 + (index * recordStride));
      const total164 = safeReadU32(recordBase.add(0x164));
      const effectiveTotal = total164 === null || total164 === 0 ? 100 : total164;
      const requiredDone = Math.max(1, Math.ceil((effectiveTotal * 5) / 100));
      const done168 = safeReadU32(recordBase.add(0x168));
      if (done168 === null || done168 < requiredDone) {
        recordBase.add(0x168).writeU32(requiredDone);
      }
      recordBase.add(0x16c).writeU8(0);
      ptr(owner).add(0x11468 + index).writeU8(0);
      forcedSelectorReadyOnPtr178CountsByIndex[index] =
        (forcedSelectorReadyOnPtr178CountsByIndex[index] || 0) + 1;
    }
    totalForcedSelectorReadyOnPtr178 += candidateIndices.length;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      blockingStateIndices: blockingStateIndices,
      before: before,
      after: after
    };
    lastSelectorReadyOnPtr178State = state;
    send({
      event: "selector-ready-on-ptr178",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after,
      candidateIndices: candidateIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      blockingStateIndices: blockingStateIndices,
      before: before,
      error: String(_error)
    };
    lastSelectorReadyOnPtr178State = state;
    send({
      event: "selector-ready-on-ptr178-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error)
    };
  }
}

function collectPreparedDispatchIndices(ownerSnapshot) {
  if (!ownerSnapshot) {
    return [];
  }
  const ptr1c8Set = {};
  const flagged20 = {};
  const flagged21 = {};
  for (const index of ownerSnapshot.ptr1c8SetIndices || []) {
    ptr1c8Set[index] = 1;
  }
  for (const index of ownerSnapshot.flagged20Indices || []) {
    flagged20[index] = 1;
  }
  for (const index of ownerSnapshot.flagged21Indices || []) {
    flagged21[index] = 1;
  }
  const preparedIndices = [];
  for (const entry of ownerSnapshot.selectorPtr178Details || []) {
    if (!entry || entry.index === null || entry.index === undefined) {
      continue;
    }
    const readyLoopState = entry.state === 0 || entry.state === 1 || entry.state === 2;
    const field180Ready =
      (typeof entry.field180 === "number" && entry.field180 !== 0) || pointerLooksSet(entry.ptr180);
    if (
      !readyLoopState ||
      !field180Ready ||
      !ptr1c8Set[entry.index] ||
      flagged20[entry.index] ||
      flagged21[entry.index]
    ) {
      continue;
    }
    preparedIndices.push(entry.index);
  }
  return preparedIndices;
}

function collectPreparedSelectorReadyIndices(ownerSnapshot) {
  if (!ownerSnapshot) {
    return [];
  }
  const ptr1c8Set = {};
  const flagged20 = {};
  const flagged21 = {};
  for (const index of ownerSnapshot.ptr1c8SetIndices || []) {
    ptr1c8Set[index] = 1;
  }
  for (const index of ownerSnapshot.flagged20Indices || []) {
    flagged20[index] = 1;
  }
  for (const index of ownerSnapshot.flagged21Indices || []) {
    flagged21[index] = 1;
  }
  const preparedIndices = [];
  for (const entry of ownerSnapshot.selectorPtr178Details || []) {
    if (!entry || entry.index === null || entry.index === undefined) {
      continue;
    }
    const readyLoopState = entry.state === 0 || entry.state === 1 || entry.state === 2;
    const field180Ready =
      (typeof entry.field180 === "number" && entry.field180 !== 0) || pointerLooksSet(entry.ptr180);
    const totalKnown = typeof entry.total164 === "number" && entry.total164 > 0;
    const pctReady = totalKnown && typeof entry.pct === "number" && entry.pct >= 5;
    const queuedLatchSet = typeof entry.queued === "number" && entry.queued !== 0;
    const busy = typeof entry.busy16c === "number" && entry.busy16c !== 0;
    if (
      !readyLoopState ||
      !field180Ready ||
      !ptr1c8Set[entry.index] ||
      flagged20[entry.index] ||
      flagged21[entry.index] ||
      (!queuedLatchSet && !busy && pctReady)
    ) {
      continue;
    }
    preparedIndices.push(entry.index);
  }
  return preparedIndices;
}

function collectActiveEligibleDispatchIndices(ownerSnapshot) {
  if (!ownerSnapshot) {
    return [];
  }
  const eligibleIndices = [];
  for (const entry of ownerSnapshot.selectorPtr178Details || []) {
    if (!entry || entry.index === null || entry.index === undefined) {
      continue;
    }
    if (
      entry.selectorReason !== "eligible" ||
      entry.flagD === 0 ||
      entry.flagE !== 0 ||
      entry.queued !== 0 ||
      entry.busy16c !== 0
    ) {
      continue;
    }
    eligibleIndices.push(entry.index);
  }
  return eligibleIndices;
}

function tryForcePreparedSelectorReady(owner, reason) {
  if (!__FORCE_PREPARED_SELECTOR_READY__) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const candidateIndices = collectPreparedSelectorReadyIndices(before).filter(
    (index) => !(index in forcedPreparedSelectorReadyCountsByIndex)
  );
  const activeBlockingIndices =
    before && before.activeIndices
      ? before.activeIndices.filter((index) => candidateIndices.indexOf(index) === -1)
      : [];
  if (
    !before ||
    activeBlockingIndices.length !== 0 ||
    before.inflightIndices.length !== 0 ||
    candidateIndices.length === 0
  ) {
    return {
      forced: false,
      before: before,
      activeBlockingIndices: activeBlockingIndices
    };
  }
  try {
    for (const index of candidateIndices) {
      const recordBase = ptr(owner).add(8 + (index * recordStride));
      const total164 = safeReadU32(recordBase.add(0x164));
      const done168 = safeReadU32(recordBase.add(0x168));
      const effectiveTotal = total164 === null || total164 === 0 ? 100 : total164;
      const requiredDone = Math.max(1, Math.ceil((effectiveTotal * 5) / 100));
      if (total164 === null || total164 === 0) {
        recordBase.add(0x164).writeU32(effectiveTotal);
      }
      if (done168 === null || done168 < requiredDone) {
        recordBase.add(0x168).writeU32(requiredDone);
      }
      recordBase.add(0x16c).writeU8(0);
      ptr(owner).add(0x11468 + index).writeU8(0);
      forcedPreparedSelectorReadyCountsByIndex[index] =
        (forcedPreparedSelectorReadyCountsByIndex[index] || 0) + 1;
    }
    totalForcedPreparedSelectorReady += candidateIndices.length;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      preparedIndices: candidateIndices,
      before: before,
      after: after
    };
    lastPreparedSelectorReadyState = state;
    send({
      event: "prepared-selector-ready",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after,
      preparedIndices: candidateIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      preparedIndices: candidateIndices,
      before: before,
      error: String(_error)
    };
    lastPreparedSelectorReadyState = state;
    send({
      event: "prepared-selector-ready-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      preparedIndices: candidateIndices,
      error: String(_error)
    };
  }
}

function collectHotDoneZeroQueuedIndices(ownerSnapshot) {
  if (!ownerSnapshot || ownerSnapshot.selectorEligibleCount === 0) {
    return [];
  }
  const candidateIndices = [];
  for (const entry of ownerSnapshot.selectorPtr178Details || []) {
    if (!entry || entry.index === null || entry.index === undefined) {
      continue;
    }
    const queued = typeof entry.queued === "number" && entry.queued !== 0;
    const active = typeof entry.flagD === "number" && entry.flagD !== 0;
    const completed = typeof entry.flagE === "number" && entry.flagE !== 0;
    const latched = typeof entry.flagF === "number" && entry.flagF !== 0;
    if (
      entry.selectorReason !== "doneZero" ||
      !active ||
      completed ||
      (!queued && !latched)
    ) {
      continue;
    }
    candidateIndices.push(entry.index);
  }
  return candidateIndices;
}

function tryDemoteHotDoneZeroQueuedRecord(owner, reason) {
  if (!__DEMOTE_HOT_DONEZERO_QUEUED_RECORD__) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const candidateIndices = collectHotDoneZeroQueuedIndices(before);
  if (
    !before ||
    before.ptr1c8SetCount !== 0 ||
    before.stateCount !== 0 ||
    before.selectorEligibleCount === 0 ||
    before.selectorReasonCounts.doneZero !== 1 ||
    candidateIndices.length !== 1
  ) {
    return {
      forced: false,
      before: before,
      candidateIndices: candidateIndices
    };
  }
  try {
    const hotIndex = candidateIndices[0];
    const recordBase = ptr(owner).add(8 + (hotIndex * recordStride));
    const beforeRecord = snapshotRecord(owner, hotIndex);
    recordBase.add(0x0d).writeU8(0);
    recordBase.add(0x0f).writeU8(0);
    ptr(owner).add(0x11468 + hotIndex).writeU8(1);
    demotedHotDoneZeroQueuedRecordCountsByIndex[hotIndex] =
      (demotedHotDoneZeroQueuedRecordCountsByIndex[hotIndex] || 0) + 1;
    totalDemotedHotDoneZeroQueuedRecords += 1;
    const afterRecord = snapshotRecord(owner, hotIndex);
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      hotIndex: hotIndex,
      candidateIndices: candidateIndices,
      before: before,
      beforeRecord: beforeRecord,
      afterRecord: afterRecord,
      after: after
    };
    lastDemotedHotDoneZeroQueuedRecordState = state;
    sendUnique(seenHotDoneZeroQueuedDemotionStates, "hot-donezero-record-demoted", state);
    return {
      forced: true,
      hotIndex: hotIndex,
      before: before,
      after: after,
      candidateIndices: candidateIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      candidateIndices: candidateIndices,
      before: before,
      error: String(_error)
    };
    lastDemotedHotDoneZeroQueuedRecordState = state;
    send({
      event: "hot-donezero-record-demoted-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      candidateIndices: candidateIndices,
      error: String(_error)
    };
  }
}

function tryForceDirectDispatchOnState1(owner, reason) {
  if (!__FORCE_DIRECT_DISPATCH_ON_STATE1__ || directDispatchInProgress) {
    sendUnique(seenDirectDispatchSkipStates, "owner-direct-dispatch-on-state1-skip", {
      reason: reason,
      enabled: __FORCE_DIRECT_DISPATCH_ON_STATE1__,
      directDispatchInProgress: directDispatchInProgress
    });
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const stateIndices = before && before.stateIndices ? before.stateIndices.slice() : [];
  const state1Indices = stateIndices
    .filter((entry) => entry && entry.state === 1)
    .map((entry) => entry.index);
  const state2Indices = stateIndices
    .filter((entry) => entry && entry.state === 2)
    .map((entry) => entry.index);
  const preparedIndices = collectPreparedDispatchIndices(before);
  const activeEligibleIndices = collectActiveEligibleDispatchIndices(before);
  const dispatchableIndices = [];
  const seenDispatchableIndices = {};
  for (const index of state1Indices.concat(state2Indices, preparedIndices, activeEligibleIndices)) {
    if (!(index in forcedDirectDispatchCountsByIndex) && !seenDispatchableIndices[index]) {
      dispatchableIndices.push(index);
      seenDispatchableIndices[index] = 1;
    }
  }
  const activeBlockingIndices =
    before && before.activeIndices
      ? before.activeIndices.filter((index) => dispatchableIndices.indexOf(index) === -1)
      : [];
  if (
    !before ||
    before.queuedIndices.length !== 0 ||
    activeBlockingIndices.length !== 0 ||
    before.inflightIndices.length !== 0 ||
    dispatchableIndices.length === 0
  ) {
    sendUnique(seenDirectDispatchSkipStates, "owner-direct-dispatch-on-state1-skip", {
      reason: reason,
      enabled: __FORCE_DIRECT_DISPATCH_ON_STATE1__,
      directDispatchInProgress: directDispatchInProgress,
      before: before,
      state1Indices: state1Indices,
      state2Indices: state2Indices,
      preparedIndices: preparedIndices,
      activeEligibleIndices: activeEligibleIndices,
      dispatchableIndices: dispatchableIndices,
      activeBlockingIndices: activeBlockingIndices
    });
    return {
      forced: false,
      before: before
    };
  }
  directDispatchInProgress = true;
  try {
    for (const index of dispatchableIndices) {
      ptr(owner).add(0x11468 + index).writeU8(0);
      ptr(owner).add(0x11d4a).writeU8(1);
      directDispatch(ptr(owner), index);
      forcedDirectDispatchCountsByIndex[index] = (forcedDirectDispatchCountsByIndex[index] || 0) + 1;
      directDispatchCountsByIndex[index] = (directDispatchCountsByIndex[index] || 0) + 1;
    }
    totalForcedDirectDispatch += dispatchableIndices.length;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      state1Indices: state1Indices,
      state2Indices: state2Indices,
      preparedIndices: preparedIndices,
      activeEligibleIndices: activeEligibleIndices,
      dispatchedIndices: dispatchableIndices,
      before: before,
      after: after
    };
    lastDirectDispatchForceState = state;
    send({
      event: "owner-direct-dispatch-on-state1",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after,
      dispatchedIndices: dispatchableIndices
    };
  } catch (_error) {
    const state = {
      reason: reason,
      state1Indices: state1Indices,
      state2Indices: state2Indices,
      preparedIndices: preparedIndices,
      activeEligibleIndices: activeEligibleIndices,
      dispatchedIndices: dispatchableIndices,
      before: before,
      error: String(_error)
    };
    lastDirectDispatchForceState = state;
    send({
      event: "owner-direct-dispatch-on-state1-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      dispatchedIndices: dispatchableIndices,
      error: String(_error)
    };
  } finally {
    directDispatchInProgress = false;
  }
}

function tryForceOwnerStageOpenOnState1(owner, reason) {
  if (!__FORCE_OWNER_STAGE_OPEN_ON_STATE1__) {
    return {
      forced: false
    };
  }
  const before = snapshotOwner(owner);
  const preparedIndices = collectPreparedDispatchIndices(before);
  if (
    !before ||
    (before.stateCount === 0 && preparedIndices.length === 0) ||
    (before.flag11b48 !== 0 && before.flag11d49 !== 0)
  ) {
    return {
      forced: false,
      before: before
    };
  }
  try {
    ptr(owner).add(0x11b48).writeU8(1);
    ptr(owner).add(0x11d49).writeU8(1);
    totalForcedOwnerStageOpen += 1;
    const after = snapshotOwner(owner);
    const state = {
      reason: reason,
      before: before,
      after: after
    };
    lastOwnerStageOpenState = state;
    send({
      event: "owner-stage-open-on-state1",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after
    };
  } catch (_error) {
    const state = {
      reason: reason,
      before: before,
      error: String(_error)
    };
    lastOwnerStageOpenState = state;
    send({
      event: "owner-stage-open-on-state1-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      error: String(_error)
    };
  }
}

function tryForceIdleSelectorEntryGates(owner, reason) {
  const before = snapshotOwner(owner);
  let forcedLatchClear = false;
  let forcedTimerOpen = false;
  let error = null;
  try {
    if (__FORCE_IDLE_SELECTOR_LATCH_CLEAR__ && before && before.flag11b58 !== 0) {
      ptr(owner).add(0x11b58).writeU8(0);
      forcedLatchClear = true;
      totalForcedIdleSelectorLatchClear += 1;
    }
    if (__FORCE_IDLE_SELECTOR_TIMER_OPEN__ && before && before.timerGateOpen === false) {
      ptr(owner).add(0x11b50).writeU64(0);
      forcedTimerOpen = true;
      totalForcedIdleSelectorTimerOpen += 1;
    }
  } catch (_error) {
    error = String(_error);
  }
  const after =
    forcedLatchClear || forcedTimerOpen || error !== null
      ? snapshotOwner(owner)
      : before;
  const state = {
    reason: reason,
    before: before,
    after: after,
    forcedLatchClear: forcedLatchClear,
    forcedTimerOpen: forcedTimerOpen,
    error: error
  };
  lastIdleSelectorEntryForceState = state;
  if (forcedLatchClear || forcedTimerOpen || error !== null) {
    send({
      event: error === null ? "idle-selector-entry-force" : "idle-selector-entry-force-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
  }
  return state;
}

function tryForcePostSelectFlag20(owner, index, reason) {
  if (!__FORCE_POST_SELECT_FLAG20_ON_BUSY__) {
    return {
      forced: false
    };
  }
  const before = snapshotRecord(owner, index);
  if (
    !before ||
    !before.validIndex ||
    before.busy16c === 0 ||
    before.flag20 !== 0 ||
    !pointerLooksSet(before.ptr178)
  ) {
    return {
      forced: false,
      before: before
    };
  }
  try {
    ptr(before.recordBase).add(0x20).writeU8(1);
    ptr(before.recordBase).add(0x16c).writeU8(0);
    if (before.done168 === 0) {
      ptr(before.recordBase).add(0x168).writeU32(1);
    }
    totalForcedPostSelectFlag20 += 1;
    const after = snapshotRecord(owner, index);
    const state = {
      reason: reason,
      index: index,
      before: before,
      after: after
    };
    lastPostSelectFlag20State = state;
    send({
      event: "post-select-flag20-on-busy",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after
    };
  } catch (_error) {
    const state = {
      reason: reason,
      index: index,
      before: before,
      error: String(_error)
    };
    lastPostSelectFlag20State = state;
    send({
      event: "post-select-flag20-on-busy-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      error: String(_error)
    };
  }
}

function tryForcePostSelectPublicationSuccess(owner, recordBase, index, reason) {
  if (!__FORCE_POST_SELECT_PUBLICATION_SUCCESS__) {
    return {
      forced: false
    };
  }
  if (
    owner === null ||
    owner === undefined ||
    recordBase === null ||
    recordBase === undefined ||
    index === null ||
    index < 0 ||
    index >= resourceCount
  ) {
    return {
      forced: false
    };
  }
  const before = snapshotRecordFromBase(owner, index, recordBase);
  if (
    !before ||
    !before.validIndex ||
    !pointerLooksSet(before.ptr178) ||
    !pointerLooksSet(before.ptr180)
  ) {
    return {
      forced: false,
      before: before
    };
  }
  let mutated = false;
  try {
    if (before.field170 !== 0) {
      ptr(recordBase).add(0x170).writeU32(0);
      mutated = true;
    }
    if (before.flag174 !== 1) {
      ptr(recordBase).add(0x174).writeU8(1);
      mutated = true;
    }
    if (before.busy16c !== 0) {
      ptr(recordBase).add(0x16c).writeU8(0);
      mutated = true;
    }
    if (before.done168 === 0 && before.total164 !== null && before.total164 > 0) {
      ptr(recordBase).add(0x168).writeU32(1);
      mutated = true;
    }
    const after = snapshotRecordFromBase(owner, index, recordBase);
    if (!mutated) {
      return {
        forced: false,
        before: before,
        after: after
      };
    }
    totalForcedPostSelectPublicationSuccess += 1;
    const state = {
      reason: reason,
      owner: hexPtr(owner),
      recordBase: hexPtr(recordBase),
      index: index,
      before: before,
      after: after
    };
    lastForcedPostSelectPublicationSuccessState = state;
    send({
      event: "post-select-publication-success-forced",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: true,
      before: before,
      after: after
    };
  } catch (_error) {
    const state = {
      reason: reason,
      owner: hexPtr(owner),
      recordBase: hexPtr(recordBase),
      index: index,
      before: before,
      error: String(_error)
    };
    lastForcedPostSelectPublicationSuccessState = state;
    send({
      event: "post-select-publication-success-forced-error",
      timestamp: Date.now() / 1000.0,
      ...state
    });
    return {
      forced: false,
      before: before,
      error: String(_error)
    };
  }
}

function sendUnique(bucket, eventName, payload) {
  const keyPayload = JSON.parse(JSON.stringify(payload));
  delete keyPayload.callCount;
  delete keyPayload.timer11b50;
  delete keyPayload.schedulerGlobal;
  const key = JSON.stringify(keyPayload);
  if (key in bucket) {
    bucket[key] += 1;
    return;
  }
  bucket[key] = 1;
  send({
    event: eventName,
    ...payload,
    timestamp: Date.now() / 1000.0
  });
}

Interceptor.attach(gateAddress, {
  onEnter(args) {
    totalGateCalls += 1;
    const owner = this.context.rdi;
    this.owner = owner;
    const recordOpenForce = tryForceRecordOpenOnField1c(owner, "gate-enter");
    const ownerStageOpenForce = tryForceOwnerStageOpenOnState1(owner, "gate-enter");
    const preparedSelectorReadyForce = tryForcePreparedSelectorReady(owner, "gate-enter");
    const idleSelectorEntryForce = tryForceIdleSelectorEntryGates(owner, "gate-enter");
    const recordDReadyOnPtr178Force = tryForceRecordDReadyOnPtr178(owner, "gate-enter");
    const seedDispatchForce = tryForceSeedDispatchOnPtr178(owner, "gate-enter");
    const selectorReadyOnPtr178Force = tryForceSelectorReadyOnPtr178(owner, "gate-enter");
    const hotDoneZeroDemotionForce = tryDemoteHotDoneZeroQueuedRecord(owner, "gate-enter");
    const directDispatchForce = tryForceDirectDispatchOnState1(owner, "gate-enter");
    const ownerStageForce = tryForceOwnerStageClear(owner, "gate-enter");
    const gateState = {
      gateRva: __GATE_RVA_TEXT__,
      callCount: totalGateCalls,
      forcedOwnerStageOpen: ownerStageOpenForce.forced === true,
      ownerStageOpenBefore: ownerStageOpenForce.before || null,
      ownerStageOpenAfter: ownerStageOpenForce.after || null,
      forcedPreparedSelectorReady: preparedSelectorReadyForce.forced === true,
      preparedSelectorReadyBefore: preparedSelectorReadyForce.before || null,
      preparedSelectorReadyAfter: preparedSelectorReadyForce.after || null,
      preparedSelectorReadyIndices: preparedSelectorReadyForce.preparedIndices || [],
      forcedRecordOpen: recordOpenForce.forced === true,
      recordOpenBefore: recordOpenForce.before || null,
      recordOpenAfter: recordOpenForce.after || null,
      recordOpenIndices: recordOpenForce.openedIndices || [],
      forcedIdleSelectorLatchClear: idleSelectorEntryForce.forcedLatchClear === true,
      forcedIdleSelectorTimerOpen: idleSelectorEntryForce.forcedTimerOpen === true,
      idleSelectorEntryForceError: idleSelectorEntryForce.error || null,
      forcedSeedDispatch: seedDispatchForce.forced === true,
      seedDispatchBefore: seedDispatchForce.before || null,
      seedDispatchAfter: seedDispatchForce.after || null,
      seededIndices: seedDispatchForce.seededIndices || [],
      forcedRecordDReadyOnPtr178: recordDReadyOnPtr178Force.forced === true,
      recordDReadyOnPtr178Before: recordDReadyOnPtr178Force.before || null,
      recordDReadyOnPtr178After: recordDReadyOnPtr178Force.after || null,
      recordDReadyOnPtr178Indices: recordDReadyOnPtr178Force.candidateIndices || [],
      forcedSelectorReadyOnPtr178: selectorReadyOnPtr178Force.forced === true,
      selectorReadyOnPtr178Before: selectorReadyOnPtr178Force.before || null,
      selectorReadyOnPtr178After: selectorReadyOnPtr178Force.after || null,
      selectorReadyOnPtr178Indices: selectorReadyOnPtr178Force.candidateIndices || [],
      forcedHotDoneZeroDemotion: hotDoneZeroDemotionForce.forced === true,
      hotDoneZeroDemotionBefore: hotDoneZeroDemotionForce.before || null,
      hotDoneZeroDemotionAfter: hotDoneZeroDemotionForce.after || null,
      hotDoneZeroDemotionIndices: hotDoneZeroDemotionForce.candidateIndices || [],
      hotDoneZeroDemotionIndex: hotDoneZeroDemotionForce.hotIndex || null,
      forcedDirectDispatch: directDispatchForce.forced === true,
      directDispatchBefore: directDispatchForce.before || null,
      directDispatchAfter: directDispatchForce.after || null,
      directlyDispatchedIndices: directDispatchForce.dispatchedIndices || [],
      forcedOwnerStageClear: ownerStageForce.forced === true,
      ownerStageForceBefore: ownerStageForce.before || null,
      ownerStageForceAfter: ownerStageForce.after || null,
      ...snapshotOwner(owner)
    };
    lastGateState = gateState;
    sendUnique(seenGateStates, "resource-gate-unique", gateState);
  },
  onLeave(retval) {
    const gateReturnState = {
      gateRva: __GATE_RVA_TEXT__,
      callCount: totalGateCalls,
      retval: ptr(retval).toString(),
      ...snapshotOwner(this.owner)
    };
    lastGateReturnState = gateReturnState;
    sendUnique(seenGateReturnStates, "resource-gate-return-unique", gateReturnState);
  }
});

Interceptor.attach(recordResetAddress, {
  onEnter(args) {
    totalRecordResetCalls += 1;
    this.owner = args[0];
    this.recordBase = args[1];
    this.index = safeReadS32(ptr(args[1]).add(8));
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeRecordResetCaller(this.callerRva);
    if (this.index !== null) {
      recordResetCountsByIndex[this.index] = (recordResetCountsByIndex[this.index] || 0) + 1;
    }
    if (this.callerRva !== null) {
      recordResetCountsByCallerRva[this.callerRva] =
        (recordResetCountsByCallerRva[this.callerRva] || 0) + 1;
    }
    this.before = snapshotRecord(this.owner, this.index);
  },
  onLeave(retval) {
    const resetState = {
      recordResetRva: __RECORD_RESET_RVA_TEXT__,
      callCount: totalRecordResetCalls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      index: this.index,
      retval: ptr(retval).toString(),
      before: this.before,
      after: snapshotRecord(this.owner, this.index),
      ownerSnapshot: snapshotOwner(this.owner)
    };
    lastRecordResetState = resetState;
    sendUnique(seenRecordResetStates, "record-reset-unique", resetState);
  }
});

Interceptor.attach(dispatchAddress, {
  onEnter(args) {
    totalDispatchCalls += 1;
    this.owner = args[0];
    this.index = args[1].toInt32();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    const owner = this.owner;
    const index = this.index;
    this.before = snapshotRecord(owner, index);
    dispatchCountsByIndex[index] = (dispatchCountsByIndex[index] || 0) + 1;
    const dispatchState = {
      dispatchRva: __DISPATCH_RVA_TEXT__,
      callCount: totalDispatchCalls,
      callerRva: this.callerRva,
      index: index,
      ...snapshotOwner(owner),
      record: this.before
    };
    lastDispatchState = dispatchState;
    sendUnique(seenDispatchStates, "resource-dispatch-unique", dispatchState);
  },
  onLeave(retval) {
    const after = snapshotRecord(this.owner, this.index);
    const forcedFinalizeOnDispatchReturn =
      this.index === null || this.index === undefined
        ? { forced: false, state: null }
        : tryForceFinalizeOnDispatchReturn(this.owner, this.index, this.before, after);
    let forcedRecordE = false;
    let forcedRecordD = false;
    if (
      __FORCE_RECORDE_ON_DISPATCH_RETURN__ &&
      after &&
      after.validIndex &&
      pointerLooksSet(after.ptr1c8) &&
      after.flagE === 0
    ) {
      try {
        ptr(after.recordBase).add(0x0e).writeU8(1);
        forcedRecordE = true;
        totalForcedRecordEDispatchReturn += 1;
        forcedDispatchReturnCountsByIndex[this.index] = (forcedDispatchReturnCountsByIndex[this.index] || 0) + 1;
      } catch (_error) {
      }
    }
    const afterCompletion = snapshotRecord(this.owner, this.index);
    if (
      __FORCE_RECORDD_CLEAR_ON_DISPATCH_RETURN__ &&
      afterCompletion &&
      afterCompletion.validIndex &&
      afterCompletion.flagD !== 0 &&
      afterCompletion.flagE !== 0
    ) {
      try {
        ptr(afterCompletion.recordBase).add(0x0d).writeU8(0);
        forcedRecordD = true;
        totalForcedRecordDDispatchReturn += 1;
        forcedRecordDClearCountsByIndex[this.index] = (forcedRecordDClearCountsByIndex[this.index] || 0) + 1;
      } catch (_error) {
      }
    }
    const dispatchReturnState = {
      dispatchRva: __DISPATCH_RVA_TEXT__,
      callCount: totalDispatchCalls,
      callerRva: this.callerRva,
      index: this.index,
      retval: ptr(retval).toString(),
      before: this.before,
      after: snapshotRecord(this.owner, this.index),
      forcedFinalizeOnDispatchReturn: forcedFinalizeOnDispatchReturn.forced === true,
      forcedFinalizeOnDispatchReturnState: forcedFinalizeOnDispatchReturn.state || null,
      forcedRecordEOnDispatchReturn: forcedRecordE,
      forcedRecordDOnDispatchReturn: forcedRecordD,
      ...snapshotOwner(this.owner)
    };
    lastDispatchReturnState = dispatchReturnState;
    sendUnique(seenDispatchReturnStates, "resource-dispatch-return-unique", dispatchReturnState);
  }
});

Interceptor.attach(dispatchProviderAcceptCompareAddress, {
  onEnter() {
    totalDispatchProviderAcceptCalls += 1;
    this.owner = ptr(this.context.rbp);
    this.index = this.context.r12 !== undefined && this.context.r12 !== null
      ? this.context.r12.toInt32()
      : null;
    this.recordBase = this.context.r15 !== undefined && this.context.r15 !== null
      ? ptr(this.context.r15)
      : null;
    this.stackPointer = ptr(this.context.rsp);
    this.outputPointerSlot = this.stackPointer.add(0x170);
    this.actualPointerBefore = ptr(this.context.rax);
    this.expectedPointer = ptr(dispatchProviderAcceptExpectedAddress);
    this.outputPointerAfterProviderCall = safeReadPointer(this.outputPointerSlot);
    this.forced = false;
    if (
      forceDispatchProviderAccept &&
      this.actualPointerBefore.compare(this.expectedPointer) !== 0
    ) {
      this.context.rax = this.expectedPointer;
      this.forced = true;
      totalForcedDispatchProviderAccept += 1;
    }
  },
  onLeave() {
    const state = {
      dispatchProviderAcceptRva: "0x59566b/0x595675",
      callCount: totalDispatchProviderAcceptCalls,
      owner: hexPtr(this.owner),
      index: this.index,
      recordBase: hexPtr(this.recordBase),
      actualPointerBefore: hexPtr(this.actualPointerBefore),
      expectedPointer: hexPtr(this.expectedPointer),
      actualPointerAfter: hexPtr(this.context.rax),
      outputPointerSlot: hexPtr(this.outputPointerSlot),
      outputPointerAfterProviderCall: hexPtr(this.outputPointerAfterProviderCall),
      outputPointerValue84:
        pointerLooksSet(this.outputPointerAfterProviderCall)
          ? safeReadS32(ptr(this.outputPointerAfterProviderCall).add(0x84))
          : null,
      forced: this.forced === true,
      record:
        this.owner === null || this.index === null
          ? null
          : snapshotRecordFromBase(this.owner, this.index, this.recordBase),
      ownerSnapshot: this.owner === null ? null : snapshotOwner(this.owner)
    };
    lastDispatchProviderAcceptState = state;
    sendUnique(
      seenDispatchProviderAcceptStates,
      "dispatch-provider-accept-unique",
      state,
    );
  }
});

Interceptor.attach(dispatchResultMetadataDerefAddress, {
  onEnter() {
    totalDispatchResultMetadataReads += 1;
    this.owner = ptr(this.context.rbp);
    this.index = this.context.r12 !== undefined && this.context.r12 !== null
      ? this.context.r12.toInt32()
      : null;
    this.recordBase = this.context.r15 !== undefined && this.context.r15 !== null
      ? ptr(this.context.r15)
      : null;
    this.stackPointer = ptr(this.context.rsp);
    this.metadataPointerSlot = this.stackPointer.add(0x170);
    this.metadataPointerBefore = safeReadPointer(this.metadataPointerSlot);
    this.contextRaxBefore = this.context.rax !== undefined && this.context.rax !== null
      ? ptr(this.context.rax)
      : null;
    this.syntheticApplied = false;
    if (
      forceDispatchResultMetadataFallback &&
      !pointerLooksSet(this.metadataPointerBefore)
    ) {
      this.metadataPointerSlot.writePointer(syntheticDispatchResultMetadata);
      this.context.rax = syntheticDispatchResultMetadata;
      this.syntheticApplied = true;
      totalForcedDispatchResultMetadataFallback += 1;
    }
    this.metadataPointerAfter = safeReadPointer(this.metadataPointerSlot);
    const activeMetadataPointer = pointerLooksSet(this.metadataPointerAfter)
      ? this.metadataPointerAfter
      : this.contextRaxBefore;
    const state = {
      dispatchResultMetadataRva: "0x5957b1",
      callCount: totalDispatchResultMetadataReads,
      owner: hexPtr(this.owner),
      index: this.index,
      recordBase: hexPtr(this.recordBase),
      metadataPointerSlot: hexPtr(this.metadataPointerSlot),
      metadataPointerBefore: hexPtr(this.metadataPointerBefore),
      contextRaxBefore: hexPtr(this.contextRaxBefore),
      metadataPointerAfter: hexPtr(this.metadataPointerAfter),
      contextRaxAfter: hexPtr(this.context.rax),
      syntheticApplied: this.syntheticApplied === true,
      syntheticPointer: this.syntheticApplied === true ? hexPtr(syntheticDispatchResultMetadata) : null,
      metadataValue00:
        pointerLooksSet(activeMetadataPointer)
          ? safeReadS32(ptr(activeMetadataPointer))
          : null,
      metadataValue20:
        pointerLooksSet(activeMetadataPointer)
          ? safeReadS32(ptr(activeMetadataPointer).add(0x20))
          : null,
      metadataValue24:
        pointerLooksSet(activeMetadataPointer)
          ? safeReadS32(ptr(activeMetadataPointer).add(0x24))
          : null,
      metadataValue84:
        pointerLooksSet(activeMetadataPointer)
          ? safeReadS32(ptr(activeMetadataPointer).add(0x84))
          : null,
      record:
        this.owner === null || this.index === null
          ? null
          : snapshotRecordFromBase(this.owner, this.index, this.recordBase),
      ownerSnapshot: this.owner === null ? null : snapshotOwner(this.owner)
    };
    lastDispatchResultMetadataState = state;
    sendUnique(
      seenDispatchResultMetadataStates,
      "dispatch-result-metadata-read-unique",
      state,
    );
  }
});

function installPostDispatchReleaseCallbackHook(address, slotOffset, stageLabel) {
  Interceptor.attach(address, {
    onEnter() {
      totalPostDispatchReleaseCallbackCalls += 1;
      this.owner =
        this.context.rdi !== undefined && this.context.rdi !== null
          ? ptr(this.context.rdi)
          : null;
      this.index =
        this.context.r13 !== undefined && this.context.r13 !== null
          ? this.context.r13.toInt32()
          : null;
      this.recordBase =
        this.context.rbp !== undefined && this.context.rbp !== null
          ? ptr(this.context.rbp)
          : null;
      this.objectPointer =
        this.context.rcx !== undefined && this.context.rcx !== null
          ? ptr(this.context.rcx)
          : null;
      this.vtablePointerBefore =
        this.context.rax !== undefined && this.context.rax !== null
          ? ptr(this.context.rax)
          : null;
      this.targetPointerBefore =
        pointerLooksSet(this.vtablePointerBefore)
          ? safeReadPointer(ptr(this.vtablePointerBefore).add(slotOffset))
          : null;
      this.syntheticApplied = false;
      if (
        forcePostDispatchReleaseCallbackFallback &&
        shouldFallbackReleaseCallbackTarget(this.targetPointerBefore)
      ) {
        this.context.rax = syntheticPostDispatchReleaseVtable;
        this.syntheticApplied = true;
        totalForcedPostDispatchReleaseCallbackFallback += 1;
      }
      this.vtablePointerAfter =
        this.context.rax !== undefined && this.context.rax !== null
          ? ptr(this.context.rax)
          : null;
      this.targetPointerAfter =
        pointerLooksSet(this.vtablePointerAfter)
          ? safeReadPointer(ptr(this.vtablePointerAfter).add(slotOffset))
          : null;
      const state = {
        releaseCallbackRva: addressToRvaText(address),
        callCount: totalPostDispatchReleaseCallbackCalls,
        stage: stageLabel,
        slotOffset: slotOffset,
        owner: hexPtr(this.owner),
        index: this.index,
        recordBase: hexPtr(this.recordBase),
        objectPointer: hexPtr(this.objectPointer),
        vtablePointerBefore: hexPtr(this.vtablePointerBefore),
        targetPointerBefore: hexPtr(this.targetPointerBefore),
        syntheticApplied: this.syntheticApplied === true,
        syntheticVtablePointer:
          this.syntheticApplied === true
            ? hexPtr(syntheticPostDispatchReleaseVtable)
            : null,
        syntheticCallbackPointer:
          this.syntheticApplied === true
            ? hexPtr(syntheticPostDispatchReleaseNoop)
            : null,
        vtablePointerAfter: hexPtr(this.vtablePointerAfter),
        targetPointerAfter: hexPtr(this.targetPointerAfter),
        record:
          this.owner === null || this.index === null
            ? null
            : snapshotRecordFromBase(this.owner, this.index, this.recordBase),
        ownerSnapshot: this.owner === null ? null : snapshotOwner(this.owner),
      };
      lastPostDispatchReleaseCallbackState = state;
      sendUnique(
        seenPostDispatchReleaseCallbackStates,
        "post-dispatch-release-callback-unique",
        state,
      );
    }
  });
}

installPostDispatchReleaseCallbackHook(
  postDispatchReleaseCallbackAddress,
  0x8,
  "release-vfunc-8",
);
installPostDispatchReleaseCallbackHook(
  postDispatchReleaseCleanupCallbackAddress,
  0x10,
  "release-vfunc-10",
);

Interceptor.attach(ptr1c8OpenAddress, {
  onEnter(args) {
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (this.callerRva !== dispatchCacheQueryOpenCallerRva) {
      this.skip = true;
      return;
    }
    totalDispatchCacheQueryCalls += 1;
    this.owner = ptr(this.context.rbp);
    this.index = this.context.r12 !== undefined && this.context.r12 !== null
      ? this.context.r12.toInt32()
      : null;
    this.recordBase = this.context.r15 !== undefined && this.context.r15 !== null
      ? ptr(this.context.r15)
      : null;
    this.ptr178 = args[0];
    this.queryPointer = args[1];
    this.argR8 = ptr(args[2]).toInt32();
    this.argR9 = ptr(args[3]).toInt32();
    this.arg5 = safeReadPointer(ptr(this.context.rsp).add(0x28));
    this.arg6 = safeReadPointer(ptr(this.context.rsp).add(0x30));
    this.before =
      this.owner === null || this.index === null
        ? null
        : snapshotRecordFromBase(this.owner, this.index, this.recordBase);
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      dispatchCacheQueryRva: "0x595710->0x6d2730",
      callerRva: this.callerRva,
      callCount: totalDispatchCacheQueryCalls,
      owner: hexPtr(this.owner),
      index: this.index,
      recordBase: hexPtr(this.recordBase),
      ptr178: hexPtr(this.ptr178),
      queryPointer: hexPtr(this.queryPointer),
      queryPreview: tryReadCString(this.queryPointer, 0x80),
      argR8: this.argR8,
      argR9: this.argR9,
      arg5: hexPtr(this.arg5),
      arg6: hexPtr(this.arg6),
      arg5SlotAfter: pointerLooksSet(this.arg5) ? hexPtr(safeReadPointer(ptr(this.arg5))) : null,
      arg6ValueAfter: pointerLooksSet(this.arg6) ? safeReadU64(ptr(this.arg6)) : null,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      before: this.before,
      after:
        this.owner === null || this.index === null
          ? null
          : snapshotRecordFromBase(this.owner, this.index, this.recordBase),
      ownerSnapshot: this.owner === null ? null : snapshotOwner(this.owner)
    };
    lastDispatchCacheQueryState = state;
    sendUnique(seenDispatchCacheQueryStates, "dispatch-cache-query-unique", state);
  }
});

Interceptor.attach(queueHandlerType3Address, {
  onEnter(args) {
    totalQueueHandlerType3Calls += 1;
    this.recordBase = args[0];
    this.owner = inferOwnerFromRecordBase(this.recordBase);
    this.index = safeReadS32(ptr(args[0]).add(8));
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeQueueHandlerCaller(this.callerRva);
    if (this.index !== null) {
      queueHandlerType3CountsByIndex[this.index] =
        (queueHandlerType3CountsByIndex[this.index] || 0) + 1;
    }
    this.before =
      this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index);
  },
  onLeave(retval) {
    const handlerState = {
      queueHandlerType3Rva: __QUEUE_HANDLER_TYPE3_RVA_TEXT__,
      callCount: totalQueueHandlerType3Calls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      index: this.index,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      before: this.before,
      after:
        this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index),
      ownerSnapshot: this.owner === null ? null : snapshotOwner(this.owner)
    };
    lastQueueHandlerType3State = handlerState;
    sendUnique(seenQueueHandlerType3States, "queue-handler-type3-unique", handlerState);
  }
});

Interceptor.attach(queueHandlerType2Address, {
  onEnter(args) {
    totalQueueHandlerType2Calls += 1;
    this.owner = args[0];
    this.recordBase = args[1];
    this.item = args[2];
    this.index = safeReadS32(ptr(args[1]).add(8));
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeQueueHandlerCaller(this.callerRva);
    if (this.index !== null) {
      queueHandlerType2CountsByIndex[this.index] =
        (queueHandlerType2CountsByIndex[this.index] || 0) + 1;
    }
    this.before = snapshotRecord(this.owner, this.index);
    this.itemSnapshot = snapshotQueueItem(this.item);
  },
  onLeave(retval) {
    const handlerState = {
      queueHandlerType2Rva: __QUEUE_HANDLER_TYPE2_RVA_TEXT__,
      callCount: totalQueueHandlerType2Calls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      itemPointer: hexPtr(this.item),
      item: this.itemSnapshot,
      index: this.index,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      before: this.before,
      after: snapshotRecord(this.owner, this.index),
      ownerSnapshot: snapshotOwner(this.owner)
    };
    lastQueueHandlerType2State = handlerState;
    sendUnique(seenQueueHandlerType2States, "queue-handler-type2-unique", handlerState);
  }
});

Interceptor.attach(queueHandlerType0Address, {
  onEnter(args) {
    totalQueueHandlerType0Calls += 1;
    this.traceThreadId = Process.getCurrentThreadId();
    this.entryStackPointer = ptr(this.context.rsp);
    this.originalStackReturnAddress = safeReadPointer(this.entryStackPointer);
    this.owner = args[0];
    this.recordBase = args[1];
    this.item = args[2];
    this.index = safeReadS32(ptr(args[1]).add(8));
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeQueueHandlerCaller(this.callerRva);
    if (this.index !== null) {
      queueHandlerType0CountsByIndex[this.index] =
        (queueHandlerType0CountsByIndex[this.index] || 0) + 1;
    }
    this.before = snapshotRecord(this.owner, this.index);
    this.itemSnapshot = snapshotQueueItem(this.item);
    const handlerLoopState = {
      owner: hexPtr(this.owner),
      primaryRecordBase: hexPtr(this.recordBase),
      index: this.index,
      rawType: 0,
      primaryRecord: this.before,
      itemPointer: hexPtr(this.item),
      item: this.itemSnapshot
    };
    this.forcedType0PrepareBranch = tryForceType0PrepareBranch(handlerLoopState);
    this.forcedType0ChildMinus1Bypass = tryForceType0ChildMinus1Bypass(handlerLoopState);
    this.itemSnapshotAfterSmoke = snapshotQueueItem(this.item);
    this.forcedItemPayload = tryForceItemPayloadFromPtr178(handlerLoopState);
    this.forcedRecordState = tryForceRecordStateFromType0(handlerLoopState, this.context);
    activeType0HandlerStatesByThread[this.traceThreadId] = {
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      itemPointer: hexPtr(this.item),
      index: this.index
    };
    activeType0HandlerReturnSlotStatesByThread[this.traceThreadId] = {
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      itemPointer: hexPtr(this.item),
      index: this.index,
      entryStackPointer: hexPtr(this.entryStackPointer),
      originalStackReturnAddress: hexPtr(this.originalStackReturnAddress)
    };
  },
  onLeave(retval) {
    const handlerState = {
      queueHandlerType0Rva: __QUEUE_HANDLER_TYPE0_RVA_TEXT__,
      callCount: totalQueueHandlerType0Calls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      itemPointer: hexPtr(this.item),
      itemBeforeSmoke: this.itemSnapshot,
      item: this.itemSnapshotAfterSmoke || this.itemSnapshot,
      index: this.index,
      entryStackPointer: hexPtr(this.entryStackPointer),
      originalStackReturnAddress: hexPtr(this.originalStackReturnAddress),
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      forcedType0PrepareBranch: this.forcedType0PrepareBranch || null,
      forcedType0ChildMinus1Bypass: this.forcedType0ChildMinus1Bypass || null,
      forcedItemPayload: this.forcedItemPayload || null,
      forcedRecordState: this.forcedRecordState || null,
      before: this.before,
      after: snapshotRecord(this.owner, this.index),
      ownerSnapshot: snapshotOwner(this.owner)
    };
    lastQueueHandlerType0State = handlerState;
    delete activeType0HandlerStatesByThread[this.traceThreadId];
    delete activeType0HandlerReturnSlotStatesByThread[this.traceThreadId];
    sendUnique(seenQueueHandlerType0States, "queue-handler-type0-unique", handlerState);
  }
});

Interceptor.attach(queueHelperPrepareAddress, {
  onEnter(args) {
    totalQueueHelperPrepareCalls += 1;
    this.traceThreadId = Process.getCurrentThreadId();
    this.savedReturnAddress = this.returnAddress;
    this.entryStackPointer = ptr(this.context.rsp);
    this.originalStackReturnAddress = safeReadPointer(this.entryStackPointer);
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeQueueHandlerCaller(this.callerRva);
    this.owner = ptr(args[0]);
    this.item = ptr(args[3]);
    this.index = safeReadS32(this.item.add(0x4));
    this.forcedType0ZlbSourceFromPtr178 =
      tryForceType0ZlbSourceFromPtr178(this.context, this.owner, this.item, this.index, this.callerRva);
    this.forcedType0RawSourceFromPtr178 =
      tryForceType0RawSourceFromPtr178(this.context, this.owner, this.item, this.index, this.callerRva);
    this.forcedType0RequestedLengthFromSourceHeader =
      tryForceType0RequestedLengthFromSourceHeader(this.context, this.owner, this.item, this.index, this.callerRva);
    this.forcedType0InnerSourceFromSideWrapper =
      tryForceType0InnerSourceFromSideWrapper(this.context, this.owner, this.item, this.index, this.callerRva);
    this.source = ptr(this.context.rdx);
    this.requestedLength = ptr(this.context.r8).toInt32();
    if (this.index !== null) {
      queueHelperPrepareCountsByIndex[this.index] =
        (queueHelperPrepareCountsByIndex[this.index] || 0) + 1;
    }
    this.sourceSnapshot = snapshotPrepareSource(this.source);
    this.before = this.index === null ? null : snapshotRecord(this.owner, this.index);
    this.itemSnapshot = snapshotQueueItem(this.item);
    this.payloadReadyBefore = itemPayloadReady(this.item);
    activeQueueHelperPrepareStatesByThread[this.traceThreadId] = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      callCount: totalQueueHelperPrepareCalls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      itemPointer: hexPtr(this.item),
      index: this.index,
      sourcePointer: hexPtr(this.source),
      requestedLength: this.requestedLength,
      entryStackPointer: this.entryStackPointer,
      originalStackReturnAddress: this.originalStackReturnAddress
    };
    const entryState = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      callCount: totalQueueHelperPrepareCalls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      sourcePointer: hexPtr(this.source),
      source: this.sourceSnapshot,
      itemPointer: hexPtr(this.item),
      item: this.itemSnapshot,
      index: this.index,
      requestedLength: this.requestedLength,
      entryStackPointer: hexPtr(this.entryStackPointer),
      originalStackReturnAddress: hexPtr(this.originalStackReturnAddress),
      payloadReadyBefore: this.payloadReadyBefore,
      forcedType0RawSourceFromPtr178:
        this.forcedType0RawSourceFromPtr178 &&
        this.forcedType0RawSourceFromPtr178.forced === true,
      forcedType0RawSourceFromPtr178State:
        this.forcedType0RawSourceFromPtr178 &&
        this.forcedType0RawSourceFromPtr178.state
          ? this.forcedType0RawSourceFromPtr178.state
          : null,
      forcedType0ZlbSourceFromPtr178:
        this.forcedType0ZlbSourceFromPtr178 &&
        this.forcedType0ZlbSourceFromPtr178.forced === true,
      forcedType0ZlbSourceFromPtr178State:
        this.forcedType0ZlbSourceFromPtr178 &&
        this.forcedType0ZlbSourceFromPtr178.state
          ? this.forcedType0ZlbSourceFromPtr178.state
          : null,
      forcedType0RequestedLengthFromSourceHeader:
        this.forcedType0RequestedLengthFromSourceHeader &&
        this.forcedType0RequestedLengthFromSourceHeader.forced === true,
      forcedType0RequestedLengthFromSourceHeaderState:
        this.forcedType0RequestedLengthFromSourceHeader &&
        this.forcedType0RequestedLengthFromSourceHeader.state
          ? this.forcedType0RequestedLengthFromSourceHeader.state
          : null,
      forcedType0InnerSourceFromSideWrapper:
        this.forcedType0InnerSourceFromSideWrapper &&
        this.forcedType0InnerSourceFromSideWrapper.forced === true,
      forcedType0InnerSourceFromSideWrapperState:
        this.forcedType0InnerSourceFromSideWrapper &&
        this.forcedType0InnerSourceFromSideWrapper.state
          ? this.forcedType0InnerSourceFromSideWrapper.state
          : null,
      before: this.before
    };
    lastQueueHelperPrepareEntryState = entryState;
    sendUnique(seenQueueHelperPrepareEntryStates, "queue-helper-prepare-entry-unique", entryState);
  },
  onLeave(retval) {
    const currentStackReturnAddressBeforeRet = safeReadPointer(this.entryStackPointer);
    const stackReturnAddressWasCorrupted =
      hexPtr(currentStackReturnAddressBeforeRet) !== hexPtr(this.originalStackReturnAddress);
    let restoredStackReturnAddress = false;
    let finalStackReturnAddress = currentStackReturnAddressBeforeRet;
    if (
      forceQueueHelperReturnSlotRestore &&
      pointerLooksSet(this.entryStackPointer) &&
      pointerLooksSet(this.originalStackReturnAddress) &&
      stackReturnAddressWasCorrupted
    ) {
      ptr(this.entryStackPointer).writePointer(ptr(this.originalStackReturnAddress));
      finalStackReturnAddress = safeReadPointer(this.entryStackPointer);
      restoredStackReturnAddress = true;
      totalForcedQueueHelperReturnSlotRestores += 1;
      const restoreState = {
        queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
        callCount: totalQueueHelperPrepareCalls,
        callerRva: this.callerRva,
        callerLabel: this.callerLabel,
        owner: hexPtr(this.owner),
        itemPointer: hexPtr(this.item),
        index: this.index,
        entryStackPointer: hexPtr(this.entryStackPointer),
        originalStackReturnAddress: hexPtr(this.originalStackReturnAddress),
        clobberedStackReturnAddress: hexPtr(currentStackReturnAddressBeforeRet),
        restoredStackReturnAddress: hexPtr(finalStackReturnAddress),
        timestamp: Date.now() / 1000.0,
      };
      lastForcedQueueHelperReturnSlotRestoreState = restoreState;
      sendUnique(
        seenQueueHelperReturnSlotRestoreStates,
        "force-queue-helper-return-slot-restore",
        restoreState,
      );
    }
    const handlerState = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      callCount: totalQueueHelperPrepareCalls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      owner: hexPtr(this.owner),
      sourcePointer: hexPtr(this.source),
      source: this.sourceSnapshot,
      itemPointer: hexPtr(this.item),
      item: this.itemSnapshot,
      index: this.index,
      requestedLength: this.requestedLength,
      payloadReadyBefore: this.payloadReadyBefore,
      forcedType0RawSourceFromPtr178:
        this.forcedType0RawSourceFromPtr178 &&
        this.forcedType0RawSourceFromPtr178.forced === true,
      forcedType0RawSourceFromPtr178State:
        this.forcedType0RawSourceFromPtr178 &&
        this.forcedType0RawSourceFromPtr178.state
          ? this.forcedType0RawSourceFromPtr178.state
          : null,
      forcedType0ZlbSourceFromPtr178:
        this.forcedType0ZlbSourceFromPtr178 &&
        this.forcedType0ZlbSourceFromPtr178.forced === true,
      forcedType0ZlbSourceFromPtr178State:
        this.forcedType0ZlbSourceFromPtr178 &&
        this.forcedType0ZlbSourceFromPtr178.state
          ? this.forcedType0ZlbSourceFromPtr178.state
          : null,
      forcedType0RequestedLengthFromSourceHeader:
        this.forcedType0RequestedLengthFromSourceHeader &&
        this.forcedType0RequestedLengthFromSourceHeader.forced === true,
      forcedType0RequestedLengthFromSourceHeaderState:
        this.forcedType0RequestedLengthFromSourceHeader &&
        this.forcedType0RequestedLengthFromSourceHeader.state
          ? this.forcedType0RequestedLengthFromSourceHeader.state
          : null,
      forcedType0InnerSourceFromSideWrapper:
        this.forcedType0InnerSourceFromSideWrapper &&
        this.forcedType0InnerSourceFromSideWrapper.forced === true,
      forcedType0InnerSourceFromSideWrapperState:
        this.forcedType0InnerSourceFromSideWrapper &&
        this.forcedType0InnerSourceFromSideWrapper.state
          ? this.forcedType0InnerSourceFromSideWrapper.state
          : null,
      returnAddress: hexPtr(this.savedReturnAddress),
      entryStackPointer: hexPtr(this.entryStackPointer),
      originalStackReturnAddress: hexPtr(this.originalStackReturnAddress),
      stackReturnAddressBeforeRet: hexPtr(currentStackReturnAddressBeforeRet),
      stackReturnAddressWasCorrupted: stackReturnAddressWasCorrupted,
      restoredStackReturnAddress: restoredStackReturnAddress,
      finalStackReturnAddress: hexPtr(finalStackReturnAddress),
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      retvalBool: ptr(retval).toInt32() !== 0,
      before: this.before,
      after: this.index === null ? null : snapshotRecord(this.owner, this.index),
      afterItem: snapshotQueueItem(this.item),
      payloadReadyAfter: itemPayloadReady(this.item)
    };
    lastQueueHelperPrepareState = handlerState;
    delete activeQueueHelperPrepareStatesByThread[this.traceThreadId];
    sendUnique(seenQueueHelperPrepareStates, "queue-helper-prepare-unique", handlerState);
  }
});

Interceptor.attach(queueHelperPreparePostParserTypeCompareAddress, {
  onEnter(_args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (this.activeQueueHelperPrepareContext === null) {
      this.skip = true;
      return;
    }
    const resolvedObjectPointer = safeReadPointer(ptr(this.context.rbp).add(0x7));
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      probeRva: "0x598a1d",
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnTypePointer: hexPtr(this.context.rax),
      expectedTypePointer: hexPtr(queueHelperPrepareExpectedTypeAddress),
      typeCompareMatched:
        hexPtr(this.context.rax) === hexPtr(queueHelperPrepareExpectedTypeAddress),
      resolvedObjectPointer: hexPtr(resolvedObjectPointer),
      resolvedObject: snapshotQueueHelperResolvedObject(resolvedObjectPointer)
    };
    lastQueueHelperPostParserTypeCompareState = state;
    sendUnique(
      seenQueueHelperPostParserTypeCompareStates,
      "queue-helper-post-parser-type-compare-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPrepareResolverCallAddress, {
  onEnter(_args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (this.activeQueueHelperPrepareContext === null) {
      this.skip = true;
      return;
    }
    const serviceObjectPointer = ptr(this.context.rcx);
    const serviceVtablePointer = safeReadPointer(serviceObjectPointer);
    const resolverFunctionPointer = pointerLooksSet(serviceVtablePointer)
      ? safeReadPointer(ptr(serviceVtablePointer).add(0x18))
      : null;
    const outPointerSlot = ptr(this.context.rdx);
    const entryPointer = ptr(this.context.r8);
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      probeRva: "0x598a1a",
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      serviceObjectPointer: hexPtr(serviceObjectPointer),
      serviceVtablePointer: hexPtr(serviceVtablePointer),
      resolverFunctionPointer: hexPtr(resolverFunctionPointer),
      outPointerSlot: hexPtr(outPointerSlot),
      outPointerBefore: hexPtr(safeReadPointer(outPointerSlot)),
      entryPointer: hexPtr(entryPointer),
      entryDword0: safeReadU32(entryPointer),
      entryDword4: safeReadU32(entryPointer.add(0x4)),
      entryQword0: safeReadU64(entryPointer),
      entryQword8: safeReadU64(entryPointer.add(0x8)),
      entryPreviewHex: tryReadPreviewHex(entryPointer, 0x20)
    };
    if (forceQueueHelperResolverSyntheticSuccess) {
      state.syntheticResolverBypass =
        tryForceQueueHelperResolverSyntheticSuccessAtCallsite(
          this.context,
          this.activeQueueHelperPrepareContext,
        );
      state.outPointerAfter = hexPtr(safeReadPointer(outPointerSlot));
      state.raxAfter = hexPtr(this.context.rax);
      state.ripAfter = hexPtr(this.context.rip);
    }
    lastQueueHelperPrepareResolverCallState = state;
    sendUnique(
      seenQueueHelperPrepareResolverCallStates,
      "queue-helper-resolver-call-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPreparePostParserClassAddress, {
  onEnter(_args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (this.activeQueueHelperPrepareContext === null) {
      this.skip = true;
      return;
    }
    const resolvedObjectPointer = safeReadPointer(ptr(this.context.rbp).add(0x7));
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      probeRva: "0x598a54",
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      classValue: ptr(this.context.rcx).toInt32(),
      resolvedObjectPointer: hexPtr(resolvedObjectPointer),
      resolvedObject: snapshotQueueHelperResolvedObject(resolvedObjectPointer),
      fallbackPayloadLength: safeReadU64(ptr(this.context.rbp).add(0x17)),
      fallbackPayloadPointer: hexPtr(safeReadPointer(ptr(this.context.rbp).add(0x1f))),
      willEnterMaterialize: ptr(this.context.rcx).toInt32() > 1
    };
    lastQueueHelperPostParserClassState = state;
    sendUnique(
      seenQueueHelperPostParserClassStates,
      "queue-helper-post-parser-class-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPreparePostParserMaterializeReturnAddress, {
  onEnter(_args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (this.activeQueueHelperPrepareContext === null) {
      this.skip = true;
      return;
    }
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      probeRva: "0x598a6f",
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      materializedPayloadLength: safeReadU64(ptr(this.context.rbp).sub(0x79)),
      materializedPayloadPointer: hexPtr(safeReadPointer(ptr(this.context.rbp).sub(0x71))),
      tempBufferState: snapshotPrepareBufferState(ptr(this.context.rsp).add(0x38)),
      parserOutputState: snapshotPrepareBufferState(ptr(this.context.rbp).add(0x0f))
    };
    lastQueueHelperPostParserMaterializeState = state;
    sendUnique(
      seenQueueHelperPostParserMaterializeStates,
      "queue-helper-post-parser-materialize-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPreparePreCleanupSuppressionAddress, {
  onEnter(_args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (
      this.activeQueueHelperPrepareContext === null ||
      !forceQueueHelperPostParserCleanupSuppression
    ) {
      this.skip = true;
      return;
    }
    const parserOutputPointer = ptr(this.context.rbp).add(0x0f);
    const tempBufferPointer = ptr(this.context.rsp).add(0x38);
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      probeRva: "0x598a81",
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlotBefore: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      materializedPayloadLength: hexPtr(this.context.rdi),
      materializedPayloadPointer: hexPtr(this.context.r14),
      parserOutputBefore: snapshotPrepareBufferState(parserOutputPointer),
      tempBufferBefore: snapshotPrepareBufferState(tempBufferPointer),
      parserOutputCleared: clearPrepareBufferState(parserOutputPointer),
      tempBufferCleared: clearPrepareBufferState(tempBufferPointer),
      parserOutputAfter: snapshotPrepareBufferState(parserOutputPointer),
      tempBufferAfter: snapshotPrepareBufferState(tempBufferPointer),
      returnSlotAfter: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      timestamp: Date.now() / 1000
    };
    totalForcedQueueHelperPostParserCleanupSuppressions += 1;
    lastForcedQueueHelperPostParserCleanupSuppressionState = state;
    sendUnique(
      seenQueueHelperPostParserCleanupSuppressionStates,
      "force-queue-helper-post-parser-cleanup-suppression",
      state,
    );
  }
});

Interceptor.attach(queueHelperPrepareBufferAllocAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (
      this.activeQueueHelperPrepareContext === null ||
      this.callerRva !== queueHelperPrepareAllocCallerRva
    ) {
      this.skip = true;
      return;
    }
    this.requestedLength = ptr(args[0]).toUInt32();
    this.alignment = ptr(args[1]).toUInt32();
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      helperRva: "0x793b40",
      callerRva: this.callerRva,
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      requestedLength: this.requestedLength,
      alignment: this.alignment,
      retval: hexPtr(retval),
      retvalPreviewHex:
        this.requestedLength > 0
          ? tryReadPreviewHex(retval, Math.min(this.requestedLength, 0x20))
          : null,
      timestamp: Date.now() / 1000.0
    };
    lastQueueHelperPrepareBufferAllocState = state;
    sendUnique(
      seenQueueHelperPrepareBufferAllocStates,
      "queue-helper-buffer-alloc-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPrepareBufferCleanupAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (
      this.activeQueueHelperPrepareContext === null ||
      queueHelperPrepareCleanupCallerRvaSet[this.callerRva] !== true
    ) {
      this.skip = true;
      return;
    }
    this.bufferPointer = args[0];
    this.before = snapshotPrepareBufferState(this.bufferPointer);
    const entryState = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      helperRva: "0x2dcb0",
      callerRva: this.callerRva,
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      bufferPointer: hexPtr(this.bufferPointer),
      before: this.before,
      timestamp: Date.now() / 1000.0
    };
    lastQueueHelperPrepareBufferCleanupEntryState = entryState;
    sendUnique(
      seenQueueHelperPrepareBufferCleanupEntryStates,
      "queue-helper-buffer-cleanup-entry-unique",
      entryState,
    );
  },
  onLeave() {
    if (this.skip === true) {
      return;
    }
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      helperRva: "0x2dcb0",
      callerRva: this.callerRva,
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      bufferPointer: hexPtr(this.bufferPointer),
      before: this.before,
      after: snapshotPrepareBufferState(this.bufferPointer),
      timestamp: Date.now() / 1000.0
    };
    lastQueueHelperPrepareBufferCleanupState = state;
    sendUnique(
      seenQueueHelperPrepareBufferCleanupStates,
      "queue-helper-buffer-cleanup-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPrepareCopyAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (
      this.activeQueueHelperPrepareContext === null ||
      this.callerRva !== queueHelperPrepareCopyCallerRva
    ) {
      this.skip = true;
      return;
    }
    this.destinationPointer = args[0];
    this.sourcePointer = args[1];
    this.length = ptr(args[2]).toUInt32();
    this.destinationPreviewBefore =
      this.length > 0 ? tryReadPreviewHex(this.destinationPointer, Math.min(this.length, 0x20)) : null;
    this.sourcePreview =
      this.length > 0 ? tryReadPreviewHex(this.sourcePointer, Math.min(this.length, 0x20)) : null;
  },
  onLeave() {
    if (this.skip === true) {
      return;
    }
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      helperRva: "0x7b9c90",
      callerRva: this.callerRva,
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      destinationPointer: hexPtr(this.destinationPointer),
      sourcePointer: hexPtr(this.sourcePointer),
      length: this.length,
      destinationPreviewBefore: this.destinationPreviewBefore,
      sourcePreview: this.sourcePreview,
      destinationPreviewAfter:
        this.length > 0 ? tryReadPreviewHex(this.destinationPointer, Math.min(this.length, 0x20)) : null,
      timestamp: Date.now() / 1000.0
    };
    lastQueueHelperPrepareCopyState = state;
    sendUnique(
      seenQueueHelperPrepareCopyStates,
      "queue-helper-copy-unique",
      state,
    );
  }
});

Interceptor.attach(queueHelperPrepareReturnBridgeAddress, {
  onEnter(_args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    if (this.activeQueueHelperPrepareContext === null) {
      this.skip = true;
      return;
    }
    const returnSlotBefore = snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext);
    const originalReturnAddress = this.activeQueueHelperPrepareContext.originalStackReturnAddress;
    const entryStackPointer = this.activeQueueHelperPrepareContext.entryStackPointer;
    let restored = false;
    if (
      forceQueueHelperReturnSlotRestore &&
      returnSlotBefore !== null &&
      returnSlotBefore.currentMatchesOriginal === false &&
      pointerLooksSet(entryStackPointer) &&
      pointerLooksSet(originalReturnAddress)
    ) {
      ptr(entryStackPointer).writePointer(ptr(originalReturnAddress));
      restored = true;
      totalForcedQueueHelperReturnSlotRestores += 1;
    }
    const state = {
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      probeRva: "0x598c99",
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlotBefore: returnSlotBefore,
      restored: restored,
      returnSlotAfter: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      timestamp: Date.now() / 1000.0,
    };
    if (restored) {
      lastForcedQueueHelperReturnSlotRestoreState = state;
      sendUnique(
        seenQueueHelperReturnSlotRestoreStates,
        "force-queue-helper-return-slot-restore",
        state,
      );
    }
  }
});

try {
  Interceptor.attach(type0HandlerReturnBridgeAddress, {
    onEnter(_args) {
      this.traceThreadId = Process.getCurrentThreadId();
      this.activeType0ReturnContext =
        activeType0HandlerReturnSlotStatesByThread[this.traceThreadId] || null;
      if (this.activeType0ReturnContext === null) {
        this.skip = true;
        return;
      }
      const returnSlotBefore = snapshotType0HandlerReturnSlot(
        this.activeType0ReturnContext,
        this.context.rsp,
      );
      let restored = false;
      if (
        forceType0HandlerReturnSlotRestore &&
        returnSlotBefore !== null &&
        returnSlotBefore.currentMatchesOriginal === false &&
        pointerLooksSet(this.context.rsp) &&
        pointerLooksSet(this.activeType0ReturnContext.originalStackReturnAddress)
      ) {
        ptr(this.context.rsp).writePointer(
          ptr(this.activeType0ReturnContext.originalStackReturnAddress)
        );
        restored = true;
        totalForcedType0HandlerReturnSlotRestores += 1;
      }
      const state = {
        queueHandlerType0Rva: __QUEUE_HANDLER_TYPE0_RVA_TEXT__,
        probeRva: "0x59890b",
        activeType0Context: this.activeType0ReturnContext,
        returnSlotBefore: returnSlotBefore,
        restored: restored,
        returnSlotAfter: snapshotType0HandlerReturnSlot(
          this.activeType0ReturnContext,
          this.context.rsp,
        ),
        timestamp: Date.now() / 1000.0,
      };
      lastType0HandlerReturnBridgeState = state;
      sendUnique(
        seenType0HandlerReturnBridgeStates,
        "type0-handler-return-bridge-unique",
        state,
      );
      if (restored) {
        lastForcedType0HandlerReturnSlotRestoreState = state;
        sendUnique(
          seenType0HandlerReturnSlotRestoreStates,
          "force-type0-handler-return-slot-restore",
          state,
        );
      }
    }
  });
} catch (error) {
  send({
    event: "interceptor-attach-failed",
    probeRva: "0x59890b",
    address: hexPtr(type0HandlerReturnBridgeAddress),
    error: String(error),
    timestamp: Date.now() / 1000.0,
  });
}

Interceptor.attach(type0PostPrepareReinitAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeType0Context = activeType0HandlerStatesByThread[this.traceThreadId] || null;
    if (
      this.activeType0Context === null ||
      this.callerRva !== type0PostPrepareReinitCallerRva
    ) {
      this.skip = true;
      return;
    }
    this.sideObject = args[0];
    this.before = snapshotType0SideObject(this.sideObject);
    const state = {
      type0PostPrepareReinitRva: "0x69d780",
      callerRva: this.callerRva,
      activeType0Context: this.activeType0Context,
      sideObjectPointer: hexPtr(this.sideObject),
      sideObject: this.before,
      timestamp: Date.now() / 1000.0
    };
    activeType0PostPrepareReinitStatesByThread[this.traceThreadId] = state;
    lastType0PostPrepareReinitEntryState = state;
    sendUnique(
      seenType0PostPrepareReinitEntryStates,
      "type0-post-prepare-reinit-entry-unique",
      state,
    );
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      type0PostPrepareReinitRva: "0x69d780",
      callerRva: this.callerRva,
      activeType0Context: this.activeType0Context,
      sideObjectPointer: hexPtr(this.sideObject),
      sideObjectBefore: this.before,
      sideObjectAfter: snapshotType0SideObject(this.sideObject),
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      timestamp: Date.now() / 1000.0
    };
    delete activeType0PostPrepareReinitStatesByThread[this.traceThreadId];
    lastType0PostPrepareReinitReturnState = state;
    sendUnique(
      seenType0PostPrepareReinitReturnStates,
      "type0-post-prepare-reinit-return-unique",
      state,
    );
  }
});

Interceptor.attach(type0PostPrepareStateCallAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeReinitContext =
      activeType0PostPrepareReinitStatesByThread[this.traceThreadId] || null;
    if (
      this.activeReinitContext === null ||
      this.callerRva !== type0PostPrepareStateCallCallerRva
    ) {
      this.skip = true;
      return;
    }
    this.stateObject = args[0];
    this.stateObjectSnapshot = snapshotType0SideObject(this.stateObject);
    this.selfPointer = safeReadPointer(this.stateObject);
    this.indirectTarget = pointerLooksSet(this.selfPointer)
      ? safeReadPointer(ptr(this.selfPointer).add(0x80))
      : null;
    const state = {
      type0PostPrepareStateCallRva: "0x6842a0",
      callerRva: this.callerRva,
      activeReinitContext: this.activeReinitContext,
      stateObjectPointer: hexPtr(this.stateObject),
      stateObject: this.stateObjectSnapshot,
      selfPointer: hexPtr(this.selfPointer),
      selfPointerRva: pointerWithinMainModule(this.selfPointer)
        ? addressToRvaText(this.selfPointer)
        : null,
      selfPointerInModule: pointerWithinMainModule(this.selfPointer),
      indirectTarget: hexPtr(this.indirectTarget),
      indirectTargetRva: pointerWithinMainModule(this.indirectTarget)
        ? addressToRvaText(this.indirectTarget)
        : null,
      indirectTargetInModule: pointerWithinMainModule(this.indirectTarget),
      argEdx: ptr(args[1]).toInt32(),
      argR8: hexPtr(args[2]),
      argR9: hexPtr(args[3]),
      timestamp: Date.now() / 1000.0
    };
    lastType0PostPrepareStateCallEntryState = state;
    sendUnique(
      seenType0PostPrepareStateCallEntryStates,
      "type0-post-prepare-state-call-entry-unique",
      state,
    );
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      type0PostPrepareStateCallRva: "0x6842a0",
      callerRva: this.callerRva,
      activeReinitContext: this.activeReinitContext,
      stateObjectPointer: hexPtr(this.stateObject),
      stateObjectBefore: this.stateObjectSnapshot,
      stateObjectAfter: snapshotType0SideObject(this.stateObject),
      selfPointer: hexPtr(this.selfPointer),
      indirectTarget: hexPtr(this.indirectTarget),
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      timestamp: Date.now() / 1000.0
    };
    lastType0PostPrepareStateCallReturnState = state;
    sendUnique(
      seenType0PostPrepareStateCallReturnStates,
      "type0-post-prepare-state-call-return-unique",
      state,
    );
  }
});

Interceptor.attach(type0PostPrepareBindAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeReinitContext =
      activeType0PostPrepareReinitStatesByThread[this.traceThreadId] || null;
    if (
      this.activeReinitContext === null ||
      this.callerRva !== type0PostPrepareBindCallerRva
    ) {
      this.skip = true;
      return;
    }
    this.targetObject = args[0];
    this.boundObject = args[1];
    const state = {
      type0PostPrepareBindRva: "0x681d40",
      callerRva: this.callerRva,
      activeReinitContext: this.activeReinitContext,
      targetObjectPointer: hexPtr(this.targetObject),
      targetObject: snapshotType0SideObject(this.targetObject),
      boundObjectPointer: hexPtr(this.boundObject),
      boundObjectRva: pointerWithinMainModule(this.boundObject)
        ? addressToRvaText(this.boundObject)
        : null,
      boundObjectInModule: pointerWithinMainModule(this.boundObject),
      timestamp: Date.now() / 1000.0
    };
    lastType0PostPrepareBindEntryState = state;
    sendUnique(
      seenType0PostPrepareBindEntryStates,
      "type0-post-prepare-bind-entry-unique",
      state,
    );
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      type0PostPrepareBindRva: "0x681d40",
      callerRva: this.callerRva,
      activeReinitContext: this.activeReinitContext,
      targetObjectPointer: hexPtr(this.targetObject),
      boundObjectPointer: hexPtr(this.boundObject),
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      timestamp: Date.now() / 1000.0
    };
    lastType0PostPrepareBindReturnState = state;
    sendUnique(
      seenType0PostPrepareBindReturnStates,
      "type0-post-prepare-bind-return-unique",
      state,
    );
  }
});

Interceptor.attach(queueHandlerType2Address, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.activeType0Context = activeType0HandlerStatesByThread[this.traceThreadId] || null;
    if (
      this.activeType0Context === null ||
      this.callerRva !== type0PostPrepareType2CallerRva
    ) {
      this.skip = true;
      return;
    }
    this.owner = args[0];
    this.recordBase = args[1];
    this.item = args[2];
    this.index = safeReadS32(ptr(args[1]).add(8));
    const state = {
      type0PostPrepareType2Rva: __QUEUE_HANDLER_TYPE2_RVA_TEXT__,
      callerRva: this.callerRva,
      activeType0Context: this.activeType0Context,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      itemPointer: hexPtr(this.item),
      index: this.index,
      record: snapshotRecord(this.owner, this.index),
      item: snapshotQueueItem(this.item),
      timestamp: Date.now() / 1000.0
    };
    lastType0PostPrepareType2EntryState = state;
    sendUnique(
      seenType0PostPrepareType2EntryStates,
      "type0-post-prepare-type2-entry-unique",
      state,
    );
  }
});

Interceptor.attach(ptr1c8OpenAddress, {
  onEnter(args) {
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (!callsiteWithinType0Handler(this.callerRva)) {
      this.skip = true;
      return;
    }
    totalType0MaterializeCalls += 1;
    this.sourcePtr = args[0];
    this.argRdx = args[1];
    this.argR8 = ptr(args[2]).toInt32();
    this.argR9 = ptr(args[3]).toInt32();
    this.arg5 = safeReadPointer(ptr(this.context.rsp).add(0x28));
    this.arg6 = safeReadPointer(ptr(this.context.rsp).add(0x30));
    this.beforeBlob = snapshotBlobHeader(this.sourcePtr);
    this.arg5SlotBefore = pointerLooksSet(this.arg5) ? hexPtr(safeReadPointer(ptr(this.arg5))) : null;
    this.arg6SlotBefore = pointerLooksSet(this.arg6) ? hexPtr(safeReadPointer(ptr(this.arg6))) : null;
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      type0MaterializeRva: "0x6d2730",
      callerRva: this.callerRva,
      callCount: totalType0MaterializeCalls,
      sourcePointer: hexPtr(this.sourcePtr),
      sourceBlob: this.beforeBlob,
      argRdx: hexPtr(this.argRdx),
      argR8: this.argR8,
      argR9: this.argR9,
      arg5: hexPtr(this.arg5),
      arg6: hexPtr(this.arg6),
      arg5SlotBefore: this.arg5SlotBefore,
      arg6SlotBefore: this.arg6SlotBefore,
      arg5SlotAfter: pointerLooksSet(this.arg5) ? hexPtr(safeReadPointer(ptr(this.arg5))) : null,
      arg6SlotAfter: pointerLooksSet(this.arg6) ? hexPtr(safeReadPointer(ptr(this.arg6))) : null,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32()
    };
    lastType0MaterializeState = state;
    sendUnique(seenType0MaterializeStates, "type0-materialize-unique", state);
  }
});

Interceptor.attach(type0PrepareStatusAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (!callsiteWithinType0Handler(this.callerRva)) {
      this.skip = true;
      return;
    }
    totalType0PrepareStatusCalls += 1;
    this.sideObject = args[0];
    this.argStatus = ptr(args[1]).toInt32();
    this.secondaryIndex = ptr(args[2]).toInt32();
    this.before = snapshotType0SideObject(this.sideObject);
    this.activeType0Context = activeType0HandlerStatesByThread[this.traceThreadId] || null;
    const entryState = {
      type0PrepareStatusRva: "0x6a0430",
      callerRva: this.callerRva,
      callCount: totalType0PrepareStatusCalls,
      activeType0Context: this.activeType0Context,
      sideObjectPointer: hexPtr(this.sideObject),
      sideObject: this.before,
      argStatus: this.argStatus,
      secondaryIndex: this.secondaryIndex
    };
    lastType0PrepareStatusEntryState = entryState;
    sendUnique(seenType0PrepareStatusEntryStates, "type0-prepare-status-entry-unique", entryState);
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      type0PrepareStatusRva: "0x6a0430",
      callerRva: this.callerRva,
      callCount: totalType0PrepareStatusCalls,
      sideObjectPointer: hexPtr(this.sideObject),
      sideObject: this.before,
      argStatus: this.argStatus,
      secondaryIndex: this.secondaryIndex,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32()
    };
    lastType0PrepareStatusState = state;
    sendUnique(seenType0PrepareStatusStates, "type0-prepare-status-unique", state);
  }
});

Interceptor.attach(type0PrepareParserAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (this.callerRva !== type0PrepareParserCallerRva) {
      this.skip = true;
      return;
    }
    this.outputPointer = ptr(args[0]);
    this.inputPointer = ptr(args[1]);
    this.statusPointer = ptr(args[2]);
    this.activeQueueHelperPrepareContext =
      activeQueueHelperPrepareStatesByThread[this.traceThreadId] || null;
    const entryState = {
      type0PrepareParserRva: "0x58ce70",
      callerRva: this.callerRva,
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      outputPointer: hexPtr(this.outputPointer),
      outputBuffer: snapshotPrepareBufferState(this.outputPointer),
      inputPointer: hexPtr(this.inputPointer),
      inputBuffer: snapshotPrepareBufferState(this.inputPointer),
      statusPointer: hexPtr(this.statusPointer),
      statusValue: safeReadS32(this.statusPointer)
    };
    lastType0PrepareParserEntryState = entryState;
    sendUnique(seenType0PrepareParserEntryStates, "type0-prepare-parser-entry-unique", entryState);
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    let forcedPayloadState = null;
    const activeType0Context = activeType0HandlerStatesByThread[this.traceThreadId] || null;
    if (forceType0ParserSingleBytePayloadTo1) {
      const dataPointer = safeReadPointer(ptr(this.outputPointer).add(0x10));
      const payloadLength = parseU64String(safeReadU64(ptr(this.outputPointer).add(0x08)));
      const firstByteBefore = safeReadU8(dataPointer);
      if (
        payloadLength === 1n &&
        pointerLooksSet(dataPointer) &&
        firstByteBefore === 0
      ) {
        try {
          ptr(dataPointer).writeU8(1);
          totalForcedType0ParserSingleBytePayloadTo1 += 1;
          const activeIndex =
            activeType0Context &&
            activeType0Context.index !== null &&
            activeType0Context.index !== undefined
              ? activeType0Context.index
              : null;
          if (activeIndex !== null) {
            forcedType0ParserSingleBytePayloadTo1CountsByIndex[activeIndex] =
              (forcedType0ParserSingleBytePayloadTo1CountsByIndex[activeIndex] || 0) + 1;
          }
          forcedPayloadState = {
            event: "force-type0-parser-single-byte-payload-to-1",
            timestamp: Date.now() / 1000.0,
            callerRva: this.callerRva,
            activeType0Context: activeType0Context,
            outputPointer: hexPtr(this.outputPointer),
            dataPointer: hexPtr(dataPointer),
            payloadLength: payloadLength.toString(),
            firstByteBefore: firstByteBefore,
            firstByteAfter: safeReadU8(dataPointer)
          };
          lastForcedType0ParserSingleBytePayloadTo1State = forcedPayloadState;
          send(forcedPayloadState);
        } catch (_error) {
          forcedPayloadState = null;
        }
      }
    }
    const state = {
      type0PrepareParserRva: "0x58ce70",
      callerRva: this.callerRva,
      activeQueueHelperPrepareContext: this.activeQueueHelperPrepareContext,
      returnSlot: snapshotQueueHelperReturnSlot(this.activeQueueHelperPrepareContext),
      retvalPointer: ptr(retval).toString(),
      outputPointer: hexPtr(this.outputPointer),
      outputBuffer: snapshotPrepareBufferState(this.outputPointer),
      inputPointer: hexPtr(this.inputPointer),
      inputBuffer: snapshotPrepareBufferState(this.inputPointer),
      statusPointer: hexPtr(this.statusPointer),
      statusValue: safeReadS32(this.statusPointer),
      forcedType0ParserSingleBytePayloadTo1: forcedPayloadState !== null,
      forcedType0ParserSingleBytePayloadTo1State: forcedPayloadState
    };
    lastType0PrepareParserState = state;
    sendUnique(seenType0PrepareParserStates, "type0-prepare-parser-unique", state);
  }
});

Interceptor.attach(type0DescriptorStatusAddress, {
  onEnter(args) {
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (!callsiteWithinType0Handler(this.callerRva)) {
      this.skip = true;
      return;
    }
    totalType0DescriptorStatusCalls += 1;
    this.sideObject = args[0];
    this.before = snapshotType0SideObject(this.sideObject);
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    let effectiveRetval = ptr(retval);
    let forcedRetval = null;
    if (
      forcedType0DescriptorStatusRetval !== null &&
      this.callerRva === type0DescriptorStatusCallerRva
    ) {
      forcedRetval = forcedType0DescriptorStatusRetval;
      retval.replace(ptr(forcedRetval));
      effectiveRetval = ptr(forcedRetval);
    }
    const state = {
      type0DescriptorStatusRva: "0x69fdd0",
      callerRva: this.callerRva,
      callCount: totalType0DescriptorStatusCalls,
      sideObjectPointer: hexPtr(this.sideObject),
      sideObject: this.before,
      retval: effectiveRetval.toString(),
      retvalS32: effectiveRetval.toInt32(),
      forcedRetvalS32: forcedRetval
    };
    lastType0DescriptorStatusState = state;
    sendUnique(seenType0DescriptorStatusStates, "type0-descriptor-status-unique", state);
    if (forcedRetval !== null) {
      send({
        event: "force-type0-descriptor-status-retval",
        timestamp: Date.now() / 1000.0,
        callerRva: this.callerRva,
        sideObjectPointer: hexPtr(this.sideObject),
        forcedRetvalS32: forcedRetval
      });
    }
  }
});

Interceptor.attach(type0SourceObjectAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (!callsiteWithinType0Handler(this.callerRva)) {
      this.skip = true;
      return;
    }
    totalType0SourceObjectCalls += 1;
    this.sideObject = args[0];
    this.before = snapshotType0SideObject(this.sideObject);
    this.activeType0Context = activeType0HandlerStatesByThread[this.traceThreadId] || null;
    this.forcedSeedState = null;
    if (
      forceType0SourceObjectFromSideSlots &&
      this.callerRva === type0SourceObjectCallerRva &&
      this.before &&
      !pointerLooksSet(this.before.ptr88)
    ) {
      const candidate = chooseType0SourceObjectCandidate(this.sideObject);
      if (candidate && candidate.seededPtr88 === true && pointerLooksSet(candidate.pointer)) {
        try {
          ptr(this.sideObject).add(0x88).writePointer(ptr(candidate.pointer));
          const activeIndex =
            this.activeType0Context &&
            this.activeType0Context.index !== null &&
            this.activeType0Context.index !== undefined
              ? this.activeType0Context.index
              : null;
          totalForcedType0SourceObjectFromSideSlots += 1;
          if (activeIndex !== null) {
            forcedType0SourceObjectFromSideSlotsCountsByIndex[activeIndex] =
              (forcedType0SourceObjectFromSideSlotsCountsByIndex[activeIndex] || 0) + 1;
          }
          this.forcedSeedState = {
            event: "force-type0-source-object-from-side-slots",
            timestamp: Date.now() / 1000.0,
            callerRva: this.callerRva,
            owner: this.activeType0Context ? this.activeType0Context.owner : null,
            recordBase: this.activeType0Context ? this.activeType0Context.recordBase : null,
            itemPointer: this.activeType0Context ? this.activeType0Context.itemPointer : null,
            index: activeIndex,
            sideObjectPointer: hexPtr(this.sideObject),
            slot: candidate.slot,
            candidatePointer: candidate.pointer,
            seededPtr88: true,
            alternateSlot: candidate.alternateSlot,
            alternatePointer: candidate.alternatePointer,
            selectionReason: candidate.selectionReason,
            siblingDelta98ToA0: candidate.siblingDelta98ToA0,
            candidateSource: snapshotType0SourceCandidate(candidate.pointer),
            alternateSource: snapshotType0SourceCandidate(candidate.alternatePointer),
            sideObjectBefore: this.before,
            sideObjectAfter: snapshotType0SideObject(this.sideObject)
          };
          lastForcedType0SourceObjectFromSideSlotsState = this.forcedSeedState;
          send(this.forcedSeedState);
        } catch (_error) {
          this.forcedSeedState = null;
        }
      }
    }
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const naturalSourcePointer = ptr(retval);
    const sideObjectAfterReturn = snapshotType0SideObject(this.sideObject);
    const forcedCandidateAfterReturn =
      this.forcedSeedState && pointerLooksSet(this.forcedSeedState.candidatePointer)
        ? snapshotType0SourceCandidate(this.forcedSeedState.candidatePointer)
        : null;
    const forcedAlternateAfterReturn =
      this.forcedSeedState && pointerLooksSet(this.forcedSeedState.alternatePointer)
        ? snapshotType0SourceCandidate(this.forcedSeedState.alternatePointer)
        : null;
    const state = {
      type0SourceObjectRva: "0x6a0120",
      callerRva: this.callerRva,
      callCount: totalType0SourceObjectCalls,
      activeType0Context: this.activeType0Context,
      sideObjectPointer: hexPtr(this.sideObject),
      sideObject: this.before,
      naturalRetval: naturalSourcePointer.toString(),
      retval: naturalSourcePointer.toString(),
      forcedType0SourceObjectFromSideSlots: this.forcedSeedState !== null,
      forcedType0SourceObjectFromSideSlotsState: this.forcedSeedState,
      source: snapshotPrepareSource(naturalSourcePointer),
      retvalPreviewHex: tryReadPreviewHex(naturalSourcePointer, 0x20),
      sideObjectAfterReturn: sideObjectAfterReturn,
      forcedCandidateAfterReturn: forcedCandidateAfterReturn,
      forcedAlternateAfterReturn: forcedAlternateAfterReturn
    };
    lastType0SourceObjectState = state;
    sendUnique(seenType0SourceObjectStates, "type0-source-object-unique", state);
  }
});

Interceptor.attach(queueLoopItemAddress, {
  onEnter() {
    totalQueueLoopItemCalls += 1;
    const loopState = snapshotQueueLoopState(this.context);
    const forcedItemPayload = tryForceItemPayloadFromPtr178(loopState);
    const forcedRecordState = tryForceRecordStateFromType0(loopState, this.context);
    if (loopState && loopState.index !== null && loopState.index !== undefined) {
      queueLoopCountsByIndex[loopState.index] = (queueLoopCountsByIndex[loopState.index] || 0) + 1;
    }
    if (loopState && loopState.rawType !== null && loopState.rawType !== undefined) {
      const rawTypeKey = String(loopState.rawType);
      queueLoopCountsByRawType[rawTypeKey] = (queueLoopCountsByRawType[rawTypeKey] || 0) + 1;
    }
    if (loopState && loopState.predictedHandler) {
      queueLoopCountsByPredictedHandler[loopState.predictedHandler] =
        (queueLoopCountsByPredictedHandler[loopState.predictedHandler] || 0) + 1;
    }
    const queueLoopItemState = {
      queueLoopItemRva: __QUEUE_LOOP_ITEM_RVA_TEXT__,
      callCount: totalQueueLoopItemCalls,
      forcedItemPayloadFromPtr178: forcedItemPayload.forced === true,
      forcedItemPayloadState: forcedItemPayload.state || null,
      forcedRecordStateFromType0: forcedRecordState.forced === true,
      forcedRecordStateState: forcedRecordState.state || null,
      ...loopState
    };
    lastQueueLoopItemState = queueLoopItemState;
    sendUnique(seenQueueLoopItemStates, "queue-loop-item-unique", queueLoopItemState);
  }
});

Interceptor.attach(queueLoopPostAddress, {
  onEnter() {
    totalQueueLoopPostCalls += 1;
    const loopState = snapshotQueueLoopState(this.context);
    const forcedType3Followon = tryForceType3FollowonOnPostState1(loopState);
    const queueLoopPostState = {
      queueLoopPostRva: __QUEUE_LOOP_POST_RVA_TEXT__,
      callCount: totalQueueLoopPostCalls,
      forcedType3FollowonOnPostState1: forcedType3Followon.forced === true,
      forcedType3FollowonOnPostState1State: forcedType3Followon.state || null,
      ...loopState
    };
    lastQueueLoopPostState = queueLoopPostState;
    sendUnique(seenQueueLoopPostStates, "queue-loop-post-unique", queueLoopPostState);
  }
});

Interceptor.attach(recordStatePostOpenCallAddress, {
  onEnter() {
    const owner = ptr(this.context.rcx);
    const recordBase = ptr(this.context.rdx);
    const itemPointer = ptr(this.context.r8);
    if (!syntheticType0RecordStateBridgeMatches(owner, itemPointer, recordBase)) {
      return;
    }
    const recordIndex = safeReadS32(recordBase.add(8));
    const recordSnapshot = snapshotRecordFromBase(owner, recordIndex, recordBase);
    send({
      event: "synthetic-recordstate-postopen-success-skip",
      timestamp: Date.now() / 1000.0,
      owner: hexPtr(owner),
      itemPointer: hexPtr(itemPointer),
      recordBase: hexPtr(recordBase),
      index: recordIndex,
      record: recordSnapshot
    });
    this.context.rax = ptr(1);
    this.context.rip = recordStatePostOpenCallAddress.add(5);
  }
});

Interceptor.attach(recordStateAddress, {
  onEnter(args) {
    totalRecordStateCalls += 1;
    this.owner = args[0];
    this.item = args[1];
    this.index = safeReadS32(ptr(args[1]).add(4));
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeQueueHandlerCaller(this.callerRva);
    this.before = snapshotRecord(this.owner, this.index);
    this.itemSnapshot = snapshotQueueItem(this.item);
  },
  onLeave(retval) {
    const after = snapshotRecord(this.owner, this.index);
    let forcedRecord21 = false;
    let forcedRecordE = false;
    if (
      __FORCE_RECORD21_ON_OPEN__ &&
      this.before &&
      this.before.validIndex &&
      after &&
      after.validIndex &&
      pointerLooksSet(after.ptr1c8) &&
      after.flag20 === 0 &&
      after.flag21 === 0
    ) {
      try {
        ptr(after.recordBase).add(0x21).writeU8(1);
        forcedRecord21 = true;
        totalForcedRecord21 += 1;
      } catch (_error) {
      }
    }
    if (
      __FORCE_RECORDE_ON_OPEN__ &&
      after &&
      after.validIndex &&
      pointerLooksSet(after.ptr1c8) &&
      after.flagE === 0
    ) {
      try {
        ptr(after.recordBase).add(0x0e).writeU8(1);
        forcedRecordE = true;
        totalForcedRecordE += 1;
      } catch (_error) {
      }
    }
    if (this.index !== null && this.index !== undefined) {
      recordStateCountsByIndex[this.index] = (recordStateCountsByIndex[this.index] || 0) + 1;
    }
    const recordState = {
      recordStateRva: __RECORD_STATE_RVA_TEXT__,
      callCount: totalRecordStateCalls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      itemPointer: hexPtr(this.item),
      itemType: safeReadS32(ptr(this.item)),
      item: this.itemSnapshot,
      index: this.index,
      retval: ptr(retval).toString(),
      before: this.before,
      after: snapshotRecord(this.owner, this.index),
      forcedRecord21: forcedRecord21,
      forcedRecordE: forcedRecordE
    };
    lastRecordState = recordState;
    sendUnique(seenRecordStates, "record-state-unique", recordState);
  }
});

Interceptor.attach(recordOpenAddress, {
  onEnter(args) {
    totalRecordOpenCalls += 1;
    this.recordBase = args[0];
    this.owner = inferOwnerFromRecordBase(this.recordBase);
    this.index = safeReadS32(ptr(args[0]).add(8));
    if (this.index !== null) {
      recordOpenCountsByIndex[this.index] = (recordOpenCountsByIndex[this.index] || 0) + 1;
    }
    this.before =
      this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index);
  },
  onLeave(retval) {
    const openState = {
      recordOpenRva: __RECORD_OPEN_RVA_TEXT__,
      callCount: totalRecordOpenCalls,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      index: this.index,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      before: this.before,
      after:
        this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index),
      ownerSnapshot: this.owner === null ? null : snapshotOwner(this.owner)
    };
    lastRecordOpenState = openState;
    sendUnique(seenRecordOpenStates, "record-open-unique", openState);
  }
});

Interceptor.attach(recordCloseAddress, {
  onEnter(args) {
    totalRecordCloseCalls += 1;
    this.recordBase = args[0];
    this.owner = inferOwnerFromRecordBase(this.recordBase);
    this.index = safeReadS32(ptr(args[0]).add(8));
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    this.callerLabel = describeRecordCloseCaller(this.callerRva);
    this.suppressClose = shouldSuppressRecordCloseCaller(this.callerRva);
    if (this.index !== null) {
      recordCloseCountsByIndex[this.index] = (recordCloseCountsByIndex[this.index] || 0) + 1;
    }
    if (this.callerRva !== null) {
      recordCloseCountsByCallerRva[this.callerRva] =
        (recordCloseCountsByCallerRva[this.callerRva] || 0) + 1;
    }
    this.before =
      this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index);
    this.ownerBefore = this.owner === null ? null : snapshotOwner(this.owner);
  },
  onLeave(retval) {
    let afterRecord =
      this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index);
    let afterOwner = this.owner === null ? null : snapshotOwner(this.owner);
    let suppressionPayload = null;
    const shouldRestoreOwnerCloseCounter =
      this.callerRva === "0x595433" &&
      this.owner !== null &&
      this.ownerBefore &&
      typeof this.ownerBefore.field114e8 === "number";
    const shouldRestorePreparedRecordFields =
      this.suppressClose &&
      this.before &&
      afterRecord &&
      (
        (
          pointerLooksSet(this.before.ptr178) &&
          !pointerLooksSet(afterRecord.ptr178)
        ) ||
        (
          pointerLooksSet(this.before.ptr180) &&
          !pointerLooksSet(afterRecord.ptr180)
        ) ||
        (
          pointerLooksSet(this.before.ptr188) &&
          !pointerLooksSet(afterRecord.ptr188)
        ) ||
        (
          pointerLooksSet(this.before.ptr1c8) &&
          !pointerLooksSet(afterRecord.ptr1c8)
        ) ||
        nonZeroValueLost(this.before.word190, afterRecord.word190) ||
        nonZeroValueLost(this.before.flag191, afterRecord.flag191)
      );
    if (
      this.suppressClose &&
      (
        shouldRestorePreparedRecordFields ||
        shouldRestoreOwnerCloseCounter
      )
    ) {
      suppressionPayload = {
        event: "record-close-call-suppression-applied",
        callerRva: this.callerRva,
        callerLabel: this.callerLabel,
        owner: hexPtr(this.owner),
        recordBase: hexPtr(this.recordBase),
        index: this.index,
        before: this.before,
        ownerBefore: this.ownerBefore,
        afterBeforeRestore: afterRecord,
        afterOwnerBeforeRestore: afterOwner,
        afterRestore: null,
        afterOwnerRestore: null,
        restoredPreparedFields: [],
        error: null
      };
      try {
        if (shouldRestorePreparedRecordFields) {
          if (
            pointerLooksSet(this.before.ptr178) &&
            !pointerLooksSet(afterRecord.ptr178)
          ) {
            ptr(this.recordBase).add(0x178).writePointer(ptr(this.before.ptr178));
            suppressionPayload.restoredPreparedFields.push("ptr178");
          }
          if (
            pointerLooksSet(this.before.ptr180) &&
            !pointerLooksSet(afterRecord.ptr180)
          ) {
            ptr(this.recordBase).add(0x180).writePointer(ptr(this.before.ptr180));
            suppressionPayload.restoredPreparedFields.push("ptr180");
          }
          if (
            pointerLooksSet(this.before.ptr188) &&
            !pointerLooksSet(afterRecord.ptr188)
          ) {
            ptr(this.recordBase).add(0x188).writePointer(ptr(this.before.ptr188));
            suppressionPayload.restoredPreparedFields.push("ptr188");
          }
          if (
            pointerLooksSet(this.before.ptr1c8) &&
            !pointerLooksSet(afterRecord.ptr1c8)
          ) {
            ptr(this.recordBase).add(0x1c8).writePointer(ptr(this.before.ptr1c8));
            suppressionPayload.restoredPreparedFields.push("ptr1c8");
          }
          if (nonZeroValueLost(this.before.word190, afterRecord.word190)) {
            ptr(this.recordBase).add(0x190).writeU16(this.before.word190);
            suppressionPayload.restoredPreparedFields.push("word190");
          }
          if (nonZeroValueLost(this.before.flag191, afterRecord.flag191)) {
            ptr(this.recordBase).add(0x191).writeU8(this.before.flag191);
            suppressionPayload.restoredPreparedFields.push("flag191");
          }
        }
        if (shouldRestoreOwnerCloseCounter) {
          const restoredOwnerField114e8 =
            this.ownerBefore.field114e8 + 1 < 0 ? 0 : this.ownerBefore.field114e8 + 1;
          ptr(this.owner).add(0x114e8).writeS32(restoredOwnerField114e8);
          suppressionPayload.restoredOwnerField114e8 = restoredOwnerField114e8;
        }
        afterRecord = snapshotRecord(this.owner, this.index);
        afterOwner = this.owner === null ? null : snapshotOwner(this.owner);
        const forceRecordDReadyOnCloseSuppression = tryForceRecordDReadyOnCloseSuppression(
          this.owner,
          this.index,
          "record-close-suppression",
          afterOwner,
          afterRecord
        );
        suppressionPayload.afterRestore = afterRecord;
        suppressionPayload.afterOwnerRestore = afterOwner;
        suppressionPayload.forcedRecordDReadyOnCloseSuppression =
          forceRecordDReadyOnCloseSuppression.forced === true;
        suppressionPayload.recordDReadyOnCloseSuppressionBefore =
          forceRecordDReadyOnCloseSuppression.beforeRecord || null;
        suppressionPayload.recordDReadyOnCloseSuppressionAfter =
          forceRecordDReadyOnCloseSuppression.afterRecord || null;
        suppressionPayload.ownerDReadyOnCloseSuppressionBefore =
          forceRecordDReadyOnCloseSuppression.beforeOwner || null;
        suppressionPayload.ownerDReadyOnCloseSuppressionAfter =
          forceRecordDReadyOnCloseSuppression.afterOwner || null;
        appliedRecordCloseCallSuppressions.push({
          callerRva: this.callerRva,
          callerLabel: this.callerLabel,
          index: this.index,
          ptr178: this.before ? this.before.ptr178 : null,
          ptr180: this.before ? this.before.ptr180 : null,
          ptr1c8: this.before ? this.before.ptr1c8 : null,
          restoredPreparedFields: suppressionPayload.restoredPreparedFields,
          restoredOwnerField114e8: shouldRestoreOwnerCloseCounter
            ? suppressionPayload.restoredOwnerField114e8
            : null
        });
        send(suppressionPayload);
      } catch (_error) {
        suppressionPayload.event = "record-close-call-suppression-error";
        suppressionPayload.error = String(_error);
        send(suppressionPayload);
      }
    }
    const closeState = {
      recordCloseRva: __RECORD_CLOSE_RVA_TEXT__,
      callCount: totalRecordCloseCalls,
      callerRva: this.callerRva,
      callerLabel: this.callerLabel,
      suppressClose: this.suppressClose,
      owner: hexPtr(this.owner),
      recordBase: hexPtr(this.recordBase),
      index: this.index,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      before: this.before,
      after: afterRecord,
      ownerSnapshot: afterOwner
    };
    lastRecordCloseState = closeState;
    sendUnique(seenRecordCloseStates, "record-close-unique", closeState);
  }
});

Interceptor.attach(selectionLoopEntryAddress, {
  onEnter(args) {
    totalSelectionLoopEntryCalls += 1;
    const owner = ptr(args[0]);
    const index = ptr(args[1]).toInt32();
    if (index !== null && index >= 0 && index < resourceCount) {
      selectionLoopEntryCountsByIndex[index] = (selectionLoopEntryCountsByIndex[index] || 0) + 1;
    }
    const state = {
      selectionLoopEntryRva: "0x596110",
      callCount: totalSelectionLoopEntryCalls,
      callerRva: callsiteRvaTextFromReturnAddress(this.returnAddress),
      owner: hexPtr(owner),
      index: index,
      record: index !== null && index >= 0 && index < resourceCount ? snapshotRecord(owner, index) : null,
      ownerSnapshot: snapshotOwner(owner)
    };
    lastSelectionLoopEntryState = state;
    sendUnique(seenSelectionLoopEntryStates, "selection-loop-entry-unique", state);
  }
});

Interceptor.attach(postSelectStatusAddress, {
  onEnter(args) {
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (this.callerRva !== postSelectStatusCallerRva) {
      this.skip = true;
      return;
    }
    totalPostSelectStatusCalls += 1;
    this.recordArgument = args[3];
    this.recordBase = args[3];
    this.owner = inferOwnerFromRecordBase(this.recordBase);
    this.index =
      this.owner === null
        ? safeReadS32(ptr(args[3]).add(8))
        : safeReadS32(ptr(args[3]).add(8));
    this.before =
      this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index);
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const originalRetval = ptr(retval).toString();
    const originalRetvalS32 = ptr(retval).toInt32();
    let forcedRetvalState = null;
    if (
      forcedPostSelectStatusRetval !== null &&
      this.owner !== null &&
      this.index !== null &&
      this.index >= 0 &&
      this.index < resourceCount &&
      originalRetvalS32 !== forcedPostSelectStatusRetval
    ) {
      retval.replace(ptr(forcedPostSelectStatusRetval));
      totalForcedPostSelectStatusRetval += 1;
      forcedRetvalState = {
        index: this.index,
        owner: hexPtr(this.owner),
        recordBase: hexPtr(this.recordBase),
        originalRetval: originalRetval,
        originalRetvalS32: originalRetvalS32,
        finalRetval: ptr(retval).toString(),
        finalRetvalS32: ptr(retval).toInt32(),
        before: this.before
      };
      lastForcedPostSelectStatusRetvalState = forcedRetvalState;
      send({
        event: "post-select-status-retval-forced",
        timestamp: Date.now() / 1000.0,
        ...forcedRetvalState
      });
    }
    const statusState = {
      postSelectStatusRva: "0x6cc2b0",
      callerRva: this.callerRva,
      callCount: totalPostSelectStatusCalls,
      owner: hexPtr(this.owner),
      recordArgument: hexPtr(this.recordArgument),
      recordBase: hexPtr(this.recordBase),
      index: this.index,
       originalRetval: originalRetval,
       originalRetvalS32: originalRetvalS32,
       retval: ptr(retval).toString(),
       retvalS32: ptr(retval).toInt32(),
       forcedRetval: forcedRetvalState !== null,
       before: this.before,
       after:
         this.owner === null || this.index === null ? null : snapshotRecord(this.owner, this.index)
    };
    lastPostSelectStatusState = statusState;
    sendUnique(seenPostSelectStatusStates, "post-select-status-unique", statusState);
  }
});

Interceptor.attach(postSelectSuccessAddress, {
  onEnter() {
    totalPostSelectSuccessCalls += 1;
    const owner = ptr(this.context.rdi);
    const slotBase = ptr(this.context.rbx);
    const recordBase = slotBase.add(8);
    const index = safeReadS32(recordBase.add(8));
    const successState = {
      postSelectSuccessRva: "0x596885",
      callCount: totalPostSelectSuccessCalls,
      owner: hexPtr(owner),
      slotBase: hexPtr(slotBase),
      recordBase: hexPtr(recordBase),
      index: index,
      record: snapshotRecord(owner, index),
      ownerSnapshot: snapshotOwner(owner)
    };
    lastPostSelectSuccessState = successState;
    sendUnique(seenPostSelectSuccessStates, "post-select-success-unique", successState);
  }
});

Interceptor.attach(ptr1c8OpenAddress, {
  onEnter(args) {
    this.callerRva = callsiteRvaTextFromReturnAddress(this.returnAddress);
    if (this.callerRva !== ptr1c8OpenCallerRva) {
      this.skip = true;
      return;
    }
    totalPtr1c8OpenCalls += 1;
    this.ptr178 = args[0];
    this.slotAddress = safeReadPointer(ptr(this.context.rsp).add(0x28));
    this.recordBase =
      this.slotAddress === null || this.slotAddress === undefined ? null : ptr(this.slotAddress).sub(0x1c8);
    this.owner = this.recordBase === null ? null : inferOwnerFromRecordBase(this.recordBase);
    this.index =
      this.recordBase === null ? null : safeReadS32(ptr(this.recordBase).add(8));
    if (this.index !== null && this.index >= 0 && this.index < resourceCount) {
      ptr1c8OpenCountsByIndex[this.index] = (ptr1c8OpenCountsByIndex[this.index] || 0) + 1;
    }
    this.before =
      this.owner === null || this.index === null
        ? null
        : snapshotRecordFromBase(this.owner, this.index, this.recordBase);
  },
  onLeave(retval) {
    if (this.skip === true) {
      return;
    }
    const state = {
      ptr1c8OpenRva: "0x597d81->0x6d2730",
      callerRva: this.callerRva,
      callCount: totalPtr1c8OpenCalls,
      owner: hexPtr(this.owner),
      index: this.index,
      recordBase: hexPtr(this.recordBase),
      slotAddress: hexPtr(this.slotAddress),
      ptr178: hexPtr(this.ptr178),
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      before: this.before,
      after:
        this.owner === null || this.index === null
          ? null
          : snapshotRecordFromBase(this.owner, this.index, this.recordBase)
    };
    lastPtr1c8OpenState = state;
    sendUnique(seenPtr1c8OpenStates, "ptr1c8-open-attempt-unique", state);
  }
});

Interceptor.attach(postSelectCommitAddress, {
  onEnter(args) {
    totalPostSelectCommitCalls += 1;
    const owner = ptr(this.context.rdi);
    const slotBase = ptr(this.context.rbx);
    const recordBase = slotBase.add(8);
    const index = safeReadS32(recordBase.add(8));
    this.owner = owner;
    this.slotBase = slotBase;
    this.recordBase = recordBase;
    this.index = index;
    const recordBefore = snapshotRecord(owner, index);
    this.recordBefore = recordBefore;
    const forceFlag20 = tryForcePostSelectFlag20(owner, index, "post-select-commit");
    this.forceFlag20 = forceFlag20;
    const forcePublication = tryForcePostSelectPublicationSuccess(
      owner,
      recordBase,
      index,
      "post-select-commit"
    );
    this.forcePublication = forcePublication;
    const commitState = {
      postSelectCommitRva: "0x596896",
      callCount: totalPostSelectCommitCalls,
      owner: hexPtr(owner),
      slotBase: hexPtr(slotBase),
      recordBase: hexPtr(recordBase),
      index: index,
      recordBefore: recordBefore,
      forcedPostSelectFlag20: forceFlag20.forced === true,
      postSelectFlag20Before: forceFlag20.before || null,
      postSelectFlag20After: forceFlag20.after || null,
      forcedPostSelectPublicationSuccess: forcePublication.forced === true,
      postSelectPublicationBefore: forcePublication.before || null,
      postSelectPublicationAfter: forcePublication.after || null,
      record: snapshotRecord(owner, index),
      ownerSnapshot: snapshotOwner(owner)
    };
    lastPostSelectCommitState = commitState;
    sendUnique(seenPostSelectCommitStates, "post-select-commit-unique", commitState);
  },
  onLeave(retval) {
    if (
      this.owner === undefined ||
      this.recordBase === undefined ||
      this.index === undefined ||
      this.index === null
    ) {
      return;
    }
    const commitReturnState = {
      postSelectCommitRva: "0x596896",
      callCount: totalPostSelectCommitCalls,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      owner: hexPtr(this.owner),
      slotBase: hexPtr(this.slotBase),
      recordBase: hexPtr(this.recordBase),
      index: this.index,
      recordBefore: this.recordBefore || null,
      forcedPostSelectFlag20: this.forceFlag20 && this.forceFlag20.forced === true,
      postSelectFlag20Before: this.forceFlag20 ? this.forceFlag20.before || null : null,
      postSelectFlag20After: this.forceFlag20 ? this.forceFlag20.after || null : null,
      forcedPostSelectPublicationSuccess:
        this.forcePublication && this.forcePublication.forced === true,
      postSelectPublicationBefore: this.forcePublication ? this.forcePublication.before || null : null,
      postSelectPublicationAfter: this.forcePublication ? this.forcePublication.after || null : null,
      recordAfter: snapshotRecord(this.owner, this.index),
      ownerSnapshotAfter: snapshotOwner(this.owner)
    };
    lastPostSelectCommitReturnState = commitReturnState;
    sendUnique(
      seenPostSelectCommitReturnStates,
      "post-select-commit-return-unique",
      commitReturnState
    );
  }
});

Interceptor.attach(postSelectLatchClearAddress, {
  onEnter() {
    totalSelectionLatchClearCalls += 1;
    this.owner = ptr(this.context.rdi);
    this.index =
      this.context.r13 !== undefined && this.context.r13 !== null ? this.context.r13.toInt32() : null;
    if (this.index !== null && this.index >= 0 && this.index < resourceCount) {
      selectionLatchClearCountsByIndex[this.index] =
        (selectionLatchClearCountsByIndex[this.index] || 0) + 1;
    }
    const latchClearState = {
      selectionLatchClearRva: "0x596554",
      callCount: totalSelectionLatchClearCalls,
      owner: hexPtr(this.owner),
      index: this.index,
      record: snapshotRecord(this.owner, this.index),
      ownerSnapshot: snapshotOwner(this.owner)
    };
    const forceRecordDReady = tryForceRecordDReadyOnLatchClear(
      this.owner,
      this.index,
      "selection-latch-clear"
    );
    this.forceRecordDReadyOnLatchClear = forceRecordDReady;
    latchClearState.forcedRecordDReadyOnLatchClear = forceRecordDReady.forced === true;
    latchClearState.recordDReadyOnLatchClearBefore =
      forceRecordDReady.beforeRecord || null;
    latchClearState.recordDReadyOnLatchClearAfter =
      forceRecordDReady.afterRecord || null;
    latchClearState.ownerDReadyOnLatchClearBefore =
      forceRecordDReady.beforeOwner || null;
    latchClearState.ownerDReadyOnLatchClearAfter =
      forceRecordDReady.afterOwner || null;
    lastSelectionLatchClearState = latchClearState;
    sendUnique(seenSelectionLatchClearStates, "selection-latch-clear-unique", latchClearState);
    if (
      !__SUPPRESS_POST_SELECT_LATCH_CLEAR__ ||
      this.owner === null ||
      this.index === null ||
      this.index < 0 ||
      this.index >= resourceCount
    ) {
      return;
    }
    if (this.context.rip !== undefined) {
      this.context.rip = postSelectLatchClearSkipAddress;
    } else if (this.context.pc !== undefined) {
      this.context.pc = postSelectLatchClearSkipAddress;
    }
    totalSuppressedPostSelectLatchClear += 1;
    const state = {
      event: "post-select-latch-clear-suppressed",
      timestamp: Date.now() / 1000.0,
      owner: hexPtr(this.owner),
      index: this.index,
      record: snapshotRecord(this.owner, this.index),
      ownerSnapshot: snapshotOwner(this.owner)
    };
    lastSuppressedPostSelectLatchClearState = state;
    send(state);
  },
  onLeave(retval) {
    if (
      this.owner === undefined ||
      this.owner === null ||
      this.index === undefined ||
      this.index === null ||
      this.index < 0 ||
      this.index >= resourceCount
    ) {
      return;
    }
    const latchClearReturnState = {
      selectionLatchClearRva: "0x596554",
      callCount: totalSelectionLatchClearCalls,
      retval: ptr(retval).toString(),
      retvalS32: ptr(retval).toInt32(),
      owner: hexPtr(this.owner),
      index: this.index,
      suppressed: __SUPPRESS_POST_SELECT_LATCH_CLEAR__,
      forcedRecordDReadyOnLatchClear:
        this.forceRecordDReadyOnLatchClear &&
        this.forceRecordDReadyOnLatchClear.forced === true,
      recordDReadyOnLatchClearBefore:
        this.forceRecordDReadyOnLatchClear
          ? this.forceRecordDReadyOnLatchClear.beforeRecord || null
          : null,
      recordDReadyOnLatchClearAfter:
        this.forceRecordDReadyOnLatchClear
          ? this.forceRecordDReadyOnLatchClear.afterRecord || null
          : null,
      recordAfter: snapshotRecord(this.owner, this.index),
      ownerSnapshotAfter: snapshotOwner(this.owner)
    };
    lastSelectionLatchClearReturnState = latchClearReturnState;
    sendUnique(
      seenSelectionLatchClearReturnStates,
      "selection-latch-clear-return-unique",
      latchClearReturnState
    );
  }
});

Interceptor.attach(idleSelectorQueueCheckAddress, {
  onEnter(args) {
    this.traceThreadId = Process.getCurrentThreadId();
    const threadState = idleSelectorThreadStates[this.traceThreadId];
    if (!threadState) {
      this.track = false;
      return;
    }
    this.track = true;
    this.owner = threadState.owner;
    this.argument = args[0];
    this.matchesOwnerQueue =
      hexPtr(args[0]) === hexPtr(ptr(threadState.owner).add(0x11bc8));
  },
  onLeave(retval) {
    if (!this.track || !this.matchesOwnerQueue) {
      return;
    }
    const originalRetval = ptr(retval).toString();
    const originalRetvalS32 = ptr(retval).toInt32();
    let finalRetval = originalRetval;
    let finalRetvalS32 = originalRetvalS32;
    let forcedQueueEmpty = false;
    if (__FORCE_IDLE_SELECTOR_QUEUE_EMPTY__) {
      retval.replace(ptr(0));
      finalRetval = "0x0";
      finalRetvalS32 = 0;
      forcedQueueEmpty = true;
      totalForcedIdleSelectorQueueEmpty += 1;
    }
    const queueCheckState = {
      idleSelectorQueueCheckRva: __IDLE_SELECTOR_QUEUE_CHECK_RVA_TEXT__,
      owner: hexPtr(this.owner),
      argument: hexPtr(this.argument),
      matchesOwnerQueue: this.matchesOwnerQueue,
      originalRetval: originalRetval,
      originalRetvalS32: originalRetvalS32,
      forcedIdleSelectorQueueEmpty: forcedQueueEmpty,
      finalRetval: finalRetval,
      finalRetvalS32: finalRetvalS32
    };
    lastIdleSelectorQueueCheckState = queueCheckState;
    idleSelectorThreadStates[this.traceThreadId].queueCheckState = queueCheckState;
    sendUnique(
      seenIdleSelectorQueueCheckStates,
      "resource-idle-selector-queue-check-unique",
      queueCheckState
    );
  }
});

Interceptor.attach(idleSelectorAddress, {
  onEnter(args) {
    totalIdleSelectorCalls += 1;
    this.owner = args[0];
    this.traceThreadId = Process.getCurrentThreadId();
    const entryForce = tryForceIdleSelectorEntryGates(this.owner, "idle-selector-enter");
    idleSelectorThreadStates[this.traceThreadId] = {
      owner: this.owner,
      queueCheckState: null,
      entryForce: entryForce
    };
    const idleSelectorState = {
      idleSelectorRva: __IDLE_SELECTOR_RVA_TEXT__,
      callCount: totalIdleSelectorCalls,
      forcedIdleSelectorLatchClear: entryForce.forcedLatchClear === true,
      forcedIdleSelectorTimerOpen: entryForce.forcedTimerOpen === true,
      idleSelectorEntryForceError: entryForce.error || null,
      ...snapshotOwner(this.owner)
    };
    lastIdleSelectorState = idleSelectorState;
    sendUnique(seenIdleSelectorStates, "resource-idle-selector-unique", idleSelectorState);
  },
  onLeave(retval) {
    const retvalS32 = ptr(retval).toInt32();
    const ownerStageForce = tryForceOwnerStageClear(this.owner, "idle-selector-return");
    const threadState = idleSelectorThreadStates[this.traceThreadId];
    const idleSelectorReturnState = {
      idleSelectorRva: __IDLE_SELECTOR_RVA_TEXT__,
      callCount: totalIdleSelectorCalls,
      retval: ptr(retval).toString(),
      retvalS32: retvalS32,
      idleSelectorQueueCheck: threadState ? threadState.queueCheckState : null,
      forcedOwnerStageClear: ownerStageForce.forced === true,
      ownerStageForceBefore: ownerStageForce.before || null,
      ownerStageForceAfter: ownerStageForce.after || null,
      ...snapshotOwner(this.owner)
    };
    delete idleSelectorThreadStates[this.traceThreadId];
    lastIdleSelectorReturnState = idleSelectorReturnState;
    sendUnique(
      seenIdleSelectorReturnStates,
      "resource-idle-selector-return-unique",
      idleSelectorReturnState
    );
  }
});

rpc.exports = {
  snapshot() {
    return {
      gateRva: __GATE_RVA_TEXT__,
      recordResetRva: __RECORD_RESET_RVA_TEXT__,
      dispatchRva: __DISPATCH_RVA_TEXT__,
      queueHandlerType3Rva: __QUEUE_HANDLER_TYPE3_RVA_TEXT__,
      recordStateRva: __RECORD_STATE_RVA_TEXT__,
      recordFinalizeRva: __RECORD_FINALIZE_RVA_TEXT__,
      queueHandlerType2Rva: __QUEUE_HANDLER_TYPE2_RVA_TEXT__,
      queueHandlerType0Rva: __QUEUE_HANDLER_TYPE0_RVA_TEXT__,
      queueHelperPrepareRva: __QUEUE_HELPER_PREPARE_RVA_TEXT__,
      queueLoopItemRva: __QUEUE_LOOP_ITEM_RVA_TEXT__,
      queueLoopPostRva: __QUEUE_LOOP_POST_RVA_TEXT__,
      recordOpenRva: __RECORD_OPEN_RVA_TEXT__,
      recordCloseRva: __RECORD_CLOSE_RVA_TEXT__,
      idleSelectorRva: __IDLE_SELECTOR_RVA_TEXT__,
      totalGateCalls: totalGateCalls,
      totalRecordResetCalls: totalRecordResetCalls,
      totalDispatchCalls: totalDispatchCalls,
      totalQueueHandlerType3Calls: totalQueueHandlerType3Calls,
      totalRecordStateCalls: totalRecordStateCalls,
      totalQueueHandlerType2Calls: totalQueueHandlerType2Calls,
      totalQueueHandlerType0Calls: totalQueueHandlerType0Calls,
      totalQueueHelperPrepareCalls: totalQueueHelperPrepareCalls,
      totalType0MaterializeCalls: totalType0MaterializeCalls,
      totalType0PrepareStatusCalls: totalType0PrepareStatusCalls,
      totalType0DescriptorStatusCalls: totalType0DescriptorStatusCalls,
      totalType0CompareGateCalls: totalType0CompareGateCalls,
      totalType0SourceObjectCalls: totalType0SourceObjectCalls,
      totalQueueLoopItemCalls: totalQueueLoopItemCalls,
      totalQueueLoopPostCalls: totalQueueLoopPostCalls,
      totalRecordOpenCalls: totalRecordOpenCalls,
      totalRecordCloseCalls: totalRecordCloseCalls,
      totalIdleSelectorCalls: totalIdleSelectorCalls,
      totalSelectionLoopEntryCalls: totalSelectionLoopEntryCalls,
      totalPostSelectStatusCalls: totalPostSelectStatusCalls,
      totalPostSelectSuccessCalls: totalPostSelectSuccessCalls,
      totalPostSelectCommitCalls: totalPostSelectCommitCalls,
      totalPtr1c8OpenCalls: totalPtr1c8OpenCalls,
      totalDispatchProviderAcceptCalls: totalDispatchProviderAcceptCalls,
      totalForcedDispatchProviderAccept: totalForcedDispatchProviderAccept,
      totalDispatchResultMetadataReads: totalDispatchResultMetadataReads,
      totalForcedDispatchResultMetadataFallback: totalForcedDispatchResultMetadataFallback,
      totalPostDispatchReleaseCallbackCalls: totalPostDispatchReleaseCallbackCalls,
      totalForcedPostDispatchReleaseCallbackFallback:
        totalForcedPostDispatchReleaseCallbackFallback,
      totalDispatchCacheQueryCalls: totalDispatchCacheQueryCalls,
      totalSelectionLatchClearCalls: totalSelectionLatchClearCalls,
        totalForcedRecord21: totalForcedRecord21,
        totalForcedRecordE: totalForcedRecordE,
        totalForcedRecordEDispatchReturn: totalForcedRecordEDispatchReturn,
        totalForcedFinalizeOnDispatchReturn: totalForcedFinalizeOnDispatchReturn,
        totalForcedRecordDDispatchReturn: totalForcedRecordDDispatchReturn,
        totalForcedOwnerStageClear: totalForcedOwnerStageClear,
      totalForcedRecordOpen: totalForcedRecordOpen,
      totalForcedSeedDispatch: totalForcedSeedDispatch,
      totalForcedRecordDReadyOnPtr178: totalForcedRecordDReadyOnPtr178,
      totalForcedRecordDReadyOnLatchClear: totalForcedRecordDReadyOnLatchClear,
      totalForcedRecordDReadyOnCloseSuppression: totalForcedRecordDReadyOnCloseSuppression,
      totalForcedSelectorReadyOnPtr178: totalForcedSelectorReadyOnPtr178,
      totalForcedDirectDispatch: totalForcedDirectDispatch,
      totalForcedOwnerStageOpen: totalForcedOwnerStageOpen,
      totalForcedPreparedSelectorReady: totalForcedPreparedSelectorReady,
      totalDemotedHotDoneZeroQueuedRecords: totalDemotedHotDoneZeroQueuedRecords,
      totalForcedIdleSelectorLatchClear: totalForcedIdleSelectorLatchClear,
      totalForcedIdleSelectorTimerOpen: totalForcedIdleSelectorTimerOpen,
      totalForcedIdleSelectorQueueEmpty: totalForcedIdleSelectorQueueEmpty,
      totalForcedPostSelectFlag20: totalForcedPostSelectFlag20,
      totalForcedPostSelectStatusRetval: totalForcedPostSelectStatusRetval,
      totalForcedPostSelectPublicationSuccess: totalForcedPostSelectPublicationSuccess,
      totalSuppressedPostSelectLatchClear: totalSuppressedPostSelectLatchClear,
      totalForcedRecordStateFromType0: totalForcedRecordStateFromType0,
      totalForcedType0Field18To2: totalForcedType0Field18To2,
      totalForcedType0PrepareBranch: totalForcedType0PrepareBranch,
      totalForcedItemPayloadFromPtr178: totalForcedItemPayloadFromPtr178,
      totalForcedType0RawSourceFromPtr178: totalForcedType0RawSourceFromPtr178,
      totalForcedType0ZlbSourceFromPtr178: totalForcedType0ZlbSourceFromPtr178,
      totalForcedType0RequestedLengthFromSourceHeader:
        totalForcedType0RequestedLengthFromSourceHeader,
      totalForcedType0SourceObjectFromSideSlots: totalForcedType0SourceObjectFromSideSlots,
      totalForcedType0InnerSourceFromSideWrapper:
      totalForcedType0InnerSourceFromSideWrapper,
      totalForcedType0ParserSingleBytePayloadTo1:
        totalForcedType0ParserSingleBytePayloadTo1,
      totalForcedQueueHelperResolverSyntheticSuccess:
        totalForcedQueueHelperResolverSyntheticSuccess,
      totalForcedQueueHelperPostParserCleanupSuppressions:
        totalForcedQueueHelperPostParserCleanupSuppressions,
      totalForcedQueueHelperReturnSlotRestores:
        totalForcedQueueHelperReturnSlotRestores,
      totalForcedType0HandlerReturnSlotRestores:
        totalForcedType0HandlerReturnSlotRestores,
      totalForcedType3FollowonOnPostState1: totalForcedType3FollowonOnPostState1,
      totalForcedFinalizeAfterType3OnPostState1: totalForcedFinalizeAfterType3OnPostState1,
      totalReenteredRecordStateAfterType3OnPostState1:
        totalReenteredRecordStateAfterType3OnPostState1,
      uniqueGateStates: Object.keys(seenGateStates).length,
      uniqueGateReturnStates: Object.keys(seenGateReturnStates).length,
      uniqueRecordResetStates: Object.keys(seenRecordResetStates).length,
      uniqueDispatchStates: Object.keys(seenDispatchStates).length,
      uniqueDispatchReturnStates: Object.keys(seenDispatchReturnStates).length,
      uniqueQueueHandlerType3States: Object.keys(seenQueueHandlerType3States).length,
      uniqueRecordStates: Object.keys(seenRecordStates).length,
      uniqueQueueHandlerType2States: Object.keys(seenQueueHandlerType2States).length,
      uniqueQueueHandlerType0States: Object.keys(seenQueueHandlerType0States).length,
      uniqueQueueHelperPrepareEntryStates: Object.keys(seenQueueHelperPrepareEntryStates).length,
      uniqueQueueHelperPrepareStates: Object.keys(seenQueueHelperPrepareStates).length,
      uniqueQueueHelperPrepareResolverCallStates:
        Object.keys(seenQueueHelperPrepareResolverCallStates).length,
      uniqueQueueHelperResolverSyntheticSuccessStates:
        Object.keys(seenQueueHelperResolverSyntheticSuccessStates).length,
      uniqueQueueHelperPostParserCleanupSuppressionStates:
        Object.keys(seenQueueHelperPostParserCleanupSuppressionStates).length,
      uniqueQueueHelperReturnSlotRestoreStates:
        Object.keys(seenQueueHelperReturnSlotRestoreStates).length,
      uniqueQueueHelperPostParserTypeCompareStates:
        Object.keys(seenQueueHelperPostParserTypeCompareStates).length,
      uniqueQueueHelperPostParserClassStates:
        Object.keys(seenQueueHelperPostParserClassStates).length,
      uniqueQueueHelperPostParserMaterializeStates:
        Object.keys(seenQueueHelperPostParserMaterializeStates).length,
      uniqueQueueHelperPrepareBufferAllocStates:
        Object.keys(seenQueueHelperPrepareBufferAllocStates).length,
      uniqueQueueHelperPrepareBufferCleanupEntryStates:
        Object.keys(seenQueueHelperPrepareBufferCleanupEntryStates).length,
      uniqueQueueHelperPrepareBufferCleanupStates:
        Object.keys(seenQueueHelperPrepareBufferCleanupStates).length,
      uniqueQueueHelperPrepareCopyStates:
        Object.keys(seenQueueHelperPrepareCopyStates).length,
      uniqueType0HandlerReturnBridgeStates:
        Object.keys(seenType0HandlerReturnBridgeStates).length,
      uniqueType0HandlerReturnSlotRestoreStates:
        Object.keys(seenType0HandlerReturnSlotRestoreStates).length,
      uniqueType0PostPrepareReinitEntryStates:
        Object.keys(seenType0PostPrepareReinitEntryStates).length,
      uniqueType0PostPrepareReinitReturnStates:
        Object.keys(seenType0PostPrepareReinitReturnStates).length,
      uniqueType0PostPrepareStateCallEntryStates:
        Object.keys(seenType0PostPrepareStateCallEntryStates).length,
      uniqueType0PostPrepareStateCallReturnStates:
        Object.keys(seenType0PostPrepareStateCallReturnStates).length,
      uniqueType0PostPrepareBindEntryStates:
        Object.keys(seenType0PostPrepareBindEntryStates).length,
      uniqueType0PostPrepareBindReturnStates:
        Object.keys(seenType0PostPrepareBindReturnStates).length,
      uniqueType0PostPrepareType2EntryStates:
        Object.keys(seenType0PostPrepareType2EntryStates).length,
      uniqueType0MaterializeStates: Object.keys(seenType0MaterializeStates).length,
      uniqueType0PrepareStatusEntryStates: Object.keys(seenType0PrepareStatusEntryStates).length,
      uniqueType0PrepareStatusStates: Object.keys(seenType0PrepareStatusStates).length,
      uniqueType0DescriptorStatusStates: Object.keys(seenType0DescriptorStatusStates).length,
      uniqueType0CompareGateStates: Object.keys(seenType0CompareGateStates).length,
      uniqueType0SourceObjectStates: Object.keys(seenType0SourceObjectStates).length,
      uniqueType0PrepareParserEntryStates: Object.keys(seenType0PrepareParserEntryStates).length,
      uniqueType0PrepareParserStates: Object.keys(seenType0PrepareParserStates).length,
      uniqueQueueLoopItemStates: Object.keys(seenQueueLoopItemStates).length,
      uniqueQueueLoopPostStates: Object.keys(seenQueueLoopPostStates).length,
      uniqueRecordOpenStates: Object.keys(seenRecordOpenStates).length,
      uniqueRecordCloseStates: Object.keys(seenRecordCloseStates).length,
      uniqueIdleSelectorStates: Object.keys(seenIdleSelectorStates).length,
      uniqueIdleSelectorReturnStates: Object.keys(seenIdleSelectorReturnStates).length,
      uniqueIdleSelectorQueueCheckStates: Object.keys(seenIdleSelectorQueueCheckStates).length,
      uniqueSelectionLoopEntryStates: Object.keys(seenSelectionLoopEntryStates).length,
      uniquePostSelectStatusStates: Object.keys(seenPostSelectStatusStates).length,
      uniquePostSelectSuccessStates: Object.keys(seenPostSelectSuccessStates).length,
        uniquePostSelectCommitStates: Object.keys(seenPostSelectCommitStates).length,
        uniquePostSelectCommitReturnStates: Object.keys(seenPostSelectCommitReturnStates).length,
        uniquePtr1c8OpenStates: Object.keys(seenPtr1c8OpenStates).length,
      uniqueDispatchProviderAcceptStates: Object.keys(seenDispatchProviderAcceptStates).length,
      uniqueDispatchResultMetadataStates:
        Object.keys(seenDispatchResultMetadataStates).length,
      uniquePostDispatchReleaseCallbackStates:
        Object.keys(seenPostDispatchReleaseCallbackStates).length,
      uniqueDispatchCacheQueryStates: Object.keys(seenDispatchCacheQueryStates).length,
        uniqueSelectionLatchClearStates: Object.keys(seenSelectionLatchClearStates).length,
        uniqueSelectionLatchClearReturnStates:
          Object.keys(seenSelectionLatchClearReturnStates).length,
        uniqueForcedFinalizeOnDispatchReturnStates:
          Object.keys(seenForcedFinalizeOnDispatchReturnStates).length,
        dispatchCountsByIndex: dispatchCountsByIndex,
        directDispatchCountsByIndex: directDispatchCountsByIndex,
      recordResetCountsByIndex: recordResetCountsByIndex,
      recordResetCountsByCallerRva: recordResetCountsByCallerRva,
      selectionLoopEntryCountsByIndex: selectionLoopEntryCountsByIndex,
      queueHandlerType3CountsByIndex: queueHandlerType3CountsByIndex,
      recordStateCountsByIndex: recordStateCountsByIndex,
      queueHandlerType2CountsByIndex: queueHandlerType2CountsByIndex,
      queueHandlerType0CountsByIndex: queueHandlerType0CountsByIndex,
      forcedType0PrepareBranchCountsByIndex: forcedType0PrepareBranchCountsByIndex,
      queueHelperPrepareCountsByIndex: queueHelperPrepareCountsByIndex,
      queueLoopCountsByIndex: queueLoopCountsByIndex,
      queueLoopCountsByRawType: queueLoopCountsByRawType,
      queueLoopCountsByPredictedHandler: queueLoopCountsByPredictedHandler,
      recordOpenCountsByIndex: recordOpenCountsByIndex,
      recordCloseCountsByIndex: recordCloseCountsByIndex,
      recordCloseCountsByCallerRva: recordCloseCountsByCallerRva,
        ptr1c8OpenCountsByIndex: ptr1c8OpenCountsByIndex,
        selectionLatchClearCountsByIndex: selectionLatchClearCountsByIndex,
        forcedDispatchReturnCountsByIndex: forcedDispatchReturnCountsByIndex,
        forcedFinalizeOnDispatchReturnCountsByIndex: forcedFinalizeOnDispatchReturnCountsByIndex,
      forcedDirectDispatchCountsByIndex: forcedDirectDispatchCountsByIndex,
      forcedRecordDReadyOnPtr178CountsByIndex: forcedRecordDReadyOnPtr178CountsByIndex,
      forcedRecordDReadyOnLatchClearCountsByIndex: forcedRecordDReadyOnLatchClearCountsByIndex,
      forcedRecordDReadyOnCloseSuppressionCountsByIndex:
        forcedRecordDReadyOnCloseSuppressionCountsByIndex,
      forcedSelectorReadyOnPtr178CountsByIndex: forcedSelectorReadyOnPtr178CountsByIndex,
      forcedPreparedSelectorReadyCountsByIndex: forcedPreparedSelectorReadyCountsByIndex,
      demotedHotDoneZeroQueuedRecordCountsByIndex: demotedHotDoneZeroQueuedRecordCountsByIndex,
      forcedRecordOpenCountsByIndex: forcedRecordOpenCountsByIndex,
      forcedRecordDClearCountsByIndex: forcedRecordDClearCountsByIndex,
      forcedRecordStateFromType0CountsByIndex: forcedRecordStateFromType0CountsByIndex,
      skippedRecordStateFromType0CountsByIndex: skippedRecordStateFromType0CountsByIndex,
      forcedType0Field18To2CountsByIndex: forcedType0Field18To2CountsByIndex,
      forcedItemPayloadFromPtr178CountsByIndex: forcedItemPayloadFromPtr178CountsByIndex,
      forcedType0RawSourceFromPtr178CountsByIndex: forcedType0RawSourceFromPtr178CountsByIndex,
      forcedType0ZlbSourceFromPtr178CountsByIndex: forcedType0ZlbSourceFromPtr178CountsByIndex,
      forcedType0RequestedLengthFromSourceHeaderCountsByIndex:
        forcedType0RequestedLengthFromSourceHeaderCountsByIndex,
      forcedType0SourceObjectFromSideSlotsCountsByIndex:
        forcedType0SourceObjectFromSideSlotsCountsByIndex,
      forcedType0InnerSourceFromSideWrapperCountsByIndex:
        forcedType0InnerSourceFromSideWrapperCountsByIndex,
      forcedType0ParserSingleBytePayloadTo1CountsByIndex:
        forcedType0ParserSingleBytePayloadTo1CountsByIndex,
      forcedType3FollowonOnPostState1CountsByIndex: forcedType3FollowonOnPostState1CountsByIndex,
      forcedFinalizeAfterType3OnPostState1CountsByIndex:
        forcedFinalizeAfterType3OnPostState1CountsByIndex,
      reenteredRecordStateAfterType3OnPostState1CountsByIndex:
        reenteredRecordStateAfterType3OnPostState1CountsByIndex,
      appliedRecordCloseCallSuppressions: appliedRecordCloseCallSuppressions,
      lastIdleSelectorEntryForceState: lastIdleSelectorEntryForceState,
      lastIdleSelectorQueueCheckState: lastIdleSelectorQueueCheckState,
      lastGateState: lastGateState,
      lastGateReturnState: lastGateReturnState,
      lastRecordResetState: lastRecordResetState,
      lastDispatchState: lastDispatchState,
      lastDispatchReturnState: lastDispatchReturnState,
      lastQueueHandlerType3State: lastQueueHandlerType3State,
      lastRecordState: lastRecordState,
        lastQueueHandlerType2State: lastQueueHandlerType2State,
        lastQueueHandlerType0State: lastQueueHandlerType0State,
        lastQueueHelperPrepareEntryState: lastQueueHelperPrepareEntryState,
        lastQueueHelperPrepareState: lastQueueHelperPrepareState,
        lastQueueHelperPrepareResolverCallState: lastQueueHelperPrepareResolverCallState,
        lastForcedQueueHelperResolverSyntheticSuccessState:
          lastForcedQueueHelperResolverSyntheticSuccessState,
        lastForcedQueueHelperPostParserCleanupSuppressionState:
          lastForcedQueueHelperPostParserCleanupSuppressionState,
        lastForcedQueueHelperReturnSlotRestoreState:
          lastForcedQueueHelperReturnSlotRestoreState,
        lastType0HandlerReturnBridgeState: lastType0HandlerReturnBridgeState,
        lastForcedType0HandlerReturnSlotRestoreState:
          lastForcedType0HandlerReturnSlotRestoreState,
        lastQueueHelperPostParserTypeCompareState: lastQueueHelperPostParserTypeCompareState,
        lastQueueHelperPostParserClassState: lastQueueHelperPostParserClassState,
        lastQueueHelperPostParserMaterializeState: lastQueueHelperPostParserMaterializeState,
        lastQueueHelperPrepareBufferAllocState: lastQueueHelperPrepareBufferAllocState,
        lastQueueHelperPrepareBufferCleanupEntryState:
          lastQueueHelperPrepareBufferCleanupEntryState,
        lastQueueHelperPrepareBufferCleanupState: lastQueueHelperPrepareBufferCleanupState,
        lastQueueHelperPrepareCopyState: lastQueueHelperPrepareCopyState,
        lastType0PostPrepareReinitEntryState: lastType0PostPrepareReinitEntryState,
        lastType0PostPrepareReinitReturnState: lastType0PostPrepareReinitReturnState,
        lastType0PostPrepareStateCallEntryState: lastType0PostPrepareStateCallEntryState,
        lastType0PostPrepareStateCallReturnState: lastType0PostPrepareStateCallReturnState,
        lastType0PostPrepareBindEntryState: lastType0PostPrepareBindEntryState,
        lastType0PostPrepareBindReturnState: lastType0PostPrepareBindReturnState,
        lastType0PostPrepareType2EntryState: lastType0PostPrepareType2EntryState,
        lastType0MaterializeState: lastType0MaterializeState,
        lastType0PrepareStatusEntryState: lastType0PrepareStatusEntryState,
        lastType0PrepareStatusState: lastType0PrepareStatusState,
        lastType0DescriptorStatusState: lastType0DescriptorStatusState,
        lastType0CompareGateState: lastType0CompareGateState,
        lastType0SourceObjectState: lastType0SourceObjectState,
        lastType0PrepareParserEntryState: lastType0PrepareParserEntryState,
        lastType0PrepareParserState: lastType0PrepareParserState,
        lastQueueLoopItemState: lastQueueLoopItemState,
      lastQueueLoopPostState: lastQueueLoopPostState,
      lastRecordOpenState: lastRecordOpenState,
      lastRecordCloseState: lastRecordCloseState,
      lastOwnerStageForceState: lastOwnerStageForceState,
      lastRecordOpenForceState: lastRecordOpenForceState,
      lastSeedDispatchForceState: lastSeedDispatchForceState,
      lastRecordDReadyOnPtr178State: lastRecordDReadyOnPtr178State,
      lastRecordDReadyOnLatchClearState: lastRecordDReadyOnLatchClearState,
      lastRecordDReadyOnCloseSuppressionState: lastRecordDReadyOnCloseSuppressionState,
      lastSelectorReadyOnPtr178State: lastSelectorReadyOnPtr178State,
      lastDirectDispatchForceState: lastDirectDispatchForceState,
      lastOwnerStageOpenState: lastOwnerStageOpenState,
      lastPreparedSelectorReadyState: lastPreparedSelectorReadyState,
      lastDemotedHotDoneZeroQueuedRecordState: lastDemotedHotDoneZeroQueuedRecordState,
      lastIdleSelectorState: lastIdleSelectorState,
      lastIdleSelectorReturnState: lastIdleSelectorReturnState,
      lastSelectionLoopEntryState: lastSelectionLoopEntryState,
      lastPostSelectStatusState: lastPostSelectStatusState,
      lastPostSelectSuccessState: lastPostSelectSuccessState,
      lastPostSelectCommitState: lastPostSelectCommitState,
      lastPostSelectCommitReturnState: lastPostSelectCommitReturnState,
      lastPtr1c8OpenState: lastPtr1c8OpenState,
      lastDispatchProviderAcceptState: lastDispatchProviderAcceptState,
      lastDispatchResultMetadataState: lastDispatchResultMetadataState,
      lastPostDispatchReleaseCallbackState: lastPostDispatchReleaseCallbackState,
      lastDispatchCacheQueryState: lastDispatchCacheQueryState,
      lastPostSelectFlag20State: lastPostSelectFlag20State,
      lastForcedPostSelectStatusRetvalState: lastForcedPostSelectStatusRetvalState,
      lastForcedPostSelectPublicationSuccessState: lastForcedPostSelectPublicationSuccessState,
      lastSelectionLatchClearState: lastSelectionLatchClearState,
      lastSelectionLatchClearReturnState: lastSelectionLatchClearReturnState,
      lastSuppressedPostSelectLatchClearState: lastSuppressedPostSelectLatchClearState,
      lastForcedRecordStateFromType0State: lastForcedRecordStateFromType0State,
      lastSkippedRecordStateFromType0State: lastSkippedRecordStateFromType0State,
      lastForcedType0Field18To2State: lastForcedType0Field18To2State,
      lastForcedType0PrepareBranchState: lastForcedType0PrepareBranchState,
      lastForcedItemPayloadFromPtr178State: lastForcedItemPayloadFromPtr178State,
      lastForcedType0RawSourceFromPtr178State: lastForcedType0RawSourceFromPtr178State,
      lastForcedType0ZlbSourceFromPtr178State: lastForcedType0ZlbSourceFromPtr178State,
      lastForcedType0RequestedLengthFromSourceHeaderState:
        lastForcedType0RequestedLengthFromSourceHeaderState,
      lastForcedType0SourceObjectFromSideSlotsState:
        lastForcedType0SourceObjectFromSideSlotsState,
      lastForcedType0InnerSourceFromSideWrapperState:
        lastForcedType0InnerSourceFromSideWrapperState,
      lastForcedType0ParserSingleBytePayloadTo1State:
        lastForcedType0ParserSingleBytePayloadTo1State,
      lastForcedType3FollowonOnPostState1State: lastForcedType3FollowonOnPostState1State,
        lastReenteredRecordStateAfterType3OnPostState1State:
          lastReenteredRecordStateAfterType3OnPostState1State,
        lastForcedFinalizeOnDispatchReturnState: lastForcedFinalizeOnDispatchReturnState
      };
    }
};
"""
        .replace("__GATE_RVA__", hex(gate_rva))
        .replace("__RECORD_RESET_RVA__", hex(record_reset_rva))
        .replace("__DISPATCH_RVA__", hex(dispatch_rva))
        .replace("__QUEUE_HANDLER_TYPE3_RVA__", hex(queue_handler_type3_rva))
        .replace("__RECORD_STATE_RVA__", hex(record_state_rva))
        .replace("__RECORD_FINALIZE_RVA__", hex(record_finalize_rva))
        .replace("__QUEUE_HANDLER_TYPE2_RVA__", hex(queue_handler_type2_rva))
        .replace("__QUEUE_HANDLER_TYPE0_RVA__", hex(queue_handler_type0_rva))
        .replace("__QUEUE_HELPER_PREPARE_RVA__", hex(queue_helper_prepare_rva))
        .replace("__TYPE0_PREPARE_STATUS_RVA__", hex(type0_prepare_status_rva))
        .replace("__TYPE0_DESCRIPTOR_STATUS_RVA__", hex(type0_descriptor_status_rva))
        .replace("__TYPE0_SOURCE_OBJECT_RVA__", hex(type0_source_object_rva))
        .replace("__TYPE0_PREPARE_PARSER_RVA__", hex(type0_prepare_parser_rva))
        .replace("__QUEUE_LOOP_ITEM_RVA__", hex(queue_loop_item_rva))
        .replace("__QUEUE_LOOP_POST_RVA__", hex(queue_loop_post_rva))
        .replace("__RECORD_OPEN_RVA__", hex(record_open_rva))
        .replace("__RECORD_CLOSE_RVA__", hex(record_close_rva))
        .replace(
            "__SUPPRESS_RECORD_CLOSE_CALL_RVAS__",
            json.dumps(suppress_record_close_call_rvas),
        )
        .replace("__IDLE_SELECTOR_RVA__", hex(idle_selector_rva))
        .replace("__SEED_DISPATCH_RVA__", hex(seed_dispatch_rva))
        .replace("__IDLE_SELECTOR_QUEUE_CHECK_RVA__", hex(idle_selector_queue_check_rva))
        .replace("__SCHEDULER_GLOBAL_RVA__", hex(scheduler_global_rva))
        .replace("__RESOURCE_COUNT__", str(resource_count))
        .replace("__RECORD_STRIDE__", hex(record_stride))
        .replace("__GATE_RVA_TEXT__", json.dumps(hex(gate_rva)))
        .replace("__RECORD_RESET_RVA_TEXT__", json.dumps(hex(record_reset_rva)))
        .replace("__DISPATCH_RVA_TEXT__", json.dumps(hex(dispatch_rva)))
        .replace("__QUEUE_HANDLER_TYPE3_RVA_TEXT__", json.dumps(hex(queue_handler_type3_rva)))
        .replace("__RECORD_STATE_RVA_TEXT__", json.dumps(hex(record_state_rva)))
        .replace("__RECORD_FINALIZE_RVA_TEXT__", json.dumps(hex(record_finalize_rva)))
        .replace("__QUEUE_HANDLER_TYPE2_RVA_TEXT__", json.dumps(hex(queue_handler_type2_rva)))
        .replace("__QUEUE_HANDLER_TYPE0_RVA_TEXT__", json.dumps(hex(queue_handler_type0_rva)))
        .replace(
            "__QUEUE_HELPER_PREPARE_RVA_TEXT__",
            json.dumps(hex(queue_helper_prepare_rva)),
        )
        .replace("__QUEUE_LOOP_ITEM_RVA_TEXT__", json.dumps(hex(queue_loop_item_rva)))
        .replace("__QUEUE_LOOP_POST_RVA_TEXT__", json.dumps(hex(queue_loop_post_rva)))
        .replace("__RECORD_OPEN_RVA_TEXT__", json.dumps(hex(record_open_rva)))
        .replace("__RECORD_CLOSE_RVA_TEXT__", json.dumps(hex(record_close_rva)))
        .replace("__IDLE_SELECTOR_RVA_TEXT__", json.dumps(hex(idle_selector_rva)))
        .replace(
            "__IDLE_SELECTOR_QUEUE_CHECK_RVA_TEXT__",
            json.dumps(hex(idle_selector_queue_check_rva)),
        )
        .replace("__FORCE_POST_SELECT_STATUS_RETVAL__", json.dumps(force_post_select_status_retval))
        .replace(
            "__FORCE_TYPE0_DESCRIPTOR_STATUS_RETVAL__",
            json.dumps(force_type0_descriptor_status_retval),
        )
        .replace(
            "__FORCE_DISPATCH_PROVIDER_ACCEPT__",
            "true" if force_dispatch_provider_accept else "false",
        )
        .replace(
            "__FORCE_DISPATCH_RESULT_METADATA_FALLBACK__",
            "true" if force_dispatch_result_metadata_fallback else "false",
        )
        .replace(
            "__FORCE_POST_DISPATCH_RELEASE_CALLBACK_FALLBACK__",
            "true" if force_post_dispatch_release_callback_fallback else "false",
        )
        .replace(
            "__FORCE_TYPE0_CHILDMINUS1_BYPASS__",
            "true" if force_type0_childminus1_bypass else "false",
        )
        .replace(
            "__FORCE_TYPE0_FIELD18_TO_2__",
            "true" if force_type0_field18_to_2 else "false",
        )
        .replace(
            "__FORCE_TYPE0_RAW_SOURCE_FROM_PTR178__",
            "true" if force_type0_raw_source_from_ptr178 else "false",
        )
        .replace(
            "__FORCE_TYPE0_ZLB_SOURCE_FROM_PTR178__",
            "true" if force_type0_zlb_source_from_ptr178 else "false",
        )
        .replace(
            "__FORCE_TYPE0_REQUESTED_LENGTH_FROM_SOURCE_HEADER__",
            "true" if force_type0_requested_length_from_source_header else "false",
        )
        .replace(
            "__FORCE_TYPE0_SOURCE_OBJECT_FROM_SIDE_SLOTS__",
            "true" if force_type0_source_object_from_side_slots else "false",
        )
        .replace(
            "__FORCE_TYPE0_INNER_SOURCE_FROM_SIDE_WRAPPER__",
            "true" if force_type0_inner_source_from_side_wrapper else "false",
        )
        .replace(
            "__FORCE_TYPE0_PARSER_SINGLE_BYTE_PAYLOAD_TO_1__",
            "true" if force_type0_parser_single_byte_payload_to_1 else "false",
        )
        .replace(
            "__FORCE_QUEUE_HELPER_RESOLVER_SYNTHETIC_SUCCESS__",
            "true" if force_queue_helper_resolver_synthetic_success else "false",
        )
        .replace(
            "__FORCE_QUEUE_HELPER_POST_PARSER_CLEANUP_SUPPRESSION__",
            "true" if force_queue_helper_post_parser_cleanup_suppression else "false",
        )
        .replace(
            "__FORCE_QUEUE_HELPER_RETURN_SLOT_RESTORE__",
            "true" if force_queue_helper_return_slot_restore else "false",
        )
        .replace(
            "__FORCE_TYPE0_HANDLER_RETURN_SLOT_RESTORE__",
            "true" if force_type0_handler_return_slot_restore else "false",
        )
        .replace("__FORCE_RECORD21_ON_OPEN__", "true" if force_record21_on_open else "false")
        .replace("__FORCE_RECORDE_ON_OPEN__", "true" if force_recorde_on_open else "false")
        .replace(
            "__FORCE_RECORDE_ON_DISPATCH_RETURN__",
            "true" if force_recorde_on_dispatch_return else "false",
        )
        .replace(
            "__FORCE_FINALIZE_ON_DISPATCH_RETURN__",
            "true" if force_finalize_on_dispatch_return else "false",
        )
        .replace(
            "__FORCE_RECORDD_CLEAR_ON_DISPATCH_RETURN__",
            "true" if force_recordd_clear_on_dispatch_return else "false",
        )
        .replace(
            "__FORCE_OWNER_STAGE_CLEAR_WHEN_DRAINED__",
            "true" if force_owner_stage_clear_when_drained else "false",
        )
        .replace(
            "__FORCE_RECORD_OPEN_ON_FIELD1C__",
            "true" if force_record_open_on_field1c else "false",
        )
        .replace(
            "__FORCE_SEED_DISPATCH_ON_PTR178__",
            "true" if force_seed_dispatch_on_ptr178 else "false",
        )
        .replace(
            "__FORCE_RECORDD_READY_ON_PTR178__",
            "true" if force_recordd_ready_on_ptr178 else "false",
        )
        .replace(
            "__FORCE_RECORDD_READY_ON_LATCH_CLEAR__",
            "true" if force_recordd_ready_on_latch_clear else "false",
        )
        .replace(
            "__FORCE_RECORDD_READY_ON_CLOSE_SUPPRESSION__",
            "true" if force_recordd_ready_on_close_suppression else "false",
        )
        .replace(
            "__FORCE_SELECTOR_READY_ON_PTR178__",
            "true" if force_selector_ready_on_ptr178 else "false",
        )
        .replace(
            "__FORCE_DIRECT_DISPATCH_ON_STATE1__",
            "true" if force_direct_dispatch_on_state1 else "false",
        )
        .replace(
            "__FORCE_OWNER_STAGE_OPEN_ON_STATE1__",
            "true" if force_owner_stage_open_on_state1 else "false",
        )
        .replace(
            "__FORCE_PREPARED_SELECTOR_READY__",
            "true" if force_prepared_selector_ready else "false",
        )
        .replace(
            "__DEMOTE_HOT_DONEZERO_QUEUED_RECORD__",
            "true" if demote_hot_donezero_queued_record else "false",
        )
        .replace(
            "__FORCE_IDLE_SELECTOR_LATCH_CLEAR__",
            "true" if force_idle_selector_latch_clear else "false",
        )
        .replace(
            "__FORCE_IDLE_SELECTOR_TIMER_OPEN__",
            "true" if force_idle_selector_timer_open else "false",
        )
        .replace(
            "__FORCE_IDLE_SELECTOR_QUEUE_EMPTY__",
            "true" if force_idle_selector_queue_empty else "false",
        )
        .replace(
            "__FORCE_POST_SELECT_FLAG20_ON_BUSY__",
            "true" if force_post_select_flag20_on_busy else "false",
        )
        .replace(
            "__FORCE_POST_SELECT_PUBLICATION_SUCCESS__",
            "true" if force_post_select_publication_success else "false",
        )
        .replace(
            "__SUPPRESS_POST_SELECT_LATCH_CLEAR__",
            "true" if suppress_post_select_latch_clear else "false",
        )
        .replace(
            "__FORCE_RECORDSTATE_FROM_TYPE0__",
            "true" if force_recordstate_from_type0 else "false",
        )
        .replace(
            "__FORCE_TYPE0_PREPARE_BRANCH__",
            "true" if force_type0_prepare_branch else "false",
        )
        .replace(
            "__FORCE_ITEM_PAYLOAD_FROM_PTR178__",
            "true" if force_item_payload_from_ptr178 else "false",
        )
        .replace(
            "__FORCE_TYPE3_FOLLOWON_ON_POST_STATE1__",
            "true" if force_type3_followon_on_post_state1 else "false",
        )
        .replace(
            "__FORCE_FINALIZE_AFTER_TYPE3_ON_POST_STATE1__",
            "true" if force_finalize_after_type3_on_post_state1 else "false",
        )
        .replace(
            "__REENTER_RECORDSTATE_AFTER_TYPE3_ON_POST_STATE1__",
            "true" if reenter_recordstate_after_type3_on_post_state1 else "false",
        )
    )


def archive_output_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-application-resource-gate-{timestamp.strftime('%Y%m%d-%H%M%S')}.jsonl"


def archive_summary_path(output_root: Path, timestamp: datetime) -> Path:
    return output_root / f"947-application-resource-gate-{timestamp.strftime('%Y%m%d-%H%M%S')}.json"


def main() -> int:
    args = parse_args()
    pid = resolve_pid(args)
    args.output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).astimezone()
    archive_path = archive_output_path(args.output_root, timestamp)
    latest_path = args.output_root / "latest-client-only.jsonl"
    archive_summary = archive_summary_path(args.output_root, timestamp)
    latest_summary = args.output_root / "latest-client-only.json"

    session = frida.attach(pid)
    script = session.create_script(
        build_script(
            gate_rva=args.gate_rva,
            record_reset_rva=args.record_reset_rva,
            dispatch_rva=args.dispatch_rva,
            queue_handler_type3_rva=args.queue_handler_type3_rva,
            record_state_rva=args.record_state_rva,
            record_finalize_rva=args.record_finalize_rva,
            queue_handler_type2_rva=args.queue_handler_type2_rva,
            queue_handler_type0_rva=args.queue_handler_type0_rva,
            queue_helper_prepare_rva=args.queue_helper_prepare_rva,
            type0_prepare_status_rva=args.type0_prepare_status_rva,
            type0_descriptor_status_rva=args.type0_descriptor_status_rva,
            type0_source_object_rva=args.type0_source_object_rva,
            type0_prepare_parser_rva=args.type0_prepare_parser_rva,
            queue_loop_item_rva=args.queue_loop_item_rva,
            queue_loop_post_rva=args.queue_loop_post_rva,
            record_open_rva=args.record_open_rva,
            record_close_rva=args.record_close_rva,
            suppress_record_close_call_rvas=args.suppress_record_close_call_rvas,
            idle_selector_rva=args.idle_selector_rva,
            seed_dispatch_rva=args.seed_dispatch_rva,
            idle_selector_queue_check_rva=args.idle_selector_queue_check_rva,
            scheduler_global_rva=args.scheduler_global_rva,
            resource_count=args.resource_count,
            record_stride=args.record_stride,
            force_record21_on_open=args.force_record21_on_open,
            force_recorde_on_open=args.force_recorde_on_open,
            force_recorde_on_dispatch_return=args.force_recorde_on_dispatch_return,
            force_finalize_on_dispatch_return=args.force_finalize_on_dispatch_return,
            force_recordd_clear_on_dispatch_return=args.force_recordd_clear_on_dispatch_return,
            force_owner_stage_clear_when_drained=args.force_owner_stage_clear_when_drained,
            force_record_open_on_field1c=args.force_record_open_on_field1c,
            force_seed_dispatch_on_ptr178=args.force_seed_dispatch_on_ptr178,
            force_recordd_ready_on_ptr178=args.force_recordd_ready_on_ptr178,
            force_recordd_ready_on_latch_clear=args.force_recordd_ready_on_latch_clear,
            force_recordd_ready_on_close_suppression=
            args.force_recordd_ready_on_close_suppression,
            force_selector_ready_on_ptr178=args.force_selector_ready_on_ptr178,
            force_direct_dispatch_on_state1=args.force_direct_dispatch_on_state1,
            force_dispatch_provider_accept=args.force_dispatch_provider_accept,
            force_dispatch_result_metadata_fallback=
            args.force_dispatch_result_metadata_fallback,
            force_post_dispatch_release_callback_fallback=
            args.force_post_dispatch_release_callback_fallback,
            force_owner_stage_open_on_state1=args.force_owner_stage_open_on_state1,
            force_prepared_selector_ready=args.force_prepared_selector_ready,
            demote_hot_donezero_queued_record=args.demote_hot_donezero_queued_record,
            force_idle_selector_latch_clear=args.force_idle_selector_latch_clear,
            force_idle_selector_timer_open=args.force_idle_selector_timer_open,
            force_idle_selector_queue_empty=args.force_idle_selector_queue_empty,
            force_post_select_flag20_on_busy=args.force_post_select_flag20_on_busy,
            force_post_select_status_retval=args.force_post_select_status_retval,
            force_post_select_publication_success=args.force_post_select_publication_success,
            suppress_post_select_latch_clear=args.suppress_post_select_latch_clear,
            force_recordstate_from_type0=args.force_recordstate_from_type0,
            force_type0_prepare_branch=args.force_type0_prepare_branch,
            force_item_payload_from_ptr178=args.force_item_payload_from_ptr178,
            force_type0_descriptor_status_retval=args.force_type0_descriptor_status_retval,
            force_type0_childminus1_bypass=args.force_type0_childminus1_bypass,
            force_type0_field18_to_2=args.force_type0_field18_to_2,
            force_type0_raw_source_from_ptr178=args.force_type0_raw_source_from_ptr178,
            force_type0_zlb_source_from_ptr178=args.force_type0_zlb_source_from_ptr178,
            force_type0_requested_length_from_source_header=
            args.force_type0_requested_length_from_source_header,
            force_type0_source_object_from_side_slots=
            args.force_type0_source_object_from_side_slots,
            force_type0_inner_source_from_side_wrapper=
            args.force_type0_inner_source_from_side_wrapper,
            force_type0_parser_single_byte_payload_to_1=
            args.force_type0_parser_single_byte_payload_to_1,
            force_queue_helper_resolver_synthetic_success=
            args.force_queue_helper_resolver_synthetic_success,
            force_queue_helper_post_parser_cleanup_suppression=
            args.force_queue_helper_post_parser_cleanup_suppression,
            force_queue_helper_return_slot_restore=
            args.force_queue_helper_return_slot_restore,
            force_type0_handler_return_slot_restore=
            args.force_type0_handler_return_slot_restore,
            force_type3_followon_on_post_state1=args.force_type3_followon_on_post_state1,
            force_finalize_after_type3_on_post_state1=
            args.force_finalize_after_type3_on_post_state1,
            reenter_recordstate_after_type3_on_post_state1=
            args.reenter_recordstate_after_type3_on_post_state1,
        )
    )

    with archive_path.open("w", encoding="utf-8") as archive_file, latest_path.open(
        "w", encoding="utf-8"
    ) as latest_file:

        def handle_message(message: dict, _data) -> None:
            if message.get("type") != "send":
                payload = {
                    "event": "frida-message",
                    "messageType": message.get("type"),
                    "payload": message.get("payload"),
                    "stack": message.get("stack"),
                    "description": message.get("description"),
                }
            else:
                payload = message.get("payload")
            if payload is None:
                return
            line = json.dumps(payload, ensure_ascii=True)
            archive_file.write(line + "\n")
            archive_file.flush()
            latest_file.write(line + "\n")
            latest_file.flush()

        script.on("message", handle_message)
        script.load()
        try:
            time.sleep(args.duration_seconds)
            snapshot = None if args.skip_snapshot else script.exports_sync.snapshot()
        finally:
            try:
                script.unload()
            finally:
                session.detach()

    summary_payload = {
        "pid": pid,
        "gateRva": hex(args.gate_rva),
        "dispatchRva": hex(args.dispatch_rva),
        "recordStateRva": hex(args.record_state_rva),
        "recordFinalizeRva": hex(args.record_finalize_rva),
        "idleSelectorRva": hex(args.idle_selector_rva),
        "seedDispatchRva": hex(args.seed_dispatch_rva),
        "queueHandlerType0Rva": hex(args.queue_handler_type0_rva),
        "queueHelperPrepareRva": hex(args.queue_helper_prepare_rva),
        "type0PrepareStatusRva": hex(args.type0_prepare_status_rva),
        "type0DescriptorStatusRva": hex(args.type0_descriptor_status_rva),
        "type0SourceObjectRva": hex(args.type0_source_object_rva),
        "archivePath": str(archive_path),
        "latestPath": str(latest_path),
        "durationSeconds": args.duration_seconds,
        "skipSnapshot": args.skip_snapshot,
        "forceRecord21OnOpen": args.force_record21_on_open,
        "forceRecordEOnOpen": args.force_recorde_on_open,
        "forceRecordEOnDispatchReturn": args.force_recorde_on_dispatch_return,
        "forceFinalizeOnDispatchReturn": args.force_finalize_on_dispatch_return,
        "forceRecordDClearOnDispatchReturn": args.force_recordd_clear_on_dispatch_return,
        "forceOwnerStageClearWhenDrained": args.force_owner_stage_clear_when_drained,
        "forceRecordOpenOnField1c": args.force_record_open_on_field1c,
        "forceSeedDispatchOnPtr178": args.force_seed_dispatch_on_ptr178,
        "forceRecordDReadyOnPtr178": args.force_recordd_ready_on_ptr178,
        "forceRecordDReadyOnLatchClear": args.force_recordd_ready_on_latch_clear,
        "forceRecordDReadyOnCloseSuppression": args.force_recordd_ready_on_close_suppression,
        "forceSelectorReadyOnPtr178": args.force_selector_ready_on_ptr178,
        "forceDirectDispatchOnState1": args.force_direct_dispatch_on_state1,
        "forceDispatchProviderAccept": args.force_dispatch_provider_accept,
        "forceDispatchResultMetadataFallback":
        args.force_dispatch_result_metadata_fallback,
        "forcePostDispatchReleaseCallbackFallback":
        args.force_post_dispatch_release_callback_fallback,
        "suppressRecordCloseCallRvas":
        [hex(value) for value in args.suppress_record_close_call_rvas],
        "forceItemPayloadFromPtr178": args.force_item_payload_from_ptr178,
        "forceType0DescriptorStatusRetval": args.force_type0_descriptor_status_retval,
        "forceType0ChildMinus1Bypass": args.force_type0_childminus1_bypass,
        "forceType0Field18To2": args.force_type0_field18_to_2,
        "forceType0RawSourceFromPtr178": args.force_type0_raw_source_from_ptr178,
        "forceType0ZlbSourceFromPtr178": args.force_type0_zlb_source_from_ptr178,
        "forceType0RequestedLengthFromSourceHeader":
        args.force_type0_requested_length_from_source_header,
        "forceType0SourceObjectFromSideSlots":
        args.force_type0_source_object_from_side_slots,
        "forceType0InnerSourceFromSideWrapper":
        args.force_type0_inner_source_from_side_wrapper,
        "forceQueueHelperResolverSyntheticSuccess":
        args.force_queue_helper_resolver_synthetic_success,
        "forceType3FollowonOnPostState1": args.force_type3_followon_on_post_state1,
        "forceFinalizeAfterType3OnPostState1":
        args.force_finalize_after_type3_on_post_state1,
        "reenterRecordStateAfterType3OnPostState1":
        args.reenter_recordstate_after_type3_on_post_state1,
        "snapshot": snapshot,
    }
    archive_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    latest_summary.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")
    print(json.dumps({"archivePath": str(archive_path), "summaryPath": str(archive_summary), "pid": pid}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
