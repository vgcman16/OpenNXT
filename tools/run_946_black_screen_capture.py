from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from collections import Counter

from protocol_automation_common import SHARED_DIR, WORKSPACE, ensure_directory, load_json, standard_tool_artifact, write_json
from protocol_946_debug_common import WORLD_LOG_DEFAULT, load_all_sessions
from run_946_scene_delivery_aid import (
    DEFAULT_CONTENT_CAPTURE_DIR,
    DEFAULT_JS5_SESSION_DIR,
    DEFAULT_RUNTIME_TRACE_DIR,
    SCENE_DELIVERY_JSON,
)
from run_946_tool_doctor import TOOL_DOCTOR_JSON


BLACK_SCREEN_CAPTURE_JSON = "black-screen-capture.json"
BLACK_SCREEN_CAPTURE_MD = "black-screen-capture.md"
POWERSHELL_EXE = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
LAUNCH_SCRIPT = WORKSPACE / "tools" / "launch-win64c-live.ps1"
RESET_CACHE_SCRIPT = WORKSPACE / "tools" / "reset_jagex_cache.ps1"
TRACE_PROCESS_SCRIPT = WORKSPACE / "tools" / "trace_process_runtime.py"
OPENNXT_BAT = WORKSPACE / "build" / "install" / "OpenNXT" / "bin" / "OpenNXT.bat"
LAUNCH_STATE_FILE = WORKSPACE / "tmp-launch-win64c-live.state.json"
DEFAULT_CAPTURE_SECONDS = 45
DEFAULT_RUNTIME_TRACE_SECONDS = 45
DEFAULT_JS5_IDLE_TIMEOUT_SECONDS = 20
LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost"}
DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON = WORKSPACE / "data" / "debug" / "client-live-watch" / "latest-summary.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch a manual-login 946 black-screen capture and bundle scene-delivery evidence."
    )
    parser.add_argument("--capture-seconds", type=int, default=DEFAULT_CAPTURE_SECONDS)
    parser.add_argument("--runtime-trace-seconds", type=int, default=DEFAULT_RUNTIME_TRACE_SECONDS)
    parser.add_argument("--js5-idle-timeout-seconds", type=int, default=DEFAULT_JS5_IDLE_TIMEOUT_SECONDS)
    parser.add_argument("--reset-cache", action="store_true")
    parser.add_argument("--client-variant", choices=("patched", "original"), default="patched")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--js5-session-dir", type=Path, default=DEFAULT_JS5_SESSION_DIR)
    parser.add_argument("--content-capture-dir", type=Path, default=DEFAULT_CONTENT_CAPTURE_DIR)
    parser.add_argument("--runtime-trace-dir", type=Path, default=DEFAULT_RUNTIME_TRACE_DIR)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    return parser.parse_args()


def required_paths() -> dict[str, Path]:
    return {
        "launchScript": LAUNCH_SCRIPT,
        "traceProcessScript": TRACE_PROCESS_SCRIPT,
        "openNxtBat": OPENNXT_BAT,
    }


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "json": output_dir / BLACK_SCREEN_CAPTURE_JSON,
        "markdown": output_dir / BLACK_SCREEN_CAPTURE_MD,
    }


