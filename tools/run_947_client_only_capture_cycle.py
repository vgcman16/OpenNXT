from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
DEBUG_ROOT = ROOT / "data" / "debug"
HOOK_PATH = DEBUG_ROOT / "direct-rs2client-patch" / "latest-client-only-hook.jsonl"
SUMMARY_PATH = DEBUG_ROOT / "direct-rs2client-patch" / "latest-client-only.json"
TRANSPORT_PATH = DEBUG_ROOT / "prelogin-transport-events.jsonl"
PROBE_LATEST = DEBUG_ROOT / "frida-crash-probe" / "latest-client-only.jsonl"
PROBE_RUNS = DEBUG_ROOT / "frida-crash-probe" / "runs"
SCREENSHOT_DIR = DEBUG_ROOT / "screenshots"
USERDUMP_ROOT = DEBUG_ROOT / "userdumps" / "947-client-only"
APPLICATION_RESOURCE_GATE_ROOT = DEBUG_ROOT / "application-resource-gate-947"
APPLICATION_RESOURCE_STATE_ROOT = DEBUG_ROOT / "application-resource-state-947"
APPLICATION_RESOURCE_BRIDGE_ROOT = DEBUG_ROOT / "application-resource-bridge-947"
PRELOGIN_PRODUCER_ROOT = DEBUG_ROOT / "prelogin-producer-947"
LOADING_GATE_ROOT = DEBUG_ROOT / "loading-gate-947"
LOADING_STATE_BUILDER_ROOT = DEBUG_ROOT / "loading-state-builder-947"
TABLE_LIFECYCLE_ROOT = DEBUG_ROOT / "table-lifecycle-947"
STARTUP_CAPTURE_ROOT = DEBUG_ROOT / "client-only-startup-capture-947"
DEFAULT_GATE_RECORD_CLOSE_BULK_CALLER_RVAS = (
    "0x5946cf",
    "0x594700",
    "0x595433",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one 947 client-only capture cycle.")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--probe-duration-seconds", type=int, default=120)
    parser.add_argument("--probe-function-start-rva", default="0x590bc0")
    parser.add_argument("--probe-fault-rva", default="0x590de8")
    parser.add_argument("--probe-state-capture-rva", default="0x590dcb")
    parser.add_argument("--probe-repair-r15-at-state-capture", action="store_true")
    parser.add_argument("--probe-repair-epilogue-frame", action="store_true")
    parser.add_argument("--probe-repair-release-frame", action="store_true")
    parser.add_argument("--skip-probe", action="store_true")
    parser.add_argument("--resource-gate-trace", action="store_true")
    parser.add_argument("--resource-state-trace", action="store_true")
    parser.add_argument("--resource-bridge-trace", action="store_true")
    parser.add_argument("--producer-trace", action="store_true")
    parser.add_argument("--loading-gate-trace", action="store_true")
    parser.add_argument("--loading-state-builder-trace", action="store_true")
    parser.add_argument("--table-lifecycle-trace", action="store_true")
    parser.add_argument("--resource-trace-duration-seconds", type=int, default=120)
    parser.add_argument("--resource-trace-wait-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--table-null-source-vector", action="store_true")
    parser.add_argument("--table-force-length-gate-0x41", action="store_true")
    parser.add_argument("--table-skip-compare-failure", action="store_true")
    parser.add_argument("--table-mirror-compare-left-into-right", action="store_true")
    parser.add_argument("--table-inject-null-master-table", action="store_true")
    parser.add_argument("--table-inject-null-master-table-count", type=int, default=67)
    parser.add_argument("--gate-force-record21-on-open", action="store_true")
    parser.add_argument("--gate-force-recorde-on-open", action="store_true")
    parser.add_argument("--gate-force-recorde-on-dispatch-return", action="store_true")
    parser.add_argument("--gate-force-finalize-on-dispatch-return", action="store_true")
    parser.add_argument("--gate-force-recordd-clear-on-dispatch-return", action="store_true")
    parser.add_argument("--gate-force-owner-stage-clear-when-drained", action="store_true")
    parser.add_argument("--gate-force-record-open-on-field1c", action="store_true")
    parser.add_argument("--gate-force-seed-dispatch-on-ptr178", action="store_true")
    parser.add_argument("--gate-force-recordd-ready-on-ptr178", action="store_true")
    parser.add_argument("--gate-force-recordd-ready-on-latch-clear", action="store_true")
    parser.add_argument("--gate-force-recordd-ready-on-close-suppression", action="store_true")
    parser.add_argument("--gate-force-selector-ready-on-ptr178", action="store_true")
    parser.add_argument("--gate-force-direct-dispatch-on-state1", action="store_true")
    parser.add_argument("--gate-force-dispatch-provider-accept", action="store_true")
    parser.add_argument("--gate-force-dispatch-result-metadata-fallback", action="store_true")
    parser.add_argument(
        "--gate-force-post-dispatch-release-callback-fallback",
        action="store_true",
    )
    parser.add_argument("--gate-force-owner-stage-open-on-state1", action="store_true")
    parser.add_argument("--gate-force-prepared-selector-ready", action="store_true")
    parser.add_argument("--gate-demote-hot-donezero-queued-record", action="store_true")
    parser.add_argument("--gate-force-idle-selector-latch-clear", action="store_true")
    parser.add_argument("--gate-force-idle-selector-timer-open", action="store_true")
    parser.add_argument("--gate-force-idle-selector-queue-empty", action="store_true")
    parser.add_argument("--gate-force-post-select-flag20-on-busy", action="store_true")
    parser.add_argument("--gate-force-post-select-status-retval", default=None)
    parser.add_argument("--gate-force-post-select-publication-success", action="store_true")
    parser.add_argument("--gate-suppress-post-select-latch-clear", action="store_true")
    parser.add_argument("--gate-suppress-record-close-bulk-pass", action="store_true")
    parser.add_argument(
        "--gate-suppress-record-close-call-rva",
        action="append",
        default=[],
        help="Additional caller RVA to suppress for the record-close helper smoke test. Repeat for multiple values.",
    )
    parser.add_argument("--gate-force-recordstate-from-type0", action="store_true")
    parser.add_argument("--gate-force-type0-prepare-branch", action="store_true")
    parser.add_argument("--gate-force-item-payload-from-ptr178", action="store_true")
    parser.add_argument("--gate-force-type0-descriptor-status-retval", default=None)
    parser.add_argument("--gate-force-type0-childminus1-bypass", action="store_true")
    parser.add_argument("--gate-force-type0-field18-to-2", action="store_true")
    parser.add_argument("--gate-force-type0-raw-source-from-ptr178", action="store_true")
    parser.add_argument("--gate-force-type0-zlb-source-from-ptr178", action="store_true")
    parser.add_argument("--gate-force-type0-requested-length-from-source-header", action="store_true")
    parser.add_argument("--gate-force-type0-source-object-from-side-slots", action="store_true")
    parser.add_argument("--gate-force-type0-inner-source-from-side-wrapper", action="store_true")
    parser.add_argument("--gate-force-type0-parser-single-byte-payload-to-1", action="store_true")
    parser.add_argument("--gate-force-queue-helper-resolver-synthetic-success", action="store_true")
    parser.add_argument("--gate-force-queue-helper-post-parser-cleanup-suppression", action="store_true")
    parser.add_argument("--gate-force-queue-helper-return-slot-restore", action="store_true")
    parser.add_argument("--gate-force-type0-handler-return-slot-restore", action="store_true")
    parser.add_argument("--gate-force-type3-followon-on-post-state1", action="store_true")
    parser.add_argument("--gate-force-finalize-after-type3-on-post-state1", action="store_true")
    parser.add_argument("--gate-reenter-recordstate-after-type3-on-post-state1", action="store_true")
    parser.add_argument("--bridge-force-state1-on-ptr178", action="store_true")
    parser.add_argument("--bridge-force-selector-ready-on-ptr178", action="store_true")
    parser.add_argument("--bridge-force-owner-11d4a-open-on-special20", action="store_true")
    parser.add_argument("--bridge-force-seed-dispatch-on-state1", action="store_true")
    parser.add_argument("--bridge-force-recordstate-on-state1", action="store_true")
    parser.add_argument("--bridge-force-direct-dispatch-on-state1", action="store_true")
    parser.add_argument("--bridge-force-finalize-on-state1", action="store_true")
    parser.add_argument(
        "--launcher-arg",
        action="append",
        default=[],
        help="Additional argument to pass through to launch-client-only.ps1. Repeat for multiple values.",
    )
    parser.add_argument(
        "--userdump-on-terminate",
        action="store_true",
        help="Capture a dump when rs2client.exe terminates, even if ProcDump does not see an unhandled exception.",
    )
    parser.add_argument("--window-capture", action="store_true")
    parser.add_argument("--window-capture-interval-seconds", type=int, default=30)
    parser.add_argument("--clear-artifacts", action="store_true")
    parser.add_argument("--kill-existing-client", action="store_true")
    return parser.parse_args()


