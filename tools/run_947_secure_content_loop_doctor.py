from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_WATCH_ROOT = WORKSPACE / "data" / "debug" / "client-live-watch"
DEFAULT_SOURCE_CACHE_DIR = WORKSPACE / "data" / "cache"
DEFAULT_RUNTIME_CACHE_DIR = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Jagex" / "RuneScape"
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "secure-content-loop-doctor-947-current"
JS5_CACHE_PATH_RE = re.compile(r"js5-(\d+)\.jcache$", re.IGNORECASE)
STUB_CACHE_SIZE = 12_288


@dataclass(frozen=True)
class SecureRequest:
    source_line: int
    socket: str
    archive: int
    build_hint: int
    trailer_hex: str


@dataclass(frozen=True)
class SecureResponseHeader:
    source_line: int
    socket: str
    archive: int
    compression: int
    length: int


@dataclass(frozen=True)
class CacheTouch:
    source_line: int
    action: str
    archive: int
    path: str


@dataclass(frozen=True)
class ArchiveObservation:
    archive: int
    request_count: int
    response_header_count: int
    file_touch_count: int
    file_write_count: int
    response_compressions: list[int]
    response_lengths: list[int]
    source_cache_size: int | None
    runtime_cache_size: int | None
    source_cache_status: str
    runtime_cache_status: str
    reasons: list[str]
    needs: list[str]