def run_command(command: list[str], *, cwd: Path, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def start_process(command: list[str], *, cwd: Path) -> subprocess.Popen[str]:
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def kill_pid(pid: int | None) -> None:
    if not pid:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/F"],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def extract_client_config_url(launch_state: dict[str, Any]) -> str:
    client_args = launch_state.get("ClientArgs")
    if not isinstance(client_args, list):
        return ""
    for index, value in enumerate(client_args):
        if not isinstance(value, str):
            continue
        if value in {"--configURI", "--configUrl", "--config-url"} and index + 1 < len(client_args):
            candidate = client_args[index + 1]
            if isinstance(candidate, str):
                return candidate
        if value.startswith("http://") or value.startswith("https://"):
            return value
    return ""


def normalize_host(value: str) -> str:
    host = value.strip().strip("[]").lower()
    if "%" in host:
        host = host.split("%", 1)[0]
    return host


def parse_endpoint(endpoint: str) -> tuple[str, int | None]:
    endpoint = endpoint.strip()
    if not endpoint:
        return "", None
    if endpoint.startswith("[") and "]:" in endpoint:
        host, port = endpoint[1:].split("]:", 1)
        return normalize_host(host), int(port) if port.isdigit() else None
    if ":" not in endpoint:
        return normalize_host(endpoint), None
    host, port = endpoint.rsplit(":", 1)
    return normalize_host(host), int(port) if port.isdigit() else None


def is_local_host(host: str) -> bool:
    normalized = normalize_host(host)
    return normalized in LOCALHOST_HOSTS or normalized in {"0.0.0.0", "::"}


def collect_client_network_snapshot(client_pid: int) -> dict[str, Any]:
    completed = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        check=False,
    )
    connections: list[dict[str, Any]] = []
    local_mitm_connections = 0
    direct_external_443_connections = 0
    for raw_line in completed.stdout.splitlines():
        line = raw_line.strip()
        if not line.startswith("TCP "):
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            owning_pid = int(parts[4])
        except ValueError:
            continue
        if owning_pid != client_pid:
            continue
        local_host, local_port = parse_endpoint(parts[1])
        remote_host, remote_port = parse_endpoint(parts[2])
        state = parts[3]
        connection = {
            "localAddress": local_host,
            "localPort": local_port,
            "remoteAddress": remote_host,
            "remotePort": remote_port,
            "state": state,
        }
        connections.append(connection)
        if remote_port == 443:
            if is_local_host(remote_host):
                local_mitm_connections += 1
            else:
                direct_external_443_connections += 1
    return {
        "clientPid": client_pid,
        "commandReturnCode": completed.returncode,
        "connections": connections,
        "localMitm443ConnectionCount": local_mitm_connections,
        "directExternal443ConnectionCount": direct_external_443_connections,
        "directExternal443Targets": sorted(
            {
                f"{connection['remoteAddress']}:{connection['remotePort']}"
                for connection in connections
                if connection.get("remotePort") == 443 and not is_local_host(connection.get("remoteAddress", ""))
            }
        ),
    }


def summarize_recent_content_sessions(content_capture_dir: Path, *, since_epoch: float) -> dict[str, Any]:
    recent_sessions = sorted(
        path for path in content_capture_dir.glob("session-*.log") if path.exists() and path.stat().st_mtime >= since_epoch
    )
    fresh_tls_session_count = 0
    local_ms_requests_observed = False
    session_route_counts: Counter[str] = Counter()
    session_summaries: list[dict[str, Any]] = []
    for path in recent_sessions:
        text = path.read_text(encoding="utf-8", errors="ignore")
        route = ""
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if "session-route=" in line:
                route = line.split("session-route=", 1)[1].split(" ", 1)[0].strip()
                break
        is_tls = "mode=tls" in text or route.startswith("tls-")
        has_ms_request = "/ms?" in text
        if is_tls:
            fresh_tls_session_count += 1
        if has_ms_request:
            local_ms_requests_observed = True
        if route:
            session_route_counts[route] += 1
        session_summaries.append(
            {
                "file": str(path),
                "tls": is_tls,
                "sessionRoute": route,
                "msRequestObserved": has_ms_request,
            }
        )
    latest_session = recent_sessions[-1] if recent_sessions else None
    return {
        "freshSessionCount": len(recent_sessions),
        "freshTlsSessionCount": fresh_tls_session_count,
        "sessionRouteCounts": dict(session_route_counts),
        "localMsRequestsObserved": local_ms_requests_observed,
        "latestSessionLog": str(latest_session) if latest_session else "",
        "sessions": session_summaries,
    }


def summarize_live_watch(world_window: str | None) -> dict[str, Any]:
    payload = load_json(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON, {}) or {}
    if not isinstance(payload, dict) or not payload:
        return {"present": False, "path": str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON)}
    summary = payload.get("summary") or {}
    if world_window and summary.get("worldWindowSelected") not in {"", None, world_window}:
        return {"present": False, "path": str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON)}
    return {
        "present": True,
        "path": str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON),
        "terminalState": summary.get("terminalState"),
        "deepHooksEnabled": summary.get("deepHooksEnabled"),
        "worldWindowSelected": summary.get("worldWindowSelected"),
        "localContentMitmObserved": summary.get("localContentMitmObserved", False),
        "localMsRequestsObserved": summary.get("localMsRequestsObserved", False),
        "proxyRawGameObserved": summary.get("proxyRawGameObserved", False),
        "proxySecureGameTlsObserved": summary.get("proxySecureGameTlsObserved", False),
        "proxySecureGamePassthroughObserved": summary.get("proxySecureGamePassthroughObserved", False),
        "proxyHttpContentTlsObserved": summary.get("proxyHttpContentTlsObserved", False),
        "contentSessionRoutes": summary.get("contentSessionRoutes", {}),
        "proxyRouteModes": summary.get("proxyRouteModes", {}),
        "firstArchiveRequestSeconds": summary.get("firstArchiveRequestSeconds"),
        "firstArchiveResponseSeconds": summary.get("firstArchiveResponseSeconds"),
        "localMitm443Connections": summary.get("localMitm443Connections", 0),
        "directExternal443Connections": summary.get("directExternal443Connections", 0),
    }


