from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
TOOLS = WORKSPACE / "tools"
DEBUG_ROOT = WORKSPACE / "data" / "debug"
DIRECT_PATCH_TOOL = TOOLS / "launch_rs2client_direct_patch.py"
CAPTURE_WINDOW_TOOL = TOOLS / "capture_window.py"
INSPECT_SCREENSHOT_TOOL = TOOLS / "inspect_runescape_screenshot.py"
PATCHED_CLIENT = WORKSPACE / "data" / "clients" / "947" / "win64c" / "patched" / "rs2client.exe"
ORIGINAL_CLIENT = WORKSPACE / "data" / "clients" / "947" / "win64c" / "original" / "rs2client.exe"
RSA_CONFIG = WORKSPACE / "data" / "config" / "rsa.toml"
SESSION_ROOT = DEBUG_ROOT / "lobby-tls-terminator"
OUTPUT_ROOT = DEBUG_ROOT / "inline-subset-probe-947"
DEFAULT_CONFIG_URL = (
    "https://rs.config.runescape.com/k=5/l=0/jav_config.ws"
    "?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
    "&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0&downloadMetadataSource=live"
)
DEFAULT_REDIRECTS = [
    "content.runescape.com=localhost",
    "lobby*.runescape.com=localhost",
    "world*.runescape.com=localhost",
]
DEFAULT_JUMP_BYPASSES = [
    "0x59002d:0x5900a5",
    "0x5902d5:0x5903bd",
    "0x590c58:0x590c81",
]


@dataclass
class SessionSummary:
    path: Path
    route_source: str | None
    remote: str | None
    raw_client_to_remote: int | None
    remote_to_raw_client: int | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Launch one contained 947 direct-patch inline subset, capture the RuneTekApp window, "
            "and summarize just the new lobby-tls-terminator raw-js5 sessions."
        )
    )
    parser.add_argument(
        "--patch-inline-offset",
        action="append",
        default=[],
        help="Repeatable inline patch offset (hex or decimal).",
    )
    parser.add_argument(
        "--patch-jump-bypass",
        action="append",
        default=[],
        help="Repeatable jump-bypass spec (source:target). Defaults to the current client-only startup trio.",
    )
    parser.add_argument(
        "--resolve-redirect",
        action="append",
        default=[],
        help="Repeatable host=target redirect. Defaults to content/lobby/world localhost containment.",
    )
    parser.add_argument(
        "--label",
        help="Optional run label. Defaults to offsets joined with '-'.",
    )
    parser.add_argument(
        "--config-url",
        default=DEFAULT_CONFIG_URL,
        help="Config URL to pass to the direct client.",
    )
    parser.add_argument(
        "--monitor-seconds",
        type=float,
        default=5.0,
        help="Direct-patch monitor window for the spawned process.",
    )
    parser.add_argument(
        "--capture-after-seconds",
        type=float,
        default=20.0,
        help="Delay before the first window capture.",
    )
    parser.add_argument(
        "--late-capture-after-seconds",
        type=float,
        default=50.0,
        help="Delay before the second window capture.",
    )
    parser.add_argument(
        "--allow-retail-js5-upstream",
        action="store_true",
        default=True,
        help="Keep raw JS5/content passthrough to retail upstream enabled.",
    )
    return parser.parse_args()


def make_label(offsets: list[str]) -> str:
    if not offsets:
        return "no-inline"
    return "inline-" + "-".join(offset.lower().replace("0x", "") for offset in offsets)


def run_json_command(command: list[str]) -> Any:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        cwd=str(WORKSPACE),
    )
    return json.loads(result.stdout)


def run_text_command(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        cwd=str(WORKSPACE),
    )
    return result.stdout


def kill_existing_rs2clients() -> None:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='rs2client.exe'\" | "
        "ForEach-Object { "
        "  try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {}"
        "}"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
    )
    time.sleep(2.0)


def capture_and_classify(pid: int, output_path: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(CAPTURE_WINDOW_TOOL),
        "--pid",
        str(pid),
        "--output",
        str(output_path),
    ]
    try:
        run_text_command(command)
    except subprocess.CalledProcessError as exc:
        return {
            "imagePath": str(output_path),
            "state": "capture-failed",
            "progressRatio": None,
            "detectedTexts": [],
            "captureError": exc.stderr.strip() or exc.stdout.strip() or str(exc),
        }
    return run_json_command([sys.executable, str(INSPECT_SCREENSHOT_TOOL), str(output_path)])