def run_command(args: list[str], *, cwd: Path | None = None, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=True)


def powershell_args(script: Path, *extra: str) -> list[str]:
    return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *extra]


def kill_existing_clients() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process rs2client -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def clear_artifacts() -> None:
    for path in (
        HOOK_PATH,
        SUMMARY_PATH,
        TRANSPORT_PATH,
        PROBE_LATEST,
        APPLICATION_RESOURCE_GATE_ROOT / "latest-client-only.jsonl",
        APPLICATION_RESOURCE_GATE_ROOT / "latest-client-only.json",
        APPLICATION_RESOURCE_STATE_ROOT / "latest-client-only.jsonl",
        APPLICATION_RESOURCE_STATE_ROOT / "latest-client-only.json",
        APPLICATION_RESOURCE_BRIDGE_ROOT / "latest-client-only.jsonl",
        APPLICATION_RESOURCE_BRIDGE_ROOT / "latest-client-only.json",
        PRELOGIN_PRODUCER_ROOT / "latest-client-only.jsonl",
        PRELOGIN_PRODUCER_ROOT / "latest-client-only.json",
        LOADING_GATE_ROOT / "latest-client-only.jsonl",
        LOADING_GATE_ROOT / "latest-client-only.json",
        LOADING_STATE_BUILDER_ROOT / "latest-client-only.jsonl",
        LOADING_STATE_BUILDER_ROOT / "latest-client-only.json",
        TABLE_LIFECYCLE_ROOT / "latest-client-only.jsonl",
        TABLE_LIFECYCLE_ROOT / "latest-client-only.json",
    ):
        if path.exists():
            path.unlink()


