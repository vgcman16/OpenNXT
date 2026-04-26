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
TABLE_LIFECYCLE_LATEST = DEBUG_ROOT / "table-lifecycle-947" / "latest-client-only.jsonl"
SCREENSHOT_DIR = DEBUG_ROOT / "screenshots"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one 947 client-only cycle with table-lifecycle tracing.")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--trace-duration-seconds", type=int, default=120)
    parser.add_argument("--window-capture", action="store_true")
    parser.add_argument("--window-capture-interval-seconds", type=int, default=30)
    parser.add_argument("--clear-artifacts", action="store_true")
    parser.add_argument("--kill-existing-client", action="store_true")
    parser.add_argument(
        "--launcher-arg",
        action="append",
        default=[],
        help="Extra argument token to pass through to launch-client-only.ps1. Repeat for multiple tokens.",
    )
    parser.add_argument(
        "--table-lifecycle-arg",
        action="append",
        default=[],
        help="Extra argument token to pass through to trace_947_table_lifecycle.py. Repeat for multiple tokens.",
    )
    return parser.parse_args()


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
    for path in (HOOK_PATH, SUMMARY_PATH, TRANSPORT_PATH, TABLE_LIFECYCLE_LATEST):
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


def wait_for_main_pid(deadline: float) -> int | None:
    while time.time() < deadline:
        for event in read_hook_events():
            if event.get("action") == "exception-handler-installed" and event.get("pid"):
                return int(event["pid"])
        time.sleep(0.5)
    return None


def process_exists(pid: int) -> bool:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() == str(pid)


def start_launcher(timestamp: str, launcher_args: list[str]) -> tuple[subprocess.Popen[str], Path, Path]:
    stdout_log = ROOT / f"tmp-client-only-table-lifecycle-{timestamp}.stdout.log"
    stderr_log = ROOT / f"tmp-client-only-table-lifecycle-{timestamp}.stderr.log"
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


def start_table_lifecycle_tracer(timestamp: str, duration_seconds: int, extra_args: list[str]) -> tuple[subprocess.Popen[str], Path, Path]:
    stdout_log = ROOT / f"tmp-table-lifecycle-cycle-{timestamp}.stdout.log"
    stderr_log = ROOT / f"tmp-table-lifecycle-cycle-{timestamp}.stderr.log"
    return (
        subprocess.Popen(
            [
                sys.executable,
                str(TOOLS / "trace_947_table_lifecycle.py"),
                "--process-name",
                "rs2client",
                "--ignore-existing-processes",
                "--duration-seconds",
                str(duration_seconds),
                *extra_args,
            ],
            cwd=ROOT,
            stdout=stdout_log.open("w", encoding="utf-8"),
            stderr=stderr_log.open("w", encoding="utf-8"),
            text=True,
        ),
        stdout_log,
        stderr_log,
    )


def capture_window(pid: int, timestamp: str, label: str) -> Path | None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    output = SCREENSHOT_DIR / f"rs2client-table-lifecycle-{timestamp}-{pid}-{label}.png"
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


def read_json_file(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def main() -> int:
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    if args.kill_existing_client:
        kill_existing_clients()
    if args.clear_artifacts:
        clear_artifacts()

    tracer_process, tracer_stdout, tracer_stderr = start_table_lifecycle_tracer(
        timestamp,
        args.trace_duration_seconds,
        list(args.table_lifecycle_arg),
    )
    launcher_process, launcher_stdout, launcher_stderr = start_launcher(timestamp, list(args.launcher_arg))

    deadline = time.time() + args.timeout_seconds
    main_pid = wait_for_main_pid(deadline)
    screenshot_paths: list[str] = []

    if args.window_capture and main_pid is not None:
        while time.time() < deadline and process_exists(main_pid):
            elapsed = int(round(args.timeout_seconds - max(0.0, deadline - time.time())))
            label = f"t{elapsed:03d}s"
            output = capture_window(main_pid, timestamp, label)
            if output is not None:
                screenshot_paths.append(str(output))
            time.sleep(args.window_capture_interval_seconds)

    try:
        tracer_process.wait(timeout=max(30, args.trace_duration_seconds + 15))
    except subprocess.TimeoutExpired:
        tracer_process.kill()

    try:
        launcher_process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        launcher_process.kill()

    latest_summary = read_json_file(SUMMARY_PATH)
    client_pid = None
    if latest_summary and latest_summary.get("ClientPid"):
        try:
            client_pid = int(latest_summary["ClientPid"])
        except (TypeError, ValueError):
            client_pid = None
    if client_pid is None:
        client_pid = main_pid

    summary = {
        "mainPid": main_pid,
        "clientPid": client_pid,
        "clientExited": False if client_pid is None else (not process_exists(client_pid)),
        "launcherArgs": list(args.launcher_arg),
        "tableLifecycleArgs": list(args.table_lifecycle_arg),
        "launcherStdoutLog": str(launcher_stdout),
        "launcherStderrLog": str(launcher_stderr),
        "tableLifecycleStdoutLog": str(tracer_stdout),
        "tableLifecycleStderrLog": str(tracer_stderr),
        "latestHookPath": str(HOOK_PATH),
        "latestSummaryPath": str(SUMMARY_PATH),
        "latestTableLifecyclePath": str(TABLE_LIFECYCLE_LATEST),
        "transportPath": str(TRANSPORT_PATH),
        "screenshotPaths": screenshot_paths,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
