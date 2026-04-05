from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import threading
from urllib.parse import parse_qs, urlparse

import frida

try:
    from tools.launch_runescape_wrapper_rewrite import (
        build_connect_redirects,
        is_secure_retail_startup_contract,
        normalize_jump_bypass_specs,
        normalize_patch_offsets,
        patch_remote_embedded_rsa_moduli,
        patch_remote_inline_offsets,
        patch_remote_jump_bypass_blocks,
        patch_remote_null_read_offsets,
        query_process_command_line,
        query_process_path,
    )
    from tools.trace_rs2client_live import build_hook_script as build_startup_hook_script
    from tools.trace_rs2client_live import normalize_payload as normalize_startup_hook_payload
    from tools.trace_947_application_resource_gate import (
        DEFAULT_DISPATCH_RVA as DEFAULT_RESOURCE_GATE_DISPATCH_RVA,
        DEFAULT_GATE_RVA as DEFAULT_RESOURCE_GATE_GATE_RVA,
        DEFAULT_IDLE_SELECTOR_RVA as DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_RVA,
        DEFAULT_IDLE_SELECTOR_QUEUE_CHECK_RVA as DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_QUEUE_CHECK_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE0_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE0_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE2_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE2_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE3_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE3_RVA,
        DEFAULT_QUEUE_HELPER_PREPARE_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HELPER_PREPARE_RVA,
        DEFAULT_QUEUE_LOOP_ITEM_RVA as DEFAULT_RESOURCE_GATE_QUEUE_LOOP_ITEM_RVA,
        DEFAULT_QUEUE_LOOP_POST_RVA as DEFAULT_RESOURCE_GATE_QUEUE_LOOP_POST_RVA,
        DEFAULT_RECORD_CLOSE_RVA as DEFAULT_RESOURCE_GATE_RECORD_CLOSE_RVA,
        DEFAULT_RECORD_FINALIZE_RVA as DEFAULT_RESOURCE_GATE_RECORD_FINALIZE_RVA,
        DEFAULT_RECORD_OPEN_RVA as DEFAULT_RESOURCE_GATE_RECORD_OPEN_RVA,
        DEFAULT_RECORD_RESET_RVA as DEFAULT_RESOURCE_GATE_RECORD_RESET_RVA,
        DEFAULT_RECORD_STATE_RVA as DEFAULT_RESOURCE_GATE_RECORD_STATE_RVA,
        DEFAULT_RECORD_STRIDE as DEFAULT_RESOURCE_GATE_RECORD_STRIDE,
        DEFAULT_RESOURCE_COUNT as DEFAULT_RESOURCE_GATE_RESOURCE_COUNT,
        DEFAULT_SCHEDULER_GLOBAL_RVA as DEFAULT_RESOURCE_GATE_SCHEDULER_GLOBAL_RVA,
        DEFAULT_SEED_DISPATCH_RVA as DEFAULT_RESOURCE_GATE_SEED_DISPATCH_RVA,
        DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA as DEFAULT_RESOURCE_GATE_TYPE0_DESCRIPTOR_STATUS_RVA,
        DEFAULT_TYPE0_PREPARE_PARSER_RVA as DEFAULT_RESOURCE_GATE_TYPE0_PREPARE_PARSER_RVA,
        DEFAULT_TYPE0_PREPARE_STATUS_RVA as DEFAULT_RESOURCE_GATE_TYPE0_PREPARE_STATUS_RVA,
        DEFAULT_TYPE0_SOURCE_OBJECT_RVA as DEFAULT_RESOURCE_GATE_TYPE0_SOURCE_OBJECT_RVA,
        archive_output_path as resource_gate_archive_output_path,
        archive_summary_path as resource_gate_archive_summary_path,
        build_script as build_resource_gate_script,
    )
    from tools.trace_947_prelogin_producer_path import (
        archive_output_path as producer_archive_output_path,
        archive_summary_path as producer_archive_summary_path,
        build_script as build_prelogin_producer_script,
        build_summary as build_prelogin_producer_summary,
    )
    from tools.trace_947_loading_state_builder import (
        DEFAULT_LOADING_CALLSITE_RVA as DEFAULT_LOADING_STATE_CALLSITE_RVA,
        DEFAULT_LOADING_GATE_RVA as DEFAULT_LOADING_STATE_GATE_RVA,
        DEFAULT_RECORD_STRIDE as DEFAULT_LOADING_STATE_RECORD_STRIDE,
        DEFAULT_STATE_COPY_RVA as DEFAULT_LOADING_STATE_COPY_RVA,
        archive_output_path as loading_state_archive_output_path,
        archive_summary_path as loading_state_archive_summary_path,
        build_script as build_loading_state_builder_script,
    )