def read_hook_events() -> list[dict]:
    if not HOOK_PATH.exists():
        return []
    events: list[dict] = []
    for line in HOOK_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def read_direct_patch_summary() -> dict:
    if not SUMMARY_PATH.exists():
        return {}
    try:
        data = json.loads(SUMMARY_PATH.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_launcher_summary(stdout_log: Path | None) -> dict:
    if stdout_log is None or not stdout_log.exists():
        return {}
    try:
        data = json.loads(stdout_log.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def wait_for_main_pid(deadline: float, *, launcher_stdout_log: Path | None = None) -> int:
    while time.time() < deadline:
        for event in read_hook_events():
            if event.get("action") == "exception-handler-installed" and event.get("pid"):
                return int(event["pid"])
        summary = read_direct_patch_summary()
        summary_pid = summary.get("pid")
        if summary_pid and summary.get("processAlive") and process_exists(int(summary_pid)):
            return int(summary_pid)
        launcher_summary = read_launcher_summary(launcher_stdout_log)
        for key in ("ClientPid", "BootstrapClientPid"):
            launcher_pid = launcher_summary.get(key)
            if launcher_pid and process_exists(int(launcher_pid)):
                return int(launcher_pid)
        time.sleep(0.5)
    raise TimeoutError(
        "Timed out waiting for exception-handler-installed in latest-client-only-hook.jsonl "
        "or a live pid in latest-client-only.json / launcher stdout summary"
    )


def process_exists(pid: int) -> bool:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == str(pid)


def list_procdump_pids() -> set[int]:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process procdump -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            pids.add(int(line))
        except ValueError:
            continue
    return pids


def list_userdump_dirs() -> list[Path]:
    if not USERDUMP_ROOT.exists():
        return []
    return [path for path in USERDUMP_ROOT.iterdir() if path.is_dir()]


def start_userdump(*, dump_on_terminate: bool) -> dict:
    before_pids = list_procdump_pids()
    before_dirs = {path.resolve() for path in list_userdump_dirs()}
    args = powershell_args(TOOLS / "start_947_client_userdump.ps1", "-WaitForProcess")
    if dump_on_terminate:
        args.append("-DumpOnTerminate")
    process = subprocess.Popen(
        args,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )

    deadline = time.time() + 15.0
    created_dir: Path | None = None
    monitor_pid: int | None = None

    while time.time() < deadline:
        for path in list_userdump_dirs():
            resolved = path.resolve()
            if resolved not in before_dirs:
                created_dir = path
                break

        new_pids = sorted(list_procdump_pids() - before_pids)
        if new_pids:
            monitor_pid = new_pids[0]

        if created_dir is not None or monitor_pid is not None:
            return {
                "MonitorPid": monitor_pid,
                "Mode": "wait",
                "DumpOnTerminate": dump_on_terminate,
                "TargetPid": None,
                "ProcessName": "rs2client.exe",
                "OutputDir": str(created_dir) if created_dir is not None else None,
                "StdoutLog": str(created_dir / "procdump.stdout.log") if created_dir is not None else None,
                "StderrLog": str(created_dir / "procdump.stderr.log") if created_dir is not None else None,
                "ProcDumpExe": None,
            }

        if process.poll() is not None and process.returncode not in (0, None):
            raise RuntimeError(f"start_947_client_userdump.ps1 exited early with code {process.returncode}")

        time.sleep(0.25)

    if process.poll() is None:
        process.kill()
    raise TimeoutError("Timed out waiting for ProcDump monitor startup")


def start_launcher(timestamp: str, launcher_args: list[str]) -> tuple[subprocess.Popen[str], Path, Path]:
    stdout_log = ROOT / f"tmp-client-only-cycle-{timestamp}.stdout.log"
    stderr_log = ROOT / f"tmp-client-only-cycle-{timestamp}.stderr.log"
    stdout_file = stdout_log.open("w", encoding="utf-8")
    stderr_file = stderr_log.open("w", encoding="utf-8")
    process = subprocess.Popen(
        powershell_args(TOOLS / "launch-client-only.ps1", *launcher_args),
        cwd=ROOT,
        stdout=stdout_file,
        stderr=stderr_file,
        text=True,
    )
    return process, stdout_log, stderr_log


def start_probe(
    pid: int,
    timestamp: str,
    duration_seconds: int,
    *,
    function_start_rva: str,
    fault_rva: str,
    state_capture_rva: str,
    repair_r15_at_state_capture: bool,
    repair_epilogue_frame: bool,
    repair_release_frame: bool,
) -> subprocess.Popen[str]:
    PROBE_RUNS.mkdir(parents=True, exist_ok=True)
    output_path = PROBE_RUNS / f"947-client-only-crash-probe-{timestamp}.jsonl"
    stdout_log = output_path.with_suffix(".stdout.log")
    stderr_log = output_path.with_suffix(".stderr.log")
    probe_args = [
        sys.executable,
        str(TOOLS / "trace_947_client_crash_probe.py"),
        "--pid",
        str(pid),
        "--output",
        str(output_path),
        "--latest-output",
        str(PROBE_LATEST),
        "--duration-seconds",
        str(duration_seconds),
        "--function-start-rva",
        function_start_rva,
        "--fault-rva",
        fault_rva,
        "--state-capture-rva",
        state_capture_rva,
    ]
    if repair_r15_at_state_capture:
        probe_args.append("--repair-r15-at-state-capture")
    if repair_epilogue_frame:
        probe_args.append("--repair-epilogue-frame")
    if repair_release_frame:
        probe_args.append("--repair-release-frame")
    return subprocess.Popen(
        probe_args,
        cwd=ROOT,
        stdout=stdout_log.open("w", encoding="utf-8"),
        stderr=stderr_log.open("w", encoding="utf-8"),
        text=True,
    )


def start_waiting_trace(
    *,
    script_name: str,
    timestamp: str,
    duration_seconds: int,
    wait_timeout_seconds: float,
    output_root: Path,
    extra_args: list[str] | None = None,
) -> dict:
    STARTUP_CAPTURE_ROOT.mkdir(parents=True, exist_ok=True)
    run_prefix = STARTUP_CAPTURE_ROOT / f"{timestamp}-{script_name.replace('.py', '')}"
    stdout_log = run_prefix.with_suffix(".stdout.log")
    stderr_log = run_prefix.with_suffix(".stderr.log")
    process = subprocess.Popen(
        [
            sys.executable,
            str(TOOLS / script_name),
            "--process-name",
            "rs2client",
            "--ignore-existing-processes",
            "--wait-timeout-seconds",
            str(wait_timeout_seconds),
            "--duration-seconds",
            str(duration_seconds),
            "--output-root",
            str(output_root),
            *(extra_args or []),
        ],
        cwd=ROOT,
        stdout=stdout_log.open("w", encoding="utf-8"),
        stderr=stderr_log.open("w", encoding="utf-8"),
        text=True,
    )
    return {
        "Process": process,
        "ScriptName": script_name,
        "OutputRoot": str(output_root),
        "LatestJsonlPath": str(output_root / "latest-client-only.jsonl"),
        "LatestSummaryPath": str(output_root / "latest-client-only.json"),
        "StdoutLog": str(stdout_log),
        "StderrLog": str(stderr_log),
    }


def capture_window(pid: int, timestamp: str, label: str) -> Path | None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    output = SCREENSHOT_DIR / f"rs2client-cycle-{timestamp}-{pid}-{label}.png"
    result = subprocess.run(
        [sys.executable, str(TOOLS / "capture_window.py"), "--pid", str(pid), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return output


def newest_dump_after(started_at: float) -> Path | None:
    dumps = sorted(USERDUMP_ROOT.rglob("*.dmp"), key=lambda item: item.stat().st_mtime, reverse=True)
    for dump in dumps:
        if dump.stat().st_mtime >= started_at:
            return dump
    return None


def build_gate_trace_extra_args(args: argparse.Namespace) -> list[str]:
    gate_extra_args: list[str] = []
    if args.gate_force_record21_on_open:
        gate_extra_args.append("--force-record21-on-open")
    if args.gate_force_recorde_on_open:
        gate_extra_args.append("--force-recorde-on-open")
    if args.gate_force_recorde_on_dispatch_return:
        gate_extra_args.append("--force-recorde-on-dispatch-return")
    if args.gate_force_finalize_on_dispatch_return:
        gate_extra_args.append("--force-finalize-on-dispatch-return")
    if args.gate_force_recordd_clear_on_dispatch_return:
        gate_extra_args.append("--force-recordd-clear-on-dispatch-return")
    if args.gate_force_owner_stage_clear_when_drained:
        gate_extra_args.append("--force-owner-stage-clear-when-drained")
    if args.gate_force_record_open_on_field1c:
        gate_extra_args.append("--force-record-open-on-field1c")
    if args.gate_force_seed_dispatch_on_ptr178:
        gate_extra_args.append("--force-seed-dispatch-on-ptr178")
    if args.gate_force_recordd_ready_on_ptr178:
        gate_extra_args.append("--force-recordd-ready-on-ptr178")
    if args.gate_force_recordd_ready_on_latch_clear:
        gate_extra_args.append("--force-recordd-ready-on-latch-clear")
    if args.gate_force_recordd_ready_on_close_suppression:
        gate_extra_args.append("--force-recordd-ready-on-close-suppression")
    if args.gate_force_selector_ready_on_ptr178:
        gate_extra_args.append("--force-selector-ready-on-ptr178")
    if args.gate_force_direct_dispatch_on_state1:
        gate_extra_args.append("--force-direct-dispatch-on-state1")
    if args.gate_force_dispatch_provider_accept:
        gate_extra_args.append("--force-dispatch-provider-accept")
    if args.gate_force_dispatch_result_metadata_fallback:
        gate_extra_args.append("--force-dispatch-result-metadata-fallback")
    if args.gate_force_post_dispatch_release_callback_fallback:
        gate_extra_args.append("--force-post-dispatch-release-callback-fallback")
    if args.gate_force_owner_stage_open_on_state1:
        gate_extra_args.append("--force-owner-stage-open-on-state1")
    if args.gate_force_prepared_selector_ready:
        gate_extra_args.append("--force-prepared-selector-ready")
    if args.gate_demote_hot_donezero_queued_record:
        gate_extra_args.append("--demote-hot-donezero-queued-record")
    if args.gate_force_idle_selector_latch_clear:
        gate_extra_args.append("--force-idle-selector-latch-clear")
    if args.gate_force_idle_selector_timer_open:
        gate_extra_args.append("--force-idle-selector-timer-open")
    if args.gate_force_idle_selector_queue_empty:
        gate_extra_args.append("--force-idle-selector-queue-empty")
    if args.gate_force_post_select_flag20_on_busy:
        gate_extra_args.append("--force-post-select-flag20-on-busy")
    if args.gate_force_post_select_status_retval is not None:
        gate_extra_args.extend(
            ["--force-post-select-status-retval", str(args.gate_force_post_select_status_retval)]
        )
    if args.gate_force_post_select_publication_success:
        gate_extra_args.append("--force-post-select-publication-success")
    if args.gate_suppress_post_select_latch_clear:
        gate_extra_args.append("--suppress-post-select-latch-clear")
    if args.gate_suppress_record_close_bulk_pass:
        for caller_rva in DEFAULT_GATE_RECORD_CLOSE_BULK_CALLER_RVAS:
            gate_extra_args.extend(["--suppress-record-close-call-rva", caller_rva])
    for caller_rva in args.gate_suppress_record_close_call_rva:
        gate_extra_args.extend(["--suppress-record-close-call-rva", str(caller_rva)])
    if args.gate_force_item_payload_from_ptr178:
        gate_extra_args.append("--force-item-payload-from-ptr178")
    if args.gate_force_type0_descriptor_status_retval is not None:
        gate_extra_args.extend(
            [
                "--force-type0-descriptor-status-retval",
                str(args.gate_force_type0_descriptor_status_retval),
            ]
        )
    if args.gate_force_type0_childminus1_bypass:
        gate_extra_args.append("--force-type0-childminus1-bypass")
    if args.gate_force_type0_field18_to_2:
        gate_extra_args.append("--force-type0-field18-to-2")
    if args.gate_force_type0_raw_source_from_ptr178:
        gate_extra_args.append("--force-type0-raw-source-from-ptr178")
    if args.gate_force_type0_zlb_source_from_ptr178:
        gate_extra_args.append("--force-type0-zlb-source-from-ptr178")
    if args.gate_force_type0_requested_length_from_source_header:
        gate_extra_args.append("--force-type0-requested-length-from-source-header")
    if args.gate_force_type0_source_object_from_side_slots:
        gate_extra_args.append("--force-type0-source-object-from-side-slots")
    if args.gate_force_type0_inner_source_from_side_wrapper:
        gate_extra_args.append("--force-type0-inner-source-from-side-wrapper")
    if args.gate_force_type0_parser_single_byte_payload_to_1:
        gate_extra_args.append("--force-type0-parser-single-byte-payload-to-1")
    if args.gate_force_queue_helper_resolver_synthetic_success:
        gate_extra_args.append("--force-queue-helper-resolver-synthetic-success")
    if args.gate_force_queue_helper_post_parser_cleanup_suppression:
        gate_extra_args.append("--force-queue-helper-post-parser-cleanup-suppression")
    if args.gate_force_queue_helper_return_slot_restore:
        gate_extra_args.append("--force-queue-helper-return-slot-restore")
    if args.gate_force_type0_handler_return_slot_restore:
        gate_extra_args.append("--force-type0-handler-return-slot-restore")
    if args.gate_force_recordstate_from_type0:
        gate_extra_args.append("--force-recordstate-from-type0")
    if args.gate_force_type0_prepare_branch:
        gate_extra_args.append("--force-type0-prepare-branch")
    if args.gate_force_type3_followon_on_post_state1:
        gate_extra_args.append("--force-type3-followon-on-post-state1")
    if args.gate_force_finalize_after_type3_on_post_state1:
        gate_extra_args.append("--force-finalize-after-type3-on-post-state1")
    if args.gate_reenter_recordstate_after_type3_on_post_state1:
        gate_extra_args.append("--reenter-recordstate-after-type3-on-post-state1")
    return gate_extra_args


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.kill_existing_client:
        kill_existing_clients()
    if args.clear_artifacts:
        clear_artifacts()

    started_at = time.time()
    userdump_info = start_userdump(dump_on_terminate=args.userdump_on_terminate)

    resource_gate_trace: dict | None = None
    resource_state_trace: dict | None = None
    resource_bridge_trace: dict | None = None
    producer_trace: dict | None = None
    loading_gate_trace: dict | None = None
    loading_state_builder_trace: dict | None = None
    table_lifecycle_trace: dict | None = None
    if args.resource_gate_trace:
        gate_extra_args = build_gate_trace_extra_args(args)
        resource_gate_trace = start_waiting_trace(
            script_name="trace_947_application_resource_gate.py",
            timestamp=f"{timestamp}-gate",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=APPLICATION_RESOURCE_GATE_ROOT,
            extra_args=gate_extra_args,
        )
    if args.resource_state_trace:
        resource_state_trace = start_waiting_trace(
            script_name="trace_947_application_resource_state.py",
            timestamp=f"{timestamp}-state",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=APPLICATION_RESOURCE_STATE_ROOT,
        )
    if args.resource_bridge_trace:
        bridge_extra_args: list[str] = []
        if args.bridge_force_state1_on_ptr178:
            bridge_extra_args.append("--force-state1-on-ptr178")
        if args.bridge_force_selector_ready_on_ptr178:
            bridge_extra_args.append("--force-selector-ready-on-ptr178")
        if args.bridge_force_owner_11d4a_open_on_special20:
            bridge_extra_args.append("--force-owner-11d4a-open-on-special20")
        if args.bridge_force_seed_dispatch_on_state1:
            bridge_extra_args.append("--force-seed-dispatch-on-state1")
        if args.bridge_force_recordstate_on_state1:
            bridge_extra_args.append("--force-recordstate-on-state1")
        if args.bridge_force_direct_dispatch_on_state1:
            bridge_extra_args.append("--force-direct-dispatch-on-state1")
        if args.bridge_force_finalize_on_state1:
            bridge_extra_args.append("--force-finalize-on-state1")
        resource_bridge_trace = start_waiting_trace(
            script_name="trace_947_application_resource_bridge.py",
            timestamp=f"{timestamp}-bridge",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=APPLICATION_RESOURCE_BRIDGE_ROOT,
            extra_args=bridge_extra_args,
        )
    if args.producer_trace:
        producer_trace = start_waiting_trace(
            script_name="trace_947_prelogin_producer_path.py",
            timestamp=f"{timestamp}-producer",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=PRELOGIN_PRODUCER_ROOT,
        )
    if args.loading_gate_trace:
        loading_gate_trace = start_waiting_trace(
            script_name="trace_947_loading_gate.py",
            timestamp=f"{timestamp}-loading-gate",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=LOADING_GATE_ROOT,
        )
    if args.loading_state_builder_trace:
        loading_state_builder_trace = start_waiting_trace(
            script_name="trace_947_loading_state_builder.py",
            timestamp=f"{timestamp}-loading-state-builder",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=LOADING_STATE_BUILDER_ROOT,
        )
    if args.table_lifecycle_trace:
        table_extra_args: list[str] = []
        if args.table_null_source_vector:
            table_extra_args.append("--null-source-vector")
        if args.table_force_length_gate_0x41:
            table_extra_args.append("--force-length-gate-0x41")
        if args.table_skip_compare_failure:
            table_extra_args.append("--skip-compare-failure")
        if args.table_mirror_compare_left_into_right:
            table_extra_args.append("--mirror-compare-left-into-right")
        if args.table_inject_null_master_table:
            table_extra_args.append("--inject-null-master-table")
        if args.table_inject_null_master_table_count != 67:
            table_extra_args.extend(
                ["--inject-null-master-table-count", str(args.table_inject_null_master_table_count)]
            )
        table_lifecycle_trace = start_waiting_trace(
            script_name="trace_947_table_lifecycle.py",
            timestamp=f"{timestamp}-table-lifecycle",
            duration_seconds=args.resource_trace_duration_seconds,
            wait_timeout_seconds=args.resource_trace_wait_timeout_seconds,
            output_root=TABLE_LIFECYCLE_ROOT,
            extra_args=table_extra_args,
        )

    launcher_process, launcher_stdout, launcher_stderr = start_launcher(timestamp, args.launcher_arg)

    deadline = time.time() + args.timeout_seconds
    main_pid = wait_for_main_pid(deadline, launcher_stdout_log=launcher_stdout)

    probe_process: subprocess.Popen[str] | None = None
    if not args.skip_probe:
        probe_process = start_probe(
            main_pid,
            f"{timestamp}-cycle",
            args.probe_duration_seconds,
            function_start_rva=args.probe_function_start_rva,
            fault_rva=args.probe_fault_rva,
                state_capture_rva=args.probe_state_capture_rva,
                repair_r15_at_state_capture=args.probe_repair_r15_at_state_capture,
                repair_epilogue_frame=args.probe_repair_epilogue_frame,
                repair_release_frame=args.probe_repair_release_frame,
            )
    window_capture_path = None
    window_capture_paths: list[str] = []
    if args.window_capture:
        time.sleep(2.0)
        first_capture = capture_window(main_pid, timestamp, "start")
        if first_capture is not None:
            window_capture_path = first_capture
            window_capture_paths.append(str(first_capture))

    next_window_capture_at = time.time() + max(1, args.window_capture_interval_seconds)

    client_exited = False
    while time.time() < deadline:
        if not process_exists(main_pid):
            client_exited = True
            break
        if args.window_capture and time.time() >= next_window_capture_at:
            capture_index = len(window_capture_paths)
            capture_path = capture_window(main_pid, timestamp, f"step{capture_index:02d}")
            if capture_path is not None:
                if window_capture_path is None:
                    window_capture_path = capture_path
                window_capture_paths.append(str(capture_path))
            next_window_capture_at = time.time() + max(1, args.window_capture_interval_seconds)
        time.sleep(0.5)

    if probe_process is not None:
        try:
            probe_process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            probe_process.kill()

    for trace in (
        resource_gate_trace,
        resource_state_trace,
        resource_bridge_trace,
        producer_trace,
        loading_gate_trace,
        loading_state_builder_trace,
        table_lifecycle_trace,
    ):
        if trace is None:
            continue
        process = trace["Process"]
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()

    try:
        launcher_process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        launcher_process.kill()

    summary = {
        "mainPid": main_pid,
        "clientExited": client_exited,
        "hookPath": str(HOOK_PATH),
        "summaryPath": str(SUMMARY_PATH),
        "transportPath": str(TRANSPORT_PATH),
        "probeLatestPath": None if args.skip_probe else str(PROBE_LATEST),
        "probeFunctionStartRva": None if args.skip_probe else args.probe_function_start_rva,
        "probeFaultRva": None if args.skip_probe else args.probe_fault_rva,
        "probeStateCaptureRva": None if args.skip_probe else args.probe_state_capture_rva,
        "probeRepairR15AtStateCapture": False if args.skip_probe else args.probe_repair_r15_at_state_capture,
        "probeRepairEpilogueFrame": False if args.skip_probe else args.probe_repair_epilogue_frame,
        "probeRepairReleaseFrame": False if args.skip_probe else args.probe_repair_release_frame,
        "windowCapturePath": str(window_capture_path) if window_capture_path else None,
        "windowCapturePaths": window_capture_paths,
        "newestDumpPath": str(newest_dump_after(started_at)) if newest_dump_after(started_at) else None,
        "launcherStdoutLog": str(launcher_stdout),
        "launcherStderrLog": str(launcher_stderr),
        "userdumpInfo": userdump_info,
        "resourceGateTrace": None
        if resource_gate_trace is None
        else {
            "ScriptName": resource_gate_trace["ScriptName"],
            "OutputRoot": resource_gate_trace["OutputRoot"],
            "LatestJsonlPath": resource_gate_trace["LatestJsonlPath"],
            "LatestSummaryPath": resource_gate_trace["LatestSummaryPath"],
            "StdoutLog": resource_gate_trace["StdoutLog"],
            "StderrLog": resource_gate_trace["StderrLog"],
            "TracePid": resource_gate_trace["Process"].pid,
            "TraceExitCode": resource_gate_trace["Process"].returncode,
        },
        "resourceStateTrace": None
        if resource_state_trace is None
        else {
            "ScriptName": resource_state_trace["ScriptName"],
            "OutputRoot": resource_state_trace["OutputRoot"],
            "LatestJsonlPath": resource_state_trace["LatestJsonlPath"],
            "LatestSummaryPath": resource_state_trace["LatestSummaryPath"],
            "StdoutLog": resource_state_trace["StdoutLog"],
            "StderrLog": resource_state_trace["StderrLog"],
            "TracePid": resource_state_trace["Process"].pid,
            "TraceExitCode": resource_state_trace["Process"].returncode,
        },
        "resourceBridgeTrace": None
        if resource_bridge_trace is None
        else {
            "ScriptName": resource_bridge_trace["ScriptName"],
            "OutputRoot": resource_bridge_trace["OutputRoot"],
            "LatestJsonlPath": resource_bridge_trace["LatestJsonlPath"],
            "LatestSummaryPath": resource_bridge_trace["LatestSummaryPath"],
            "StdoutLog": resource_bridge_trace["StdoutLog"],
            "StderrLog": resource_bridge_trace["StderrLog"],
            "TracePid": resource_bridge_trace["Process"].pid,
            "TraceExitCode": resource_bridge_trace["Process"].returncode,
        },
        "producerTrace": None
        if producer_trace is None
        else {
            "ScriptName": producer_trace["ScriptName"],
            "OutputRoot": producer_trace["OutputRoot"],
            "LatestJsonlPath": producer_trace["LatestJsonlPath"],
            "LatestSummaryPath": producer_trace["LatestSummaryPath"],
            "StdoutLog": producer_trace["StdoutLog"],
            "StderrLog": producer_trace["StderrLog"],
            "TracePid": producer_trace["Process"].pid,
            "TraceExitCode": producer_trace["Process"].returncode,
        },
        "loadingGateTrace": None
        if loading_gate_trace is None
        else {
            "ScriptName": loading_gate_trace["ScriptName"],
            "OutputRoot": loading_gate_trace["OutputRoot"],
            "LatestJsonlPath": loading_gate_trace["LatestJsonlPath"],
            "LatestSummaryPath": loading_gate_trace["LatestSummaryPath"],
            "StdoutLog": loading_gate_trace["StdoutLog"],
            "StderrLog": loading_gate_trace["StderrLog"],
            "TracePid": loading_gate_trace["Process"].pid,
            "TraceExitCode": loading_gate_trace["Process"].returncode,
        },
        "loadingStateBuilderTrace": None
        if loading_state_builder_trace is None
        else {
            "ScriptName": loading_state_builder_trace["ScriptName"],
            "OutputRoot": loading_state_builder_trace["OutputRoot"],
            "LatestJsonlPath": loading_state_builder_trace["LatestJsonlPath"],
            "LatestSummaryPath": loading_state_builder_trace["LatestSummaryPath"],
            "StdoutLog": loading_state_builder_trace["StdoutLog"],
            "StderrLog": loading_state_builder_trace["StderrLog"],
            "TracePid": loading_state_builder_trace["Process"].pid,
            "TraceExitCode": loading_state_builder_trace["Process"].returncode,
        },
        "tableLifecycleTrace": None
        if table_lifecycle_trace is None
        else {
            "ScriptName": table_lifecycle_trace["ScriptName"],
            "OutputRoot": table_lifecycle_trace["OutputRoot"],
            "LatestJsonlPath": table_lifecycle_trace["LatestJsonlPath"],
            "LatestSummaryPath": table_lifecycle_trace["LatestSummaryPath"],
            "StdoutLog": table_lifecycle_trace["StdoutLog"],
            "StderrLog": table_lifecycle_trace["StderrLog"],
            "TracePid": table_lifecycle_trace["Process"].pid,
            "TraceExitCode": table_lifecycle_trace["Process"].returncode,
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