def evaluate_launch_route(launch_state: dict[str, Any]) -> dict[str, Any]:
    config_url = extract_client_config_url(launch_state)
    params = parse_qs(urlparse(config_url).query) if config_url else {}
    host_rewrite = params.get("hostRewrite", [""])[0]
    lobby_host_rewrite = params.get("lobbyHostRewrite", [""])[0]
    content_route_rewrite = params.get("contentRouteRewrite", [""])[0]
    use_content_tls_route = bool(launch_state.get("UseContentTlsRoute"))
    force_lobby_tls_mitm = bool(launch_state.get("ForceLobbyTlsMitm"))
    content_route_mode = launch_state.get("ContentRouteMode")
    if not isinstance(content_route_mode, str) or not content_route_mode:
        content_route_mode = "content-only-local-mitm" if content_route_rewrite == "1" else "disabled"
    canonical_mitm_launch = (
        use_content_tls_route
        and force_lobby_tls_mitm
        and host_rewrite == "0"
        and lobby_host_rewrite in {"", "0"}
        and content_route_rewrite == "1"
        and content_route_mode == "content-only-local-mitm"
    )
    return {
        "configUrl": config_url,
        "hostRewrite": host_rewrite,
        "lobbyHostRewrite": lobby_host_rewrite,
        "contentRouteRewrite": content_route_rewrite,
        "contentRouteMode": content_route_mode,
        "useContentTlsRoute": use_content_tls_route,
        "forceLobbyTlsMitm": force_lobby_tls_mitm,
        "canonicalMitmLaunch": canonical_mitm_launch,
        "nonCanonicalHostRewrite": force_lobby_tls_mitm and host_rewrite == "1",
    }


def list_world_windows(world_log: Path) -> list[str]:
    return [f"{session['startLine']}:{session['endLine']}" for session in load_all_sessions(world_log)]


def latest_path(paths: list[Path], *, since_epoch: float | None = None) -> Path | None:
    filtered = [path for path in paths if path.exists() and (since_epoch is None or path.stat().st_mtime >= since_epoch)]
    if not filtered:
        return None
    return sorted(filtered, key=lambda path: path.stat().st_mtime)[-1]


def launch_live_stack(args: argparse.Namespace) -> dict[str, Any]:
    if LAUNCH_STATE_FILE.exists():
        LAUNCH_STATE_FILE.unlink()
    command = [
        str(POWERSHELL_EXE),
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(LAUNCH_SCRIPT),
        "-ForceLobbyTlsMitm",
        "-DisableWatchdog",
    ]
    if args.client_variant == "original":
        command.append("-UseOriginalClient")
    completed = run_command(command, cwd=WORKSPACE, timeout=180)
    payload = load_json(LAUNCH_STATE_FILE, None)
    if not isinstance(payload, dict):
        try:
            payload = load_json_from_text(completed.stdout)
        except ValueError:
            payload = None
    return {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "state": payload,
    }


def load_json_from_text(text: str) -> dict[str, Any]:
    import json

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("Expected JSON object")
    return payload