except ImportError:
    from launch_runescape_wrapper_rewrite import (  # type: ignore
        build_connect_redirects,
        is_secure_retail_startup_contract,
        normalize_jump_bypass_specs,
        normalize_patch_offsets,
        patch_remote_embedded_rsa_moduli,
        patch_remote_inline_offsets,
        patch_remote_jump_bypass_blocks,
        patch_remote_null_read_offsets,
        query_process_command_line,
        query_process_path,
    )
    from trace_rs2client_live import build_hook_script as build_startup_hook_script  # type: ignore
    from trace_rs2client_live import normalize_payload as normalize_startup_hook_payload  # type: ignore
    from trace_947_application_resource_gate import (  # type: ignore
        DEFAULT_DISPATCH_RVA as DEFAULT_RESOURCE_GATE_DISPATCH_RVA,
        DEFAULT_GATE_RVA as DEFAULT_RESOURCE_GATE_GATE_RVA,
        DEFAULT_IDLE_SELECTOR_RVA as DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_RVA,
        DEFAULT_IDLE_SELECTOR_QUEUE_CHECK_RVA as DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_QUEUE_CHECK_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE0_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE0_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE2_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE2_RVA,
        DEFAULT_QUEUE_HANDLER_TYPE3_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE3_RVA,
        DEFAULT_QUEUE_HELPER_PREPARE_RVA as DEFAULT_RESOURCE_GATE_QUEUE_HELPER_PREPARE_RVA,
        DEFAULT_QUEUE_LOOP_ITEM_RVA as DEFAULT_RESOURCE_GATE_QUEUE_LOOP_ITEM_RVA,
        DEFAULT_QUEUE_LOOP_POST_RVA as DEFAULT_RESOURCE_GATE_QUEUE_LOOP_POST_RVA,
        DEFAULT_RECORD_CLOSE_RVA as DEFAULT_RESOURCE_GATE_RECORD_CLOSE_RVA,
        DEFAULT_RECORD_FINALIZE_RVA as DEFAULT_RESOURCE_GATE_RECORD_FINALIZE_RVA,
        DEFAULT_RECORD_OPEN_RVA as DEFAULT_RESOURCE_GATE_RECORD_OPEN_RVA,
        DEFAULT_RECORD_RESET_RVA as DEFAULT_RESOURCE_GATE_RECORD_RESET_RVA,
        DEFAULT_RECORD_STATE_RVA as DEFAULT_RESOURCE_GATE_RECORD_STATE_RVA,
        DEFAULT_RECORD_STRIDE as DEFAULT_RESOURCE_GATE_RECORD_STRIDE,
        DEFAULT_RESOURCE_COUNT as DEFAULT_RESOURCE_GATE_RESOURCE_COUNT,
        DEFAULT_SCHEDULER_GLOBAL_RVA as DEFAULT_RESOURCE_GATE_SCHEDULER_GLOBAL_RVA,
        DEFAULT_SEED_DISPATCH_RVA as DEFAULT_RESOURCE_GATE_SEED_DISPATCH_RVA,
        DEFAULT_TYPE0_DESCRIPTOR_STATUS_RVA as DEFAULT_RESOURCE_GATE_TYPE0_DESCRIPTOR_STATUS_RVA,
        DEFAULT_TYPE0_PREPARE_PARSER_RVA as DEFAULT_RESOURCE_GATE_TYPE0_PREPARE_PARSER_RVA,
        DEFAULT_TYPE0_PREPARE_STATUS_RVA as DEFAULT_RESOURCE_GATE_TYPE0_PREPARE_STATUS_RVA,
        DEFAULT_TYPE0_SOURCE_OBJECT_RVA as DEFAULT_RESOURCE_GATE_TYPE0_SOURCE_OBJECT_RVA,
        archive_output_path as resource_gate_archive_output_path,
        archive_summary_path as resource_gate_archive_summary_path,
        build_script as build_resource_gate_script,
    )
    from trace_947_prelogin_producer_path import (  # type: ignore
        archive_output_path as producer_archive_output_path,
        archive_summary_path as producer_archive_summary_path,
        build_script as build_prelogin_producer_script,
        build_summary as build_prelogin_producer_summary,
    )
    from trace_947_loading_state_builder import (  # type: ignore
        DEFAULT_LOADING_CALLSITE_RVA as DEFAULT_LOADING_STATE_CALLSITE_RVA,
        DEFAULT_LOADING_GATE_RVA as DEFAULT_LOADING_STATE_GATE_RVA,
        DEFAULT_RECORD_STRIDE as DEFAULT_LOADING_STATE_RECORD_STRIDE,
        DEFAULT_STATE_COPY_RVA as DEFAULT_LOADING_STATE_COPY_RVA,
        archive_output_path as loading_state_archive_output_path,
        archive_summary_path as loading_state_archive_summary_path,
        build_script as build_loading_state_builder_script,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch a local rs2client.exe directly, apply the same in-memory guard patches used on the "
            "947 wrapper child path, and report whether the process survives startup."
        )
    )
    parser.add_argument("--client-exe", required=True, help="Path to the local rs2client.exe")
    parser.add_argument("--working-dir", required=True, help="Working directory for the client process")
    parser.add_argument(
        "--client-arg",
        action="append",
        default=[],
        help="Repeatable client argument to append after the executable path",
    )
    parser.add_argument("--summary-output", required=True, help="Path to write the JSON summary")
    parser.add_argument("--trace-output", help="Optional JSONL trace output")
    parser.add_argument(
        "--startup-hook-output",
        help="Optional JSONL file for a pre-resume Frida startup hook on the direct client",
    )
    parser.add_argument(
        "--startup-hook-verbose",
        action="store_true",
        help="Emit higher-volume startup hook events when --startup-hook-output is enabled",
    )
    parser.add_argument("--rsa-config", help="Optional rsa.toml to patch embedded moduli in memory")
    parser.add_argument(
        "--js5-rsa-source-exe",
        help=(
            "Optional rs2client.exe path whose embedded 4096-bit JS5 modulus should replace "
            "the launched client's current JS5 modulus instead of using rsa.toml."
        ),
    )
    parser.add_argument(
        "--patch-inline-offset",
        action="append",
        default=[],
        help="Repeatable inline patch offset (hex or decimal)",
    )
    parser.add_argument(
        "--patch-null-read-offset",
        action="append",
        default=[],
        help="Repeatable null-read patch offset (hex or decimal)",
    )
    parser.add_argument(
        "--patch-jump-bypass",
        action="append",
        default=[],
        help="Repeatable source:target jump-bypass patch (hex or decimal)",
    )
    parser.add_argument(
        "--resolve-redirect",
        action="append",
        default=[],
        help="Repeatable host=target redirect applied inside GetAddrInfo* before resume",
    )
    parser.add_argument(
        "--patch-delay-seconds",
        type=float,
        default=0.0,
        help="Optional delay after spawn before applying patches",
    )
    parser.add_argument(
        "--monitor-seconds",
        type=float,
        default=15.0,
        help="How long to wait before deciding whether the process survived startup",
    )
    parser.add_argument(
        "--resource-gate-output-root",
        help="Optional directory for pre-resume 947 application-resource gate JSONL/summary artifacts",
    )
    parser.add_argument(
        "--producer-output-root",
        help="Optional directory for pre-resume 947 producer-path JSONL/summary artifacts",
    )
    parser.add_argument(
        "--loading-state-output-root",
        help="Optional directory for pre-resume 947 loading-state builder JSONL/summary artifacts",
    )
    parser.add_argument(
        "--loading-state-state-copy-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_LOADING_STATE_COPY_RVA,
        help=f"947 loading-state copy RVA (default: 0x{DEFAULT_LOADING_STATE_COPY_RVA:x})",
    )
    parser.add_argument(
        "--loading-state-gate-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_LOADING_STATE_GATE_RVA,
        help=f"947 loading-state gate RVA (default: 0x{DEFAULT_LOADING_STATE_GATE_RVA:x})",
    )
    parser.add_argument(
        "--loading-state-callsite-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_LOADING_STATE_CALLSITE_RVA,
        help=f"947 loading-state pre-callsite RVA (default: 0x{DEFAULT_LOADING_STATE_CALLSITE_RVA:x})",
    )
    parser.add_argument(
        "--loading-state-record-stride",
        type=lambda value: int(value, 0),
        default=DEFAULT_LOADING_STATE_RECORD_STRIDE,
        help=f"947 loading-state record stride (default: 0x{DEFAULT_LOADING_STATE_RECORD_STRIDE:x})",
    )
    parser.add_argument(
        "--resource-gate-gate-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_GATE_RVA,
        help=f"Application-resource gate RVA (default: 0x{DEFAULT_RESOURCE_GATE_GATE_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_DISPATCH_RVA,
        help=f"Application-resource dispatch RVA (default: 0x{DEFAULT_RESOURCE_GATE_DISPATCH_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-record-state-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_RECORD_STATE_RVA,
        help=f"Application-resource record-state RVA (default: 0x{DEFAULT_RESOURCE_GATE_RECORD_STATE_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-record-reset-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_RECORD_RESET_RVA,
        help=f"Application-resource record-reset RVA (default: 0x{DEFAULT_RESOURCE_GATE_RECORD_RESET_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-record-finalize-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_RECORD_FINALIZE_RVA,
        help=f"Application-resource record-finalize RVA (default: 0x{DEFAULT_RESOURCE_GATE_RECORD_FINALIZE_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-queue-handler-type3-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE3_RVA,
        help=f"Application-resource queue type-3 handler RVA (default: 0x{DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE3_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-queue-handler-type2-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE2_RVA,
        help=f"Application-resource queue type-2 handler RVA (default: 0x{DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE2_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-queue-handler-type0-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE0_RVA,
        help=f"Application-resource queue type-0 handler RVA (default: 0x{DEFAULT_RESOURCE_GATE_QUEUE_HANDLER_TYPE0_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-queue-helper-prepare-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_QUEUE_HELPER_PREPARE_RVA,
        help=f"Application-resource queue helper prepare RVA (default: 0x{DEFAULT_RESOURCE_GATE_QUEUE_HELPER_PREPARE_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-queue-loop-item-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_QUEUE_LOOP_ITEM_RVA,
        help=f"Application-resource queue loop item RVA (default: 0x{DEFAULT_RESOURCE_GATE_QUEUE_LOOP_ITEM_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-queue-loop-post-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_QUEUE_LOOP_POST_RVA,
        help=f"Application-resource queue loop post RVA (default: 0x{DEFAULT_RESOURCE_GATE_QUEUE_LOOP_POST_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-record-open-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_RECORD_OPEN_RVA,
        help=f"Application-resource record-open RVA (default: 0x{DEFAULT_RESOURCE_GATE_RECORD_OPEN_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-record-close-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_RECORD_CLOSE_RVA,
        help=f"Application-resource record-close RVA (default: 0x{DEFAULT_RESOURCE_GATE_RECORD_CLOSE_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-seed-dispatch-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_SEED_DISPATCH_RVA,
        help=f"Application-resource seed-dispatch RVA (default: 0x{DEFAULT_RESOURCE_GATE_SEED_DISPATCH_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-idle-selector-queue-check-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_QUEUE_CHECK_RVA,
        help=f"Application-resource idle-selector queue-check RVA (default: 0x{DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_QUEUE_CHECK_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-scheduler-global-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_SCHEDULER_GLOBAL_RVA,
        help=f"Application-resource scheduler global RVA (default: 0x{DEFAULT_RESOURCE_GATE_SCHEDULER_GLOBAL_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-idle-selector-rva",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_RVA,
        help=f"Application-resource idle-selector RVA (default: 0x{DEFAULT_RESOURCE_GATE_IDLE_SELECTOR_RVA:x})",
    )
    parser.add_argument(
        "--resource-gate-resource-count",
        type=int,
        default=DEFAULT_RESOURCE_GATE_RESOURCE_COUNT,
        help=f"Application-resource count (default: {DEFAULT_RESOURCE_GATE_RESOURCE_COUNT})",
    )
    parser.add_argument(
        "--resource-gate-record-stride",
        type=lambda value: int(value, 0),
        default=DEFAULT_RESOURCE_GATE_RECORD_STRIDE,
        help=f"Application-resource record stride (default: 0x{DEFAULT_RESOURCE_GATE_RECORD_STRIDE:x})",
    )
    parser.add_argument(
        "--resource-gate-force-record21-on-open",
        action="store_true",
        help="Smoke test: force record+0x21 when record-state opens ptr1c8",
    )
    parser.add_argument(
        "--resource-gate-force-recorde-on-open",
        action="store_true",
        help="Smoke test: force record+0x0e when record-state opens ptr1c8",
    )
    parser.add_argument(
        "--resource-gate-force-recorde-on-dispatch-return",
        action="store_true",
        help="Smoke test: force record+0x0e on dispatch return when ptr1c8 exists and +0x0e is still unset",
    )
    parser.add_argument(
        "--resource-gate-force-recordd-clear-on-dispatch-return",
        action="store_true",
        help="Smoke test: clear record+0x0d on dispatch return once the record is complete",
    )
    parser.add_argument(
        "--resource-gate-force-owner-stage-clear-when-drained",
        action="store_true",
        help="Smoke test: clear owner+0x11b58, owner+0x11d49, and owner+0x11d4a once active/inflight sets are drained",
    )
    parser.add_argument(
        "--resource-gate-force-seed-dispatch-on-ptr178",
        action="store_true",
        help="Smoke test: invoke the seed-dispatch handler for ptr178-backed records",
    )
    parser.add_argument(
        "--resource-gate-force-direct-dispatch-on-state1",
        action="store_true",
        help="Smoke test: invoke direct dispatch for state-1 records",
    )
    parser.add_argument(
        "--resource-gate-force-owner-stage-open-on-state1",
        action="store_true",
        help="Smoke test: reopen owner stage when state-1 records exist",
    )
    parser.add_argument(
        "--resource-gate-force-prepared-selector-ready",
        action="store_true",
        help="Smoke test: satisfy the selector-ready predicate for prepared records",
    )
    parser.add_argument(
        "--resource-gate-force-idle-selector-latch-clear",
        action="store_true",
        help="Smoke test: clear the idle-selector latch so the selector can re-run",
    )
    parser.add_argument(
        "--resource-gate-force-idle-selector-timer-open",
        action="store_true",
        help="Smoke test: reopen the idle-selector timer gate",
    )
    parser.add_argument(
        "--resource-gate-force-idle-selector-queue-empty",
        action="store_true",
        help="Smoke test: force the idle-selector queue-empty predicate",
    )
    parser.add_argument(
        "--resource-gate-force-post-select-flag20-on-busy",
        action="store_true",
        help="Smoke test: force record+0x20 after post-select on busy records",
    )
    parser.add_argument(
        "--resource-gate-force-recordstate-from-type0",
        action="store_true",
        help="Smoke test: invoke record-state directly from the queue type-0 path",
    )
    parser.add_argument(
        "--resource-gate-force-item-payload-from-ptr178",
        action="store_true",
        help="Smoke test: source queue payloads from ptr178-backed records",
    )
    parser.add_argument(
        "--resource-gate-force-type3-followon-on-post-state1",
        action="store_true",
        help="Smoke test: invoke the type-3 follow-on path after post state-1 handling",
    )
    parser.add_argument(
        "--resource-gate-force-finalize-after-type3-on-post-state1",
        action="store_true",
        help="Smoke test: invoke record finalize after the type-3 follow-on on post state-1 handling",
    )
    return parser.parse_args(argv)


