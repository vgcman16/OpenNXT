from __future__ import annotations

import argparse
import ctypes
import json
import re
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse

import psutil

from protocol_automation_common import WORKSPACE, ensure_directory, stable_json_text, standard_tool_artifact, write_json
from protocol_946_debug_common import WORLD_LOG_DEFAULT, extract_kv_pairs, load_all_sessions, parse_timestamp
from run_946_black_screen_capture import (
    DEFAULT_CONTENT_CAPTURE_DIR,
    DEFAULT_JS5_SESSION_DIR,
    LAUNCH_STATE_FILE,
    LAUNCH_SCRIPT,
    POWERSHELL_EXE,
    evaluate_launch_route,
    finalize_process,
    kill_pid,
    select_new_world_window,
)
from run_946_scene_delivery_aid import DEFAULT_CLIENTERROR_DIR


DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "client-live-watch"
DEFAULT_RUNTIME_TRACE_DIR = WORKSPACE / "data" / "debug" / "runtime-trace"
DEFAULT_SERVER_CONFIG_PATH = WORKSPACE / "data" / "config" / "server.toml"
DEFAULT_SERVER_LOG = next(
    (
        candidate
        for candidate in (
            WORKSPACE / "tmp-runserver.err.log",
            WORKSPACE / "tmp-manual-js5.err.log",
        )
        if candidate.exists()
    ),
    WORKSPACE / "tmp-runserver.err.log",
)
TRACE_SCRIPT = WORKSPACE / "tools" / "trace_rs2client_live.py"
WATCH_PS1 = WORKSPACE / "tools" / "watch-rs2client-live.ps1"
WATCH_CMD = WORKSPACE / "tools" / "watch-rs2client-live.cmd"
LATEST_SUMMARY_JSON = "latest-summary.json"
LATEST_SUMMARY_MD = "latest-summary.md"
LATEST_SESSION_JSONL = "latest-session.jsonl"
LATEST_HOOKS_JSONL = "latest-hooks.jsonl"
LOCALHOST_HOSTS = {"127.0.0.1", "::1", "localhost"}
DEFAULT_POLL_INTERVAL = 0.25
DEFAULT_SAMPLE_INTERVAL = 1.0
DEFAULT_DIRECTORY_DISCOVERY_INTERVAL = 2.0
SESSION_EVIDENCE_LEEWAY_SECONDS = 15.0
WORLD_LOG_PRESCAN_MAX_BYTES = 64 * 1024 * 1024
MAX_RECENT_CONTENT_SESSION_FILES = 256
MAX_RECENT_JS5_SUMMARY_FILES = 64
MAX_RECENT_CLIENTERROR_FILES = 64
HOOK_ALLOWED_TLS_STATUSES = {
    0x00000000,
    0x00090312,
    0x00090313,
    0x00090320,
    0x00090321,
    0x80090318,
}
JS5_LIVE_REQUEST_RE = re.compile(
    r"Queued js5 request #(?P<requestId>\d+) from (?P<remote>\S+): opcode=(?P<opcode>\d+), "
    r"priority=(?P<priority>true|false), nxt=(?P<nxt>true|false), build=(?P<build>\d+), "
    r"occurrence=(?P<occurrence>\d+), (?P<requestKind>[^,]+)\(index=(?P<index>\d+), archive=(?P<archive>\d+)\)"
)
JS5_LIVE_RESPONSE_RE = re.compile(
    r"Serving js5 response #(?P<requestId>\d+) to (?P<remote>\S+): "
    r"(?P<requestKind>[^,]+)\(index=(?P<index>\d+), archive=(?P<archive>\d+)\), "
    r"priority=(?P<priority>true|false), occurrence=(?P<occurrence>\d+), bytes=(?P<bytes>\d+)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Launch or attach to rs2client.exe and stream a merged live terminal feed plus structured artifacts."
    )
    parser.add_argument("--pid", type=int, help="Attach to an already running rs2client.exe process id.")
    parser.add_argument(
        "--force-launch",
        action="store_true",
        help="Always launch a fresh client even if a main rs2client.exe process is already running.",
    )
    parser.add_argument("--duration-seconds", type=int, default=0, help="Optional maximum watch duration. 0 means until exit or Ctrl+C.")
    parser.add_argument("--verbose", action="store_true", help="Emit noisier read/send/recv events.")
    parser.add_argument("--no-frida", action="store_true", help="Disable deep hooks and use passive observation only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--client-variant", choices=("patched", "original"), default="patched")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--content-capture-dir", type=Path, default=DEFAULT_CONTENT_CAPTURE_DIR)
    parser.add_argument("--js5-session-dir", type=Path, default=DEFAULT_JS5_SESSION_DIR)
    parser.add_argument("--clienterror-dir", type=Path, default=DEFAULT_CLIENTERROR_DIR)
    parser.add_argument("--runtime-trace-dir", type=Path, default=DEFAULT_RUNTIME_TRACE_DIR)
    parser.add_argument("--server-log", type=Path, default=DEFAULT_SERVER_LOG)
    return parser.parse_args()


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def epoch_to_iso(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def session_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def required_paths(args: argparse.Namespace) -> dict[str, Path]:
    paths = {
        "worldLog": args.world_log,
        "contentCaptureDir": args.content_capture_dir,
        "js5SessionDir": args.js5_session_dir,
        "clienterrorDir": args.clienterror_dir,
        "launchScript": LAUNCH_SCRIPT,
        "watchWrapperPs1": WATCH_PS1,
        "watchWrapperCmd": WATCH_CMD,
    }
    if not args.no_frida:
        paths["traceRs2ClientLive"] = TRACE_SCRIPT
    return paths


def session_paths(output_dir: Path, stamp: str) -> dict[str, Path]:
    return {
        "sessionJsonl": output_dir / f"session-{stamp}.jsonl",
        "summaryJson": output_dir / f"summary-{stamp}.json",
        "summaryMarkdown": output_dir / f"summary-{stamp}.md",
        "hooksJsonl": output_dir / f"hooks-{stamp}.jsonl",
        "hookDir": output_dir / f"hook-streams-{stamp}",
        "launchStdout": output_dir / f"launch-{stamp}.stdout.log",
        "launchStderr": output_dir / f"launch-{stamp}.stderr.log",
    }


def copy_latest(paths: dict[str, Path], output_dir: Path) -> None:
    copies = {
        paths["summaryJson"]: output_dir / LATEST_SUMMARY_JSON,
        paths["summaryMarkdown"]: output_dir / LATEST_SUMMARY_MD,
        paths["sessionJsonl"]: output_dir / LATEST_SESSION_JSONL,
        paths["hooksJsonl"]: output_dir / LATEST_HOOKS_JSONL,
    }
    for source, target in copies.items():
        if source.exists():
            shutil.copyfile(source, target)


def hook_target_paths(paths: dict[str, Path], client_pid: int) -> dict[str, Path]:
    hook_dir = paths["hookDir"]
    ensure_directory(hook_dir)
    return {
        "jsonl": hook_dir / f"pid-{client_pid}.jsonl",
        "stdout": hook_dir / f"pid-{client_pid}.stdout.log",
        "stderr": hook_dir / f"pid-{client_pid}.stderr.log",
    }


def start_hook_process(
    args: argparse.Namespace,
    client_pid: int,
    *,
    output_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> tuple[subprocess.Popen[str] | None, list[str]]:
    if args.no_frida:
        return None, []
    command = [
        sys.executable,
        str(TRACE_SCRIPT),
        "--pid",
        str(client_pid),
        "--output",
        str(output_path),
    ]
    if args.duration_seconds > 0:
        command.extend(["--duration-seconds", str(args.duration_seconds)])
    if args.verbose:
        command.append("--verbose")
    process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE),
        stdout=stdout_path.open("w", encoding="utf-8"),
        stderr=stderr_path.open("w", encoding="utf-8"),
        text=True,
    )
    return process, command


def should_retry_hook_target(target: dict[str, Any], active_pids: set[int], now_epoch: float) -> bool:
    process = target.get("process")
    pid = int(target.get("pid", 0) or 0)
    if process is None or pid not in active_pids:
        return False
    return_code = process.poll()
    if return_code is None or return_code == 0:
        return False
    output_path = target.get("output")
    if not isinstance(output_path, Path):
        return False
    if output_path.exists() and output_path.stat().st_size > 0:
        return False
    attempts = int(target.get("attempts", 0) or 0)
    if attempts >= 3:
        return False
    last_start = float(target.get("lastStartEpoch", 0.0) or 0.0)
    return now_epoch - last_start >= 1.0


def safe_process_name(process: psutil.Process) -> str:
    try:
        return str(process.name() or "")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def safe_process_exe(process: psutil.Process) -> str:
    try:
        return str(process.exe() or "")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def safe_process_cmdline(process: psutil.Process) -> list[str]:
    try:
        return [str(part) for part in (process.cmdline() or [])]
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return []


def normalize_cmdline_text(cmdline: Any) -> str:
    if isinstance(cmdline, (list, tuple)):
        return " ".join(str(part) for part in cmdline)
    return str(cmdline or "")


def is_compile_shader_cmdline(cmdline: Any) -> bool:
    return "--compileshader" in normalize_cmdline_text(cmdline).lower()


def infer_build_from_client_path(executable_path: str | None) -> int | None:
    if not executable_path:
        return None
    parts = Path(executable_path).parts
    for index, part in enumerate(parts):
        if part.lower() != "clients":
            continue
        if index + 1 >= len(parts):
            return None
        try:
            return int(parts[index + 1])
        except ValueError:
            return None
    return None


def launch_state_runtime_pids(launch_state: dict[str, Any] | None) -> set[int]:
    if not isinstance(launch_state, dict):
        return set()
    pids: set[int] = set()
    for key in ("ClientPid", "BootstrapClientPid", "WrapperPid"):
        parsed = _parse_int(launch_state.get(key))
        if parsed is not None and parsed > 0:
            pids.add(parsed)
    return pids


def launch_state_matches_client(launch_state: dict[str, Any] | None, client_pid: int | None) -> bool:
    parsed_client_pid = _parse_int(client_pid)
    if parsed_client_pid is None or parsed_client_pid <= 0:
        return False
    return parsed_client_pid in launch_state_runtime_pids(launch_state)


