from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from protocol_automation_common import (
    SHARED_DIR,
    WORKSPACE,
    artifact_input_fingerprint,
    cache_hit,
    ensure_directory,
    load_json,
    record_cache_entry,
    stable_json_text,
    standard_tool_artifact,
    write_json,
)
from protocol_946_debug_common import (
    WORLD_LOG_DEFAULT,
    load_session_input,
    parse_timestamp,
    session_summary,
)


SCENE_DELIVERY_JSON = "scene-delivery-analysis.json"
SCENE_DELIVERY_MD = "scene-delivery-analysis.md"
SCENE_DELIVERY_CACHE_KEY = "scene-delivery-aid"
DEFAULT_JS5_SESSION_DIR = WORKSPACE / "data" / "debug" / "js5-proxy-recorder-live"
DEFAULT_CONTENT_CAPTURE_DIR = WORKSPACE / "data" / "debug" / "lobby-tls-terminator"
DEFAULT_RUNTIME_TRACE_DIR = WORKSPACE / "data" / "debug" / "runtime-trace"
DEFAULT_CLIENTERROR_DIR = WORKSPACE / "data" / "debug" / "clienterror"
DEFAULT_CHECKSUM_COMPARE_JSON = WORKSPACE / "data" / "debug" / "checksum-table-compare" / "compare-report.json"
DEFAULT_PREFETCH_COMPARE_JSON = WORKSPACE / "data" / "debug" / "prefetch-table-compare" / "compare-report.json"
DEFAULT_BLACK_SCREEN_CAPTURE_JSON = SHARED_DIR / "black-screen-capture.json"
DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON = WORKSPACE / "data" / "debug" / "client-live-watch" / "latest-summary.json"
SESSION_ID_RE = re.compile(r"session#(?P<id>\d+)")
REQUEST_ARCHIVE_RE = re.compile(r"archive\[(?P<index>\d+),(?P<archive>\d+)\]")
REFERENCE_TABLE_RE = re.compile(r"reference-table\[(?P<archive>\d+)\]")
CONTENT_BYTES_RE = re.compile(
    r"session#(?P<id>\d+) bytes (?P<direction>[a-z\-]+)->remote=(?P<to_remote>\d+) remote->(?P=direction)=(?P<from_remote>\d+)"
)
CONTENT_MODE_RE = re.compile(r"session#(?P<id>\d+) mode=(?P<mode>[\w-]+)")
CONTENT_SESSION_ROUTE_RE = re.compile(r"session#(?P<id>\d+) session-route=(?P<route>[\w-]+)")
CONTENT_REMOTE_RE = re.compile(r"session#(?P<id>\d+) remote=(?P<remote>.+)")
CONTENT_SNI_RE = re.compile(r"session#(?P<id>\d+) tls-client-sni=(?P<sni>.+)")
CONTENT_FIRST_CHUNK_RE = re.compile(
    r"(?P<prefix>tls-client->remote|remote->tls-client) first-chunk-(?P<chunk>\d+) bytes=(?P<bytes>\d+) hex=(?P<hex>[0-9a-f ]+)",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Correlate 946 world-bootstrap timing with JS5 asset delivery, runtime traces, and cache signals."
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--world-window")
    parser.add_argument("--js5-session-dir", type=Path, default=DEFAULT_JS5_SESSION_DIR)
    parser.add_argument("--content-capture-dir", type=Path, default=DEFAULT_CONTENT_CAPTURE_DIR)
    parser.add_argument("--runtime-trace-dir", type=Path, default=DEFAULT_RUNTIME_TRACE_DIR)
    parser.add_argument("--clienterror-dir", type=Path, default=DEFAULT_CLIENTERROR_DIR)
    parser.add_argument("--checksum-report-json", type=Path, default=DEFAULT_CHECKSUM_COMPARE_JSON)
    parser.add_argument("--prefetch-report-json", type=Path, default=DEFAULT_PREFETCH_COMPARE_JSON)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / SCENE_DELIVERY_JSON,
        output_dir / SCENE_DELIVERY_MD,
    ]


def safe_parse_timestamp(value: str | None):
    if not value:
        return None
    parsed = parse_timestamp(value)
    if parsed is not None:
        return parsed
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def relative_seconds(start_timestamp: str | None, current_timestamp: str | None) -> float | None:
    start = safe_parse_timestamp(start_timestamp)
    current = safe_parse_timestamp(current_timestamp)
    if not start or not current:
        return None
    return round((current - start).total_seconds(), 3)


def absolute_event_timestamp(session: dict[str, Any], millis_key: str):
    start = safe_parse_timestamp(session.get("startTimestamp"))
    millis = session.get(millis_key)
    if start is None or millis is None:
        return None
    return start + timedelta(milliseconds=float(millis))


def classify_js5_session(session: dict[str, Any]) -> str:
    request_count = int(session.get("requestCount", 0) or 0)
    archive_requests = int(session.get("archiveRequests", 0) or 0)
    response_header_count = int(session.get("responseHeaderCount", 0) or 0)
    response_bytes = int(session.get("responseBytes", 0) or 0)
    truncated_response = bool(session.get("truncatedResponse"))
    if request_count <= 0:
        return "client-never-opened-js5"
    if archive_requests <= 0:
        return "reference-tables-only"
    if truncated_response:
        return "archive-delivery-truncated"
    if response_header_count <= 0 and response_bytes <= 0:
        return "archive-requested-no-response"
    return "archive-delivery-observed"


