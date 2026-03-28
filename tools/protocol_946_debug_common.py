from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from protocol_automation_common import (
    PHASE_DIRS,
    SHARED_DIR,
    WORKSPACE,
    REPO_ROOT,
    ensure_directory,
    load_json,
    stable_json_text,
    write_json,
)


BUILD_ID = 946
HIGH_SIGNAL_HANDOFF_OPCODES = {17, 48, 83, 113}
DEFAULT_SENDER_OPCODES = [17, 48, 83, 113]
PLAYER_INFO_OPCODE = 42
POST_LOGIN_STAGE_ORDER = [
    "appearance",
    "login-response",
    "pipeline-switch",
    "rebuild",
    "default-state",
    "interfaces",
]
WORLD_LOG_DEFAULT = WORKSPACE / "data" / "debug" / "world-bootstrap-raw.log"
DECOMP_LOG_DIR_DEFAULT = REPO_ROOT / "ghidra-projects"
GHIDRA_PROJECT_DIR_DEFAULT = WORKSPACE / "data" / "debug" / "ghidra"
GHIDRA_PROJECT_NAME_DEFAULT = "rs2client-headless-unlocked"
GHIDRA_SCRIPTS_DEFAULT = REPO_ROOT / "ghidra-scripts"
DEFAULT_GHIDRA_DIR = Path.home() / "Tools" / "ghidra" / "ghidra_12.0.4_PUBLIC"
GHIDRA_PROGRAM_NAME_DEFAULT = "rs2client.exe"
GHIDRA_CLONE_ROOT_DEFAULT = Path(tempfile.gettempdir()) / "opennxt-ghidra-clones"
PLAYER_INFO_ENCODER = (
    WORKSPACE
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "opennxt"
    / "model"
    / "entity"
    / "updating"
    / "PlayerInfoEncoder.kt"
)
WORLD_STAGE_PREFIX = "world-stage "
WORLD_KIND_PREFIX = "world-"
RAW_PACKET_KINDS = {"send-raw", "recv-raw"}
KV_RE = re.compile(r'([A-Za-z][A-Za-z0-9_-]*)=(".*?"|\S+)')
CONST_RE = re.compile(r"private\s+const\s+val\s+SEND_APPEARANCE_UPDATES\s*=\s*(true|false)")
TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})T(?P<time>\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d+))?Z$"
)
DECOMPILE_SIGNATURE_RE = re.compile(
    r"((?:undefined|void|longlong|int|char|uint|ushort|bool|float)\s+[*\w\s]*FUN_[0-9A-Fa-f]+\([^\)]*\))",
    re.M,
)
SYMBOL_PATTERNS = {
    "functions": re.compile(r"\bFUN_[0-9A-Fa-f]+\b"),
    "data": re.compile(r"\bDAT_[0-9A-Fa-f]+\b"),
    "pointers": re.compile(r"\bPTR_[A-Za-z0-9_]+\b"),
}
DEFAULT_SESSION_JSON_NAME = "session.json"


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def extract_kv_pairs(text: str) -> dict[str, str]:
    return {key: unquote(value) for key, value in KV_RE.findall(text)}