def maybe_reset_cache(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.reset_cache:
        return None
    if not RESET_CACHE_SCRIPT.exists():
        return {
            "command": [str(POWERSHELL_EXE), "-ExecutionPolicy", "Bypass", "-File", str(RESET_CACHE_SCRIPT)],
            "returnCode": 1,
            "stdout": "",
            "stderr": "reset-cache-script-missing",
        }
    command = [
        str(POWERSHELL_EXE),
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RESET_CACHE_SCRIPT),
    ]
    completed = run_command(command, cwd=WORKSPACE, timeout=120)
    return {
        "command": command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def start_js5_recorder(args: argparse.Namespace) -> tuple[subprocess.Popen[str], list[str]]:
    ensure_directory(args.js5_session_dir)
    command = [
        os.environ.get("COMSPEC", "cmd.exe"),
        "/c",
        "call",
        str(OPENNXT_BAT),
        "run-tool",
        "js5-proxy-recorder",
        "--bind-port",
        "43595",
        "--remote-host",
        "content.runescape.com",
        "--remote-port",
        "43594",
        "--max-sessions",
        "6",
        "--idle-timeout-seconds",
        str(args.js5_idle_timeout_seconds),
        "--session-idle-timeout-seconds",
        str(max(5, min(args.js5_idle_timeout_seconds, 15))),
        "--output-dir",
        str(args.js5_session_dir),
    ]
    return start_process(command, cwd=WORKSPACE), command


def start_runtime_trace(args: argparse.Namespace, client_pid: int) -> tuple[subprocess.Popen[str], list[str], Path]:
    ensure_directory(args.runtime_trace_dir)
    trace_path = args.runtime_trace_dir / f"black-screen-runtime-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.jsonl"
    command = [
        sys.executable,
        str(TRACE_PROCESS_SCRIPT),
        "--pid",
        str(client_pid),
        "--timeout-seconds",
        str(args.runtime_trace_seconds),
        "--output",
        str(trace_path),
    ]
    return start_process(command, cwd=WORKSPACE), command, trace_path


def finalize_process(process: subprocess.Popen[str] | None, *, timeout_seconds: int = 5) -> dict[str, Any]:
    if process is None:
        return {"returnCode": None, "stdout": "", "stderr": ""}
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
    return {
        "returnCode": process.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def select_new_world_window(before_windows: list[str], world_log: Path) -> str | None:
    after_windows = list_world_windows(world_log)
    for window in reversed(after_windows):
        if window not in before_windows:
            return window
    return after_windows[-1] if after_windows else None


def run_downstream_tools(world_window: str | None) -> dict[str, Any]:
    scene_command = [sys.executable, str(WORKSPACE / "tools" / "run_946_scene_delivery_aid.py"), "--force"]
    if world_window:
        scene_command.extend(["--world-window", world_window])
    scene_completed = run_command(scene_command, cwd=WORKSPACE, timeout=180)
    doctor_command = [sys.executable, str(WORKSPACE / "tools" / "run_946_tool_doctor.py"), "--force"]
    doctor_completed = run_command(doctor_command, cwd=WORKSPACE, timeout=180)
    return {
        "sceneDeliveryCommand": scene_command,
        "sceneDeliveryReturnCode": scene_completed.returncode,
        "sceneDeliveryStdout": scene_completed.stdout,
        "sceneDeliveryStderr": scene_completed.stderr,
        "toolDoctorCommand": doctor_command,
        "toolDoctorReturnCode": doctor_completed.returncode,
        "toolDoctorStdout": doctor_completed.stdout,
        "toolDoctorStderr": doctor_completed.stderr,
        "sceneDeliveryArtifact": load_json(SHARED_DIR / SCENE_DELIVERY_JSON, {}) or {},
        "toolDoctorArtifact": load_json(SHARED_DIR / TOOL_DOCTOR_JSON, {}) or {},
    }


def build_capture_artifact(args: argparse.Namespace) -> dict[str, Any]:
    missing = {name: str(path) for name, path in required_paths().items() if not path.exists()}
    if missing:
        return standard_tool_artifact(
            tool_name="run_946_black_screen_capture",
            status="blocked",
            inputs={
                "captureSeconds": args.capture_seconds,
                "runtimeTraceSeconds": args.runtime_trace_seconds,
                "js5IdleTimeoutSeconds": args.js5_idle_timeout_seconds,
                "resetCache": bool(args.reset_cache),
                "clientVariant": args.client_variant,
            },
            artifacts={
                "blackScreenCaptureJson": str(output_paths(args.output_dir)["json"]),
                "blackScreenCaptureMarkdown": str(output_paths(args.output_dir)["markdown"]),
            },
            summary={
                "worldWindowSelected": "",
                "overlapAchieved": False,
                "statusReason": "missing-helper-paths",
            },
            extra={"missingPaths": missing},
        )

    reset_result = maybe_reset_cache(args)
    capture_started_at = time.time()
    before_windows = list_world_windows(args.world_log)
    launch = launch_live_stack(args)
    launch_state = launch.get("state") if isinstance(launch.get("state"), dict) else {}
    launch_evaluation = evaluate_launch_route(launch_state if isinstance(launch_state, dict) else {})
    client_pid = launch_state.get("ClientPid") if isinstance(launch_state, dict) else None
    runtime_trace_process = None
    runtime_trace_command: list[str] = []
    runtime_trace_path = None

    if isinstance(client_pid, int):
        runtime_trace_process, runtime_trace_command, runtime_trace_path = start_runtime_trace(args, client_pid)

    time.sleep(max(1, args.capture_seconds))
    network_snapshot = collect_client_network_snapshot(client_pid) if isinstance(client_pid, int) else {}
    content_capture_summary = summarize_recent_content_sessions(args.content_capture_dir, since_epoch=capture_started_at)

    for pid_key in ("ClientPid", "WatchdogPid", "GameProxyPid", "LobbyProxyPid", "ServerPid", "WrapperPid"):
        value = launch_state.get(pid_key) if isinstance(launch_state, dict) else None
        if isinstance(value, int):
            kill_pid(value)

    runtime_trace_result = finalize_process(runtime_trace_process)
    world_window = select_new_world_window(before_windows, args.world_log)
    live_watch = summarize_live_watch(world_window)
    latest_js5_summary = latest_path(sorted(args.js5_session_dir.glob("summary-*.json")), since_epoch=capture_started_at)
    downstream = run_downstream_tools(world_window)
    scene_delivery = downstream["sceneDeliveryArtifact"]
    tool_doctor = downstream["toolDoctorArtifact"]
    overlap_achieved = ((scene_delivery.get("summary") or {}).get("overlapConfidence")) not in {None, "missing"}

    if launch.get("returnCode") != 0 or not isinstance(client_pid, int):
        status = "blocked"
        reason = "launch-failed"
    elif launch_evaluation["nonCanonicalHostRewrite"]:
        status = "partial"
        reason = "non-canonical-host-rewrite"
    elif not world_window:
        status = "partial"
        reason = "prelogin-route-regression"
    elif (
        launch_evaluation["canonicalMitmLaunch"]
        and int(network_snapshot.get("directExternal443ConnectionCount", 0) or 0) > 0
        and not content_capture_summary["localMsRequestsObserved"]
    ):
        status = "partial"
        reason = "content-route-bypassed-local-mitm"
    elif not overlap_achieved:
        status = "partial"
        reason = "overlap-missing"
    elif tool_doctor.get("status") == "blocked":
        status = "partial"
        reason = "doctor-blocked"
    else:
        status = "ok"
        reason = "capture-complete"

    return standard_tool_artifact(
        tool_name="run_946_black_screen_capture",
        status=status,
        inputs={
            "captureSeconds": args.capture_seconds,
            "runtimeTraceSeconds": args.runtime_trace_seconds,
            "js5IdleTimeoutSeconds": args.js5_idle_timeout_seconds,
            "resetCache": bool(args.reset_cache),
            "clientVariant": args.client_variant,
            "worldLog": str(args.world_log),
            "js5SessionDir": str(args.js5_session_dir),
            "contentCaptureDir": str(args.content_capture_dir),
            "runtimeTraceDir": str(args.runtime_trace_dir),
        },
        artifacts={
            "blackScreenCaptureJson": str(output_paths(args.output_dir)["json"]),
            "blackScreenCaptureMarkdown": str(output_paths(args.output_dir)["markdown"]),
        },
        summary={
            "worldWindowSelected": world_window or "",
            "overlapAchieved": overlap_achieved,
            "sceneDeliveryVerdict": (scene_delivery.get("verdict") or {}).get("likelyBlocker"),
            "toolDoctorStatus": tool_doctor.get("status"),
            "canonicalMitmLaunch": launch_evaluation["canonicalMitmLaunch"],
            "hostRewrite": launch_evaluation["hostRewrite"],
            "lobbyHostRewrite": launch_evaluation["lobbyHostRewrite"],
            "contentRouteRewrite": launch_evaluation["contentRouteRewrite"],
            "contentRouteMode": launch_evaluation["contentRouteMode"],
            "freshLocalTlsSessionCount": content_capture_summary["freshTlsSessionCount"],
            "sessionRouteCounts": content_capture_summary.get("sessionRouteCounts", {}),
            "localMsRequestsObserved": content_capture_summary["localMsRequestsObserved"],
            "localMitm443ConnectionCount": network_snapshot.get("localMitm443ConnectionCount", 0),
            "directExternal443ConnectionCount": network_snapshot.get("directExternal443ConnectionCount", 0),
            "liveWatcherPresent": live_watch.get("present", False),
            "liveWatcherTerminalState": live_watch.get("terminalState", ""),
            "statusReason": reason,
        },
        extra={
            "launchedAt": iso_now(),
            "resetCache": reset_result,
            "launch": launch,
            "launchEvaluation": launch_evaluation,
            "networkSnapshot": network_snapshot,
            "js5Recorder": {
                "command": [],
                "summaryJson": str(latest_js5_summary) if latest_js5_summary else "",
                "returnCode": None,
                "stdout": "",
                "stderr": "",
            },
            "contentCapture": content_capture_summary,
            "runtimeTrace": {
                "command": runtime_trace_command,
                "path": str(runtime_trace_path) if runtime_trace_path else "",
                **runtime_trace_result,
            },
            "liveWatcher": live_watch,
            "downstream": downstream,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Black Screen Capture",
        "",
        f"- Status: `{artifact['status']}`",
        f"- World window selected: `{artifact['summary'].get('worldWindowSelected', '')}`",
        f"- Overlap achieved: `{artifact['summary'].get('overlapAchieved', False)}`",
        f"- Scene delivery verdict: `{artifact['summary'].get('sceneDeliveryVerdict')}`",
        f"- Tool doctor status: `{artifact['summary'].get('toolDoctorStatus')}`",
        f"- Canonical MITM launch: `{artifact['summary'].get('canonicalMitmLaunch', False)}`",
        f"- hostRewrite: `{artifact['summary'].get('hostRewrite', '')}`",
        f"- lobbyHostRewrite: `{artifact['summary'].get('lobbyHostRewrite', '')}`",
        f"- contentRouteRewrite: `{artifact['summary'].get('contentRouteRewrite', '')}`",
        f"- contentRouteMode: `{artifact['summary'].get('contentRouteMode', '')}`",
        f"- Fresh local TLS sessions: `{artifact['summary'].get('freshLocalTlsSessionCount', 0)}`",
        f"- Session route counts: `{artifact['summary'].get('sessionRouteCounts', {})}`",
        f"- Local `/ms` observed: `{artifact['summary'].get('localMsRequestsObserved', False)}`",
        f"- Local MITM `:443` connections: `{artifact['summary'].get('localMitm443ConnectionCount', 0)}`",
        f"- Direct external `:443` connections: `{artifact['summary'].get('directExternal443ConnectionCount', 0)}`",
        f"- Live watcher present: `{artifact['summary'].get('liveWatcherPresent', False)}`",
        f"- Live watcher terminal state: `{artifact['summary'].get('liveWatcherTerminalState', '')}`",
        f"- Status reason: `{artifact['summary'].get('statusReason')}`",
        "",
        "## Commands",
        "",
    ]
    launch = artifact.get("launch") or {}
    js5 = artifact.get("js5Recorder") or {}
    content_capture = artifact.get("contentCapture") or {}
    runtime = artifact.get("runtimeTrace") or {}
    lines.append(f"- Launch: `{launch.get('command')}`")
    lines.append(f"- JS5 recorder: `{js5.get('command')}`")
    lines.append(f"- Runtime trace: `{runtime.get('command')}`")
    lines.extend(["", "## Paths", ""])
    lines.append(f"- Launch state file: `{LAUNCH_STATE_FILE}`")
    lines.append(f"- JS5 summary: `{js5.get('summaryJson', '')}`")
    lines.append(f"- Content capture: `{content_capture.get('latestSessionLog', '')}`")
    lines.append(f"- Runtime trace: `{runtime.get('path', '')}`")
    live_watch = artifact.get("liveWatcher") or {}
    lines.append(f"- Live watcher summary: `{live_watch.get('path', '')}`")
    lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    outputs = output_paths(output_dir)
    write_json(outputs["json"], artifact)
    outputs["markdown"].write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    artifact = build_capture_artifact(args)
    write_artifacts(args.output_dir, artifact)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0 if artifact["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