def parse_js5_session_log(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    session_id = None
    start_timestamp = ""
    end_timestamp = ""
    request_count = 0
    master_reference_requests = 0
    reference_table_requests = 0
    archive_requests = 0
    unique_reference_tables: set[int] = set()
    unique_archive_pairs: set[tuple[int, int]] = set()
    request_samples: list[str] = []
    status_markers = Counter()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if session_id is None:
            match = SESSION_ID_RE.search(line)
            if match:
                session_id = int(match.group("id"))
        if " start=" in line:
            start_timestamp = line.rsplit("start=", 1)[1].strip()
        elif " end=" in line:
            end_timestamp = line.rsplit("end=", 1)[1].strip()
        elif " idle-timeout=" in line:
            status_markers["idle-timeout"] += 1
        elif " request " in line:
            request_count += 1
            if len(request_samples) < 8:
                request_samples.append(line)
            if "master-reference-table" in line:
                master_reference_requests += 1
                continue
            reference_match = REFERENCE_TABLE_RE.search(line)
            if reference_match:
                reference_table_requests += 1
                unique_reference_tables.add(int(reference_match.group("archive")))
                continue
            archive_match = REQUEST_ARCHIVE_RE.search(line)
            if archive_match:
                archive_requests += 1
                unique_archive_pairs.add((int(archive_match.group("index")), int(archive_match.group("archive"))))
                continue
        elif " handshake-type=" in line:
            status_markers["handshake-type"] += 1
        elif " js5-handshake " in line:
            status_markers["js5-handshake"] += 1
        elif " response-header " in line:
            status_markers["response-header"] += 1

    start = safe_parse_timestamp(start_timestamp)
    end = safe_parse_timestamp(end_timestamp)
    duration_seconds = None
    if start and end:
        duration_seconds = round((end - start).total_seconds(), 3)

    summary = {
        "file": str(path),
        "captureFormat": "legacy",
        "sessionId": session_id,
        "startTimestamp": start_timestamp,
        "endTimestamp": end_timestamp,
        "durationSeconds": duration_seconds,
        "requestCount": request_count,
        "masterReferenceRequests": master_reference_requests,
        "referenceTableRequests": reference_table_requests,
        "archiveRequests": archive_requests,
        "responseHeaderCount": status_markers["response-header"],
        "responseBytes": 0,
        "uniqueReferenceTables": sorted(unique_reference_tables),
        "uniqueArchivePairs": [{"index": index, "archive": archive} for index, archive in sorted(unique_archive_pairs)],
        "sampleRequests": request_samples,
        "statusMarkers": dict(sorted(status_markers.items())),
        "status": "ok",
        "sessionLog": str(path),
    }
    summary["sceneDeliveryState"] = classify_js5_session(summary)
    return summary


def list_js5_session_logs(js5_session_dir: Path) -> list[Path]:
    if not js5_session_dir.exists():
        return []
    return sorted(js5_session_dir.glob("session-*.log"), key=lambda path: path.stat().st_mtime)


def list_js5_summary_jsons(js5_session_dir: Path) -> list[Path]:
    if not js5_session_dir.exists():
        return []
    return sorted(js5_session_dir.glob("summary-*.json"), key=lambda path: path.stat().st_mtime)


def list_content_capture_logs(content_capture_dir: Path) -> list[Path]:
    if not content_capture_dir.exists():
        return []
    return sorted(content_capture_dir.glob("session-*.log"), key=lambda path: path.stat().st_mtime)


def decode_first_chunk_hex(value: str) -> bytes:
    compact = value.replace(" ", "").strip()
    if not compact:
        return b""
    try:
        return bytes.fromhex(compact)
    except ValueError:
        return b""


def parse_content_http_request(payload: bytes) -> dict[str, Any] | None:
    text = payload.decode("latin1", errors="ignore")
    if not (text.startswith("GET ") or text.startswith("POST ") or text.startswith("HEAD ")):
        return None
    first_line = text.split("\r\n", 1)[0]
    parts = first_line.split(" ", 2)
    if len(parts) < 2:
        return None
    method, target = parts[0], parts[1]
    parsed = urlparse(target)
    query = parse_qs(parsed.query)
    index = None
    archive = None
    try:
        if "m" in query:
            index = int(query["m"][0])
    except (ValueError, TypeError, IndexError):
        index = None
    try:
        if "a" in query:
            archive = int(query["a"][0])
    except (ValueError, TypeError, IndexError):
        archive = None
    if archive == 255 and index == 255:
        label = "master-reference-table"
    elif archive == 255 and index is not None:
        label = f"reference-table[{index}]"
    elif index is not None and archive is not None:
        label = f"archive[{index},{archive}]"
    else:
        label = parsed.path or target
    return {
        "method": method,
        "target": target,
        "path": parsed.path,
        "query": {key: values[0] for key, values in query.items() if values},
        "index": index,
        "archive": archive,
        "label": label,
    }


def parse_content_http_response(payload: bytes) -> dict[str, Any] | None:
    if not payload.startswith(b"HTTP/"):
        return None
    header_end = payload.find(b"\r\n\r\n")
    if header_end < 0:
        return None
    header_blob = payload[:header_end].decode("latin1", errors="ignore")
    lines = header_blob.split("\r\n")
    if not lines:
        return None
    status_code = None
    parts = lines[0].split(" ", 2)
    if len(parts) >= 2:
        try:
            status_code = int(parts[1])
        except ValueError:
            status_code = None
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    content_length = None
    if "content-length" in headers:
        try:
            content_length = int(headers["content-length"])
        except ValueError:
            content_length = None
    return {
        "statusCode": status_code,
        "contentLength": content_length,
        "headerBytes": header_end + 4,
    }


def parse_content_capture_log(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    session_id = None
    start_timestamp = ""
    end_timestamp = ""
    mode = ""
    session_route = ""
    remote_target = ""
    sni = ""
    request_count = 0
    master_reference_requests = 0
    reference_table_requests = 0
    archive_requests = 0
    response_header_count = 0
    response_bytes = 0
    response_status = None
    response_content_length = None
    response_header_bytes = None
    request_samples: list[str] = []
    http_requests: list[dict[str, Any]] = []
    unique_reference_tables: set[int] = set()
    unique_archive_pairs: set[tuple[int, int]] = set()
    status_markers = Counter()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if session_id is None:
            match = SESSION_ID_RE.search(line)
            if match:
                session_id = int(match.group("id"))
        if " start=" in line:
            start_timestamp = line.rsplit("start=", 1)[1].strip()
            continue
        if " end=" in line:
            end_timestamp = line.rsplit("end=", 1)[1].strip()
            continue
        mode_match = CONTENT_MODE_RE.match(line)
        if mode_match:
            mode = mode_match.group("mode")
            continue
        route_match = CONTENT_SESSION_ROUTE_RE.match(line)
        if route_match:
            session_route = route_match.group("route")
            continue
        remote_match = CONTENT_REMOTE_RE.match(line)
        if remote_match:
            remote_target = remote_match.group("remote")
            continue
        sni_match = CONTENT_SNI_RE.match(line)
        if sni_match:
            sni = sni_match.group("sni")
            continue
        if "session-error=" in line:
            status_markers["session-error"] += 1
            continue
        chunk_match = CONTENT_FIRST_CHUNK_RE.match(line)
        if chunk_match:
            prefix = chunk_match.group("prefix")
            if prefix == "remote->tls-client":
                response_header_count += 1
                response = parse_content_http_response(decode_first_chunk_hex(chunk_match.group("hex")))
                if response is not None:
                    if response_status is None:
                        response_status = response.get("statusCode")
                    if response_content_length is None:
                        response_content_length = response.get("contentLength")
                    if response_header_bytes is None:
                        response_header_bytes = response.get("headerBytes")
                continue
            request = parse_content_http_request(decode_first_chunk_hex(chunk_match.group("hex")))
            if request is None:
                continue
            request_count += 1
            if len(request_samples) < 8:
                request_samples.append(f"{request['method']} {request['target']}")
            http_requests.append(request)
            index = request.get("index")
            archive = request.get("archive")
            if archive == 255 and index == 255:
                master_reference_requests += 1
            elif archive == 255 and index is not None:
                reference_table_requests += 1
                unique_reference_tables.add(index)
            elif index is not None and archive is not None:
                archive_requests += 1
                unique_archive_pairs.add((index, archive))
            continue
        bytes_match = CONTENT_BYTES_RE.match(line)
        if bytes_match:
            response_bytes = int(bytes_match.group("from_remote"))

    effective_route = session_route or mode
    if effective_route not in {"tls", "tls-http-content"}:
        return {}

    start = safe_parse_timestamp(start_timestamp)
    end = safe_parse_timestamp(end_timestamp)
    duration_seconds = None
    if start and end:
        duration_seconds = round((end - start).total_seconds(), 3)
    response_body_bytes = max(response_bytes - (response_header_bytes or 0), 0)
    expected_response_bytes = None
    if response_content_length is not None and response_header_bytes is not None:
        expected_response_bytes = response_content_length + response_header_bytes
    truncated_response = expected_response_bytes is not None and response_bytes < expected_response_bytes

    summary = {
        "file": str(path),
        "captureFormat": "content-proxy",
        "sessionId": session_id,
        "startTimestamp": start_timestamp,
        "endTimestamp": end_timestamp,
        "durationSeconds": duration_seconds,
        "requestCount": request_count,
        "masterReferenceRequests": master_reference_requests,
        "referenceTableRequests": reference_table_requests,
        "archiveRequests": archive_requests,
        "responseHeaderCount": response_header_count,
        "responseBytes": response_bytes,
        "responseBodyBytes": response_body_bytes,
        "responseStatus": response_status,
        "responseContentLength": response_content_length,
        "responseHeaderBytes": response_header_bytes,
        "expectedResponseBytes": expected_response_bytes,
        "truncatedResponse": truncated_response,
        "uniqueReferenceTables": sorted(unique_reference_tables),
        "uniqueArchivePairs": [{"index": index, "archive": archive} for index, archive in sorted(unique_archive_pairs)],
        "sampleRequests": request_samples,
        "httpRequests": http_requests,
        "statusMarkers": dict(sorted(status_markers.items())),
        "status": "partial" if status_markers or truncated_response else "ok",
        "sessionLog": str(path),
        "sessionRoute": effective_route,
        "remoteTarget": remote_target,
        "tlsClientSni": sni,
        "firstRequestAtMillis": 0 if request_count > 0 else None,
        "firstArchiveRequestAtMillis": 0 if archive_requests > 0 else None,
        "firstResponseHeaderAtMillis": 0 if response_header_count > 0 or response_bytes > 0 else None,
        "firstArchiveResponseAtMillis": 0 if archive_requests > 0 and (response_header_count > 0 or response_bytes > 0) else None,
    }
    summary["sceneDeliveryState"] = classify_js5_session(summary)
    return summary


def load_structured_js5_sessions(js5_session_dir: Path) -> tuple[list[dict[str, Any]], list[Path]]:
    summary_paths = list_js5_summary_jsons(js5_session_dir)
    sessions: list[dict[str, Any]] = []
    for summary_path in summary_paths[-12:]:
        payload = load_json(summary_path, {}) or {}
        for session in payload.get("sessions", []):
            if not isinstance(session, dict):
                continue
            entry = dict(session)
            entry["captureFormat"] = "structured"
            entry["summaryFile"] = str(summary_path)
            entry["file"] = entry.get("sessionLog") or str(summary_path)
            entry["sceneDeliveryState"] = classify_js5_session(entry)
            sessions.append(entry)
    return sessions, summary_paths


def select_delivery_sessions(
    *,
    structured_sessions: list[dict[str, Any]],
    content_sessions: list[dict[str, Any]],
    legacy_sessions: list[dict[str, Any]],
    world_session: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], str, str, list[dict[str, Any]], str]:
    for capture_format, sessions in (
        ("structured", structured_sessions),
        ("content-proxy", content_sessions),
        ("legacy", legacy_sessions),
    ):
        if not sessions:
            continue
        relevant, selection, overlap_confidence, fallback = pick_relevant_js5_sessions(
            js5_sessions=sessions,
            world_session=world_session,
            capture_format=capture_format,
        )
        if overlap_confidence != "missing":
            return relevant, selection, overlap_confidence, fallback, capture_format

    for capture_format, sessions in (
        ("content-proxy", content_sessions),
        ("structured", structured_sessions),
        ("legacy", legacy_sessions),
    ):
        if not sessions:
            continue
        _, selection, overlap_confidence, fallback = pick_relevant_js5_sessions(
            js5_sessions=sessions,
            world_session=world_session,
            capture_format=capture_format,
        )
        return [], selection, overlap_confidence, fallback, capture_format

    return [], "no-js5-capture", "missing", [], "missing"


def timestamps_overlap(
    start_a: str | None,
    end_a: str | None,
    start_b: str | None,
    end_b: str | None,
    *,
    pad_seconds: int = 60,
) -> bool:
    a_start = safe_parse_timestamp(start_a)
    a_end = safe_parse_timestamp(end_a) or a_start
    b_start = safe_parse_timestamp(start_b)
    b_end = safe_parse_timestamp(end_b) or b_start
    if not a_start or not b_start or not a_end or not b_end:
        return False
    a_start = a_start.timestamp() - pad_seconds
    a_end = a_end.timestamp() + pad_seconds
    b_start = b_start.timestamp()
    b_end = b_end.timestamp()
    return b_start <= a_end and b_end >= a_start


def pick_relevant_js5_sessions(
    *,
    js5_sessions: list[dict[str, Any]],
    world_session: dict[str, Any] | None,
    capture_format: str,
) -> tuple[list[dict[str, Any]], str, str, list[dict[str, Any]]]:
    if not js5_sessions:
        return [], "no-js5-capture", "missing", []
    if not world_session:
        latest = js5_sessions[-3:]
        overlap = "exact" if capture_format == "structured" else "fallback"
        return latest, f"{capture_format}-latest", overlap, []
    overlapping = [
        session
        for session in js5_sessions
        if timestamps_overlap(
            world_session.get("startTimestamp"),
            world_session.get("endTimestamp"),
            session.get("startTimestamp"),
            session.get("endTimestamp"),
        )
    ]
    if overlapping:
        overlap = "exact" if capture_format == "structured" else "fallback"
        return overlapping, f"{capture_format}-overlap", overlap, []
    return [], f"{capture_format}-no-overlap", "missing", js5_sessions[-2:]


def parse_runtime_trace_file(path: Path) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    timeout_count = 0
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        snapshots.append(payload)
        if payload.get("timeout"):
            timeout_count += 1

    if not snapshots:
        return {
            "file": str(path),
            "sampleCount": 0,
            "timeoutCount": 0,
            "startTimestamp": "",
            "endTimestamp": "",
            "latestConnectionPorts": [],
            "openCacheFiles": [],
        }

    first = snapshots[0]
    last = snapshots[-1]
    latest_snapshot = next((snapshot for snapshot in reversed(snapshots) if not snapshot.get("timeout")), last)
    ports = sorted(
        {
            connection.get("remote", {}).get("port")
            for connection in latest_snapshot.get("connections", [])
            if isinstance(connection, dict) and connection.get("remote", {}).get("port") is not None
        }
    )
    open_cache_files = [
        path_text
        for path_text in latest_snapshot.get("open_files", [])
        if isinstance(path_text, str) and path_text.lower().endswith(".jcache")
    ]
    return {
        "file": str(path),
        "sampleCount": len(snapshots),
        "timeoutCount": timeout_count,
        "startTimestamp": first.get("timestamp", ""),
        "endTimestamp": last.get("timestamp", ""),
        "latestConnectionPorts": ports,
        "latestCpuPercent": latest_snapshot.get("cpu_percent"),
        "latestThreadCount": latest_snapshot.get("num_threads"),
        "latestRss": (latest_snapshot.get("memory_info") or {}).get("rss"),
        "openCacheFiles": open_cache_files[:16],
    }


def pick_relevant_runtime_trace(
    *,
    runtime_trace_dir: Path,
    world_session: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    if not runtime_trace_dir.exists():
        return None, "missing-runtime-trace-dir"
    candidates = sorted(runtime_trace_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)[:8]
    if not candidates:
        return None, "no-runtime-trace-files"
    parsed = [parse_runtime_trace_file(path) for path in candidates]
    if not world_session:
        return parsed[0], "latest"
    for summary in parsed:
        if timestamps_overlap(
            world_session.get("startTimestamp"),
            world_session.get("endTimestamp"),
            summary.get("startTimestamp"),
            summary.get("endTimestamp"),
        ):
            return summary, "overlap"
    return parsed[0], "latest-no-overlap"


def clienterror_summary(clienterror_dir: Path) -> dict[str, Any]:
    if not clienterror_dir.exists():
        return {"present": False, "fileCount": 0, "files": []}
    files = sorted(clienterror_dir.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True)
    return {
        "present": True,
        "fileCount": len(files),
        "files": [str(path) for path in files[:8]],
    }


def capture_bundle_launch_evaluation(capture_bundle: dict[str, Any]) -> dict[str, Any]:
    evaluation = capture_bundle.get("launchEvaluation")
    if isinstance(evaluation, dict):
        return evaluation
    launch_state = ((capture_bundle.get("launch") or {}).get("state")) or {}
    if not isinstance(launch_state, dict):
        return {}
    client_args = launch_state.get("ClientArgs")
    config_url = ""
    if isinstance(client_args, list):
        for index, value in enumerate(client_args):
            if not isinstance(value, str):
                continue
            if value in {"--configURI", "--configUrl", "--config-url"} and index + 1 < len(client_args):
                candidate = client_args[index + 1]
                if isinstance(candidate, str):
                    config_url = candidate
                    break
            if value.startswith("http://") or value.startswith("https://"):
                config_url = value
                break
    params = parse_qs(urlparse(config_url).query) if config_url else {}
    host_rewrite = params.get("hostRewrite", [""])[0]
    lobby_host_rewrite = params.get("lobbyHostRewrite", [""])[0]
    content_route_rewrite = params.get("contentRouteRewrite", [""])[0]
    force_lobby_tls_mitm = bool(launch_state.get("ForceLobbyTlsMitm"))
    use_content_tls_route = bool(launch_state.get("UseContentTlsRoute"))
    content_route_mode = launch_state.get("ContentRouteMode")
    if not isinstance(content_route_mode, str) or not content_route_mode:
        content_route_mode = "content-only-local-mitm" if content_route_rewrite == "1" else "disabled"
    return {
        "configUrl": config_url,
        "hostRewrite": host_rewrite,
        "lobbyHostRewrite": lobby_host_rewrite,
        "contentRouteRewrite": content_route_rewrite,
        "contentRouteMode": content_route_mode,
        "forceLobbyTlsMitm": force_lobby_tls_mitm,
        "useContentTlsRoute": use_content_tls_route,
        "canonicalMitmLaunch": (
            force_lobby_tls_mitm
            and use_content_tls_route
            and host_rewrite == "0"
            and lobby_host_rewrite in {"", "0"}
            and content_route_rewrite == "1"
            and content_route_mode == "content-only-local-mitm"
        ),
        "nonCanonicalHostRewrite": force_lobby_tls_mitm and host_rewrite == "1",
    }


def summarize_capture_bundle(capture_bundle: dict[str, Any], *, world_log: Path) -> dict[str, Any]:
    if not isinstance(capture_bundle, dict) or not capture_bundle:
        return {
            "present": False,
            "status": None,
            "statusReason": None,
            "canonicalMitmLaunch": False,
            "nonCanonicalHostRewrite": False,
            "hostRewrite": "",
            "lobbyHostRewrite": "",
            "contentRouteRewrite": "",
            "contentRouteMode": "",
            "freshLocalTlsSessionCount": 0,
            "localMsRequestsObserved": False,
            "localMitm443ConnectionCount": 0,
            "directExternal443ConnectionCount": 0,
            "path": str(DEFAULT_BLACK_SCREEN_CAPTURE_JSON),
        }
    bundle_world_log = (((capture_bundle.get("inputs") or {}).get("worldLog")) or "")
    relevant = not bundle_world_log or bundle_world_log == str(world_log)
    summary = capture_bundle.get("summary") or {}
    launch_evaluation = capture_bundle_launch_evaluation(capture_bundle)
    if not relevant:
        return {
            "present": False,
            "status": None,
            "statusReason": None,
            "canonicalMitmLaunch": False,
            "nonCanonicalHostRewrite": False,
            "hostRewrite": "",
            "lobbyHostRewrite": "",
            "contentRouteRewrite": "",
            "contentRouteMode": "",
            "freshLocalTlsSessionCount": 0,
            "localMsRequestsObserved": False,
            "localMitm443ConnectionCount": 0,
            "directExternal443ConnectionCount": 0,
            "path": str(DEFAULT_BLACK_SCREEN_CAPTURE_JSON),
        }
    return {
        "present": relevant,
        "status": capture_bundle.get("status"),
        "statusReason": summary.get("statusReason"),
        "worldWindowSelected": summary.get("worldWindowSelected"),
        "overlapAchieved": summary.get("overlapAchieved"),
        "js5Summary": (((capture_bundle.get("js5Recorder") or {}).get("summaryJson")) or ""),
        "contentSessionLog": (
            ((capture_bundle.get("contentCapture") or {}).get("latestSessionLog"))
            or ((capture_bundle.get("contentCapture") or {}).get("sessionLog"))
            or ""
        ),
        "runtimeTracePath": (((capture_bundle.get("runtimeTrace") or {}).get("path")) or ""),
        "canonicalMitmLaunch": bool(launch_evaluation.get("canonicalMitmLaunch")),
        "nonCanonicalHostRewrite": bool(launch_evaluation.get("nonCanonicalHostRewrite")),
        "hostRewrite": launch_evaluation.get("hostRewrite", ""),
        "lobbyHostRewrite": launch_evaluation.get("lobbyHostRewrite", ""),
        "contentRouteRewrite": launch_evaluation.get("contentRouteRewrite", ""),
        "contentRouteMode": launch_evaluation.get("contentRouteMode", ""),
        "freshLocalTlsSessionCount": summary.get("freshLocalTlsSessionCount", 0),
        "sessionRouteCounts": summary.get("sessionRouteCounts", {}),
        "localMsRequestsObserved": summary.get("localMsRequestsObserved", False),
        "localMitm443ConnectionCount": summary.get("localMitm443ConnectionCount", 0),
        "directExternal443ConnectionCount": summary.get("directExternal443ConnectionCount", 0),
        "path": str(DEFAULT_BLACK_SCREEN_CAPTURE_JSON),
    }


def summarize_live_watch_summary(live_watch: dict[str, Any], *, world_log: Path) -> dict[str, Any]:
    if not isinstance(live_watch, dict) or not live_watch:
        return {
            "present": False,
            "path": str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON),
            "captureFormat": "missing",
        }
    inputs = live_watch.get("inputs") or {}
    relevant = not inputs.get("worldLog") or inputs.get("worldLog") == str(world_log)
    if not relevant:
        return {
            "present": False,
            "path": str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON),
            "captureFormat": "missing",
        }
    summary = live_watch.get("summary") or {}
    start_timestamp = summary.get("sessionStartedAt") or ""
    first_js5_request = summary.get("firstJs5RequestSeconds")
    first_archive_request = summary.get("firstArchiveRequestSeconds")
    first_js5_response = summary.get("firstJs5ResponseSeconds")
    first_archive_response = summary.get("firstArchiveResponseSeconds")
    usable_for_scene_delivery = bool(
        summary.get("localContentMitmObserved")
        or summary.get("localMsRequestsObserved")
        or int(summary.get("archiveRequestCount", 0) or 0) > 0
        or int(summary.get("responseHeaderCount", 0) or 0) > 0
        or int(summary.get("responseBytes", 0) or 0) > 0
        or (summary.get("proxyHttpContentTlsObserved") and summary.get("proxyMitmHandshakeOkObserved"))
    )

    def seconds_to_millis(value: Any) -> int | None:
        try:
            if value is None:
                return None
            return int(round(float(value) * 1000))
        except (TypeError, ValueError):
            return None

    request_count = 1 if summary.get("localMsRequestsObserved") else 0
    archive_requests = int(summary.get("archiveRequestCount", 0) or 0)
    response_headers = int(summary.get("responseHeaderCount", 0) or 0)
    response_bytes = int(summary.get("responseBytes", 0) or 0)
    if request_count <= 0:
        scene_state = "client-never-opened-js5"
    elif archive_requests <= 0:
        scene_state = "reference-tables-only"
    elif response_headers <= 0 and response_bytes <= 0:
        scene_state = "archive-requested-no-response"
    else:
        scene_state = "archive-delivery-observed"

    pseudo_session = {
        "file": summary.get("latestSessionJsonl") or str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON),
        "captureFormat": "live-watch",
        "sessionId": 1,
        "startTimestamp": start_timestamp,
        "endTimestamp": summary.get("sessionEndedAt") or start_timestamp,
        "durationSeconds": summary.get("sessionDurationSeconds"),
        "requestCount": max(request_count, archive_requests),
        "masterReferenceRequests": 0,
        "referenceTableRequests": request_count if archive_requests <= 0 else 0,
        "archiveRequests": archive_requests,
        "responseHeaderCount": response_headers,
        "responseBytes": response_bytes,
        "firstRequestAtMillis": seconds_to_millis(first_js5_request),
        "firstArchiveRequestAtMillis": seconds_to_millis(first_archive_request),
        "firstResponseHeaderAtMillis": seconds_to_millis(first_js5_response),
        "firstArchiveResponseAtMillis": seconds_to_millis(first_archive_response),
        "sceneDeliveryState": scene_state,
        "status": live_watch.get("status", "ok"),
    }
    return {
        "present": True,
        "path": str(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON),
        "captureFormat": "live-watch",
        "summary": summary,
        "pseudoSession": pseudo_session,
        "usableForSceneDelivery": usable_for_scene_delivery,
    }