def parse_session_summary(path: Path) -> SessionSummary:
    route_source = None
    remote = None
    raw_client_to_remote = None
    remote_to_raw_client = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "raw-route-source=" in line:
            route_source = line.split("raw-route-source=", 1)[1].strip()
        elif "remote=" in line and "bytes " not in line:
            remote = line.split("remote=", 1)[1].strip()
        elif "bytes raw-client->remote=" in line:
            tail = line.split("bytes raw-client->remote=", 1)[1]
            raw_part, remote_part = tail.split(" remote->raw-client=")
            raw_client_to_remote = int(raw_part.strip())
            remote_to_raw_client = int(remote_part.strip())
    return SessionSummary(
        path=path,
        route_source=route_source,
        remote=remote,
        raw_client_to_remote=raw_client_to_remote,
        remote_to_raw_client=remote_to_raw_client,
    )


def snapshot_session_paths() -> set[Path]:
    if not SESSION_ROOT.exists():
        return set()
    return set(SESSION_ROOT.glob("session-*.log"))


def collect_new_sessions(start_time: datetime, before_paths: set[Path]) -> list[SessionSummary]:
    sessions: list[SessionSummary] = []
    if not SESSION_ROOT.exists():
        return sessions
    threshold = start_time.timestamp() - 2.0
    for path in sorted(SESSION_ROOT.glob("session-*.log")):
        if path in before_paths:
            continue
        if path.stat().st_mtime < threshold:
            continue
        sessions.append(parse_session_summary(path))
    return sessions


def main() -> int:
    args = parse_args()
    offsets = list(args.patch_inline_offset)
    label = args.label or make_label(offsets)
    run_root = OUTPUT_ROOT / label
    run_root.mkdir(parents=True, exist_ok=True)

    summary_path = run_root / f"{label}.json"
    trace_path = run_root / f"{label}.jsonl"
    hook_path = run_root / f"{label}-hook.jsonl"
    capture_now_path = run_root / f"{label}-now.png"
    capture_late_path = run_root / f"{label}-late.png"

    kill_existing_rs2clients()
    start_time = datetime.now(timezone.utc)
    before_session_paths = snapshot_session_paths()

    command = [
        sys.executable,
        str(DIRECT_PATCH_TOOL),
        "--client-exe",
        str(PATCHED_CLIENT),
        "--working-dir",
        str(PATCHED_CLIENT.parent),
        "--client-arg",
        args.config_url,
        "--summary-output",
        str(summary_path),
        "--trace-output",
        str(trace_path),
        "--startup-hook-output",
        str(hook_path),
        "--rsa-config",
        str(RSA_CONFIG),
        "--js5-rsa-source-exe",
        str(ORIGINAL_CLIENT),
        "--monitor-seconds",
        str(args.monitor_seconds),
    ]
    redirects = list(args.resolve_redirect) if args.resolve_redirect else list(DEFAULT_REDIRECTS)
    jump_bypasses = list(args.patch_jump_bypass) if args.patch_jump_bypass else list(DEFAULT_JUMP_BYPASSES)
    for redirect in redirects:
        command.extend(["--resolve-redirect", redirect])
    for offset in offsets:
        command.extend(["--patch-inline-offset", offset])
    for spec in jump_bypasses:
        command.extend(["--patch-jump-bypass", spec])

    subprocess.run(command, check=True, cwd=str(WORKSPACE))

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    pid = int(summary_payload["pid"])
    time.sleep(max(0.0, args.capture_after_seconds))
    first_capture = capture_and_classify(pid, capture_now_path)

    additional_delay = max(0.0, args.late_capture_after_seconds - args.capture_after_seconds)
    if additional_delay > 0:
        time.sleep(additional_delay)
    second_capture = capture_and_classify(pid, capture_late_path)

    sessions = collect_new_sessions(start_time, before_session_paths)
    raw_js5_sessions = [
        {
            "path": str(item.path),
            "remote": item.remote,
            "rawRouteSource": item.route_source,
            "rawClientToRemote": item.raw_client_to_remote,
            "remoteToRawClient": item.remote_to_raw_client,
        }
        for item in sessions
        if item.route_source == "raw-js5-retail"
    ]

    probe_summary = {
        "label": label,
        "startTimeUtc": start_time.isoformat(),
        "patchInlineOffsets": offsets,
        "patchJumpBypasses": jump_bypasses,
        "resolveRedirects": redirects,
        "directPatchSummaryPath": str(summary_path),
        "directPatchTracePath": str(trace_path),
        "startupHookPath": str(hook_path),
        "pid": pid,
        "firstCapture": first_capture,
        "firstCapturePath": str(capture_now_path),
        "secondCapture": second_capture,
        "secondCapturePath": str(capture_late_path),
        "rawJs5RetailSessions": raw_js5_sessions,
        "rawJs5RetailSessionCount": len(raw_js5_sessions),
        "rawJs5RetailBytesTotal": sum(item.get("remoteToRawClient") or 0 for item in raw_js5_sessions),
    }
    probe_summary_path = run_root / f"{label}-probe-summary.json"
    probe_summary_path.write_text(json.dumps(probe_summary, indent=2), encoding="utf-8")
    print(json.dumps(probe_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