def parse_resolve_redirect_specs(values: list[str] | None) -> dict[str, str]:
    redirects: dict[str, str] = {}
    for raw_value in values or []:
        text = str(raw_value or "").strip()
        if not text or "=" not in text:
            raise ValueError(f"Invalid resolve redirect spec: {raw_value!r}")
        host, target = text.split("=", 1)
        normalized_host = host.strip().lower()
        normalized_target = target.strip()
        if not normalized_host or not normalized_target:
            raise ValueError(f"Invalid resolve redirect spec: {raw_value!r}")
        redirects[normalized_host] = normalized_target
    return redirects


def uses_secure_retail_startup_contract(argv_values: list[str] | None) -> bool:
    for raw_value in argv_values or []:
        value = str(raw_value or "").strip()
        if value and is_secure_retail_startup_contract(value):
            return True
    return False


def _write_trace(handle, action: str, **payload: Any) -> None:
    if handle is None:
        return
    event = {"timestamp": round(time.time(), 6), "action": action, **payload}
    handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
    handle.flush()


def build_summary(
    *,
    client_exe: Path,
    working_dir: Path,
    argv_list: list[str],
    launch_mode: str,
    monitor_seconds: float,
    patch_delay_seconds: float,
    inline_patch_offsets: list[int],
    inline_patch_results: list[dict[str, Any]],
    null_patch_offsets: list[int],
    null_patch_results: list[dict[str, Any]],
    jump_bypass_specs: list[tuple[int, int]],
    jump_patch_results: list[dict[str, Any]],
    rsa_config_path: Path | None,
    rsa_patch_results: Any,
    resolve_redirects: dict[str, str],
    connect_redirects: dict[str, dict[str, Any]],
    startup_hook_output: Path | None,
    startup_hook_verbose: bool,
    trace_output: Path | None,
    process_pid: int,
    exit_code: int | None,
    summary_stage: str,
) -> dict[str, Any]:
    live_process_path = query_process_path(process_pid)
    live_command_line = query_process_command_line(process_pid)
    alive = exit_code is None and (live_process_path is not None or live_command_line is not None)
    return {
        "pid": process_pid,
        "clientExe": str(client_exe),
        "workingDir": str(working_dir),
        "argv": argv_list,
        "launchMode": launch_mode,
        "monitorSeconds": monitor_seconds,
        "patchDelaySeconds": patch_delay_seconds,
        "inlinePatchOffsets": [f"0x{offset:x}" for offset in inline_patch_offsets],
        "inlinePatchResults": inline_patch_results,
        "nullReadPatchOffsets": [f"0x{offset:x}" for offset in null_patch_offsets],
        "nullReadPatchResults": null_patch_results,
        "jumpBypassSpecs": [
            {"sourceOffset": f"0x{source:x}", "targetOffset": f"0x{target:x}"}
            for source, target in jump_bypass_specs
        ],
        "jumpBypassResults": jump_patch_results,
        "rsaConfigPath": str(rsa_config_path) if rsa_config_path is not None else None,
        "rsaPatchResults": rsa_patch_results,
        "resolveRedirects": resolve_redirects,
        "connectRedirects": connect_redirects,
        "startupHookOutput": str(startup_hook_output) if startup_hook_output is not None else None,
        "startupHookVerbose": startup_hook_verbose,
        "summaryStage": summary_stage,
        "processAlive": alive,
        "exitCode": exit_code,
        "liveProcessPath": live_process_path,
        "liveCommandLine": live_command_line,
        "traceOutput": str(trace_output) if trace_output is not None else None,
    }