def parse_opcode(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def parse_size(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def is_interesting_kind(kind: str) -> bool:
    return kind in RAW_PACKET_KINDS or kind.startswith(WORLD_KIND_PREFIX)


def parse_timestamp(value: str) -> datetime | None:
    match = TIMESTAMP_RE.match(value)
    if not match:
        return None
    fraction = (match.group("fraction") or "")[:6].ljust(6, "0")
    try:
        parsed = datetime.strptime(
            f"{match.group('date')}T{match.group('time')}",
            "%Y-%m-%dT%H:%M:%S",
        ).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return parsed.replace(microsecond=int(fraction or "0"))


def duration_seconds(start_timestamp: str, end_timestamp: str) -> float | None:
    start = parse_timestamp(start_timestamp)
    end = parse_timestamp(end_timestamp)
    if not start or not end:
        return None
    delta = (end - start).total_seconds()
    return round(delta, 3) if delta >= 0 else None


def opcode_counts(events: list[dict[str, Any]], *, kind: str) -> dict[int, int]:
    counts: Counter[int] = Counter()
    for event in events:
        if event.get("kind") != kind:
            continue
        opcode = event.get("opcode")
        if isinstance(opcode, int):
            counts[opcode] += 1
    return dict(sorted(counts.items()))


def world_marker_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    markers = Counter(
        event["kind"]
        for event in events
        if event.get("kind", "").startswith(WORLD_KIND_PREFIX) and event.get("kind") != "world-stage"
    )
    return dict(sorted(markers.items()))


def parse_world_log(world_log_path: Path) -> list[dict[str, Any]]:
    if not world_log_path.exists():
        return []
    events: list[dict[str, Any]] = []
    with world_log_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n")
            if not line:
                continue
            parts = line.split(" ", 2)
            if len(parts) < 2:
                continue
            timestamp = parts[0]
            kind = parts[1]
            rest = parts[2] if len(parts) > 2 else ""
            if not is_interesting_kind(kind):
                continue
            data = extract_kv_pairs(rest)
            event = {
                "lineNumber": line_number,
                "timestamp": timestamp,
                "kind": kind,
                "stage": data.get("stage", ""),
                "opcode": parse_opcode(data.get("opcode")),
                "bytes": parse_size(data.get("bytes")),
                "preview": data.get("preview", ""),
                "playerName": data.get("name", ""),
                "data": data,
                "raw": line,
            }
            events.append(event)
    return events


def build_session(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    session_stage_events = [event for event in events if event["kind"] == "world-stage"]
    stage_order = [event["stage"] for event in session_stage_events if event["stage"]]
    unique_stages = list(dict.fromkeys(stage_order))
    stage_counts = Counter(stage_order)
    return {
        "startLine": events[0]["lineNumber"],
        "endLine": events[-1]["lineNumber"],
        "startTimestamp": events[0]["timestamp"],
        "endTimestamp": events[-1]["timestamp"],
        "durationSeconds": duration_seconds(events[0]["timestamp"], events[-1]["timestamp"]),
        "playerName": next((event["playerName"] for event in events if event["playerName"]), ""),
        "eventCount": len(events),
        "stageSequence": unique_stages,
        "stageCounts": dict(sorted(stage_counts.items())),
        "clientOpcodeCounts": opcode_counts(events, kind="recv-raw"),
        "serverOpcodeCounts": opcode_counts(events, kind="send-raw"),
        "markerCounts": world_marker_counts(events),
        "events": events,
    }


def split_sessions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if event.get("kind") == "world-stage" and event.get("stage") == "appearance" and current:
            session = build_session(current)
            if session:
                sessions.append(session)
            current = [event]
        else:
            current.append(event)
    if current:
        session = build_session(current)
        if session:
            sessions.append(session)
    return sessions


def load_all_sessions(path: Path) -> list[dict[str, Any]]:
    return split_sessions(parse_world_log(path))


def find_latest_session(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    sessions = split_sessions(events)
    if sessions:
        return sessions[-1]

    stage_events = [event for event in events if event["kind"] == "world-stage"]
    if not stage_events:
        return None
    return build_session(events)


def parse_window_spec(window: str | None) -> tuple[int, int] | None:
    if not window:
        return None
    if ":" not in window:
        raise ValueError(f"Invalid window spec '{window}'. Expected start:end.")
    start_text, end_text = window.split(":", 1)
    start = int(start_text.strip())
    end = int(end_text.strip())
    if start <= 0 or end < start:
        raise ValueError(f"Invalid window bounds '{window}'.")
    return start, end


def extract_session_window(events: list[dict[str, Any]], window: str | None) -> dict[str, Any] | None:
    bounds = parse_window_spec(window)
    if bounds is None:
        return find_latest_session(events)
    start_line, end_line = bounds
    selected = [event for event in events if start_line <= event["lineNumber"] <= end_line]
    return build_session(selected)


def load_session_input(path: Path, window: str | None = None) -> dict[str, Any] | None:
    if path.suffix.lower() == ".json":
        payload = load_json(path, {})
        if isinstance(payload, dict):
            if isinstance(payload.get("events"), list):
                return build_session([entry for entry in payload["events"] if isinstance(entry, dict)])
            session = payload.get("session")
            if isinstance(session, dict) and isinstance(session.get("events"), list):
                return build_session([entry for entry in session["events"] if isinstance(entry, dict)])
    events = parse_world_log(path)
    return extract_session_window(events, window)


def session_summary(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {
            "exists": False,
            "startLine": None,
            "endLine": None,
            "startTimestamp": "",
            "endTimestamp": "",
            "durationSeconds": None,
            "playerName": "",
            "eventCount": 0,
            "stageSequence": [],
            "stageCounts": {},
            "clientOpcodeCounts": {},
            "serverOpcodeCounts": {},
            "markerCounts": {},
        }
    return {
        "exists": True,
        "startLine": session["startLine"],
        "endLine": session["endLine"],
        "startTimestamp": session["startTimestamp"],
        "endTimestamp": session["endTimestamp"],
        "durationSeconds": session.get("durationSeconds"),
        "playerName": session["playerName"],
        "eventCount": session["eventCount"],
        "stageSequence": session["stageSequence"],
        "stageCounts": session["stageCounts"],
        "clientOpcodeCounts": session.get("clientOpcodeCounts", {}),
        "serverOpcodeCounts": session.get("serverOpcodeCounts", {}),
        "markerCounts": session.get("markerCounts", {}),
    }


def session_opcode_events(session: dict[str, Any] | None, *, kind: str) -> dict[int, list[dict[str, Any]]]:
    observations: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if not session:
        return observations
    for event in session["events"]:
        opcode = event.get("opcode")
        if not isinstance(opcode, int):
            continue
        if event["kind"] == kind:
            observations[opcode].append(event)
    return observations


def observed_client_opcode_events(session: dict[str, Any] | None) -> dict[int, list[dict[str, Any]]]:
    return session_opcode_events(session, kind="recv-raw")


def observed_server_opcode_events(session: dict[str, Any] | None) -> dict[int, list[dict[str, Any]]]:
    return session_opcode_events(session, kind="send-raw")


def stage_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(event["stage"] or "unknown" for event in events)
    return dict(sorted(counter.items()))


def sample_previews(events: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for event in events[:limit]:
        samples.append(
            {
                "lineNumber": event["lineNumber"],
                "stage": event["stage"],
                "bytes": event["bytes"],
                "preview": event["preview"],
            }
        )
    return samples


def list_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "entries" in payload:
        entries = payload.get("entries")
        return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
    return [entry for entry in payload if isinstance(entry, dict)] if isinstance(payload, list) else []


def build_index(entries: list[dict[str, Any]]) -> dict[tuple[str, int], dict[str, Any]]:
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for entry in entries:
        side = str(entry.get("side", "")).lower()
        opcode = entry.get("opcode")
        if side and isinstance(opcode, int):
            index[(side, opcode)] = entry
    return index


def load_phase_inputs() -> dict[str, Any]:
    return {
        "phase3Candidates": list_entries(load_json(PHASE_DIRS[3] / "nameCandidates.json", [])),
        "generatedPackets": list_entries(load_json(PHASE_DIRS[5] / "generatedPackets.json", [])),
        "verifiedPackets": list_entries(load_json(SHARED_DIR / "verified-packets.json", {})),
        "evidenceIndex": list_entries(load_json(SHARED_DIR / "evidence-index.json", [])),
    }


def unresolved_candidates(
    phase3_candidates: list[dict[str, Any]],
    generated_index: dict[tuple[str, int], dict[str, Any]],
    verified_index: dict[tuple[str, int], dict[str, Any]],
    *,
    side: str,
) -> dict[int, dict[str, Any]]:
    suspects: dict[int, dict[str, Any]] = {}
    for candidate in phase3_candidates:
        if candidate.get("side") != side:
            continue
        opcode = candidate.get("opcode")
        if not isinstance(opcode, int):
            continue
        if (side, opcode) in generated_index or (side, opcode) in verified_index:
            continue
        suspects[opcode] = candidate
    return suspects


def unresolved_client_candidates(
    phase3_candidates: list[dict[str, Any]],
    generated_index: dict[tuple[str, int], dict[str, Any]],
    verified_index: dict[tuple[str, int], dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    return unresolved_candidates(phase3_candidates, generated_index, verified_index, side="client")


def unresolved_server_candidates(
    phase3_candidates: list[dict[str, Any]],
    generated_index: dict[tuple[str, int], dict[str, Any]],
    verified_index: dict[tuple[str, int], dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    return unresolved_candidates(phase3_candidates, generated_index, verified_index, side="server")


def evidence_sender_fields(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    targets = entry.get("targets") if isinstance(entry.get("targets"), dict) else {}
    return (
        str(targets.get("primarySender", "")),
        str(targets.get("primarySenderName", "")),
        str(targets.get("parserTarget", "")),
        str(targets.get("parserName", "")),
    )


def phase3_sender_fields(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    evidence = entry.get("evidence")
    if isinstance(evidence, dict):
        return (
            str(evidence.get("primarySender", "")),
            str(evidence.get("primarySenderName", "")),
            str(evidence.get("parserTarget", "")),
            str(evidence.get("parserName", "")),
        )
    return ("", "", "", "")


def candidate_decomp_logs_for_selection(
    phase3_candidates: list[dict[str, Any]],
    world_log_path: Path | None,
    decomp_log_dir: Path,
    manual_opcodes: list[int] | None = None,
) -> list[Path]:
    generated_index: dict[tuple[str, int], dict[str, Any]] = {}
    verified_index: dict[tuple[str, int], dict[str, Any]] = {}
    unresolved = unresolved_client_candidates(phase3_candidates, generated_index, verified_index)
    observed_opcodes: set[int] = set(manual_opcodes or [])
    if world_log_path and world_log_path.exists():
        events = parse_world_log(world_log_path)
        session = find_latest_session(events)
        observed_opcodes.update(observed_client_opcode_events(session).keys())
    selected = set(opcode for opcode in unresolved if opcode in observed_opcodes)
    selected.update(opcode for opcode in (manual_opcodes or []) if opcode in unresolved)
    matched: set[Path] = set()
    for opcode in sorted(selected):
        candidate = unresolved.get(opcode)
        if not candidate:
            continue
        primary_sender, _, parser_target, _ = phase3_sender_fields(candidate)
        for address in (primary_sender, parser_target):
            if not address:
                continue
            path = decomp_log_dir / f"decomp-{address}.log"
            if path.exists():
                matched.add(path)
    return sorted(matched)


def decode_bytes_best_effort(data: bytes) -> tuple[str, str]:
    candidates: list[tuple[str, bytes]] = []
    if data.startswith(b"\xef\xbb\xbf"):
        candidates.append(("utf-8-sig", data))
    if data.startswith(b"\xff\xfe"):
        candidates.append(("utf-16", data))
        candidates.append(("utf-16le", data))
    if data.startswith(b"\xfe\xff"):
        candidates.append(("utf-16", data))
        candidates.append(("utf-16be", data))
    if b"\x00" in data[:128]:
        candidates.extend(
            [
                ("utf-16", data),
                ("utf-16le", data),
                ("utf-16be", data),
            ]
        )
    candidates.extend(
        [
            ("utf-8", data),
            ("utf-16", data),
            ("utf-16le", data),
            ("latin1", data),
        ]
    )
    seen: set[str] = set()
    for encoding, payload in candidates:
        if encoding in seen:
            continue
        seen.add(encoding)
        try:
            text = payload.decode(encoding)
            return text.replace("\x00", ""), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin1", errors="replace").replace("\x00", ""), "latin1-replace"


def read_text_best_effort(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    return decode_bytes_best_effort(data)


def useful_log_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("INFO "):
            continue
        if line.startswith("Press any key"):
            continue
        lines.append(line)
    return lines


def decomp_status_for_text(text: str) -> dict[str, Any]:
    lines = useful_log_lines(text)
    body = extract_decompiled_body(text)
    warnings = [line for line in lines if line.startswith("WARN") or line.startswith("WARNING")]
    errors = [line for line in lines if line.startswith("ERROR") or "Decompile failed:" in line]
    if body:
        status = "clean"
    elif errors:
        status = "error-only"
    elif warnings:
        status = "warning-only"
    elif lines:
        status = "warning-only"
    else:
        status = "empty"
    return {
        "status": status,
        "snippet": (lines[-8:] if lines else []),
        "warnings": warnings[-8:],
        "errors": errors[-8:],
        "body": body,
        "symbols": extract_symbol_references(body or text),
    }


def decomp_status_for_path(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"status": "missing", "path": "", "snippet": []}
    if not path.exists():
        return {"status": "missing", "path": str(path), "snippet": []}
    text, encoding = read_text_best_effort(path)
    summary = decomp_status_for_text(text)
    summary["path"] = str(path)
    summary["encoding"] = encoding
    return summary


def extract_decompiled_body(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    if "Decompiled C:" in normalized:
        body = normalized.split("Decompiled C:", 1)[1].strip()
        return body.split("\n\n (GhidraScript)", 1)[0].strip()
    match = DECOMPILE_SIGNATURE_RE.search(normalized)
    if not match:
        return ""
    body = normalized[match.start() :].strip()
    return body.split("\n\n (GhidraScript)", 1)[0].strip()


def extract_symbol_references(text: str) -> dict[str, list[str]]:
    references: dict[str, list[str]] = {}
    for label, pattern in SYMBOL_PATTERNS.items():
        matches = sorted(set(pattern.findall(text)))
        if matches:
            references[label] = matches[:32]
    return references


def parse_callref_lines(text: str) -> list[str]:
    lines = useful_log_lines(text)
    filtered = [
        line
        for line in lines
        if not line.startswith("Function:")
        and not line.startswith("Target:")
        and "GhidraScript" not in line
    ]
    return filtered[:24]


def resolve_project_location(project_dir: Path, project_name: str) -> Path:
    direct = project_dir / f"{project_name}.gpr"
    if direct.exists():
        return project_dir
    nested = project_dir / project_name / f"{project_name}.gpr"
    if nested.exists():
        return project_dir / project_name
    raise FileNotFoundError(f"Could not find {project_name}.gpr under {project_dir}")


def project_storage_paths(project_dir: Path, project_name: str) -> tuple[Path, Path, Path]:
    resolved_project_dir = resolve_project_location(project_dir, project_name)
    gpr_path = resolved_project_dir / f"{project_name}.gpr"
    rep_path = resolved_project_dir / f"{project_name}.rep"
    if not gpr_path.exists():
        raise FileNotFoundError(f"Missing project file {gpr_path}")
    if not rep_path.exists():
        raise FileNotFoundError(f"Missing project repository {rep_path}")
    return resolved_project_dir, gpr_path, rep_path


def sanitize_clone_label(label: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", label.strip())
    return cleaned.strip("-._") or "clone"


def _ignore_lock_entries(_: str, names: list[str]) -> set[str]:
    return {name for name in names if name.endswith(".lock") or name.endswith(".lock~")}


def clone_ghidra_project(
    *,
    project_dir: Path,
    project_name: str,
    clone_root: Path | None = None,
    clone_label: str = "",
) -> dict[str, Any]:
    _, gpr_path, rep_path = project_storage_paths(project_dir, project_name)
    resolved_clone_root = clone_root or GHIDRA_CLONE_ROOT_DEFAULT
    ensure_directory(resolved_clone_root)
    safe_label = sanitize_clone_label(clone_label)
    clone_project_dir = Path(
        tempfile.mkdtemp(
            prefix=f"{project_name}-{safe_label}-",
            dir=str(resolved_clone_root),
        )
    )
    clone_gpr_path = clone_project_dir / gpr_path.name
    clone_rep_path = clone_project_dir / rep_path.name
    shutil.copy2(gpr_path, clone_gpr_path)
    shutil.copytree(rep_path, clone_rep_path, ignore=_ignore_lock_entries)
    return {
        "cloneStrategy": "disposable-project-clone",
        "sourceProjectDir": str(gpr_path.parent),
        "sourceProjectName": project_name,
        "cloneRoot": str(resolved_clone_root),
        "cloneProjectDir": str(clone_project_dir),
        "cloneProjectName": project_name,
        "cloneProjectFile": str(clone_gpr_path),
        "cloneRepositoryDir": str(clone_rep_path),
    }


def cleanup_ghidra_project_clone(
    clone_info: dict[str, Any] | None,
    *,
    keep_clone: bool = False,
) -> dict[str, Any]:
    if not clone_info:
        return {"status": "not-used", "path": "", "error": ""}
    clone_path = Path(str(clone_info.get("cloneProjectDir", "")))
    if keep_clone:
        return {"status": "kept", "path": str(clone_path), "error": ""}
    if not clone_path.exists():
        return {"status": "already-missing", "path": str(clone_path), "error": ""}
    try:
        shutil.rmtree(clone_path)
    except OSError as exc:
        return {"status": "cleanup-failed", "path": str(clone_path), "error": str(exc)}
    return {"status": "cleaned", "path": str(clone_path), "error": ""}


def classify_headless_error(
    stdout_text: str,
    stderr_text: str,
    return_code: int,
    *,
    output_exists: bool | None = None,
) -> str | None:
    combined = f"{stdout_text}\n{stderr_text}".lower()
    if "unable to lock project" in combined or "lockexception" in combined:
        return "project-lock"
    if return_code != 0:
        if "ghidrascript" in combined or "postscript" in combined or "decompile failed:" in combined:
            return "script-failure"
        return "headless-failure"
    if output_exists is False and ("error" in combined or "decompile failed:" in combined or "exception" in combined):
        return "script-failure"
    return None


def run_headless_postscript(
    *,
    ghidra_dir: Path,
    project_dir: Path,
    project_name: str,
    script_name: str,
    script_args: list[str],
    script_path: Path = GHIDRA_SCRIPTS_DEFAULT,
    program_name: str = GHIDRA_PROGRAM_NAME_DEFAULT,
    analyze: bool = False,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    analyze_headless = ghidra_dir / "support" / "analyzeHeadless.bat"
    if not analyze_headless.exists():
        raise FileNotFoundError(f"analyzeHeadless.bat not found at {analyze_headless}")
    resolved_project_dir = resolve_project_location(project_dir, project_name)
    command = [
        str(analyze_headless),
        str(resolved_project_dir),
        project_name,
        "-process",
        program_name,
    ]
    if not analyze:
        command.append("-noanalysis")
    command.extend(
        [
            "-scriptPath",
            str(script_path),
            "-postScript",
            script_name,
            *[str(arg) for arg in script_args],
        ]
    )
    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = process.communicate(timeout=timeout_seconds)
        timed_out = False
        return_code = process.returncode
    except subprocess.TimeoutExpired:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        stdout_bytes, stderr_bytes = process.communicate()
        stderr_bytes = (stderr_bytes or b"") + f"\nTIMEOUT after {timeout_seconds} seconds".encode("utf-8")
        timed_out = True
        return_code = -1
    stdout_text, stdout_encoding = decode_bytes_best_effort(stdout_bytes or b"")
    stderr_text, stderr_encoding = decode_bytes_best_effort(stderr_bytes or b"")
    return {
        "returnCode": return_code,
        "command": command,
        "stdoutText": stdout_text,
        "stderrText": stderr_text,
        "stdoutEncoding": stdout_encoding,
        "stderrEncoding": stderr_encoding,
        "timedOut": timed_out,
    }


def load_sender_analysis(path: Path) -> dict[str, Any]:
    payload = load_json(path, {})
    return payload if isinstance(payload, dict) else {}


def write_markdown(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    path.write_text(text, encoding="utf-8")


def write_session_json(path: Path, session: dict[str, Any]) -> None:
    write_json(
        path,
        {
            "session": session,
            "summary": session_summary(session),
        },
    )