def read_configured_build(config_path: Path = DEFAULT_SERVER_CONFIG_PATH, default: int = 947) -> int:
    if not config_path.exists():
        return default
    try:
        for raw_line in config_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if not line.startswith("build"):
                continue
            _, _, value = line.partition("=")
            parsed = _parse_int(value.strip())
            if parsed is not None:
                return parsed
    except OSError:
        return default
    return default


def resolve_runtime_build(*, client_pid: int | None, launch_state: dict[str, Any] | None = None) -> int:
    if isinstance(launch_state, dict) and (client_pid is None or launch_state_matches_client(launch_state, client_pid)):
        for key in ("ClientBuild", "build"):
            parsed = _parse_int(launch_state.get(key))
            if parsed is not None:
                return parsed
    if client_pid is not None and psutil.pid_exists(client_pid):
        try:
            executable_path = psutil.Process(client_pid).exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            executable_path = ""
        inferred = infer_build_from_client_path(executable_path)
        if inferred is not None:
            return inferred
    return read_configured_build()


def discover_process_family(root_pid: int) -> dict[int, psutil.Process]:
    try:
        root = psutil.Process(int(root_pid))
    except (psutil.NoSuchProcess, psutil.AccessDenied, ValueError):
        return {}

    root_name = safe_process_name(root).lower()
    root_exe = safe_process_exe(root).lower()
    related_pids: set[int] = {int(root_pid)}

    try:
        for child in root.children(recursive=True):
            child_name = safe_process_name(child).lower()
            child_exe = safe_process_exe(child).lower()
            if is_compile_shader_cmdline(safe_process_cmdline(child)):
                continue
            if (root_exe and child_exe == root_exe) or (root_name and child_name == root_name):
                related_pids.add(int(child.pid))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    for process in psutil.process_iter(["pid", "name", "exe", "create_time", "ppid", "cmdline"]):
        try:
            pid = int(process.info["pid"])
            name = str(process.info.get("name") or "").lower()
            exe = str(process.info.get("exe") or "").lower()
            parent_pid = int(process.info.get("ppid") or 0)
            cmdline = process.info.get("cmdline") or []
        except (KeyError, TypeError, ValueError):
            continue
        if is_compile_shader_cmdline(cmdline):
            continue
        same_binary = bool(root_exe and exe and exe == root_exe) or bool(root_name and name and name == root_name)
        if not same_binary:
            continue
        related_parent = parent_pid == int(root_pid) or parent_pid in related_pids
        if related_parent or pid == int(root_pid):
            related_pids.add(pid)

    family: dict[int, psutil.Process] = {}
    for pid in sorted(related_pids):
        try:
            family[pid] = psutil.Process(pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return family


def decode_first_chunk_payload(line: str) -> bytes:
    marker = " hex="
    if marker not in line:
        return b""
    payload = line.split(marker, 1)[1].strip().replace(" ", "")
    if not payload:
        return b""
    try:
        return bytes.fromhex(payload)
    except ValueError:
        return b""


def _parse_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_http_payload(payload: bytes) -> dict[str, Any] | None:
    if not payload:
        return None
    text = payload.decode("latin1", errors="ignore")
    if text.startswith(("GET ", "POST ", "HEAD ")):
        first_line = text.split("\r\n", 1)[0]
        parts = first_line.split(" ", 2)
        if len(parts) < 2:
            return None
        target = parts[1]
        parsed = urlparse(target)
        query = parse_qs(parsed.query)
        return {
            "kind": "request",
            "method": parts[0],
            "target": target,
            "path": parsed.path,
            "index": _parse_int(query.get("m", [None])[0]),
            "archive": _parse_int(query.get("a", [None])[0]),
        }
    if text.startswith("HTTP/"):
        first_line = text.split("\r\n", 1)[0]
        parts = first_line.split(" ", 2)
        headers = {}
        for header_line in text.split("\r\n")[1:]:
            if not header_line:
                break
            if ":" not in header_line:
                continue
            key, value = header_line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
        return {
            "kind": "response",
            "statusCode": _parse_int(parts[1] if len(parts) > 1 else None),
            "contentLength": _parse_int(headers.get("content-length")),
            "contentType": headers.get("content-type", ""),
        }
    return None


def parse_log_timestamp(text: str) -> datetime | None:
    parsed = parse_timestamp(text)
    if parsed is not None:
        return parsed
    try:
        normalized = text.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def parse_content_session_metadata(path: Path) -> dict[str, datetime | None]:
    start_at: datetime | None = None
    end_at: datetime | None = None
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                if " start=" in line and "session#" in line and start_at is None:
                    start_text = line.split(" start=", 1)[1].strip()
                    start_at = parse_log_timestamp(start_text)
                elif " end=" in line and "session#" in line:
                    end_text = line.split(" end=", 1)[1].strip()
                    end_at = parse_log_timestamp(end_text)
    except OSError:
        return {"start": None, "end": None}
    return {"start": start_at, "end": end_at}


def content_session_overlaps_watch(
    path: Path,
    *,
    session_started_at: datetime | None,
    leeway_seconds: float = SESSION_EVIDENCE_LEEWAY_SECONDS,
) -> bool:
    metadata = parse_content_session_metadata(path)
    start_at = metadata.get("start")
    end_at = metadata.get("end")
    if session_started_at is None:
        return True
    lower_bound = session_started_at.timestamp() - leeway_seconds
    if isinstance(end_at, datetime) and end_at.timestamp() < lower_bound:
        return False
    if isinstance(start_at, datetime) and start_at.timestamp() < lower_bound:
        if isinstance(end_at, datetime):
            return end_at.timestamp() >= lower_bound
        return False
    if not isinstance(start_at, datetime):
        try:
            return path.stat().st_mtime >= lower_bound
        except OSError:
            return False
    return True


def file_is_recent_for_watch(
    path: Path,
    *,
    session_started_at: datetime | None,
    leeway_seconds: float = SESSION_EVIDENCE_LEEWAY_SECONDS,
) -> bool:
    if session_started_at is None:
        return True
    try:
        return path.stat().st_mtime >= (session_started_at.timestamp() - leeway_seconds)
    except OSError:
        return False


def recent_directory_paths(
    directory: Path,
    pattern: str,
    *,
    since_epoch: float | None,
    max_files: int,
) -> list[Path]:
    if not directory.exists():
        return []
    candidates: list[tuple[float, Path]] = []
    for path in directory.glob(pattern):
        if not path.is_file():
            continue
        try:
            modified_at = path.stat().st_mtime
        except OSError:
            continue
        if since_epoch is not None and modified_at < since_epoch:
            continue
        candidates.append((modified_at, path))
    candidates.sort(key=lambda item: (item[0], item[1].name))
    if max_files > 0:
        candidates = candidates[-max_files:]
    return [path for _, path in candidates]


def is_nonfatal_graphics_exception(details: dict[str, Any]) -> bool:
    backtrace = details.get("backtrace")
    if not isinstance(backtrace, list):
        return False
    symbols = " ".join(str(frame.get("symbol", "")) for frame in backtrace if isinstance(frame, dict))
    if "NVDEV_Thunk" in symbols or "OpenAdapter10_2" in symbols or "OpenAdapter_D3D11On12" in symbols:
        return True
    context = details.get("context")
    if isinstance(context, dict):
        exception_code = str(context.get("rdi", "")).lower()
        if exception_code == "0xe06d7363" and ("OpenAdapter" in symbols or "NVDEV_Thunk" in symbols):
            return True
    return False


def relative_millis(start_epoch: float, event_epoch: float) -> int:
    return max(0, int(round((event_epoch - start_epoch) * 1000)))


def relative_display(start_epoch: float, event_epoch: float) -> str:
    total_millis = relative_millis(start_epoch, event_epoch)
    minutes, rem = divmod(total_millis, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes:02}:{seconds:02}.{millis:03}"


class TailState:
    def __init__(self) -> None:
        self.positions: dict[str, int] = {}
        self.seen_files: set[str] = set()

    def prime_file(self, path: Path) -> None:
        if path.exists():
            self.positions[str(path)] = path.stat().st_size
            self.seen_files.add(str(path))

    def prime_directory(self, directory: Path, pattern: str) -> None:
        if not directory.exists():
            return
        for path in directory.glob(pattern):
            if path.is_file():
                self.prime_file(path)

    def read_new_lines(self, path: Path, *, start_at_end_for_new: bool) -> list[str]:
        if not path.exists():
            return []
        key = str(path)
        size = path.stat().st_size
        if key not in self.positions:
            self.positions[key] = size if start_at_end_for_new else 0
            self.seen_files.add(key)
        if self.positions[key] > size:
            self.positions[key] = 0
        if size == self.positions[key]:
            return []
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            handle.seek(self.positions[key])
            data = handle.read()
            self.positions[key] = handle.tell()
        return [line for line in data.splitlines() if line]


def get_window_info(pid: int) -> dict[str, Any]:
    user32 = ctypes.windll.user32
    results: list[dict[str, Any]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(process_id))
        if process_id.value != pid:
            return True
        length = user32.GetWindowTextLengthW(ctypes.c_void_p(hwnd))
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(ctypes.c_void_p(hwnd), buffer, length + 1)
        results.append(
            {
                "hwnd": int(hwnd),
                "title": buffer.value,
                "visible": bool(user32.IsWindowVisible(ctypes.c_void_p(hwnd))),
                "hung": bool(user32.IsHungAppWindow(ctypes.c_void_p(hwnd))),
            }
        )
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    if not results:
        return {"exists": False, "title": "", "visible": False, "hung": False}
    visible = next((row for row in results if row["visible"]), results[0])
    return {"exists": True, **visible}


def emit_event(
    session_handle: Any,
    session_start_epoch: float,
    event_epoch: float,
    category: str,
    action: str,
    details: dict[str, Any],
    *,
    source: str,
    terminal: bool,
) -> dict[str, Any]:
    event = {
        "timestamp": epoch_to_iso(event_epoch),
        "relativeMillis": relative_millis(session_start_epoch, event_epoch),
        "category": category,
        "action": action,
        "source": source,
        "details": details,
    }
    session_handle.write(json.dumps(event, sort_keys=True) + "\n")
    session_handle.flush()
    if terminal:
        print(format_terminal_event(session_start_epoch, event_epoch, category, action, details))
    return event


def format_terminal_event(session_start_epoch: float, event_epoch: float, category: str, action: str, details: dict[str, Any]) -> str:
    preview_bits: list[str] = []
    for key in (
        "path",
        "moduleName",
        "fileCategory",
        "target",
        "statusCode",
        "contentLength",
        "remoteHost",
        "remotePort",
        "host",
        "service",
        "status",
        "stage",
        "kind",
        "title",
        "summary",
        "count",
        "playerName",
    ):
        value = details.get(key)
        if value in (None, "", []):
            continue
        preview_bits.append(f"{key}={value}")
    if "index" in details and details.get("index") is not None:
        preview_bits.append(f"index={details['index']}")
    if "archive" in details and details.get("archive") is not None:
        preview_bits.append(f"archive={details['archive']}")
    if "bytes" in details and details.get("bytes") not in (None, 0):
        preview_bits.append(f"bytes={details['bytes']}")
    if "totalBytesRead" in details and details.get("totalBytesRead") not in (None, 0):
        preview_bits.append(f"total={details['totalBytesRead']}")
    if "bytesSent" in details and details.get("bytesSent") not in (None, 0):
        preview_bits.append(f"sent={details['bytesSent']}")
    if "bytesReceived" in details and details.get("bytesReceived") not in (None, 0):
        preview_bits.append(f"recv={details['bytesReceived']}")
    return f"{relative_display(session_start_epoch, event_epoch)} {category:<18} {action:<18} {' '.join(preview_bits)}".rstrip()


def normalize_world_line(raw_line: str) -> tuple[str, str, dict[str, Any]] | None:
    parts = raw_line.split(" ", 2)
    if len(parts) < 2:
        return None
    kind = parts[1]
    rest = parts[2] if len(parts) > 2 else ""
    data = extract_kv_pairs(rest)
    if kind == "world-stage":
        return "world.stage", "stage", {"stage": data.get("stage", ""), "kind": kind, "playerName": data.get("name", "")}
    if kind.startswith("world-"):
        details = {"kind": kind, "playerName": data.get("name", "")}
        details.update({key: value for key, value in data.items() if key not in {"name"}})
        return "world.marker", kind, details
    if kind in {"send-raw", "recv-raw"}:
        details = {"kind": kind, "opcode": _parse_int(data.get("opcode")), "bytes": _parse_int(data.get("bytes")), "playerName": data.get("name", "")}
        return "world.packet", kind, details
    return None


def normalize_content_line(raw_line: str) -> tuple[str, str, dict[str, Any]] | None:
    line = raw_line.strip()
    if not line:
        return None
    if "session-route=" in line and "session#" in line:
        route = line.split("session-route=", 1)[1].split(" ", 1)[0].strip()
        return "proxy.content", "route", {"summary": route, "sessionRoute": route}
    if "tls-route-mode=" in line and "session#" in line:
        route_mode = line.split("tls-route-mode=", 1)[1].split(" ", 1)[0].strip()
        return "proxy.content", "route-mode", {"summary": route_mode, "routeMode": route_mode}
    if "tls-first-appdata-source=" in line and "session#" in line:
        source = line.split("tls-first-appdata-source=", 1)[1].split(" ", 1)[0].strip()
        return "proxy.content", "route-source", {"summary": source, "routeSource": source}
    if "tls-clienthello-sni=" in line and "session#" in line:
        sni = line.split("tls-clienthello-sni=", 1)[1].split(" ", 1)[0].strip()
        return "proxy.content", "clienthello-sni", {"summary": sni, "tlsClienthelloSni": sni}
    if "tls-cert-subject=" in line and "session#" in line:
        subject = line.split("tls-cert-subject=", 1)[1].strip()
        return "proxy.content", "cert-subject", {"summary": subject, "tlsCertSubject": subject}
    if "tls-cert-issuer=" in line and "session#" in line:
        issuer = line.split("tls-cert-issuer=", 1)[1].strip()
        return "proxy.content", "cert-issuer", {"summary": issuer, "tlsCertIssuer": issuer}
    if "tls-cert-thumbprint=" in line and "session#" in line:
        thumbprint = line.split("tls-cert-thumbprint=", 1)[1].strip()
        return "proxy.content", "cert-thumbprint", {"summary": thumbprint, "tlsCertThumbprint": thumbprint}
    if "tls-server-wrap=" in line and "session#" in line:
        wrap_status = line.split("tls-server-wrap=", 1)[1].split(" ", 1)[0].strip()
        return "proxy.content", "wrap-status", {"summary": wrap_status, "tlsServerWrapStatus": wrap_status}
    if "mode=" in line and "session#" in line:
        mode = line.split("mode=", 1)[1].split(" ", 1)[0].strip()
        return "proxy.content", "session", {"summary": mode}
    if "session-error=" in line:
        error = line.split("session-error=", 1)[1].strip()
        return "proxy.content", "error", {"summary": error}
    if " first-chunk-" in line:
        parsed = parse_http_payload(decode_first_chunk_payload(line))
        if not parsed:
            return None
        if parsed["kind"] == "request":
            return "proxy.content", "request", parsed
        return "proxy.content", "response", parsed
    if " bytes " in line and "->" in line:
        details = {}
        if "tls-client->remote=" in line:
            to_remote = line.split("tls-client->remote=", 1)[1].split(" ", 1)[0]
            from_remote = line.split("remote->tls-client=", 1)[1].strip()
            details["bytes"] = _parse_int(to_remote) or 0
            details["bytesReceived"] = _parse_int(from_remote) or 0
            return "proxy.content", "transfer", details
        if "raw-client->remote=" in line:
            to_remote = line.split("raw-client->remote=", 1)[1].split(" ", 1)[0]
            from_remote = line.split("remote->raw-client=", 1)[1].strip()
            details["bytes"] = _parse_int(to_remote) or 0
            details["bytesReceived"] = _parse_int(from_remote) or 0
            return "proxy.content", "transfer", details
    return None


def normalize_js5_summary(path: Path) -> tuple[str, str, dict[str, Any]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return None
    archive_requests = sum(int((session or {}).get("archiveRequests", 0) or 0) for session in sessions if isinstance(session, dict))
    response_headers = sum(int((session or {}).get("responseHeaderCount", 0) or 0) for session in sessions if isinstance(session, dict))
    return "proxy.js5", "summary", {"count": len(sessions), "archiveRequests": archive_requests, "responseHeaders": response_headers, "path": str(path)}


def normalize_js5_live_line(line: str) -> tuple[str, str, dict[str, Any]] | None:
    request_match = JS5_LIVE_REQUEST_RE.search(line)
    if request_match:
        return (
            "proxy.js5",
            "request",
            {
                "requestId": _parse_int(request_match.group("requestId")) or 0,
                "remote": request_match.group("remote"),
                "opcode": _parse_int(request_match.group("opcode")) or 0,
                "priority": request_match.group("priority") == "true",
                "nxt": request_match.group("nxt") == "true",
                "build": _parse_int(request_match.group("build")) or 0,
                "occurrence": _parse_int(request_match.group("occurrence")) or 0,
                "requestKind": request_match.group("requestKind"),
                "index": _parse_int(request_match.group("index")) or 0,
                "archive": _parse_int(request_match.group("archive")) or 0,
            },
        )
    response_match = JS5_LIVE_RESPONSE_RE.search(line)
    if response_match:
        return (
            "proxy.js5",
            "response",
            {
                "requestId": _parse_int(response_match.group("requestId")) or 0,
                "remote": response_match.group("remote"),
                "priority": response_match.group("priority") == "true",
                "occurrence": _parse_int(response_match.group("occurrence")) or 0,
                "requestKind": response_match.group("requestKind"),
                "index": _parse_int(response_match.group("index")) or 0,
                "archive": _parse_int(response_match.group("archive")) or 0,
                "bytes": _parse_int(response_match.group("bytes")) or 0,
            },
        )
    return None


def normalize_clienterror_file(path: Path) -> tuple[str, str, dict[str, Any]]:
    return "client.exception", "clienterror-file", {"path": str(path), "bytes": path.stat().st_size}


def is_local_host(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower().strip("[]") in LOCALHOST_HOSTS


def collect_process_events(
    process: psutil.Process,
    previous: dict[str, Any],
    *,
    include_file_delta: bool,
    sample_due: bool,
) -> list[tuple[str, str, dict[str, Any], float]]:
    events: list[tuple[str, str, dict[str, Any], float]] = []
    now_epoch = time.time()

    try:
        connections = list(process.net_connections(kind="inet"))
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        connections = []
    current_conn_keys = {
        (
            getattr(connection.laddr, "ip", ""),
            getattr(connection.laddr, "port", 0),
            getattr(connection.raddr, "ip", "") if connection.raddr else "",
            getattr(connection.raddr, "port", 0) if connection.raddr else 0,
            connection.status,
        )
        for connection in connections
    }
    previous_conn_keys = previous.setdefault("connections", set())
    for key in sorted(current_conn_keys - previous_conn_keys):
        _, _, remote_ip, remote_port, status = key
        events.append(("client.proc", "connection-open", {"remoteHost": remote_ip, "remotePort": remote_port, "status": status}, now_epoch))
    for key in sorted(previous_conn_keys - current_conn_keys):
        _, _, remote_ip, remote_port, status = key
        events.append(("client.proc", "connection-close", {"remoteHost": remote_ip, "remotePort": remote_port, "status": status}, now_epoch))
    previous["connections"] = current_conn_keys

    window = get_window_info(process.pid)
    if window != previous.get("window"):
        events.append(("client.window", "state", window, now_epoch))
        previous["window"] = window

    if include_file_delta:
        try:
            open_files = {item.path for item in process.open_files()}
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            open_files = set()
        previous_files = previous.setdefault("openFiles", set())
        for path in sorted(open_files - previous_files):
            category = "cache" if ".jcache" in path.lower() or "jagex" in path.lower() else "unknown"
            events.append(("client.file", "open-passive", {"path": path, "fileCategory": category}, now_epoch))
        previous["openFiles"] = open_files

    if sample_due:
        try:
            memory = process.memory_info()
            cpu_percent = process.cpu_percent(interval=None)
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            memory = None
            cpu_percent = None
        local_443 = 0
        external_443 = 0
        for connection in connections:
            remote_ip = getattr(connection.raddr, "ip", "") if connection.raddr else ""
            remote_port = getattr(connection.raddr, "port", 0) if connection.raddr else 0
            if remote_port == 443:
                if is_local_host(remote_ip):
                    local_443 += 1
                else:
                    external_443 += 1
        sample = {
            "cpuPercent": cpu_percent,
            "rssBytes": getattr(memory, "rss", 0) if memory else 0,
            "localMitm443Connections": local_443,
            "directExternal443Connections": external_443,
            "threadCount": process.num_threads() if process.is_running() else 0,
        }
        events.append(("client.proc", "sample", sample, now_epoch))
    return events


def collect_family_sample(processes: dict[int, psutil.Process]) -> tuple[dict[str, Any], float]:
    now_epoch = time.time()
    aggregate = {
        "cpuPercent": 0.0,
        "rssBytes": 0,
        "localMitm443Connections": 0,
        "directExternal443Connections": 0,
        "threadCount": 0,
        "pidCount": 0,
        "pids": [],
    }
    for pid, process in sorted(processes.items()):
        try:
            connections = list(process.net_connections(kind="inet"))
            memory = process.memory_info()
            cpu_percent = process.cpu_percent(interval=None)
            thread_count = process.num_threads() if process.is_running() else 0
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue
        local_443 = 0
        external_443 = 0
        for connection in connections:
            remote_ip = getattr(connection.raddr, "ip", "") if connection.raddr else ""
            remote_port = getattr(connection.raddr, "port", 0) if connection.raddr else 0
            if remote_port == 443:
                if is_local_host(remote_ip):
                    local_443 += 1
                else:
                    external_443 += 1
        aggregate["cpuPercent"] += float(cpu_percent or 0.0)
        aggregate["rssBytes"] += int(getattr(memory, "rss", 0) or 0)
        aggregate["localMitm443Connections"] += local_443
        aggregate["directExternal443Connections"] += external_443
        aggregate["threadCount"] += int(thread_count or 0)
        aggregate["pidCount"] += 1
        aggregate["pids"].append(int(pid))
    return aggregate, now_epoch


def collect_family_events(
    processes: dict[int, psutil.Process],
    previous: dict[int, dict[str, Any]],
    *,
    include_file_delta: bool,
    sample_due: bool,
) -> list[tuple[str, str, dict[str, Any], float]]:
    events: list[tuple[str, str, dict[str, Any], float]] = []
    current_pids = set(processes)
    for stale_pid in list(previous.keys()):
        if stale_pid not in current_pids:
            previous.pop(stale_pid, None)
    for pid, process in sorted(processes.items()):
        process_events = collect_process_events(
            process,
            previous.setdefault(pid, {}),
            include_file_delta=include_file_delta,
            sample_due=False,
        )
        for category, action, details, event_epoch in process_events:
            merged_details = {"pid": pid}
            merged_details.update(details)
            events.append((category, action, merged_details, event_epoch))
    if sample_due:
        aggregate, now_epoch = collect_family_sample(processes)
        events.append(("client.proc", "sample", aggregate, now_epoch))
    return events


def update_summary(summary: dict[str, Any], event: dict[str, Any]) -> None:
    category = event["category"]
    action = event["action"]
    details = event["details"]
    timestamp = parse_timestamp(event["timestamp"]) or datetime.now(timezone.utc)

    summary["eventCount"] += 1
    summary["categoryCounts"][category] += 1

    if category == "world.stage":
        stage = details.get("stage")
        if stage and stage not in summary["worldStages"]:
            summary["worldStages"].append(stage)
        summary["worldBootstrapObserved"] = True
    elif category == "world.marker":
        if action == "world-send-rebuild-tail" and summary.get("rebuildTailTimestamp") is None:
            summary["rebuildTailTimestamp"] = timestamp
        if details.get("kind") == "world-awaiting-ready-signal":
            summary["awaitingReadySignalCount"] += 1
    elif category == "proxy.content":
        if action == "route":
            route = str(details.get("sessionRoute") or details.get("summary") or "")
            if route:
                summary["contentSessionRoutes"][route] += 1
            if route == "raw-game":
                summary["proxyRawGameObserved"] = True
            elif route == "tls-secure-game":
                summary["proxySecureGameTlsObserved"] = True
            elif route == "tls-http-content":
                summary["proxyHttpContentTlsObserved"] = True
                summary["localContentMitmObserved"] = True
        elif action == "route-mode":
            route_mode = str(details.get("routeMode") or details.get("summary") or "")
            if route_mode:
                summary["proxyRouteModes"][route_mode] += 1
            if route_mode == "passthrough":
                summary["proxySecureGamePassthroughObserved"] = True
        elif action == "route-source":
            route_source = str(details.get("routeSource") or details.get("summary") or "")
            if route_source:
                summary["contentRouteSources"][route_source] += 1
            if route_source == "backend":
                summary["proxySecureGameBackendFirstObserved"] = True
        elif action == "clienthello-sni":
            tls_clienthello_sni = str(details.get("tlsClienthelloSni") or details.get("summary") or "")
            summary["tlsClienthelloSnis"][tls_clienthello_sni] += 1
        elif action == "cert-subject":
            subject = str(details.get("tlsCertSubject") or details.get("summary") or "")
            if subject:
                summary["tlsCertSubjects"][subject] += 1
        elif action == "cert-issuer":
            issuer = str(details.get("tlsCertIssuer") or details.get("summary") or "")
            if issuer:
                summary["tlsCertIssuers"][issuer] += 1
        elif action == "cert-thumbprint":
            thumbprint = str(details.get("tlsCertThumbprint") or details.get("summary") or "")
            if thumbprint:
                summary["tlsCertThumbprints"][thumbprint] += 1
        elif action == "wrap-status":
            wrap_status = str(details.get("tlsServerWrapStatus") or details.get("summary") or "")
            if wrap_status:
                summary["proxyMitmWrapStatuses"][wrap_status] += 1
            if wrap_status == "ok":
                summary["proxyMitmHandshakeOkObserved"] = True
            elif wrap_status in {"error", "eof"}:
                summary["proxyMitmHandshakeFailedObserved"] = True
        if action == "request":
            summary["localContentMitmObserved"] = True
            summary["localMsRequestsObserved"] = True
            if summary["firstJs5RequestTimestamp"] is None:
                summary["firstJs5RequestTimestamp"] = timestamp
            archive = details.get("archive")
            if archive is not None and archive != 255:
                summary["archiveRequestCount"] += 1
                if summary["firstArchiveRequestTimestamp"] is None:
                    summary["firstArchiveRequestTimestamp"] = timestamp
                summary["proxyArchiveRequestBySource"][event["source"]] = True
        elif action == "response":
            summary["localContentMitmObserved"] = True
            summary["responseHeaderCount"] += 1
            content_length = details.get("contentLength")
            if isinstance(content_length, int):
                summary["responseBytes"] += max(content_length, 0)
            if summary["firstJs5ResponseTimestamp"] is None:
                summary["firstJs5ResponseTimestamp"] = timestamp
            if summary["proxyArchiveRequestBySource"].get(event["source"]) and summary["firstArchiveResponseTimestamp"] is None:
                summary["firstArchiveResponseTimestamp"] = timestamp
        elif action == "error":
            summary["contentErrors"].append(details.get("summary", ""))
    elif category == "proxy.js5":
        if action == "summary":
            summary["js5SummaryCount"] += 1
            summary["archiveRequestCount"] = max(summary["archiveRequestCount"], int(details.get("archiveRequests", 0) or 0))
            summary["responseHeaderCount"] = max(summary["responseHeaderCount"], int(details.get("responseHeaders", 0) or 0))
        elif action == "request":
            summary["js5LiveRequestCount"] += 1
            request_kind = str(details.get("requestKind") or "")
            index = _parse_int(details.get("index")) or 0
            archive = _parse_int(details.get("archive")) or 0
            if request_kind == "reference-table" and index == 255:
                summary["js5ReferenceTable255RequestCount"] += 1
                summary["js5ReferenceTable255ArchiveCounts"][archive] += 1
            else:
                summary["archiveRequestCount"] += 1
                if summary["firstArchiveRequestTimestamp"] is None:
                    summary["firstArchiveRequestTimestamp"] = timestamp
            if summary["firstJs5RequestTimestamp"] is None:
                summary["firstJs5RequestTimestamp"] = timestamp
        elif action == "response":
            summary["js5LiveResponseCount"] += 1
            request_kind = str(details.get("requestKind") or "")
            index = _parse_int(details.get("index")) or 0
            archive = _parse_int(details.get("archive")) or 0
            if request_kind == "reference-table" and index == 255:
                summary["js5ReferenceTable255ResponseCount"] += 1
            else:
                if summary["firstArchiveResponseTimestamp"] is None:
                    summary["firstArchiveResponseTimestamp"] = timestamp
            if summary["firstJs5ResponseTimestamp"] is None:
                summary["firstJs5ResponseTimestamp"] = timestamp
            summary["responseBytes"] += max(_parse_int(details.get("bytes")) or 0, 0)
    elif category == "client.file":
        file_category = details.get("fileCategory") or "unknown"
        if action in {"open", "open-passive"}:
            summary["fileOpenCounts"][file_category] += 1
        if action == "close":
            summary["fileBytesRead"][file_category] += int(details.get("totalBytesRead", 0) or 0)
    elif category == "client.tls":
        status = details.get("status")
        policy_status = details.get("policyStatus")
        if action == "initialize-security-context" and status == 0:
            summary["tlsContextEstablished"] = True
        if action == "query-context-attributes":
            attribute_name = str(details.get("attributeName") or "")
            if attribute_name:
                summary["tlsAttributeCounts"][attribute_name] += 1
            if status == 0 and attribute_name == "SECPKG_ATTR_REMOTE_CERT_CONTEXT":
                summary["tlsRemoteCertObserved"] = True
            if status == 0 and attribute_name == "SECPKG_ATTR_CONNECTION_INFO":
                summary["tlsConnectionInfoObserved"] = True
        if action in {"encrypt-message", "decrypt-message"} and status == 0:
            summary["tlsAppDataObserved"] = True
            if action == "encrypt-message":
                summary["tlsEncryptCount"] += 1
                if summary["firstTlsEncryptTimestamp"] is None:
                    summary["firstTlsEncryptTimestamp"] = timestamp
            else:
                summary["tlsDecryptCount"] += 1
                if summary["firstTlsDecryptTimestamp"] is None:
                    summary["firstTlsDecryptTimestamp"] = timestamp
        if isinstance(status, int) and status not in HOOK_ALLOWED_TLS_STATUSES:
            summary["tlsAnomalies"].append({"action": action, "status": status})
        if isinstance(policy_status, dict) and int(policy_status.get("error", 0) or 0) != 0:
            summary["tlsAnomalies"].append({"action": action, "policyError": policy_status.get("error")})
    elif category == "client.module":
        module_name = str(details.get("moduleName") or "").lower()
        module_path = str(details.get("path") or "")
        if module_name:
            summary["loadedModuleNames"].add(module_name)
        if module_path:
            summary["loadedModulePaths"].add(module_path)
        if "cef" in module_name or "chrome" in module_name:
            summary["cefObserved"] = True
        if any(token in module_name for token in ("ssl", "crypto", "curl", "nss3", "boringssl")):
            summary["cryptoModuleObserved"] = True
    elif category == "client.exception":
        summary["exceptionCount"] += 1
        if is_nonfatal_graphics_exception(details):
            summary["nonFatalGraphicsExceptionCount"] += 1
        else:
            summary["crashDetected"] = True
            summary["fatalExceptionCount"] += 1
    elif category == "client.net":
        host = details.get("host")
        if isinstance(host, str) and host:
            summary["resolvedHosts"].add(host)
    elif category == "client.proc":
        if action == "sample":
            summary["lastProcessSample"] = details
        remote_port = details.get("remotePort")
        remote_host = details.get("remoteHost")
        if remote_port == 443:
            if is_local_host(remote_host):
                summary["localMitm443Seen"] = True
            else:
                summary["directExternal443Seen"] = True
                if remote_host:
                    summary["directExternal443Targets"].add(f"{remote_host}:{remote_port}")
    elif category == "client.window":
        if details.get("exists"):
            summary["windowObserved"] = True
            if details.get("title"):
                summary["latestWindowTitle"] = details.get("title")


def derive_terminal_state(summary: dict[str, Any], process_alive: bool) -> str:
    if summary["crashDetected"]:
        return "crash"
    if "interfaces" in summary["worldStages"]:
        if summary["localContentMitmObserved"] or summary["archiveRequestCount"] > 0 or summary["responseHeaderCount"] > 0:
            return "black-screen-plateau"
        return "black-screen-loading"
    if summary["worldBootstrapObserved"]:
        return "world-bootstrap"
    if (
        process_alive
        and int(summary.get("js5ReferenceTable255RequestCount", 0) or 0) > 0
        and int(summary.get("archiveRequestCount", 0) or 0) == 0
        and not summary.get("worldBootstrapObserved")
    ):
        return "loading-application-resources-loop"
    if summary.get("proxyMitmHandshakeFailedObserved") and not summary.get("proxyMitmHandshakeOkObserved"):
        return "prelogin-mitm-handshake-failed"
    if summary.get("proxyHttpContentTlsObserved") and summary.get("proxyMitmHandshakeOkObserved"):
        return "prelogin-http-content"
    if summary.get("proxySecureGamePassthroughObserved"):
        return "prelogin-secure-game-passthrough"
    if summary.get("proxySecureGameTlsObserved"):
        return "prelogin-secure-game"
    if summary.get("contentErrors") or (summary.get("tlsContextEstablished") and not summary.get("tlsAppDataObserved")):
        return "prelogin-tls-failed"
    if summary.get("proxyRawGameObserved"):
        return "prelogin-raw-game-only"
    if summary["windowObserved"] and process_alive:
        if not summary["localMitm443Seen"] and not summary["directExternal443Seen"]:
            return "login-screen"
        return "prelogin-stall-before-secure-game"
    return "prelogin-stall-before-secure-game"


def summarize_timing(summary: dict[str, Any], key: str) -> float | None:
    value = summary.get(key)
    if not isinstance(value, datetime):
        return None
    start = summary.get("sessionStartedAt")
    if not isinstance(start, datetime):
        return None
    return round((value - start).total_seconds(), 3)


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {})
    lines = [
        "# Live Rs2Client Watch",
        "",
        f"- Build: `{artifact.get('build')}`",
        f"- Status: `{artifact['status']}`",
        f"- Launch mode: `{summary.get('launchMode')}`",
        f"- Client pid: `{summary.get('clientPid')}`",
        f"- Family pids: `{','.join(str(pid) for pid in summary.get('familyPids', []))}`",
        f"- Canonical route status: `{summary.get('canonicalRouteStatus')}`",
        f"- Terminal state: `{summary.get('terminalState')}`",
        f"- World bootstrap observed: `{summary.get('worldBootstrapObserved')}`",
        f"- Local content MITM observed: `{summary.get('localContentMitmObserved')}`",
        f"- Proxy raw-game observed: `{summary.get('proxyRawGameObserved')}`",
        f"- Proxy tls-secure-game observed: `{summary.get('proxySecureGameTlsObserved')}`",
        f"- Proxy secure-game passthrough observed: `{summary.get('proxySecureGamePassthroughObserved')}`",
        f"- Proxy tls-http-content observed: `{summary.get('proxyHttpContentTlsObserved')}`",
        f"- Proxy MITM handshake ok observed: `{summary.get('proxyMitmHandshakeOkObserved')}`",
        f"- Proxy MITM handshake failed observed: `{summary.get('proxyMitmHandshakeFailedObserved')}`",
        f"- Proxy MITM wrap statuses: `{summary.get('proxyMitmWrapStatuses')}`",
        f"- Proxy route modes: `{summary.get('proxyRouteModes')}`",
        f"- Secure-game backend-first observed: `{summary.get('proxySecureGameBackendFirstObserved')}`",
        f"- Route sources: `{summary.get('contentRouteSources')}`",
        f"- ClientHello SNI values: `{summary.get('tlsClienthelloSnis')}`",
        f"- TLS cert subjects: `{summary.get('tlsCertSubjects')}`",
        f"- TLS cert issuers: `{summary.get('tlsCertIssuers')}`",
        f"- TLS cert thumbprints: `{summary.get('tlsCertThumbprints')}`",
        f"- First archive request seconds: `{summary.get('firstArchiveRequestSeconds')}`",
        f"- First archive response seconds: `{summary.get('firstArchiveResponseSeconds')}`",
        f"- Response headers: `{summary.get('responseHeaderCount')}`",
        f"- Live JS5 requests: `{summary.get('js5LiveRequestCount')}`",
        f"- Live JS5 responses: `{summary.get('js5LiveResponseCount')}`",
        f"- 255 table requests: `{summary.get('js5ReferenceTable255RequestCount')}`",
        f"- 255 table responses: `{summary.get('js5ReferenceTable255ResponseCount')}`",
        f"- 255 table archives: `{summary.get('js5ReferenceTable255ArchiveCounts')}`",
        f"- Crash detected: `{summary.get('crashDetected')}`",
        f"- Fatal exceptions: `{summary.get('fatalExceptionCount')}`",
        f"- Nonfatal graphics exceptions: `{summary.get('nonFatalGraphicsExceptionCount')}`",
        f"- TLS anomalies: `{summary.get('tlsAnomalyCount')}`",
        f"- TLS context established: `{summary.get('tlsContextEstablished')}`",
        f"- TLS app-data observed: `{summary.get('tlsAppDataObserved')}`",
        f"- TLS encrypt count: `{summary.get('tlsEncryptCount')}`",
        f"- TLS decrypt count: `{summary.get('tlsDecryptCount')}`",
        f"- CEF observed: `{summary.get('cefObserved')}`",
        f"- Crypto modules observed: `{summary.get('cryptoModuleObserved')}`",
        f"- World window pre-scan skipped: `{summary.get('worldWindowSelectionSkipped')}`",
        f"- World window pre-scan reason: `{summary.get('worldWindowSelectionSkipReason')}`",
        "",
        "## Artifacts",
        "",
        f"- Session JSONL: `{artifact['artifacts'].get('sessionJsonl')}`",
        f"- Summary JSON: `{artifact['artifacts'].get('summaryJson')}`",
        f"- Summary Markdown: `{artifact['artifacts'].get('summaryMarkdown')}`",
        f"- Hook JSONL: `{artifact['artifacts'].get('hooksJsonl')}`",
        "",
    ]
    if summary.get("directExternal443Targets"):
        lines.append("## Direct External 443 Targets")
        lines.append("")
        for target in summary["directExternal443Targets"]:
            lines.append(f"- `{target}`")
        lines.append("")
    if summary.get("resolvedHosts"):
        lines.append("## Resolved Hosts")
        lines.append("")
        for host in summary["resolvedHosts"]:
            lines.append(f"- `{host}`")
        lines.append("")
    if summary.get("loadedModuleNames"):
        lines.append("## Interesting Modules")
        lines.append("")
        for module_name in summary["loadedModuleNames"]:
            lines.append(f"- `{module_name}`")
        lines.append("")
    return "\n".join(lines)


def build_summary_artifact(
    args: argparse.Namespace,
    *,
    status: str,
    paths: dict[str, Path],
    runtime_build: int,
    launch_mode: str,
    client_pid: int | None,
    launch: dict[str, Any] | None,
    launch_evaluation: dict[str, Any] | None,
    summary: dict[str, Any],
    world_window: str | None,
) -> dict[str, Any]:
    family_pids = [int(pid) for pid in summary.get("familyPids", []) if isinstance(pid, int)]
    process_alive = any(psutil.pid_exists(pid) for pid in family_pids) if family_pids else (client_pid is not None and psutil.pid_exists(client_pid))
    terminal_state = derive_terminal_state(summary, process_alive)
    canonical_route_status = "unknown"
    if launch_evaluation:
        canonical_route_status = "canonical" if launch_evaluation.get("canonicalMitmLaunch") else "non-canonical"
    return standard_tool_artifact(
        tool_name="watch_rs2client_live",
        status=status,
        build=runtime_build,
        inputs={
            "launchMode": launch_mode,
            "clientVariant": args.client_variant,
            "pid": args.pid or 0,
            "durationSeconds": args.duration_seconds,
            "verbose": bool(args.verbose),
            "noFrida": bool(args.no_frida),
            "worldLog": str(args.world_log),
            "contentCaptureDir": str(args.content_capture_dir),
            "js5SessionDir": str(args.js5_session_dir),
            "clienterrorDir": str(args.clienterror_dir),
            "serverLog": str(getattr(args, "server_log", DEFAULT_SERVER_LOG)),
        },
        artifacts={
            "sessionJsonl": str(paths["sessionJsonl"]),
            "summaryJson": str(paths["summaryJson"]),
            "summaryMarkdown": str(paths["summaryMarkdown"]),
            "hooksJsonl": str(paths["hooksJsonl"]),
            "latestSummaryJson": str(args.output_dir / LATEST_SUMMARY_JSON),
            "latestSessionJsonl": str(args.output_dir / LATEST_SESSION_JSONL),
        },
        summary={
            "launchMode": launch_mode,
            "clientPid": client_pid,
            "familyPids": family_pids,
            "canonicalRouteStatus": canonical_route_status,
            "terminalState": terminal_state,
            "sessionStartedAt": summary["sessionStartedAt"].isoformat() if isinstance(summary.get("sessionStartedAt"), datetime) else "",
            "sessionEndedAt": summary["sessionEndedAt"].isoformat() if isinstance(summary.get("sessionEndedAt"), datetime) else "",
            "sessionDurationSeconds": summarize_timing(summary, "sessionEndedAt"),
            "worldBootstrapObserved": bool(summary["worldBootstrapObserved"]),
            "worldWindowSelected": world_window or "",
            "localContentMitmObserved": bool(summary["localContentMitmObserved"]),
            "localMsRequestsObserved": bool(summary["localMsRequestsObserved"]),
            "proxyRawGameObserved": bool(summary["proxyRawGameObserved"]),
            "proxySecureGameTlsObserved": bool(summary["proxySecureGameTlsObserved"]),
            "proxySecureGamePassthroughObserved": bool(summary["proxySecureGamePassthroughObserved"]),
            "proxyHttpContentTlsObserved": bool(summary["proxyHttpContentTlsObserved"]),
            "proxyMitmHandshakeOkObserved": bool(summary["proxyMitmHandshakeOkObserved"]),
            "proxyMitmHandshakeFailedObserved": bool(summary["proxyMitmHandshakeFailedObserved"]),
            "contentSessionRoutes": dict(summary["contentSessionRoutes"]),
            "proxyMitmWrapStatuses": dict(summary["proxyMitmWrapStatuses"]),
            "proxyRouteModes": dict(summary["proxyRouteModes"]),
            "contentRouteSources": dict(summary["contentRouteSources"]),
            "proxySecureGameBackendFirstObserved": bool(summary["proxySecureGameBackendFirstObserved"]),
            "tlsClienthelloSnis": dict(summary["tlsClienthelloSnis"]),
            "tlsCertSubjects": dict(summary["tlsCertSubjects"]),
            "tlsCertIssuers": dict(summary["tlsCertIssuers"]),
            "tlsCertThumbprints": dict(summary["tlsCertThumbprints"]),
            "firstJs5RequestSeconds": summarize_timing(summary, "firstJs5RequestTimestamp"),
            "firstArchiveRequestSeconds": summarize_timing(summary, "firstArchiveRequestTimestamp"),
            "firstJs5ResponseSeconds": summarize_timing(summary, "firstJs5ResponseTimestamp"),
            "firstArchiveResponseSeconds": summarize_timing(summary, "firstArchiveResponseTimestamp"),
            "responseHeaderCount": summary["responseHeaderCount"],
            "responseBytes": summary["responseBytes"],
            "archiveRequestCount": summary["archiveRequestCount"],
            "js5LiveRequestCount": int(summary.get("js5LiveRequestCount", 0) or 0),
            "js5LiveResponseCount": int(summary.get("js5LiveResponseCount", 0) or 0),
            "js5ReferenceTable255RequestCount": int(summary.get("js5ReferenceTable255RequestCount", 0) or 0),
            "js5ReferenceTable255ResponseCount": int(summary.get("js5ReferenceTable255ResponseCount", 0) or 0),
            "js5ReferenceTable255ArchiveCounts": dict(summary.get("js5ReferenceTable255ArchiveCounts", {})),
            "crashDetected": bool(summary["crashDetected"]),
            "exceptionCount": summary["exceptionCount"],
            "fatalExceptionCount": summary["fatalExceptionCount"],
            "nonFatalGraphicsExceptionCount": summary["nonFatalGraphicsExceptionCount"],
            "tlsAnomalyCount": len(summary["tlsAnomalies"]),
            "tlsContextEstablished": bool(summary["tlsContextEstablished"]),
            "tlsAppDataObserved": bool(summary["tlsAppDataObserved"]),
            "tlsEncryptCount": int(summary["tlsEncryptCount"]),
            "tlsDecryptCount": int(summary["tlsDecryptCount"]),
            "firstTlsEncryptSeconds": summarize_timing(summary, "firstTlsEncryptTimestamp"),
            "firstTlsDecryptSeconds": summarize_timing(summary, "firstTlsDecryptTimestamp"),
            "tlsRemoteCertObserved": bool(summary["tlsRemoteCertObserved"]),
            "tlsConnectionInfoObserved": bool(summary["tlsConnectionInfoObserved"]),
            "tlsAttributeCounts": dict(summary["tlsAttributeCounts"]),
            "fileOpenCounts": dict(summary["fileOpenCounts"]),
            "fileBytesRead": dict(summary["fileBytesRead"]),
            "worldStages": list(summary["worldStages"]),
            "directExternal443Targets": sorted(summary["directExternal443Targets"]),
            "resolvedHosts": sorted(summary["resolvedHosts"]),
            "loadedModuleNames": sorted(summary["loadedModuleNames"]),
            "cefObserved": bool(summary["cefObserved"]),
            "cryptoModuleObserved": bool(summary["cryptoModuleObserved"]),
            "localMitm443Connections": int((summary.get("lastProcessSample") or {}).get("localMitm443Connections", 0) or 0),
            "directExternal443Connections": int((summary.get("lastProcessSample") or {}).get("directExternal443Connections", 0) or 0),
            "deepHooksEnabled": not args.no_frida,
            "worldWindowSelectionSkipped": bool(summary.get("worldWindowSelectionSkipped")),
            "worldWindowSelectionSkipReason": str(summary.get("worldWindowSelectionSkipReason") or ""),
        },
        extra={
            "launch": launch or {},
            "launchEvaluation": launch_evaluation or {},
            "details": {
                "eventCount": summary["eventCount"],
                "categoryCounts": dict(summary["categoryCounts"]),
                "tlsAnomalies": summary["tlsAnomalies"],
                "contentErrors": summary["contentErrors"],
                "lastProcessSample": summary.get("lastProcessSample") or {},
                "latestWindowTitle": summary.get("latestWindowTitle", ""),
            },
        },
    )


def prepare_world_window_baseline(
    world_log: Path,
    *,
    max_prescan_bytes: int = WORLD_LOG_PRESCAN_MAX_BYTES,
) -> tuple[list[str], bool, str]:
    if not world_log.exists():
        return [], False, ""
    try:
        world_log_size = world_log.stat().st_size
    except OSError:
        return [], True, "world-log-stat-failed"
    if world_log_size > max_prescan_bytes:
        return [], True, f"world-log-too-large:{world_log_size}"
    try:
        return [f"{session['startLine']}:{session['endLine']}" for session in load_all_sessions(world_log)], False, ""
    except MemoryError:
        return [], True, "world-log-prescan-memoryerror"


def latest_rs2client_pid() -> int | None:
    main_candidates = []
    all_candidates = []
    for process in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        try:
            if (process.info.get("name") or "").lower() == "rs2client.exe":
                pid = int(process.info["pid"])
                created = float(process.info.get("create_time") or 0.0)
                cmdline_parts = process.info.get("cmdline") or []
                command_line = normalize_cmdline_text(cmdline_parts)
                candidate = (created, pid)
                all_candidates.append(candidate)
                if not is_compile_shader_cmdline(command_line):
                    main_candidates.append(candidate)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if main_candidates:
        return sorted(main_candidates)[-1][1]
    if not all_candidates:
        return None
    return sorted(all_candidates)[-1][1]


def resolve_watch_target(args: argparse.Namespace) -> tuple[str, int | None, bool]:
    if args.pid is not None:
        return "attach", int(args.pid), False
    if not args.force_launch:
        existing_pid = latest_rs2client_pid()
        if existing_pid is not None:
            return "attach", int(existing_pid), True
    return "launch", None, False


def pick_family_root(candidate_pid: int | None, family_processes: dict[int, psutil.Process]) -> int | None:
    if candidate_pid is not None and psutil.pid_exists(candidate_pid):
        return int(candidate_pid)
    for pid in sorted(family_processes):
        if psutil.pid_exists(pid):
            return int(pid)
    return None


def launch_live_stack_for_watch(args: argparse.Namespace, paths: dict[str, Path]) -> dict[str, Any]:
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
    stdout_handle = paths["launchStdout"].open("w", encoding="utf-8")
    stderr_handle = paths["launchStderr"].open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(WORKSPACE),
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
    )
    state: dict[str, Any] | None = None
    deadline = time.time() + 180.0
    while time.time() < deadline:
        if LAUNCH_STATE_FILE.exists():
            try:
                payload = json.loads(LAUNCH_STATE_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                payload = None
            if isinstance(payload, dict):
                state = payload
                if isinstance(payload.get("ClientPid"), int):
                    break
        if process.poll() is not None and state is None:
            break
        time.sleep(0.5)
    stdout_handle.flush()
    stderr_handle.flush()
    stdout_handle.close()
    stderr_handle.close()
    return {
        "command": command,
        "returnCode": process.poll(),
        "stdout": paths["launchStdout"].read_text(encoding="utf-8", errors="ignore") if paths["launchStdout"].exists() else "",
        "stderr": paths["launchStderr"].read_text(encoding="utf-8", errors="ignore") if paths["launchStderr"].exists() else "",
        "state": state,
        "launcherPid": int(process.pid),
    }


def main() -> int:
    args = parse_args()
    ensure_directory(args.output_dir)
    stamp = session_stamp()
    paths = session_paths(args.output_dir, stamp)
    runtime_build = resolve_runtime_build(client_pid=args.pid)
    missing = {name: str(path) for name, path in required_paths(args).items() if not path.exists()}
    if missing:
        artifact = standard_tool_artifact(
            tool_name="watch_rs2client_live",
            status="blocked",
            build=runtime_build,
            inputs={"launchMode": "attach" if args.pid else "launch"},
            artifacts={"summaryJson": str(paths["summaryJson"]), "summaryMarkdown": str(paths["summaryMarkdown"])},
            summary={"reason": "missing-required-paths"},
            extra={"missingPaths": missing},
        )
        write_json(paths["summaryJson"], artifact)
        paths["summaryMarkdown"].write_text(render_markdown(artifact), encoding="utf-8")
        copy_latest(paths, args.output_dir)
        print(stable_json_text({"status": "blocked", "artifacts": artifact["artifacts"]}), end="")
        return 1

    world_before, world_window_selection_skipped, world_window_selection_skip_reason = prepare_world_window_baseline(args.world_log)
    tail = TailState()
    if args.world_log.exists():
        tail.prime_file(args.world_log)
    if args.server_log.exists():
        tail.prime_file(args.server_log)

    launch_mode, client_pid, auto_attached_existing = resolve_watch_target(args)
    launch: dict[str, Any] | None = None
    launch_state: dict[str, Any] | None = None
    launch_evaluation: dict[str, Any] | None = None
    if launch_mode == "launch":
        launch = launch_live_stack_for_watch(args, paths)
        launch_state = launch.get("state") if isinstance(launch.get("state"), dict) else None
        launch_evaluation = evaluate_launch_route(launch_state or {})
        runtime_build = resolve_runtime_build(client_pid=None, launch_state=launch_state)
        client_pid = int(launch_state["ClientPid"]) if isinstance(launch_state, dict) and isinstance(launch_state.get("ClientPid"), int) else None
        if client_pid is None or (launch.get("returnCode") not in (None, 0)):
            artifact = standard_tool_artifact(
                tool_name="watch_rs2client_live",
                status="blocked",
                build=runtime_build,
                inputs={"launchMode": launch_mode, "clientVariant": args.client_variant},
                artifacts={"summaryJson": str(paths["summaryJson"]), "summaryMarkdown": str(paths["summaryMarkdown"])},
                summary={"reason": "launch-failed"},
                extra={"launch": launch or {}},
            )
            write_json(paths["summaryJson"], artifact)
            paths["summaryMarkdown"].write_text(render_markdown(artifact), encoding="utf-8")
            copy_latest(paths, args.output_dir)
            print(stable_json_text({"status": "blocked", "artifacts": artifact["artifacts"]}), end="")
            return 1
    else:
        if client_pid is None:
            client_pid = latest_rs2client_pid()
        if client_pid is None or not psutil.pid_exists(client_pid):
            artifact = standard_tool_artifact(
                tool_name="watch_rs2client_live",
                status="blocked",
                build=runtime_build,
                inputs={"launchMode": launch_mode, "pid": args.pid or 0},
                artifacts={"summaryJson": str(paths["summaryJson"]), "summaryMarkdown": str(paths["summaryMarkdown"])},
                summary={"reason": "attach-target-missing"},
            )
            write_json(paths["summaryJson"], artifact)
            paths["summaryMarkdown"].write_text(render_markdown(artifact), encoding="utf-8")
            copy_latest(paths, args.output_dir)
            print(stable_json_text({"status": "blocked", "artifacts": artifact["artifacts"]}), end="")
            return 1
        if LAUNCH_STATE_FILE.exists():
            payload = json.loads(LAUNCH_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and launch_state_matches_client(payload, client_pid):
                launch_state = payload
                launch_evaluation = evaluate_launch_route(payload)
                runtime_build = resolve_runtime_build(client_pid=client_pid, launch_state=payload)

    ensure_directory(paths["hookDir"])
    session_start_epoch = time.time()
    recent_file_lower_bound = session_start_epoch - SESSION_EVIDENCE_LEEWAY_SECONDS
    tracked_content_paths = recent_directory_paths(
        args.content_capture_dir,
        "session-*.log",
        since_epoch=recent_file_lower_bound,
        max_files=MAX_RECENT_CONTENT_SESSION_FILES,
    )
    tracked_js5_summary_paths = recent_directory_paths(
        args.js5_session_dir,
        "summary-*.json",
        since_epoch=recent_file_lower_bound,
        max_files=MAX_RECENT_JS5_SUMMARY_FILES,
    )
    tracked_clienterror_paths = recent_directory_paths(
        args.clienterror_dir,
        "*",
        since_epoch=recent_file_lower_bound,
        max_files=MAX_RECENT_CLIENTERROR_FILES,
    )
    summary = {
        "sessionStartedAt": datetime.now(timezone.utc),
        "sessionEndedAt": None,
        "eventCount": 0,
        "categoryCounts": Counter(),
        "worldStages": [],
        "worldBootstrapObserved": False,
        "rebuildTailTimestamp": None,
        "awaitingReadySignalCount": 0,
        "localContentMitmObserved": False,
        "localMsRequestsObserved": False,
        "proxyRawGameObserved": False,
        "proxySecureGameTlsObserved": False,
        "proxySecureGamePassthroughObserved": False,
        "proxyHttpContentTlsObserved": False,
        "proxyMitmHandshakeOkObserved": False,
        "proxyMitmHandshakeFailedObserved": False,
        "contentSessionRoutes": Counter(),
        "proxyMitmWrapStatuses": Counter(),
        "proxyRouteModes": Counter(),
        "contentRouteSources": Counter(),
        "proxySecureGameBackendFirstObserved": False,
        "tlsClienthelloSnis": Counter(),
        "tlsCertSubjects": Counter(),
        "tlsCertIssuers": Counter(),
        "tlsCertThumbprints": Counter(),
        "archiveRequestCount": 0,
        "responseHeaderCount": 0,
        "responseBytes": 0,
        "firstJs5RequestTimestamp": None,
        "firstArchiveRequestTimestamp": None,
        "firstJs5ResponseTimestamp": None,
        "firstArchiveResponseTimestamp": None,
        "proxyArchiveRequestBySource": defaultdict(bool),
        "fileOpenCounts": Counter(),
        "fileBytesRead": Counter(),
        "tlsAnomalies": [],
        "tlsContextEstablished": False,
        "tlsAppDataObserved": False,
        "tlsEncryptCount": 0,
        "tlsDecryptCount": 0,
        "firstTlsEncryptTimestamp": None,
        "firstTlsDecryptTimestamp": None,
        "tlsRemoteCertObserved": False,
        "tlsConnectionInfoObserved": False,
        "tlsAttributeCounts": Counter(),
        "contentErrors": [],
        "crashDetected": False,
        "exceptionCount": 0,
        "fatalExceptionCount": 0,
        "nonFatalGraphicsExceptionCount": 0,
        "js5SummaryCount": 0,
        "js5LiveRequestCount": 0,
        "js5LiveResponseCount": 0,
        "js5ReferenceTable255RequestCount": 0,
        "js5ReferenceTable255ResponseCount": 0,
        "js5ReferenceTable255ArchiveCounts": Counter(),
        "lastProcessSample": {},
        "windowObserved": False,
        "latestWindowTitle": "",
        "localMitm443Seen": False,
        "directExternal443Seen": False,
        "directExternal443Targets": set(),
        "resolvedHosts": set(),
        "loadedModuleNames": set(),
        "loadedModulePaths": set(),
        "cefObserved": False,
        "cryptoModuleObserved": False,
        "familyPids": [],
        "worldWindowSelectionSkipped": world_window_selection_skipped,
        "worldWindowSelectionSkipReason": world_window_selection_skip_reason,
    }

    family_processes = discover_process_family(int(client_pid)) if client_pid is not None else {}
    if client_pid is not None and not family_processes:
        try:
            family_processes = {int(client_pid): psutil.Process(int(client_pid))}
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            family_processes = {}
    summary["familyPids"] = sorted(family_processes)

    hook_targets: dict[int, dict[str, Any]] = {}
    for pid in summary["familyPids"]:
        target_paths = hook_target_paths(paths, pid)
        hook_process, hook_command = start_hook_process(
            args,
            pid,
            output_path=target_paths["jsonl"],
            stdout_path=target_paths["stdout"],
            stderr_path=target_paths["stderr"],
        )
        hook_targets[pid] = {
            "pid": pid,
            "process": hook_process,
            "command": hook_command,
            "output": target_paths["jsonl"],
            "stdout": target_paths["stdout"],
            "stderr": target_paths["stderr"],
            "attempts": 1 if hook_process is not None else 0,
            "lastStartEpoch": time.time(),
        }

    with paths["sessionJsonl"].open("w", encoding="utf-8") as session_handle, paths["hooksJsonl"].open("w", encoding="utf-8") as hooks_handle:
        event = emit_event(
            session_handle,
            session_start_epoch,
            session_start_epoch,
            "client.lifecycle",
            "watch-start",
            {
                "launchMode": launch_mode,
                "pid": client_pid,
                "familyPids": summary["familyPids"],
                "deepHooksEnabled": not args.no_frida,
                "autoAttachedExisting": auto_attached_existing,
                "canonicalRouteStatus": "canonical" if (launch_evaluation or {}).get("canonicalMitmLaunch") else ("non-canonical" if launch_evaluation else "unknown"),
            },
            source="watch",
            terminal=True,
        )
        update_summary(summary, event)
        for process in family_processes.values():
            try:
                process.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        previous_process_state: dict[int, dict[str, Any]] = {}
        hook_tail = TailState()
        last_sample_time = 0.0
        last_directory_discovery_time = 0.0
        deadline = session_start_epoch + args.duration_seconds if args.duration_seconds > 0 else None
        try:
            while True:
                now_epoch = time.time()
                if deadline is not None and now_epoch >= deadline:
                    break
                family_root = pick_family_root(int(client_pid) if client_pid is not None else None, family_processes)
                if family_root is None:
                    break
                current_family = discover_process_family(family_root)
                if not current_family and family_processes:
                    current_family = {pid: process for pid, process in family_processes.items() if psutil.pid_exists(pid)}
                if not current_family:
                    break

                previous_family_pids = set(family_processes)
                current_family_pids = set(current_family)
                for new_pid in sorted(current_family_pids - previous_family_pids):
                    family_processes[new_pid] = current_family[new_pid]
                    try:
                        family_processes[new_pid].cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                    if new_pid not in hook_targets:
                        target_paths = hook_target_paths(paths, new_pid)
                        hook_process, hook_command = start_hook_process(
                            args,
                            new_pid,
                            output_path=target_paths["jsonl"],
                            stdout_path=target_paths["stdout"],
                            stderr_path=target_paths["stderr"],
                        )
                        hook_targets[new_pid] = {
                            "pid": new_pid,
                            "process": hook_process,
                            "command": hook_command,
                            "output": target_paths["jsonl"],
                            "stdout": target_paths["stdout"],
                            "stderr": target_paths["stderr"],
                            "attempts": 1 if hook_process is not None else 0,
                            "lastStartEpoch": now_epoch,
                        }
                    lifecycle_event = emit_event(
                        session_handle,
                        session_start_epoch,
                        now_epoch,
                        "client.lifecycle",
                        "family-member-start",
                        {"pid": new_pid},
                        source="watch",
                        terminal=True,
                    )
                    update_summary(summary, lifecycle_event)
                for ended_pid in sorted(previous_family_pids - current_family_pids):
                    family_processes.pop(ended_pid, None)
                    previous_process_state.pop(ended_pid, None)
                    lifecycle_event = emit_event(
                        session_handle,
                        session_start_epoch,
                        now_epoch,
                        "client.lifecycle",
                        "family-member-exit",
                        {"pid": ended_pid},
                        source="watch",
                        terminal=True,
                    )
                    update_summary(summary, lifecycle_event)
                for pid in current_family_pids & previous_family_pids:
                    family_processes[pid] = current_family[pid]
                summary["familyPids"] = sorted(family_processes)

                for pid, target in sorted(hook_targets.items()):
                    if not should_retry_hook_target(target, current_family_pids, now_epoch):
                        continue
                    hook_process, hook_command = start_hook_process(
                        args,
                        pid,
                        output_path=target["output"],
                        stdout_path=target["stdout"],
                        stderr_path=target["stderr"],
                    )
                    target["process"] = hook_process
                    target["command"] = hook_command
                    target["attempts"] = int(target.get("attempts", 0) or 0) + (1 if hook_process is not None else 0)
                    target["lastStartEpoch"] = now_epoch
                    lifecycle_event = emit_event(
                        session_handle,
                        session_start_epoch,
                        now_epoch,
                        "client.lifecycle",
                        "hook-retry",
                        {"pid": pid, "attempt": target["attempts"]},
                        source="watch",
                        terminal=True,
                    )
                    update_summary(summary, lifecycle_event)

                for pid, target in sorted(hook_targets.items()):
                    for raw_line in hook_tail.read_new_lines(target["output"], start_at_end_for_new=False):
                        try:
                            payload = json.loads(raw_line)
                        except json.JSONDecodeError:
                            continue
                        payload.setdefault("pid", pid)
                        hooks_handle.write(json.dumps(payload, sort_keys=True) + "\n")
                        hooks_handle.flush()
                        event_epoch = float(payload.get("timestamp", now_epoch) or now_epoch)
                        category = str(payload.get("category", "client.unknown"))
                        action = str(payload.get("action", "event"))
                        details = {key: value for key, value in payload.items() if key not in {"timestamp", "category", "action"}}
                        event = emit_event(
                            session_handle,
                            session_start_epoch,
                            event_epoch,
                            category,
                            action,
                            details,
                            source=f"hooks:{pid}",
                            terminal=True,
                        )
                        update_summary(summary, event)

                if (now_epoch - last_directory_discovery_time) >= DEFAULT_DIRECTORY_DISCOVERY_INTERVAL:
                    tracked_content_paths = recent_directory_paths(
                        args.content_capture_dir,
                        "session-*.log",
                        since_epoch=recent_file_lower_bound,
                        max_files=MAX_RECENT_CONTENT_SESSION_FILES,
                    )
                    tracked_js5_summary_paths = recent_directory_paths(
                        args.js5_session_dir,
                        "summary-*.json",
                        since_epoch=recent_file_lower_bound,
                        max_files=MAX_RECENT_JS5_SUMMARY_FILES,
                    )
                    tracked_clienterror_paths = recent_directory_paths(
                        args.clienterror_dir,
                        "*",
                        since_epoch=recent_file_lower_bound,
                        max_files=MAX_RECENT_CLIENTERROR_FILES,
                    )
                    last_directory_discovery_time = now_epoch

                for raw_line in tail.read_new_lines(args.world_log, start_at_end_for_new=True):
                    normalized = normalize_world_line(raw_line)
                    if not normalized:
                        continue
                    category, action, details = normalized
                    event = emit_event(session_handle, session_start_epoch, now_epoch, category, action, details, source="world-log", terminal=True)
                    update_summary(summary, event)

                for path in tracked_content_paths:
                    if not content_session_overlaps_watch(path, session_started_at=summary.get("sessionStartedAt")):
                        continue
                    for raw_line in tail.read_new_lines(path, start_at_end_for_new=False):
                        normalized = normalize_content_line(raw_line)
                        if not normalized:
                            continue
                        category, action, details = normalized
                        event = emit_event(session_handle, session_start_epoch, now_epoch, category, action, details, source=str(path), terminal=True)
                        update_summary(summary, event)

                for path in tracked_js5_summary_paths:
                    if not file_is_recent_for_watch(path, session_started_at=summary.get("sessionStartedAt")):
                        continue
                    if str(path) in tail.seen_files:
                        continue
                    tail.seen_files.add(str(path))
                    normalized = normalize_js5_summary(path)
                    if not normalized:
                        continue
                    category, action, details = normalized
                    event = emit_event(session_handle, session_start_epoch, now_epoch, category, action, details, source=str(path), terminal=True)
                    update_summary(summary, event)

                for path in tracked_clienterror_paths:
                    if not file_is_recent_for_watch(path, session_started_at=summary.get("sessionStartedAt")):
                        continue
                    if str(path) in tail.seen_files or not path.is_file():
                        continue
                    tail.seen_files.add(str(path))
                    category, action, details = normalize_clienterror_file(path)
                    event = emit_event(session_handle, session_start_epoch, now_epoch, category, action, details, source=str(path), terminal=True)
                    update_summary(summary, event)

                if args.server_log.exists():
                    for raw_line in tail.read_new_lines(args.server_log, start_at_end_for_new=True):
                        normalized = normalize_js5_live_line(raw_line)
                        if not normalized:
                            continue
                        category, action, details = normalized
                        event = emit_event(session_handle, session_start_epoch, now_epoch, category, action, details, source=str(args.server_log), terminal=True)
                        update_summary(summary, event)

                sample_due = (now_epoch - last_sample_time) >= DEFAULT_SAMPLE_INTERVAL
                for category, action, details, event_epoch in collect_family_events(
                    family_processes,
                    previous_process_state,
                    include_file_delta=args.no_frida,
                    sample_due=sample_due,
                ):
                    event = emit_event(session_handle, session_start_epoch, event_epoch, category, action, details, source="process", terminal=sample_due or action != "sample")
                    update_summary(summary, event)
                if sample_due:
                    last_sample_time = now_epoch

                time.sleep(DEFAULT_POLL_INTERVAL)
        except KeyboardInterrupt:
            pass

    summary["sessionEndedAt"] = datetime.now(timezone.utc)
    hook_results: dict[str, Any] = {}
    hook_commands: dict[str, list[str]] = {}
    hook_files: dict[str, str] = {}
    for pid, target in sorted(hook_targets.items()):
        hook_results[str(pid)] = finalize_process(target["process"])
        hook_commands[str(pid)] = list(target["command"])
        hook_files[str(pid)] = str(target["output"])
    world_window = ""
    if launch_mode == "launch" and args.world_log.exists() and not world_window_selection_skipped:
        world_window = select_new_world_window(world_before, args.world_log)
    status = "partial" if args.no_frida else "ok"
    artifact = build_summary_artifact(
        args,
        status=status,
        paths=paths,
        runtime_build=runtime_build,
        launch_mode=launch_mode,
        client_pid=int(client_pid) if client_pid is not None else None,
        launch=launch,
        launch_evaluation=launch_evaluation,
        summary=summary,
        world_window=world_window,
    )
    artifact["details"]["hookCommands"] = hook_commands
    artifact["details"]["hookProcesses"] = hook_results
    artifact["details"]["hookFiles"] = hook_files
    artifact["summary"]["autoAttachedExisting"] = auto_attached_existing
    write_json(paths["summaryJson"], artifact)
    paths["summaryMarkdown"].write_text(render_markdown(artifact), encoding="utf-8")
    copy_latest(paths, args.output_dir)

    if launch_mode == "launch" and isinstance(launch_state, dict):
        for pid_key in ("ClientPid", "WatchdogPid", "GameProxyPid", "LobbyProxyPid", "ServerPid", "WrapperPid"):
            value = launch_state.get(pid_key)
            if isinstance(value, int):
                kill_pid(value)

    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0 if artifact["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