def write_summary_output(summary_output: Path, summary: dict[str, Any]) -> None:
    temp_output = summary_output.with_name(summary_output.name + ".tmp")
    temp_output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    temp_output.replace(summary_output)


def infer_client_variant(client_exe: Path) -> str:
    normalized = client_exe.parent.name.strip().lower()
    if normalized in {"original", "patched", "compressed"}:
        return normalized
    return ""


def extract_startup_contract_hint(
    client_exe: Path,
    client_args: list[str],
    process_pid: int | None = None,
) -> dict[str, Any]:
    config_url = next(
        (
            value
            for value in client_args
            if value.startswith("http://") or value.startswith("https://")
        ),
        "",
    )
    query = parse_qs(urlparse(config_url).query) if config_url else {}
    requested_source = (
        query.get("downloadMetadataSource", [""])[0].strip().lower()
        if query
        else ""
    )
    if requested_source not in {"original", "patched", "compressed", "live"}:
        requested_source = infer_client_variant(client_exe)
    hint = {
        "timestampUtc": datetime.now(timezone.utc).isoformat(),
        "clientExe": str(client_exe),
        "clientVariant": infer_client_variant(client_exe),
        "configUrl": config_url,
        "downloadMetadataSource": requested_source,
    }
    if process_pid is not None:
        hint["pid"] = int(process_pid)
    return hint