def cache_signal_summary(path: Path, *, kind: str) -> dict[str, Any]:
    payload = load_json(path, {}) or {}
    summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
    return {
        "present": path.exists(),
        "path": str(path),
        "tool": payload.get("tool"),
        "status": payload.get("status"),
        "kind": kind,
        "summary": summary,
    }


def world_timeline(session: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not session:
        return []
    timeline: list[dict[str, Any]] = []
    for event in session.get("events", []):
        kind = event.get("kind", "")
        include = False
        label = kind
        detail = ""
        if kind == "world-stage":
            include = True
            label = f"stage:{event.get('stage')}"
        elif kind in {
            "world-send-rebuild-tail",
            "world-waiting-map-build-complete",
            "world-map-build-complete-compat",
            "world-client-display-config",
            "world-ready-signal-latched",
            "world-ready-signal",
            "world-awaiting-ready-signal",
            "world-send-minimal-varcs",
        }:
            include = True
            detail = stable_json_text(event.get("data", {})).strip()
        elif kind == "send-raw" and event.get("opcode") == 42 and (event.get("bytes") or 0) > 3:
            include = True
            label = "send-raw:PLAYER_INFO"
            detail = f"bytes={event.get('bytes')}"
        if not include:
            continue
        timeline.append(
            {
                "kind": kind,
                "label": label,
                "timestamp": event.get("timestamp", ""),
                "relativeSeconds": relative_seconds(session.get("startTimestamp"), event.get("timestamp")),
                "detail": detail,
            }
        )
        if len(timeline) >= 18:
            break
    return timeline


def first_world_event_timestamp(session: dict[str, Any] | None, kind: str):
    if not session:
        return None
    for event in session.get("events", []):
        if event.get("kind") == kind:
            return safe_parse_timestamp(event.get("timestamp"))
    return None


def summarize_relevant_js5_sessions(relevant_sessions: list[dict[str, Any]], overlap_confidence: str) -> dict[str, Any]:
    if not relevant_sessions:
        return {
            "count": 0,
            "requestCount": 0,
            "archiveRequests": 0,
            "referenceTableRequests": 0,
            "masterReferenceRequests": 0,
            "responseHeaderCount": 0,
            "responseBytes": 0,
            "truncatedCount": 0,
            "sceneDeliveryState": "capture-missing",
            "overlapConfidence": overlap_confidence,
        }
    request_count = sum(int(session.get("requestCount", 0) or 0) for session in relevant_sessions)
    archive_requests = sum(int(session.get("archiveRequests", 0) or 0) for session in relevant_sessions)
    reference_table_requests = sum(int(session.get("referenceTableRequests", 0) or 0) for session in relevant_sessions)
    master_reference_requests = sum(int(session.get("masterReferenceRequests", 0) or 0) for session in relevant_sessions)
    response_header_count = sum(int(session.get("responseHeaderCount", 0) or 0) for session in relevant_sessions)
    response_bytes = sum(int(session.get("responseBytes", 0) or 0) for session in relevant_sessions)
    truncated_count = sum(1 for session in relevant_sessions if session.get("truncatedResponse"))
    if request_count <= 0:
        state = "client-never-opened-js5"
    elif archive_requests <= 0:
        state = "reference-tables-only"
    elif truncated_count > 0:
        state = "archive-delivery-truncated"
    else:
        state = "archive-delivery-observed"
    return {
        "count": len(relevant_sessions),
        "requestCount": request_count,
        "archiveRequests": archive_requests,
        "referenceTableRequests": reference_table_requests,
        "masterReferenceRequests": master_reference_requests,
        "responseHeaderCount": response_header_count,
        "responseBytes": response_bytes,
        "truncatedCount": truncated_count,
        "sceneDeliveryState": state,
        "overlapConfidence": overlap_confidence,
    }


def correlate_world_to_js5(world_session: dict[str, Any] | None, relevant_sessions: list[dict[str, Any]], overlap_confidence: str) -> dict[str, Any]:
    rebuild_tail = first_world_event_timestamp(world_session, "world-send-rebuild-tail")
    world_start = safe_parse_timestamp((world_session or {}).get("startTimestamp"))

    def earliest(key: str):
        candidates = [absolute_event_timestamp(session, key) for session in relevant_sessions]
        valid = [candidate for candidate in candidates if candidate is not None]
        if rebuild_tail is not None:
            post_rebuild = [candidate for candidate in valid if candidate >= rebuild_tail]
            if post_rebuild:
                return min(post_rebuild)
        return min(valid) if valid else None

    first_js5_request = earliest("firstRequestAtMillis")
    first_archive_request = earliest("firstArchiveRequestAtMillis")
    first_js5_response = earliest("firstResponseHeaderAtMillis")
    first_archive_response = earliest("firstArchiveResponseAtMillis")

    def from_world_start(timestamp):
        if not timestamp or not world_start:
            return None
        return round((timestamp - world_start).total_seconds(), 3)

    def from_rebuild_tail(timestamp):
        if not timestamp or not rebuild_tail:
            return None
        return round((timestamp - rebuild_tail).total_seconds(), 3)

    return {
        "firstJs5RequestSeconds": from_world_start(first_js5_request),
        "firstArchiveRequestSeconds": from_world_start(first_archive_request),
        "firstJs5ResponseSeconds": from_world_start(first_js5_response),
        "firstArchiveResponseSeconds": from_world_start(first_archive_response),
        "responseHeaderCount": sum(int(session.get("responseHeaderCount", 0) or 0) for session in relevant_sessions),
        "responseBytes": sum(int(session.get("responseBytes", 0) or 0) for session in relevant_sessions),
        "overlapConfidence": overlap_confidence,
        "afterRebuildTailSeconds": {
            "firstJs5Request": from_rebuild_tail(first_js5_request),
            "firstArchiveRequest": from_rebuild_tail(first_archive_request),
            "firstJs5Response": from_rebuild_tail(first_js5_response),
            "firstArchiveResponse": from_rebuild_tail(first_archive_response),
        },
    }


def verdict(
    *,
    js5_summary: dict[str, Any],
    relevant_sessions: list[dict[str, Any]],
    world_session: dict[str, Any] | None,
    checksum_signal: dict[str, Any],
    runtime_trace: dict[str, Any] | None,
    capture_bundle: dict[str, Any],
) -> dict[str, Any]:
    checksum_mismatch_count = int((checksum_signal.get("summary") or {}).get("entryMismatchCount", 0) or 0)
    if capture_bundle.get("statusReason") == "prelogin-route-regression":
        return {
            "likelyBlocker": "prelogin-route-regression",
            "recommendation": "The latest canonical MITM launch never produced a fresh world bootstrap window. Fix the pre-login MITM route before treating scene-delivery gaps as world-side blockers.",
        }
    if capture_bundle.get("statusReason") == "content-route-bypassed-local-mitm":
        return {
            "likelyBlocker": "content-route-bypassed-local-mitm",
            "recommendation": "The canonical MITM launch still produced direct external `:443` content sockets without fresh local `/ms` capture. Fix the content-only jav_config route before diagnosing asset delivery.",
        }
    if not world_session:
        return {
            "likelyBlocker": "missing-world-session",
            "recommendation": "Capture a fresh world-bootstrap session before trusting scene-delivery conclusions.",
        }
    if checksum_mismatch_count > 0:
        return {
            "likelyBlocker": "cache-drift",
            "recommendation": "Cache drift is still present. Refresh the cache and rerun the scene delivery aid before chasing handoff timing.",
        }
    state = js5_summary["sceneDeliveryState"]
    if state == "capture-missing":
        return {
            "likelyBlocker": "capture-missing",
            "recommendation": "Run the client with JS5 proxy recording active so scene delivery can be correlated with this bootstrap session.",
        }
    proxy_no_response = any(
        session.get("captureFormat") == "content-proxy"
        and int(session.get("requestCount", 0) or 0) > 0
        and int(session.get("responseBytes", 0) or 0) <= 0
        and "127.0.0.1:43595" in str(session.get("remoteTarget", ""))
        for session in relevant_sessions
    )
    if proxy_no_response:
        return {
            "likelyBlocker": "content-proxy-no-response",
            "recommendation": "The content MITM path forwarded HTTPS content requests into the local JS5 recorder at `127.0.0.1:43595` and got no response bytes. Use direct TLS MITM relay or an HTTP-aware recorder for content capture instead of the JS5 proxy.",
        }
    if state == "client-never-opened-js5":
        return {
            "likelyBlocker": "client-never-opened-js5",
            "recommendation": "The client never opened a usable JS5 request stream during this bootstrap window. Focus on the first loader-to-JS5 transition and capture a fresh proxy session.",
        }
    if state == "reference-tables-only":
        return {
            "likelyBlocker": "reference-tables-only",
            "recommendation": "The client reached JS5 bootstrap but never progressed beyond reference tables. Focus on scene/prefetch gating and the first asset-delivery transition after rebuild.",
        }
    if state == "archive-delivery-truncated":
        return {
            "likelyBlocker": "archive-delivery-truncated",
            "recommendation": "Archive delivery started, but at least one overlapping content response ended before the declared `Content-Length` finished. Fix the local content MITM/proxy path before changing more world bootstrap behavior.",
        }
    if state == "archive-requested-no-response":
        return {
            "likelyBlocker": "archive-requested-no-response",
            "recommendation": "The client requested real content archives, but no response bytes came back during the overlapping window. Focus on the content delivery route before changing world bootstrap packets.",
        }
    if runtime_trace and runtime_trace.get("timeoutCount"):
        return {
            "likelyBlocker": "archive-delivery-observed-but-runtime-stalled",
            "recommendation": "Archive delivery overlapped this run, but the runtime still stalled. Compare the requested archive groups against live scene assets and inspect any matching client error artifacts.",
        }
    return {
        "likelyBlocker": "archive-delivery-observed",
        "recommendation": "Archive delivery overlapped this bootstrap. The next lead is scene settle/render state after asset delivery, not more early packet guessing.",
    }


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    world_session = load_session_input(args.world_log, args.world_window)
    world_summary = session_summary(world_session)

    structured_sessions, structured_summaries = load_structured_js5_sessions(args.js5_session_dir)
    legacy_logs = list_js5_session_logs(args.js5_session_dir) if not structured_summaries else []
    legacy_sessions = [parse_js5_session_log(path) for path in legacy_logs[-12:]]
    content_logs = list_content_capture_logs(args.content_capture_dir)
    content_sessions = [
        session
        for session in (parse_content_capture_log(path) for path in content_logs[-256:])
        if session and (
            int(session.get("requestCount", 0) or 0) > 0
            or int(session.get("responseBytes", 0) or 0) > 0
            or int(session.get("responseHeaderCount", 0) or 0) > 0
        )
    ]
    relevant_js5_sessions, js5_selection, overlap_confidence, fallback_sessions, selected_capture_format = select_delivery_sessions(
        structured_sessions=structured_sessions,
        content_sessions=content_sessions,
        legacy_sessions=legacy_sessions,
        world_session=world_session,
    )

    js5_summary = summarize_relevant_js5_sessions(relevant_js5_sessions, overlap_confidence)
    correlation = correlate_world_to_js5(world_session, relevant_js5_sessions, overlap_confidence)
    runtime_trace, runtime_selection = pick_relevant_runtime_trace(
        runtime_trace_dir=args.runtime_trace_dir,
        world_session=world_session,
    )
    checksum_signal = cache_signal_summary(args.checksum_report_json, kind="checksum")
    prefetch_signal = cache_signal_summary(args.prefetch_report_json, kind="prefetch")
    client_errors = clienterror_summary(args.clienterror_dir)
    capture_bundle = summarize_capture_bundle(load_json(DEFAULT_BLACK_SCREEN_CAPTURE_JSON, {}) or {}, world_log=args.world_log)
    live_watch = summarize_live_watch_summary(load_json(DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON, {}) or {}, world_log=args.world_log)
    if live_watch.get("present") and live_watch.get("usableForSceneDelivery") and overlap_confidence == "missing":
        relevant_js5_sessions = [live_watch["pseudoSession"]]
        js5_selection = "live-watch"
        overlap_confidence = "exact"
        fallback_sessions = fallback_sessions or []
        selected_capture_format = "live-watch"
        js5_summary = summarize_relevant_js5_sessions(relevant_js5_sessions, overlap_confidence)
        correlation = correlate_world_to_js5(world_session, relevant_js5_sessions, overlap_confidence)
    scene_verdict = verdict(
        js5_summary=js5_summary,
        relevant_sessions=relevant_js5_sessions,
        world_session=world_session,
        checksum_signal=checksum_signal,
        runtime_trace=runtime_trace,
        capture_bundle=capture_bundle,
    )
    if (
        overlap_confidence == "missing"
        and live_watch.get("present")
        and not live_watch.get("usableForSceneDelivery")
        and str((live_watch.get("summary") or {}).get("terminalState", "")).startswith("prelogin-")
    ):
        scene_verdict = {
            "likelyBlocker": "prelogin-route-regression",
            "recommendation": "The latest live watcher never reached the local HTTP content branch. Fix the pre-login secure-game routing path before treating missing asset capture as a scene-delivery blocker.",
        }

    status = "ok" if world_session and overlap_confidence != "missing" else "partial"
    if capture_bundle.get("statusReason") in {"prelogin-route-regression", "content-route-bypassed-local-mitm"}:
        status = "partial"
    return standard_tool_artifact(
        tool_name="run_946_scene_delivery_aid",
        status=status,
        inputs={
            "worldLog": str(args.world_log),
            "worldWindow": args.world_window or "",
            "js5SessionDir": str(args.js5_session_dir),
            "contentCaptureDir": str(args.content_capture_dir),
            "runtimeTraceDir": str(args.runtime_trace_dir),
            "clienterrorDir": str(args.clienterror_dir),
            "checksumReportJson": str(args.checksum_report_json),
            "prefetchReportJson": str(args.prefetch_report_json),
            "inputFingerprint": input_fingerprint(args),
        },
        artifacts={
            "sceneDeliveryAnalysisJson": str(args.output_dir / SCENE_DELIVERY_JSON),
            "sceneDeliveryAnalysisMarkdown": str(args.output_dir / SCENE_DELIVERY_MD),
        },
        summary={
            "worldSessionExists": bool(world_session),
            "relevantJs5SessionCount": js5_summary["count"],
            "archiveRequestsObserved": js5_summary["archiveRequests"],
            "referenceTableRequests": js5_summary["referenceTableRequests"],
            "responseHeaderCount": js5_summary["responseHeaderCount"],
            "responseBytes": js5_summary["responseBytes"],
            "truncatedJs5SessionCount": js5_summary["truncatedCount"],
            "sceneDeliveryState": scene_verdict["likelyBlocker"],
            "overlapConfidence": overlap_confidence,
            "selectedCaptureFormat": selected_capture_format,
            "runtimeTracePresent": bool(runtime_trace),
            "clientErrorFileCount": client_errors["fileCount"],
            "checksumStatus": checksum_signal.get("status"),
            "prefetchState": (prefetch_signal.get("summary") or {}).get("comparisonState"),
            "captureBundlePresent": bool(capture_bundle.get("present")),
            "liveWatchPresent": bool(live_watch.get("present")),
        },
        extra={
            "worldSession": world_summary,
            "timeline": world_timeline(world_session),
            "js5": {
                "summary": js5_summary,
                "captureFormat": selected_capture_format,
                "selectionStrategy": js5_selection,
                "availableStructuredSummaryCount": len(structured_summaries),
                "availableContentSessionCount": len(content_sessions),
                "availableLegacySessionCount": len(legacy_sessions),
                "relevantSessions": relevant_js5_sessions,
                "fallbackSessions": fallback_sessions,
            },
            "correlation": correlation,
            "runtimeTrace": {
                "selectionStrategy": runtime_selection,
                "summary": runtime_trace,
            },
            "clientErrors": client_errors,
            "captureBundle": {
                **capture_bundle,
            },
            "liveWatch": {
                **live_watch,
            },
            "cacheSignals": {
                "checksum": checksum_signal,
                "prefetch": prefetch_signal,
            },
            "verdict": scene_verdict,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    correlation = artifact.get("correlation", {}) or {}
    rebuild_tail = correlation.get("afterRebuildTailSeconds", {}) or {}
    lines = [
        "# 946 Scene Delivery Aid",
        "",
        f"- Status: `{artifact['status']}`",
        f"- World session present: `{artifact['summary']['worldSessionExists']}`",
        f"- Relevant JS5 sessions: `{artifact['summary']['relevantJs5SessionCount']}`",
        f"- Overlap confidence: `{artifact['summary']['overlapConfidence']}`",
        f"- Selected capture format: `{artifact['summary'].get('selectedCaptureFormat', 'missing')}`",
        f"- Scene delivery state: `{artifact['summary']['sceneDeliveryState']}`",
        f"- Archive requests observed: `{artifact['summary']['archiveRequestsObserved']}`",
        f"- Response headers observed: `{artifact['summary']['responseHeaderCount']}`",
        f"- Response bytes observed: `{artifact['summary']['responseBytes']}`",
        f"- Truncated archive sessions: `{artifact['summary'].get('truncatedJs5SessionCount', 0)}`",
        f"- Capture bundle present: `{artifact['summary']['captureBundlePresent']}`",
        f"- Live watcher present: `{artifact['summary'].get('liveWatchPresent', False)}`",
        "",
        "## Verdict",
        "",
        f"- Likely blocker: `{artifact.get('verdict', {}).get('likelyBlocker', 'unknown')}`",
        f"- Recommendation: {artifact.get('verdict', {}).get('recommendation', 'No recommendation available.')}",
        "",
        "## Delivery Answers",
        "",
        f"- Overlapping content capture matched: `{artifact['summary']['overlapConfidence'] != 'missing'}`",
        f"- Client requested real archives: `{artifact['summary']['archiveRequestsObserved'] > 0}`",
        f"- Server sent response headers back: `{artifact['summary']['responseHeaderCount'] > 0}`",
        f"- First JS5 request after `world-send-rebuild-tail`: `{rebuild_tail.get('firstJs5Request')}` seconds",
        f"- First archive request after `world-send-rebuild-tail`: `{rebuild_tail.get('firstArchiveRequest')}` seconds",
        f"- First JS5 response after `world-send-rebuild-tail`: `{rebuild_tail.get('firstJs5Response')}` seconds",
        f"- First archive response after `world-send-rebuild-tail`: `{rebuild_tail.get('firstArchiveResponse')}` seconds",
        "",
        "## World Timeline",
        "",
    ]
    timeline = artifact.get("timeline", [])
    if not timeline:
        lines.append("- No world timeline available.")
    else:
        for item in timeline:
            relative = item.get("relativeSeconds")
            relative_text = f" t+`{relative}`s" if relative is not None else ""
            detail = f" {item['detail']}" if item.get("detail") else ""
            lines.append(f"- `{item['label']}`{relative_text}{detail}")
    lines.extend(["", "## Capture Sessions", ""])
    relevant_sessions = ((artifact.get("js5") or {}).get("relevantSessions")) or []
    if not relevant_sessions:
        lines.append("- No overlapping content capture matched this world session.")
        fallback_sessions = ((artifact.get("js5") or {}).get("fallbackSessions")) or []
        if fallback_sessions:
            fallback = fallback_sessions[0]
            lines.append(
                f"- Latest fallback capture: `{Path(fallback['file']).name}` format=`{fallback.get('captureFormat', 'legacy')}` state=`{fallback['sceneDeliveryState']}` requests=`{fallback.get('requestCount', 0)}`"
            )
    else:
        for session in relevant_sessions:
            lines.append(
                f"- `{Path(session['file']).name}` format=`{session.get('captureFormat', 'legacy')}` state=`{session['sceneDeliveryState']}` requests=`{session.get('requestCount', 0)}` archiveRequests=`{session.get('archiveRequests', 0)}` responseHeaders=`{session.get('responseHeaderCount', 0)}` responseBytes=`{session.get('responseBytes', 0)}`"
            )
    runtime_summary = ((artifact.get("runtimeTrace") or {}).get("summary")) or {}
    lines.extend(["", "## Runtime Trace", ""])
    if not runtime_summary:
        lines.append("- No runtime trace summary available.")
    else:
        lines.append(
            f"- File: `{Path(runtime_summary.get('file', '')).name if runtime_summary.get('file') else 'n/a'}` samples=`{runtime_summary.get('sampleCount', 0)}` timeouts=`{runtime_summary.get('timeoutCount', 0)}` ports=`{runtime_summary.get('latestConnectionPorts', [])}`"
        )
    capture_bundle = artifact.get("captureBundle") or {}
    lines.extend(["", "## Capture Bundle", ""])
    if not capture_bundle.get("present"):
        lines.append("- No black-screen capture bundle was linked to this analysis.")
    else:
        lines.append(f"- Status: `{capture_bundle.get('status')}`")
        lines.append(f"- Status reason: `{capture_bundle.get('statusReason')}`")
        lines.append(f"- World window selected: `{capture_bundle.get('worldWindowSelected')}`")
        lines.append(f"- Overlap achieved: `{capture_bundle.get('overlapAchieved')}`")
        lines.append(f"- Canonical MITM launch: `{capture_bundle.get('canonicalMitmLaunch')}`")
        lines.append(f"- hostRewrite: `{capture_bundle.get('hostRewrite')}`")
        lines.append(f"- lobbyHostRewrite: `{capture_bundle.get('lobbyHostRewrite')}`")
        lines.append(f"- contentRouteRewrite: `{capture_bundle.get('contentRouteRewrite')}`")
        lines.append(f"- contentRouteMode: `{capture_bundle.get('contentRouteMode')}`")
        lines.append(f"- Fresh local TLS sessions: `{capture_bundle.get('freshLocalTlsSessionCount')}`")
        lines.append(f"- Local `/ms` observed: `{capture_bundle.get('localMsRequestsObserved')}`")
        lines.append(f"- Local MITM `:443` connections: `{capture_bundle.get('localMitm443ConnectionCount')}`")
        lines.append(f"- Direct external `:443` connections: `{capture_bundle.get('directExternal443ConnectionCount')}`")
        lines.append(f"- JS5 summary: `{capture_bundle.get('js5Summary')}`")
        lines.append(f"- Content capture: `{capture_bundle.get('contentSessionLog')}`")
        lines.append(f"- Runtime trace: `{capture_bundle.get('runtimeTracePath')}`")
    live_watch = artifact.get("liveWatch") or {}
    lines.extend(["", "## Live Watch", ""])
    if not live_watch.get("present"):
        lines.append("- No live watcher summary was linked to this analysis.")
    else:
        watch_summary = live_watch.get("summary") or {}
        lines.append(f"- Terminal state: `{watch_summary.get('terminalState')}`")
        lines.append(f"- Deep hooks enabled: `{watch_summary.get('deepHooksEnabled')}`")
        lines.append(f"- Local content MITM observed: `{watch_summary.get('localContentMitmObserved')}`")
        lines.append(f"- First archive request seconds: `{watch_summary.get('firstArchiveRequestSeconds')}`")
        lines.append(f"- First archive response seconds: `{watch_summary.get('firstArchiveResponseSeconds')}`")
    lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    structured_summaries = list_js5_summary_jsons(args.js5_session_dir)
    legacy_logs = list_js5_session_logs(args.js5_session_dir) if not structured_summaries else []
    jsonl_logs = sorted(args.js5_session_dir.glob("session-*.jsonl"), key=lambda path: path.stat().st_mtime) if args.js5_session_dir.exists() else []
    content_logs = list_content_capture_logs(args.content_capture_dir)
    runtime_logs = sorted(args.runtime_trace_dir.glob("*.jsonl"), key=lambda path: path.stat().st_mtime) if args.runtime_trace_dir.exists() else []
    clienterror_files = sorted(args.clienterror_dir.glob("*"), key=lambda path: path.stat().st_mtime) if args.clienterror_dir.exists() else []
    return artifact_input_fingerprint(
        "run_946_scene_delivery_aid",
        [
            WORKSPACE / "tools" / "run_946_scene_delivery_aid.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            WORKSPACE / "tools" / "protocol_946_debug_common.py",
            args.world_log,
            args.checksum_report_json,
            args.prefetch_report_json,
            DEFAULT_BLACK_SCREEN_CAPTURE_JSON,
            DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON,
            *structured_summaries[-12:],
            *content_logs[-256:],
            *legacy_logs[-12:],
            *jsonl_logs[-12:],
            *runtime_logs[-8:],
            *clienterror_files[-8:],
        ],
        worldWindow=args.world_window or "",
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / SCENE_DELIVERY_JSON, artifact)
    (output_dir / SCENE_DELIVERY_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, SCENE_DELIVERY_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / SCENE_DELIVERY_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, SCENE_DELIVERY_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