@dataclass(frozen=True)
class RequestCycle:
    cycle_length: int
    repeat_count: int
    archives: list[int]
    tail_skew: int
    cycle_first_line: int
    cycle_last_line: int


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Decode the secure 947 splash-stage hook trace, summarize repeating 255/* reference-table "
            "request cycles, and tell you which exact cache slots are still unhealthy in staged/runtime cache."
        )
    )
    parser.add_argument("--hook-path", type=Path, default=None)
    parser.add_argument("--watch-root", type=Path, default=DEFAULT_WATCH_ROOT)
    parser.add_argument("--source-cache-dir", type=Path, default=DEFAULT_SOURCE_CACHE_DIR)
    parser.add_argument("--runtime-cache-dir", type=Path, default=DEFAULT_RUNTIME_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-cycle-length", type=int, default=2)
    parser.add_argument("--max-cycle-length", type=int, default=32)
    parser.add_argument("--min-repeats", type=int, default=3)
    return parser.parse_args(argv)


def resolve_default_hook_path(watch_root: Path) -> Path:
    candidates: list[Path] = []
    if watch_root.exists():
        latest_root_hook = watch_root / "latest-hooks.jsonl"
        if latest_root_hook.is_file():
            candidates.append(latest_root_hook)
        candidates.extend(path for path in watch_root.glob("attach-*\\latest-hooks.jsonl") if path.is_file())
        candidates.extend(path for path in watch_root.glob("attach-*\\hooks-*.jsonl") if path.is_file())
        candidates.extend(path for path in watch_root.glob("hooks-*.jsonl") if path.is_file())
    if not candidates:
        raise FileNotFoundError(f"No attach hook JSONL found under {watch_root}")
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0]


def safe_bytes_from_hex(hex_text: str) -> bytes:
    normalized = (hex_text or "").strip()
    if not normalized:
        return b""
    try:
        return bytes.fromhex(normalized)
    except ValueError:
        return b""


def parse_preview_requests(source_line: int, socket: str, preview_hex: str) -> list[SecureRequest]:
    payload = safe_bytes_from_hex(preview_hex)
    requests: list[SecureRequest] = []
    offset = 0
    while offset + 10 <= len(payload):
        chunk = payload[offset : offset + 10]
        if chunk[0] != 0x01 or chunk[1] != 0xFF:
            break
        requests.append(
            SecureRequest(
                source_line=source_line,
                socket=socket,
                archive=int.from_bytes(chunk[2:6], "big"),
                build_hint=int.from_bytes(chunk[6:8], "big"),
                trailer_hex=chunk[6:10].hex(),
            )
        )
        offset += 10
    return requests


def parse_response_header(source_line: int, socket: str, preview_hex: str) -> SecureResponseHeader | None:
    payload = safe_bytes_from_hex(preview_hex)
    if len(payload) < 10 or payload[0] != 0xFF:
        return None
    return SecureResponseHeader(
        source_line=source_line,
        socket=socket,
        archive=int.from_bytes(payload[1:5], "big"),
        compression=payload[5],
        length=int.from_bytes(payload[6:10], "big"),
    )


def parse_cache_touch(source_line: int, event: dict[str, object]) -> CacheTouch | None:
    action = str(event.get("action", ""))
    if action not in {"open", "write"}:
        return None
    path = str(event.get("path", ""))
    match = JS5_CACHE_PATH_RE.search(path)
    if not match:
        return None
    return CacheTouch(
        source_line=source_line,
        action=action,
        archive=int(match.group(1)),
        path=path,
    )


def parse_hook(path: Path) -> tuple[list[SecureRequest], list[SecureResponseHeader], list[CacheTouch], Counter[str]]:
    requests: list[SecureRequest] = []
    responses: list[SecureResponseHeader] = []
    touches: list[CacheTouch] = []
    socket_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for source_line, raw_line in enumerate(handle, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            event = json.loads(raw_line)
            action = str(event.get("action", ""))
            socket = str(event.get("socket", ""))
            if action in {"send", "WSASend", "send-first-chunk"}:
                parsed_requests = parse_preview_requests(source_line, socket, str(event.get("previewHex", "")))
                requests.extend(parsed_requests)
                if parsed_requests:
                    socket_counts[socket] += len(parsed_requests)
                continue
            if action in {"recv", "WSARecv", "recv-first-chunk"}:
                header = parse_response_header(source_line, socket, str(event.get("previewHex", "")))
                if header is not None:
                    responses.append(header)
                continue
            cache_touch = parse_cache_touch(source_line, event)
            if cache_touch is not None:
                touches.append(cache_touch)
    return requests, responses, touches, socket_counts


def canonicalize_cycle(values: list[int]) -> list[int]:
    if not values:
        return []
    best_index = min(range(len(values)), key=lambda index: tuple(values[index:] + values[:index]))
    return values[best_index:] + values[:best_index]


def find_repeating_suffix(
    requests: list[SecureRequest],
    min_cycle_length: int,
    max_cycle_length: int,
    min_repeats: int,
) -> RequestCycle | None:
    if len(requests) < min_cycle_length * min_repeats:
        return None
    archives = [request.archive for request in requests]
    upper_cycle_length = min(max_cycle_length, len(archives) // min_repeats)
    best: RequestCycle | None = None
    for cycle_length in range(min_cycle_length, upper_cycle_length + 1):
        cycle = archives[-cycle_length:]
        repeat_count = 1
        offset = len(archives) - cycle_length * 2
        while offset >= 0 and archives[offset : offset + cycle_length] == cycle:
            repeat_count += 1
            offset -= cycle_length
        if repeat_count < min_repeats:
            continue
        candidate = RequestCycle(
            cycle_length=cycle_length,
            repeat_count=repeat_count,
            archives=canonicalize_cycle(list(cycle)),
            tail_skew=0,
            cycle_first_line=requests[len(requests) - cycle_length].source_line,
            cycle_last_line=requests[-1].source_line,
        )
        if best is None or (
            candidate.repeat_count * candidate.cycle_length,
            candidate.repeat_count,
            candidate.cycle_length,
        ) > (
            best.repeat_count * best.cycle_length,
            best.repeat_count,
            best.cycle_length,
        ):
            best = candidate
    return best


def inspect_cache_size(root: Path, archive: int) -> int | None:
    candidate = root / f"js5-{archive}.jcache"
    if not candidate.exists():
        return None
    return candidate.stat().st_size


def inspect_cache_shape(root: Path, archive: int) -> dict[str, int] | None:
    candidate = root / f"js5-{archive}.jcache"
    if not candidate.exists():
        return None
    try:
        connection = sqlite3.connect(f"file:{candidate}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        cursor = connection.cursor()
        cache_index_rows = cursor.execute("select count(*) from cache_index").fetchone()
        cache_rows = cursor.execute("select count(*) from cache").fetchone()
        cache_index_data_len = cursor.execute("select length(DATA) from cache_index where KEY = 1").fetchone()
        return {
            "cache_index_rows": 0 if not cache_index_rows else int(cache_index_rows[0]),
            "cache_rows": 0 if not cache_rows else int(cache_rows[0]),
            "cache_index_data_len": 0 if not cache_index_data_len or cache_index_data_len[0] is None else int(cache_index_data_len[0]),
        }
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def classify_cache_size(size: int | None) -> str:
    if size is None:
        return "missing"
    if size == STUB_CACHE_SIZE:
        return "stub-like"
    return "present"


def build_archive_observations(
    requests: Iterable[SecureRequest],
    responses: Iterable[SecureResponseHeader],
    touches: Iterable[CacheTouch],
    source_cache_dir: Path,
    runtime_cache_dir: Path,
) -> list[ArchiveObservation]:
    request_counts = Counter(request.archive for request in requests)
    response_counts = Counter(response.archive for response in responses)
    touch_counts = Counter(touch.archive for touch in touches)
    write_counts = Counter(touch.archive for touch in touches if touch.action == "write")
    response_lengths: dict[int, list[int]] = {}
    response_compressions: dict[int, list[int]] = {}
    for response in responses:
        response_lengths.setdefault(response.archive, []).append(response.length)
        response_compressions.setdefault(response.archive, []).append(response.compression)

    observations: list[ArchiveObservation] = []
    for archive in sorted(set(request_counts) | set(response_counts) | set(touch_counts)):
        source_size = inspect_cache_size(source_cache_dir, archive)
        runtime_size = inspect_cache_size(runtime_cache_dir, archive)
        source_shape = inspect_cache_shape(source_cache_dir, archive)
        runtime_shape = inspect_cache_shape(runtime_cache_dir, archive)
        source_status = classify_cache_size(source_size)
        runtime_status = classify_cache_size(runtime_size)
        if source_shape and source_shape["cache_index_rows"] > 0:
            source_status = "present"
        elif source_shape and source_shape["cache_rows"] > 0:
            source_status = "missing-reference-table"
        if runtime_shape and runtime_shape["cache_index_rows"] > 0:
            runtime_status = "present"
        elif runtime_shape and runtime_shape["cache_rows"] > 0:
            runtime_status = "missing-reference-table"
        reasons: list[str] = []
        needs: list[str] = []
        if source_status == "stub-like":
            reasons.append(f"source-cache-stub={source_size}")
            needs.append(f"refresh data/cache/js5-{archive}.jcache")
        elif source_status == "missing-reference-table":
            reasons.append(
                "source-cache-missing-reference-table"
                if not source_shape
                else f"source-cache-missing-reference-table cacheRows={source_shape['cache_rows']}"
            )
            needs.append(f"refresh data/cache/js5-{archive}.jcache reference table")
        elif source_status == "missing":
            reasons.append("source-cache-missing")
            needs.append(f"create data/cache/js5-{archive}.jcache")
        if runtime_status == "stub-like":
            reasons.append(f"runtime-cache-stub={runtime_size}")
            needs.append(f"refresh ProgramData runtime js5-{archive}.jcache")
        elif runtime_status == "missing-reference-table":
            reasons.append(
                "runtime-cache-missing-reference-table"
                if not runtime_shape
                else f"runtime-cache-missing-reference-table cacheRows={runtime_shape['cache_rows']}"
            )
            needs.append(f"refresh ProgramData runtime js5-{archive}.jcache reference table")
        elif runtime_status == "missing":
            reasons.append("runtime-cache-missing")
            needs.append(f"create ProgramData runtime js5-{archive}.jcache")
        if request_counts[archive] > 0 and response_counts[archive] == 0:
            reasons.append("request-without-visible-response-header")
        observations.append(
            ArchiveObservation(
                archive=archive,
                request_count=request_counts[archive],
                response_header_count=response_counts[archive],
                file_touch_count=touch_counts[archive],
                file_write_count=write_counts[archive],
                response_compressions=sorted(set(response_compressions.get(archive, []))),
                response_lengths=sorted(set(response_lengths.get(archive, []))),
                source_cache_size=source_size,
                runtime_cache_size=runtime_size,
                source_cache_status=source_status,
                runtime_cache_status=runtime_status,
                reasons=reasons,
                needs=sorted(set(needs)),
            )
        )
    observations.sort(key=lambda item: (-item.request_count, item.archive))
    return observations


def render_markdown(
    hook_path: Path,
    primary_socket: str,
    requests: list[SecureRequest],
    responses: list[SecureResponseHeader],
    touches: list[CacheTouch],
    cycle: RequestCycle | None,
    observations: list[ArchiveObservation],
    likely_blocker: str,
) -> str:
    top_lines = []
    for observation in observations[:16]:
        line = (
            f"- archive `{observation.archive}` req=`{observation.request_count}` "
            f"resp=`{observation.response_header_count}` writes=`{observation.file_write_count}` "
            f"source=`{observation.source_cache_status}:{observation.source_cache_size}` "
            f"runtime=`{observation.runtime_cache_status}:{observation.runtime_cache_size}`"
        )
        if observation.reasons:
            line += f" reasons=`{'; '.join(observation.reasons)}`"
        top_lines.append(line)

    cycle_lines = ["- none detected"]
    if cycle is not None:
        cycle_lines = [
            f"- cycle length=`{cycle.cycle_length}` repeats=`{cycle.repeat_count}` tailSkew=`{cycle.tail_skew}`",
            f"- cycle archives=`{','.join(str(value) for value in cycle.archives)}`",
            f"- cycle lines=`{cycle.cycle_first_line}-{cycle.cycle_last_line}`",
        ]

    return "\n".join(
        [
            "# 947 Secure Content Loop Doctor",
            "",
            f"- Hook path: `{hook_path}`",
            f"- Primary socket: `{primary_socket}`",
            f"- Parsed secure requests: `{len(requests)}`",
            f"- Parsed secure response headers: `{len(responses)}`",
            f"- Parsed cache touches: `{len(touches)}`",
            f"- Likely blocker: `{likely_blocker}`",
            "",
            "## Repeating Tail",
            "",
            *cycle_lines,
            "",
            "## Hot Archives",
            "",
            *top_lines,
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    hook_path = args.hook_path or resolve_default_hook_path(args.watch_root)
    requests, responses, touches, socket_counts = parse_hook(hook_path)
    primary_socket = socket_counts.most_common(1)[0][0] if socket_counts else ""
    if primary_socket:
        requests = [request for request in requests if request.socket == primary_socket]
        responses = [response for response in responses if response.socket == primary_socket]
    cycle = find_repeating_suffix(
        requests,
        min_cycle_length=args.min_cycle_length,
        max_cycle_length=args.max_cycle_length,
        min_repeats=args.min_repeats,
    )
    observations = build_archive_observations(
        requests=requests,
        responses=responses,
        touches=touches,
        source_cache_dir=args.source_cache_dir,
        runtime_cache_dir=args.runtime_cache_dir,
    )
    unhealthy_cycle_archives = []
    if cycle is not None:
        unhealthy_cycle_archives = [
            observation.archive
            for observation in observations
            if observation.archive in set(cycle.archives)
            and observation.source_cache_status == "stub-like"
            and observation.runtime_cache_status == "stub-like"
        ]
    if unhealthy_cycle_archives:
        likely_blocker = "secure-reference-table-loop-on-stubbed-archives"
    elif cycle is not None and all(observation.response_header_count > 0 for observation in observations if observation.archive in set(cycle.archives)):
        likely_blocker = "client-repeats-successful-secure-reference-tables"
    elif cycle is not None:
        likely_blocker = "secure-reference-table-loop"
    elif requests:
        likely_blocker = "secure-reference-table-warmup-no-stable-cycle-yet"
    else:
        likely_blocker = "no-secure-reference-table-requests-detected"

    artifact = {
        "tool": "run_947_secure_content_loop_doctor",
        "schemaVersion": 1,
        "hookPath": str(hook_path),
        "primarySocket": primary_socket,
        "requestCount": len(requests),
        "responseHeaderCount": len(responses),
        "cacheTouchCount": len(touches),
        "likelyBlocker": likely_blocker,
        "cycle": asdict(cycle) if cycle is not None else None,
        "observations": [asdict(observation) for observation in observations],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "secure-content-loop-doctor.json"
    markdown_path = args.output_dir / "secure-content-loop-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    markdown_path.write_text(
        render_markdown(
            hook_path=hook_path,
            primary_socket=primary_socket,
            requests=requests,
            responses=responses,
            touches=touches,
            cycle=cycle,
            observations=observations,
            likely_blocker=likely_blocker,
        ),
        encoding="utf-8",
    )
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "likelyBlocker": likely_blocker}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