def write_startup_contract_hint(summary_output: Path, hint: dict[str, Any]) -> Path:
    hint_output = summary_output.parent / "latest-startup-contract.json"
    write_summary_output(hint_output, hint)
    return hint_output


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client_exe = Path(args.client_exe)
    working_dir = Path(args.working_dir)
    summary_output = Path(args.summary_output)
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    trace_output = Path(args.trace_output) if args.trace_output else None
    startup_hook_output = Path(args.startup_hook_output) if args.startup_hook_output else None
    resource_gate_output_root = Path(args.resource_gate_output_root) if args.resource_gate_output_root else None
    producer_output_root = Path(args.producer_output_root) if args.producer_output_root else None
    loading_state_output_root = (
        Path(args.loading_state_output_root) if args.loading_state_output_root else None
    )
    if trace_output is not None:
        trace_output.parent.mkdir(parents=True, exist_ok=True)
    if startup_hook_output is not None:
        startup_hook_output.parent.mkdir(parents=True, exist_ok=True)
    if resource_gate_output_root is not None:
        resource_gate_output_root.mkdir(parents=True, exist_ok=True)
    if producer_output_root is not None:
        producer_output_root.mkdir(parents=True, exist_ok=True)
    if loading_state_output_root is not None:
        loading_state_output_root.mkdir(parents=True, exist_ok=True)

    inline_patch_offsets = normalize_patch_offsets(args.patch_inline_offset)
    null_patch_offsets = normalize_patch_offsets(args.patch_null_read_offset)
    jump_bypass_specs = normalize_jump_bypass_specs(args.patch_jump_bypass)
    rsa_config_path = Path(args.rsa_config) if args.rsa_config else None
    js5_rsa_source_exe = Path(args.js5_rsa_source_exe) if args.js5_rsa_source_exe else None
    resolve_redirects = parse_resolve_redirect_specs(args.resolve_redirect)
    connect_redirects = (
        {}
        if uses_secure_retail_startup_contract(args.client_arg)
        else build_connect_redirects(resolve_redirects)
    )

    if not client_exe.exists():
        raise FileNotFoundError(f"Client executable not found: {client_exe}")
    if not working_dir.exists():
        raise FileNotFoundError(f"Working directory not found: {working_dir}")

    trace_handle = trace_output.open("w", encoding="utf-8") if trace_output is not None else None
    startup_hook_handle = startup_hook_output.open("w", encoding="utf-8") if startup_hook_output is not None else None
    resource_gate_timestamp = datetime.now(timezone.utc).astimezone()
    resource_gate_archive_path = (
        resource_gate_archive_output_path(resource_gate_output_root, resource_gate_timestamp)
        if resource_gate_output_root is not None
        else None
    )
    resource_gate_latest_path = (
        resource_gate_output_root / "latest-client-only.jsonl"
        if resource_gate_output_root is not None
        else None
    )
    resource_gate_archive_summary_output_path = (
        resource_gate_archive_summary_path(resource_gate_output_root, resource_gate_timestamp)
        if resource_gate_output_root is not None
        else None
    )
    resource_gate_latest_summary_output_path = (
        resource_gate_output_root / "latest-client-only.json"
        if resource_gate_output_root is not None
        else None
    )
    resource_gate_archive_handle = (
        resource_gate_archive_path.open("w", encoding="utf-8")
        if resource_gate_archive_path is not None
        else None
    )
    resource_gate_latest_handle = (
        resource_gate_latest_path.open("w", encoding="utf-8")
        if resource_gate_latest_path is not None
        else None
    )
    producer_timestamp = datetime.now(timezone.utc).astimezone()
    producer_archive_path = (
        producer_archive_output_path(producer_output_root, producer_timestamp)
        if producer_output_root is not None
        else None
    )
    producer_latest_path = (
        producer_output_root / "latest-client-only.jsonl"
        if producer_output_root is not None
        else None
    )
    producer_archive_summary_output_path = (
        producer_archive_summary_path(producer_output_root, producer_timestamp)
        if producer_output_root is not None
        else None
    )
    producer_latest_summary_output_path = (
        producer_output_root / "latest-client-only.json"
        if producer_output_root is not None
        else None
    )
    producer_archive_handle = (
        producer_archive_path.open("w", encoding="utf-8")
        if producer_archive_path is not None
        else None
    )
    producer_latest_handle = (
        producer_latest_path.open("w", encoding="utf-8")
        if producer_latest_path is not None
        else None
    )
    loading_state_timestamp = datetime.now(timezone.utc).astimezone()
    loading_state_archive_path = (
        loading_state_archive_output_path(loading_state_output_root, loading_state_timestamp)
        if loading_state_output_root is not None
        else None
    )
    loading_state_latest_path = (
        loading_state_output_root / "latest-client-only.jsonl"
        if loading_state_output_root is not None
        else None
    )
    loading_state_archive_summary_output_path = (
        loading_state_archive_summary_path(loading_state_output_root, loading_state_timestamp)
        if loading_state_output_root is not None
        else None
    )
    loading_state_latest_summary_output_path = (
        loading_state_output_root / "latest-client-only.json"
        if loading_state_output_root is not None
        else None
    )
    loading_state_archive_handle = (
        loading_state_archive_path.open("w", encoding="utf-8")
        if loading_state_archive_path is not None
        else None
    )
    loading_state_latest_handle = (
        loading_state_latest_path.open("w", encoding="utf-8")
        if loading_state_latest_path is not None
        else None
    )
    try:
        argv_list = [str(client_exe), *args.client_arg]
        process = None
        process_pid: int
        launch_mode = "subprocess"
        startup_session = None
        startup_script = None
        resource_gate_script = None
        producer_script = None
        loading_state_script = None
        startup_stop = threading.Event()

        def write_startup_event(event: dict[str, Any]) -> None:
            if startup_hook_handle is None:
                return
            startup_hook_handle.write(json.dumps(event, sort_keys=True, default=str) + "\n")
            startup_hook_handle.flush()

        def write_resource_gate_event(event: dict[str, Any]) -> None:
            line = json.dumps(event, sort_keys=True, default=str)
            if resource_gate_archive_handle is not None:
                resource_gate_archive_handle.write(line + "\n")
                resource_gate_archive_handle.flush()
            if resource_gate_latest_handle is not None:
                resource_gate_latest_handle.write(line + "\n")
                resource_gate_latest_handle.flush()

        def write_producer_event(event: dict[str, Any]) -> None:
            line = json.dumps(event, sort_keys=True, default=str)
            if producer_archive_handle is not None:
                producer_archive_handle.write(line + "\n")
                producer_archive_handle.flush()
            if producer_latest_handle is not None:
                producer_latest_handle.write(line + "\n")
                producer_latest_handle.flush()

        def write_loading_state_event(event: dict[str, Any]) -> None:
            line = json.dumps(event, sort_keys=True, default=str)
            if loading_state_archive_handle is not None:
                loading_state_archive_handle.write(line + "\n")
                loading_state_archive_handle.flush()
            if loading_state_latest_handle is not None:
                loading_state_latest_handle.write(line + "\n")
                loading_state_latest_handle.flush()

        use_spawn_session = (
            startup_hook_output is not None
            or bool(resolve_redirects)
            or resource_gate_output_root is not None
            or producer_output_root is not None
            or loading_state_output_root is not None
        )
        if use_spawn_session:
            device = frida.get_local_device()
            process_pid = int(device.spawn(argv_list, cwd=str(working_dir)))
            launch_mode = "frida-spawn"
            _write_trace(trace_handle, "spawned", pid=process_pid, argv=argv_list, workingDir=str(working_dir), launchMode=launch_mode)
            startup_session = device.attach(process_pid)

            def on_startup_message(message: dict[str, Any], _data: Any) -> None:
                if message.get("type") == "send":
                    payload = message.get("payload", {})
                    if isinstance(payload, dict):
                        normalized = normalize_startup_hook_payload(payload)
                        normalized.setdefault("pid", process_pid)
                        write_startup_event(normalized)
                    else:
                        write_startup_event(
                            {
                                "timestamp": round(time.time(), 6),
                                "category": "client.unknown",
                                "action": "message",
                                "pid": process_pid,
                                "payload": payload,
                            }
                        )
                    return

                write_startup_event(
                    {
                        "timestamp": round(time.time(), 6),
                        "category": "client.unknown",
                        "action": "frida-message",
                        "pid": process_pid,
                        "message": message,
                    }
                )

            def on_startup_detached(reason: str, crash: Any) -> None:
                event = {
                    "timestamp": round(time.time(), 6),
                    "category": "client.lifecycle",
                    "action": "detached",
                    "pid": process_pid,
                    "reason": reason,
                }
                if crash is not None:
                    event["crash"] = crash
                write_startup_event(event)
                startup_stop.set()

            startup_script = startup_session.create_script(
                build_startup_hook_script(
                    args.startup_hook_verbose,
                    resolve_redirects=resolve_redirects,
                    connect_redirects=connect_redirects,
                )
            )
            startup_script.on("message", on_startup_message)
            startup_session.on("detached", on_startup_detached)
            startup_script.load()
            pre_resume_event = {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "pre-resume-attached",
                "pid": process_pid,
                "verbose": bool(args.startup_hook_verbose),
                "resolveRedirects": resolve_redirects,
                "connectRedirects": connect_redirects,
            }
            write_startup_event(pre_resume_event)
            _write_trace(
                trace_handle,
                "pre-resume-attached",
                pid=process_pid,
                resolveRedirects=resolve_redirects,
                connectRedirects=connect_redirects,
            )
            if resource_gate_output_root is not None:
                def on_resource_gate_message(message: dict[str, Any], _data: Any) -> None:
                    if message.get("type") == "send":
                        payload = message.get("payload")
                        if isinstance(payload, dict):
                            write_resource_gate_event(payload)
                            return
                    write_resource_gate_event(
                        {
                            "event": "frida-message",
                            "messageType": message.get("type"),
                            "payload": message.get("payload"),
                            "stack": message.get("stack"),
                            "description": message.get("description"),
                        }
                    )

                resource_gate_script = startup_session.create_script(
                    build_resource_gate_script(
                        gate_rva=args.resource_gate_gate_rva,
                        record_reset_rva=args.resource_gate_record_reset_rva,
                        dispatch_rva=args.resource_gate_dispatch_rva,
                        queue_handler_type3_rva=args.resource_gate_queue_handler_type3_rva,
                        record_state_rva=args.resource_gate_record_state_rva,
                        record_finalize_rva=args.resource_gate_record_finalize_rva,
                        queue_handler_type2_rva=args.resource_gate_queue_handler_type2_rva,
                        queue_handler_type0_rva=args.resource_gate_queue_handler_type0_rva,
                        queue_helper_prepare_rva=args.resource_gate_queue_helper_prepare_rva,
                        type0_prepare_status_rva=getattr(
                            args,
                            "resource_gate_type0_prepare_status_rva",
                            DEFAULT_RESOURCE_GATE_TYPE0_PREPARE_STATUS_RVA,
                        ),
                        type0_descriptor_status_rva=getattr(
                            args,
                            "resource_gate_type0_descriptor_status_rva",
                            DEFAULT_RESOURCE_GATE_TYPE0_DESCRIPTOR_STATUS_RVA,
                        ),
                        type0_source_object_rva=getattr(
                            args,
                            "resource_gate_type0_source_object_rva",
                            DEFAULT_RESOURCE_GATE_TYPE0_SOURCE_OBJECT_RVA,
                        ),
                        type0_prepare_parser_rva=getattr(
                            args,
                            "resource_gate_type0_prepare_parser_rva",
                            DEFAULT_RESOURCE_GATE_TYPE0_PREPARE_PARSER_RVA,
                        ),
                        queue_loop_item_rva=args.resource_gate_queue_loop_item_rva,
                        queue_loop_post_rva=args.resource_gate_queue_loop_post_rva,
                        record_open_rva=args.resource_gate_record_open_rva,
                        record_close_rva=args.resource_gate_record_close_rva,
                        suppress_record_close_call_rvas=list(
                            getattr(args, "resource_gate_suppress_record_close_call_rvas", [])
                        ),
                        idle_selector_rva=args.resource_gate_idle_selector_rva,
                        seed_dispatch_rva=args.resource_gate_seed_dispatch_rva,
                        idle_selector_queue_check_rva=args.resource_gate_idle_selector_queue_check_rva,
                        scheduler_global_rva=args.resource_gate_scheduler_global_rva,
                        resource_count=args.resource_gate_resource_count,
                        record_stride=args.resource_gate_record_stride,
                        force_record21_on_open=args.resource_gate_force_record21_on_open,
                        force_recorde_on_open=args.resource_gate_force_recorde_on_open,
                        force_recorde_on_dispatch_return=args.resource_gate_force_recorde_on_dispatch_return,
                        force_finalize_on_dispatch_return=bool(
                            getattr(args, "resource_gate_force_finalize_on_dispatch_return", False)
                        ),
                        force_recordd_clear_on_dispatch_return=args.resource_gate_force_recordd_clear_on_dispatch_return,
                        force_owner_stage_clear_when_drained=args.resource_gate_force_owner_stage_clear_when_drained,
                        force_record_open_on_field1c=bool(
                            getattr(args, "resource_gate_force_record_open_on_field1c", False)
                        ),
                        force_seed_dispatch_on_ptr178=args.resource_gate_force_seed_dispatch_on_ptr178,
                        force_recordd_ready_on_ptr178=bool(
                            getattr(args, "resource_gate_force_recordd_ready_on_ptr178", False)
                        ),
                        force_recordd_ready_on_latch_clear=bool(
                            getattr(args, "resource_gate_force_recordd_ready_on_latch_clear", False)
                        ),
                        force_recordd_ready_on_close_suppression=bool(
                            getattr(
                                args,
                                "resource_gate_force_recordd_ready_on_close_suppression",
                                False,
                            )
                        ),
                        force_selector_ready_on_ptr178=bool(
                            getattr(args, "resource_gate_force_selector_ready_on_ptr178", False)
                        ),
                        force_direct_dispatch_on_state1=args.resource_gate_force_direct_dispatch_on_state1,
                        force_dispatch_provider_accept=bool(
                            getattr(args, "resource_gate_force_dispatch_provider_accept", False)
                        ),
                        force_dispatch_result_metadata_fallback=bool(
                            getattr(
                                args,
                                "resource_gate_force_dispatch_result_metadata_fallback",
                                False,
                            )
                        ),
                        force_post_dispatch_release_callback_fallback=bool(
                            getattr(
                                args,
                                "resource_gate_force_post_dispatch_release_callback_fallback",
                                False,
                            )
                        ),
                        force_owner_stage_open_on_state1=args.resource_gate_force_owner_stage_open_on_state1,
                        force_prepared_selector_ready=args.resource_gate_force_prepared_selector_ready,
                        demote_hot_donezero_queued_record=bool(
                            getattr(args, "resource_gate_demote_hot_donezero_queued_record", False)
                        ),
                        force_idle_selector_latch_clear=args.resource_gate_force_idle_selector_latch_clear,
                        force_idle_selector_timer_open=args.resource_gate_force_idle_selector_timer_open,
                        force_idle_selector_queue_empty=args.resource_gate_force_idle_selector_queue_empty,
                        force_post_select_flag20_on_busy=args.resource_gate_force_post_select_flag20_on_busy,
                        force_post_select_status_retval=getattr(
                            args, "resource_gate_force_post_select_status_retval", None
                        ),
                        force_post_select_publication_success=bool(
                            getattr(
                                args,
                                "resource_gate_force_post_select_publication_success",
                                False,
                            )
                        ),
                        suppress_post_select_latch_clear=bool(
                            getattr(args, "resource_gate_suppress_post_select_latch_clear", False)
                        ),
                        force_recordstate_from_type0=args.resource_gate_force_recordstate_from_type0,
                        force_type0_prepare_branch=bool(
                            getattr(args, "resource_gate_force_type0_prepare_branch", False)
                        ),
                        force_item_payload_from_ptr178=args.resource_gate_force_item_payload_from_ptr178,
                        force_type0_descriptor_status_retval=getattr(
                            args, "resource_gate_force_type0_descriptor_status_retval", None
                        ),
                        force_type0_childminus1_bypass=bool(
                            getattr(args, "resource_gate_force_type0_childminus1_bypass", False)
                        ),
                        force_type0_field18_to_2=bool(
                            getattr(args, "resource_gate_force_type0_field18_to_2", False)
                        ),
                        force_type3_followon_on_post_state1=args.resource_gate_force_type3_followon_on_post_state1,
                        force_finalize_after_type3_on_post_state1=(
                            args.resource_gate_force_finalize_after_type3_on_post_state1
                        ),
                        force_type0_raw_source_from_ptr178=bool(
                            getattr(args, "resource_gate_force_type0_raw_source_from_ptr178", False)
                        ),
                        force_type0_zlb_source_from_ptr178=bool(
                            getattr(args, "resource_gate_force_type0_zlb_source_from_ptr178", False)
                        ),
                        force_type0_requested_length_from_source_header=bool(
                            getattr(
                                args,
                                "resource_gate_force_type0_requested_length_from_source_header",
                                False,
                            )
                        ),
                        force_type0_source_object_from_side_slots=bool(
                            getattr(
                                args,
                                "resource_gate_force_type0_source_object_from_side_slots",
                                False,
                            )
                        ),
                        force_type0_inner_source_from_side_wrapper=bool(
                            getattr(
                                args,
                                "resource_gate_force_type0_inner_source_from_side_wrapper",
                                False,
                            )
                        ),
                        force_type0_parser_single_byte_payload_to_1=bool(
                            getattr(
                                args,
                                "resource_gate_force_type0_parser_single_byte_payload_to_1",
                                False,
                            )
                        ),
                        force_queue_helper_resolver_synthetic_success=bool(
                            getattr(
                                args,
                                "resource_gate_force_queue_helper_resolver_synthetic_success",
                                False,
                            )
                        ),
                        force_queue_helper_post_parser_cleanup_suppression=bool(
                            getattr(
                                args,
                                "resource_gate_force_queue_helper_post_parser_cleanup_suppression",
                                False,
                            )
                        ),
                        force_queue_helper_return_slot_restore=bool(
                            getattr(
                                args,
                                "resource_gate_force_queue_helper_return_slot_restore",
                                False,
                            )
                        ),
                        force_type0_handler_return_slot_restore=bool(
                            getattr(
                                args,
                                "resource_gate_force_type0_handler_return_slot_restore",
                                False,
                            )
                        ),
                        reenter_recordstate_after_type3_on_post_state1=bool(
                            getattr(
                                args,
                                "resource_gate_reenter_recordstate_after_type3_on_post_state1",
                                False,
                            )
                        ),
                    )
                )
                resource_gate_script.on("message", on_resource_gate_message)
                resource_gate_script.load()
                _write_trace(
                    trace_handle,
                    "resource-gate-attached",
                    pid=process_pid,
                    gateRva=hex(args.resource_gate_gate_rva),
                    dispatchRva=hex(args.resource_gate_dispatch_rva),
                    recordStateRva=hex(args.resource_gate_record_state_rva),
                    recordResetRva=hex(args.resource_gate_record_reset_rva),
                    recordFinalizeRva=hex(args.resource_gate_record_finalize_rva),
                    queueHandlerType3Rva=hex(args.resource_gate_queue_handler_type3_rva),
                    queueHandlerType2Rva=hex(args.resource_gate_queue_handler_type2_rva),
                    queueHandlerType0Rva=hex(args.resource_gate_queue_handler_type0_rva),
                    queueHelperPrepareRva=hex(args.resource_gate_queue_helper_prepare_rva),
                    queueLoopItemRva=hex(args.resource_gate_queue_loop_item_rva),
                    queueLoopPostRva=hex(args.resource_gate_queue_loop_post_rva),
                    recordOpenRva=hex(args.resource_gate_record_open_rva),
                    recordCloseRva=hex(args.resource_gate_record_close_rva),
                    idleSelectorRva=hex(args.resource_gate_idle_selector_rva),
                    seedDispatchRva=hex(args.resource_gate_seed_dispatch_rva),
                    idleSelectorQueueCheckRva=hex(args.resource_gate_idle_selector_queue_check_rva),
                    schedulerGlobalRva=hex(args.resource_gate_scheduler_global_rva),
                    resourceCount=args.resource_gate_resource_count,
                    recordStride=hex(args.resource_gate_record_stride),
                    forceRecord21OnOpen=bool(args.resource_gate_force_record21_on_open),
                    forceRecordEOnOpen=bool(args.resource_gate_force_recorde_on_open),
                    forceRecordEOnDispatchReturn=bool(args.resource_gate_force_recorde_on_dispatch_return),
                    forceRecordDClearOnDispatchReturn=bool(args.resource_gate_force_recordd_clear_on_dispatch_return),
                    forceOwnerStageClearWhenDrained=bool(
                        args.resource_gate_force_owner_stage_clear_when_drained
                    ),
                    forceSeedDispatchOnPtr178=bool(args.resource_gate_force_seed_dispatch_on_ptr178),
                    forceDirectDispatchOnState1=bool(args.resource_gate_force_direct_dispatch_on_state1),
                    forceOwnerStageOpenOnState1=bool(args.resource_gate_force_owner_stage_open_on_state1),
                    forcePreparedSelectorReady=bool(args.resource_gate_force_prepared_selector_ready),
                    forceIdleSelectorLatchClear=bool(args.resource_gate_force_idle_selector_latch_clear),
                    forceIdleSelectorTimerOpen=bool(args.resource_gate_force_idle_selector_timer_open),
                    forceIdleSelectorQueueEmpty=bool(args.resource_gate_force_idle_selector_queue_empty),
                    forcePostSelectFlag20OnBusy=bool(args.resource_gate_force_post_select_flag20_on_busy),
                    forceRecordStateFromType0=bool(args.resource_gate_force_recordstate_from_type0),
                    forceItemPayloadFromPtr178=bool(args.resource_gate_force_item_payload_from_ptr178),
                    forceType3FollowonOnPostState1=bool(
                        args.resource_gate_force_type3_followon_on_post_state1
                    ),
                    forceFinalizeAfterType3OnPostState1=bool(
                        args.resource_gate_force_finalize_after_type3_on_post_state1
                    ),
                )
            if producer_output_root is not None:
                def on_producer_message(message: dict[str, Any], _data: Any) -> None:
                    if message.get("type") == "send":
                        payload = message.get("payload")
                        if isinstance(payload, dict):
                            payload.setdefault("pid", process_pid)
                            write_producer_event(payload)
                            return
                    write_producer_event(
                        {
                            "event": "frida-message",
                            "pid": process_pid,
                            "messageType": message.get("type"),
                            "payload": message.get("payload"),
                            "stack": message.get("stack"),
                            "description": message.get("description"),
                        }
                    )

                producer_script = startup_session.create_script(
                    build_prelogin_producer_script(
                        producer_rva=0x590220,
                        builder_rva=0x590BC0,
                        builder_master_lookup_rva=0x590C58,
                        builder_post_gate_rva=0x590DE8,
                        fallback_rva=0x591A00,
                        indexed_table_slot_offset=0x30D0,
                        record_stride=0x108,
                    )
                )
                producer_script.on("message", on_producer_message)
                producer_script.load()
                _write_trace(
                    trace_handle,
                    "producer-attached",
                    pid=process_pid,
                    producerRva=hex(0x590220),
                    builderRva=hex(0x590BC0),
                    builderMasterLookupRva=hex(0x590C58),
                    builderPostGateRva=hex(0x590DE8),
                    fallbackRva=hex(0x591A00),
                    indexedTableSlotOffset=hex(0x30D0),
                    recordStride=hex(0x108),
                )
            if loading_state_output_root is not None:
                def on_loading_state_message(message: dict[str, Any], _data: Any) -> None:
                    if message.get("type") == "send":
                        payload = message.get("payload")
                        if isinstance(payload, dict):
                            payload.setdefault("pid", process_pid)
                            write_loading_state_event(payload)
                            return
                    write_loading_state_event(
                        {
                            "event": "frida-message",
                            "pid": process_pid,
                            "messageType": message.get("type"),
                            "payload": message.get("payload"),
                            "stack": message.get("stack"),
                            "description": message.get("description"),
                        }
                    )

                loading_state_script = startup_session.create_script(
                    build_loading_state_builder_script(
                        state_copy_rva=args.loading_state_state_copy_rva,
                        loading_gate_rva=args.loading_state_gate_rva,
                        loading_callsite_rva=args.loading_state_callsite_rva,
                        record_stride=args.loading_state_record_stride,
                    )
                )
                loading_state_script.on("message", on_loading_state_message)
                loading_state_script.load()
                _write_trace(
                    trace_handle,
                    "loading-state-attached",
                    pid=process_pid,
                    stateCopyRva=hex(args.loading_state_state_copy_rva),
                    loadingGateRva=hex(args.loading_state_gate_rva),
                    loadingCallsiteRva=hex(args.loading_state_callsite_rva),
                    recordStride=hex(args.loading_state_record_stride),
                )
        else:
            process = subprocess.Popen(argv_list, cwd=str(working_dir))
            process_pid = int(process.pid)
            _write_trace(trace_handle, "spawned", pid=process_pid, argv=argv_list, workingDir=str(working_dir), launchMode=launch_mode)

        startup_contract_hint = extract_startup_contract_hint(
            client_exe=client_exe,
            client_args=args.client_arg,
            process_pid=process_pid,
        )
        startup_contract_hint_path = write_startup_contract_hint(summary_output, startup_contract_hint)
        _write_trace(
            trace_handle,
            "startup-contract-hint",
            pid=process_pid,
            path=str(startup_contract_hint_path),
            hint=startup_contract_hint,
        )

        if args.patch_delay_seconds > 0:
            time.sleep(args.patch_delay_seconds)

        inline_patch_results = patch_remote_inline_offsets(process_pid, inline_patch_offsets)
        _write_trace(trace_handle, "inline-patched", pid=process_pid, results=inline_patch_results)

        null_patch_results = patch_remote_null_read_offsets(process_pid, null_patch_offsets)
        _write_trace(trace_handle, "null-read-patched", pid=process_pid, results=null_patch_results)

        jump_patch_results = patch_remote_jump_bypass_blocks(process_pid, jump_bypass_specs)
        _write_trace(trace_handle, "jump-bypass-patched", pid=process_pid, results=jump_patch_results)

        rsa_patch_results = None
        live_path = query_process_path(process_pid)
        if rsa_config_path is not None and live_path:
            rsa_patch_results = patch_remote_embedded_rsa_moduli(
                process_pid,
                Path(live_path),
                rsa_config_path,
                js5_rsa_source_exe=js5_rsa_source_exe,
            )
            _write_trace(trace_handle, "rsa-patched", pid=process_pid, results=rsa_patch_results)

        if use_spawn_session:
            device.resume(process_pid)
            _write_trace(trace_handle, "resumed", pid=process_pid, launchMode=launch_mode)

        ready_summary = build_summary(
            client_exe=client_exe,
            working_dir=working_dir,
            argv_list=argv_list,
            launch_mode=launch_mode,
            monitor_seconds=args.monitor_seconds,
            patch_delay_seconds=args.patch_delay_seconds,
            inline_patch_offsets=inline_patch_offsets,
            inline_patch_results=inline_patch_results,
            null_patch_offsets=null_patch_offsets,
            null_patch_results=null_patch_results,
            jump_bypass_specs=jump_bypass_specs,
            jump_patch_results=jump_patch_results,
            rsa_config_path=rsa_config_path,
            rsa_patch_results=rsa_patch_results,
            resolve_redirects=resolve_redirects,
            connect_redirects=connect_redirects,
            startup_hook_output=startup_hook_output,
            startup_hook_verbose=bool(args.startup_hook_verbose),
            trace_output=trace_output,
            process_pid=process_pid,
            exit_code=None,
            summary_stage="ready",
        )
        _write_trace(trace_handle, "summary-ready", summary=ready_summary)
        write_summary_output(summary_output, ready_summary)

        deadline = time.time() + max(0.0, args.monitor_seconds)
        exit_code = None
        while time.time() < deadline:
            if process is not None:
                exit_code = process.poll()
                if exit_code is not None:
                    break
            else:
                if query_process_path(process_pid) is None:
                    break
            time.sleep(0.25)

        if process is not None and exit_code is None:
            exit_code = process.poll()

        summary = build_summary(
            client_exe=client_exe,
            working_dir=working_dir,
            argv_list=argv_list,
            launch_mode=launch_mode,
            monitor_seconds=args.monitor_seconds,
            patch_delay_seconds=args.patch_delay_seconds,
            inline_patch_offsets=inline_patch_offsets,
            inline_patch_results=inline_patch_results,
            null_patch_offsets=null_patch_offsets,
            null_patch_results=null_patch_results,
            jump_bypass_specs=jump_bypass_specs,
            jump_patch_results=jump_patch_results,
            rsa_config_path=rsa_config_path,
            rsa_patch_results=rsa_patch_results,
            resolve_redirects=resolve_redirects,
            connect_redirects=connect_redirects,
            startup_hook_output=startup_hook_output,
            startup_hook_verbose=bool(args.startup_hook_verbose),
            trace_output=trace_output,
            process_pid=process_pid,
            exit_code=exit_code,
            summary_stage="final",
        )
        _write_trace(trace_handle, "summary", summary=summary)
        write_summary_output(summary_output, summary)

        if (
            resource_gate_script is not None
            and resource_gate_archive_summary_output_path is not None
            and resource_gate_latest_summary_output_path is not None
        ):
            try:
                resource_gate_snapshot = resource_gate_script.exports_sync.snapshot()
            except frida.InvalidOperationError:
                resource_gate_snapshot = None
            if resource_gate_snapshot is not None:
                resource_gate_summary = {
                    "pid": process_pid,
                    "gateRva": hex(args.resource_gate_gate_rva),
                    "dispatchRva": hex(args.resource_gate_dispatch_rva),
                    "recordStateRva": hex(args.resource_gate_record_state_rva),
                    "idleSelectorRva": hex(args.resource_gate_idle_selector_rva),
                    "archivePath": str(resource_gate_archive_path) if resource_gate_archive_path is not None else None,
                    "latestPath": str(resource_gate_latest_path) if resource_gate_latest_path is not None else None,
                    "durationSeconds": args.monitor_seconds,
                    "forceRecord21OnOpen": bool(args.resource_gate_force_record21_on_open),
                    "forceRecordEOnOpen": bool(args.resource_gate_force_recorde_on_open),
                    "forceRecordEOnDispatchReturn": bool(args.resource_gate_force_recorde_on_dispatch_return),
                    "forceRecordDClearOnDispatchReturn": bool(args.resource_gate_force_recordd_clear_on_dispatch_return),
                    "forceOwnerStageClearWhenDrained": bool(args.resource_gate_force_owner_stage_clear_when_drained),
                    "snapshot": resource_gate_snapshot,
                }
                resource_gate_archive_summary_output_path.write_text(
                    json.dumps(resource_gate_summary, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                resource_gate_latest_summary_output_path.write_text(
                    json.dumps(resource_gate_summary, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

        if (
            producer_script is not None
            and producer_archive_path is not None
            and producer_archive_summary_output_path is not None
            and producer_latest_summary_output_path is not None
        ):
            producer_summary = build_prelogin_producer_summary(producer_archive_path, pid=process_pid)
            try:
                producer_snapshot = producer_script.exports_sync.snapshot()
            except frida.InvalidOperationError:
                producer_snapshot = None
            if producer_snapshot is not None:
                producer_summary["snapshot"] = producer_snapshot
            producer_archive_summary_output_path.write_text(
                json.dumps(producer_summary, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            producer_latest_summary_output_path.write_text(
                json.dumps(producer_summary, indent=2, sort_keys=True),
                encoding="utf-8",
            )

        if (
            loading_state_script is not None
            and loading_state_archive_summary_output_path is not None
            and loading_state_latest_summary_output_path is not None
        ):
            try:
                loading_state_snapshot = loading_state_script.exports_sync.snapshot()
            except frida.InvalidOperationError:
                loading_state_snapshot = None
            if loading_state_snapshot is not None:
                loading_state_summary = {
                    "pid": process_pid,
                    "stateCopyRva": hex(args.loading_state_state_copy_rva),
                    "loadingGateRva": hex(args.loading_state_gate_rva),
                    "loadingCallsiteRva": hex(args.loading_state_callsite_rva),
                    "recordStride": hex(args.loading_state_record_stride),
                    "archivePath": (
                        str(loading_state_archive_path) if loading_state_archive_path is not None else None
                    ),
                    "latestPath": (
                        str(loading_state_latest_path) if loading_state_latest_path is not None else None
                    ),
                    "durationSeconds": args.monitor_seconds,
                    "snapshot": loading_state_snapshot,
                }
                loading_state_archive_summary_output_path.write_text(
                    json.dumps(loading_state_summary, indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                loading_state_latest_summary_output_path.write_text(
                    json.dumps(loading_state_summary, indent=2, sort_keys=True),
                    encoding="utf-8",
                )

        if resource_gate_script is not None:
            try:
                resource_gate_script.unload()
            except frida.InvalidOperationError:
                pass
        if producer_script is not None:
            try:
                producer_script.unload()
            except frida.InvalidOperationError:
                pass
        if loading_state_script is not None:
            try:
                loading_state_script.unload()
            except frida.InvalidOperationError:
                pass
        if startup_script is not None:
            process_alive_before_detach = query_process_path(process_pid) is not None or query_process_command_line(process_pid) is not None
            helper_detach_event = {
                "timestamp": round(time.time(), 6),
                "category": "client.lifecycle",
                "action": "helper-detach-requested",
                "pid": process_pid,
                "reason": "monitor-window-complete",
                "processAlive": process_alive_before_detach,
                "monitorSeconds": args.monitor_seconds,
            }
            write_startup_event(helper_detach_event)
            _write_trace(trace_handle, "helper-detach-requested", pid=process_pid, processAlive=process_alive_before_detach, monitorSeconds=args.monitor_seconds)
            try:
                startup_script.unload()
            except frida.InvalidOperationError:
                pass
        if startup_session is not None:
            try:
                startup_session.detach()
            except frida.InvalidOperationError:
                pass
        startup_stop.set()
    finally:
        if trace_handle is not None:
            trace_handle.close()
        if startup_hook_handle is not None:
            startup_hook_handle.close()
        if resource_gate_archive_handle is not None:
            resource_gate_archive_handle.close()
        if resource_gate_latest_handle is not None:
            resource_gate_latest_handle.close()
        if producer_archive_handle is not None:
            producer_archive_handle.close()
        if producer_latest_handle is not None:
            producer_latest_handle.close()
        if loading_state_archive_handle is not None:
            loading_state_archive_handle.close()
        if loading_state_latest_handle is not None:
            loading_state_latest_handle.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
