from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from protocol_automation_common import (
    SHARED_DIR,
    WORKSPACE,
    artifact_input_fingerprint,
    cache_hit,
    ensure_directory,
    load_json,
    output_artifact_map,
    record_cache_entry,
    stable_json_text,
    standard_tool_artifact,
    write_json,
)
from run_946_scene_delivery_aid import DEFAULT_JS5_SESSION_DIR


JS5_ARCHIVE_RESOLUTION_JSON = "js5-archive-resolution.json"
JS5_ARCHIVE_RESOLUTION_MD = "js5-archive-resolution.md"
JS5_ARCHIVE_RESOLUTION_CACHE_KEY = "js5-archive-resolver"
INDEX_KT = WORKSPACE / "src" / "main" / "kotlin" / "com" / "opennxt" / "filesystem" / "Index.kt"
PREFETCH_TABLE_KT = (
    WORKSPACE
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "opennxt"
    / "filesystem"
    / "prefetches"
    / "PrefetchTable.kt"
)
INDEX_CONST_RE = re.compile(r"const val (?P<name>[A-Z0-9_]+)\s*=\s*(?P<value>\d+)")
INDEX_PREFETCH_RE = re.compile(r"IndexPrefetch\((?:Index\.)?(?P<index>[A-Z0-9_]+|\d+)\)")
ARCHIVE_PREFETCH_RE = re.compile(r"ArchivePrefetch\(Index\.(?P<index>[A-Z0-9_]+),\s*(?P<archive>\d+)\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve structured JS5 archive traffic into meaningful 946 scene/cache labels."
    )
    parser.add_argument("--js5-session-dir", type=Path, default=DEFAULT_JS5_SESSION_DIR)
    parser.add_argument("--summary-json", type=Path)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / JS5_ARCHIVE_RESOLUTION_JSON,
        output_dir / JS5_ARCHIVE_RESOLUTION_MD,
    ]


def list_summary_jsons(js5_session_dir: Path) -> list[Path]:
    if not js5_session_dir.exists():
        return []
    return sorted(js5_session_dir.glob("summary-*.json"), key=lambda path: path.stat().st_mtime)


def parse_index_names(index_path: Path) -> dict[int, str]:
    if not index_path.exists():
        return {}
    mapping: dict[int, str] = {}
    for match in INDEX_CONST_RE.finditer(index_path.read_text(encoding="utf-8")):
        mapping[int(match.group("value"))] = match.group("name")
    return mapping


def parse_prefetch_hints(prefetch_path: Path, index_names: dict[int, str]) -> tuple[set[int], set[tuple[int, int]]]:
    if not prefetch_path.exists():
        return set(), set()

    def resolve_index(token: str) -> int | None:
        if token.isdigit():
            return int(token)
        for index, name in index_names.items():
            if name == token:
                return index
        return None

    prefetch_indexes: set[int] = set()
    prefetch_archives: set[tuple[int, int]] = set()
    text = prefetch_path.read_text(encoding="utf-8")
    for match in INDEX_PREFETCH_RE.finditer(text):
        index = resolve_index(match.group("index"))
        if index is not None:
            prefetch_indexes.add(index)
    for match in ARCHIVE_PREFETCH_RE.finditer(text):
        index = resolve_index(match.group("index"))
        if index is not None:
            prefetch_archives.add((index, int(match.group("archive"))))
    return prefetch_indexes, prefetch_archives


def default_summary_path(args: argparse.Namespace) -> Path | None:
    if args.summary_json:
        return args.summary_json if args.summary_json.exists() else None
    summaries = list_summary_jsons(args.js5_session_dir)
    return summaries[-1] if summaries else None


def load_summary_sessions(summary_path: Path | None) -> tuple[list[dict[str, Any]], Path | None]:
    if not summary_path or not summary_path.exists():
        return [], None
    payload = load_json(summary_path, {}) or {}
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        return [], summary_path
    return [entry for entry in sessions if isinstance(entry, dict)], summary_path


def load_jsonl_events(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def classify_archive(index: int, archive: int, index_name: str | None) -> str:
    if index == 255 and archive == 255:
        return "master-reference-table"
    if index == 255:
        return "reference-table"
    name = index_name or ""
    if name in {"MAPS", "WORLDMAP", "WORLDMAPAREAS", "WORLDMAPLABELS"}:
        return "map/region-related"
    if name == "INTERFACES":
        return "interface-related"
    if name.startswith("CONFIG") or name in {
        "CONFIG",
        "CLIENTSCRIPTS",
        "DEFAULTS",
        "BINARY",
        "FONTMETRICS",
        "SPRITES",
        "MODELS",
        "MATERIALS",
        "PARTICLES",
        "BILLBOARDS",
        "LOADINGSPRITES",
        "LOADINGSCREENS",
    }:
        return "config/data"
    return "unresolved"


def build_resolution_label(index: int, archive: int, index_name: str | None, category: str) -> str:
    if category == "master-reference-table":
        return "master-reference-table"
    if category == "reference-table":
        return f"reference-table[{archive}]"
    name = index_name or f"index-{index}"
    return f"archive[{index},{archive}] ({name})"


def resolve_sessions(
    sessions: list[dict[str, Any]],
    *,
    index_names: dict[int, str],
    prefetch_indexes: set[int],
    prefetch_archives: set[tuple[int, int]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    aggregate: dict[tuple[int, int], dict[str, Any]] = {}
    category_counts: Counter[str] = Counter()
    for session in sessions:
        session_id = session.get("sessionId")
        session_jsonl = session.get("sessionJsonl")
        events = load_jsonl_events(Path(session_jsonl)) if isinstance(session_jsonl, str) else []
        if not events:
            continue
        for event in events:
            event_type = event.get("eventType")
            if event_type not in {"request_frame", "response_header"}:
                continue
            index = event.get("index")
            archive = event.get("archive")
            if not isinstance(index, int) or not isinstance(archive, int):
                continue
            index_name = index_names.get(index)
            category = classify_archive(index, archive, index_name)
            key = (index, archive)
            record = aggregate.setdefault(
                key,
                {
                    "index": index,
                    "archive": archive,
                    "indexName": index_name,
                    "category": category,
                    "label": build_resolution_label(index, archive, index_name, category),
                    "prefetchedByDefault": index in prefetch_indexes or (index, archive) in prefetch_archives,
                    "requestCount": 0,
                    "responseHeaderCount": 0,
                    "firstRequestAtMillis": None,
                    "firstResponseHeaderAtMillis": None,
                    "sessionIds": [],
                    "rawLabels": [],
                },
            )
            if session_id not in record["sessionIds"]:
                record["sessionIds"].append(session_id)
            label = event.get("label")
            if isinstance(label, str) and label and label not in record["rawLabels"]:
                record["rawLabels"].append(label)
            relative_millis = event.get("relativeMillis")
            if event_type == "request_frame":
                record["requestCount"] += 1
                if isinstance(relative_millis, (int, float)):
                    current = record["firstRequestAtMillis"]
                    if current is None or relative_millis < current:
                        record["firstRequestAtMillis"] = int(relative_millis)
            elif event_type == "response_header":
                record["responseHeaderCount"] += 1
                if isinstance(relative_millis, (int, float)):
                    current = record["firstResponseHeaderAtMillis"]
                    if current is None or relative_millis < current:
                        record["firstResponseHeaderAtMillis"] = int(relative_millis)
        for record in aggregate.values():
            category_counts[record["category"]] += 0
    resolutions = sorted(
        aggregate.values(),
        key=lambda item: (
            -int(item["requestCount"]),
            -int(item["responseHeaderCount"]),
            int(item["index"]),
            int(item["archive"]),
        ),
    )
    category_counts = Counter(record["category"] for record in resolutions)
    return resolutions, dict(sorted(category_counts.items()))


def input_fingerprint(args: argparse.Namespace) -> str:
    summary_path = default_summary_path(args)
    summary_payload = load_json(summary_path, {}) if summary_path and summary_path.exists() else {}
    session_jsonls = []
    if isinstance(summary_payload, dict):
        for session in summary_payload.get("sessions", []):
            if isinstance(session, dict) and isinstance(session.get("sessionJsonl"), str):
                session_jsonls.append(Path(session["sessionJsonl"]))
    return artifact_input_fingerprint(
        "run_946_js5_archive_resolver",
        [
            WORKSPACE / "tools" / "run_946_js5_archive_resolver.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            INDEX_KT,
            PREFETCH_TABLE_KT,
            *(session_jsonls[:16]),
            *( [summary_path] if summary_path else [] ),
        ],
        js5SessionDir=str(args.js5_session_dir),
        summaryJson=str(args.summary_json) if args.summary_json else "",
    )


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    summary_path = default_summary_path(args)
    sessions, selected_summary_path = load_summary_sessions(summary_path)
    index_names = parse_index_names(INDEX_KT)
    prefetch_indexes, prefetch_archives = parse_prefetch_hints(PREFETCH_TABLE_KT, index_names)
    resolutions, category_counts = resolve_sessions(
        sessions,
        index_names=index_names,
        prefetch_indexes=prefetch_indexes,
        prefetch_archives=prefetch_archives,
    )
    status = "ok" if selected_summary_path and sessions else "partial"
    return standard_tool_artifact(
        tool_name="run_946_js5_archive_resolver",
        status=status,
        inputs={
            "js5SessionDir": str(args.js5_session_dir),
            "summaryJson": str(args.summary_json) if args.summary_json else "",
            "inputFingerprint": input_fingerprint(args),
        },
        artifacts=output_artifact_map(args.output_dir, JS5_ARCHIVE_RESOLUTION_JSON, JS5_ARCHIVE_RESOLUTION_MD),
        summary={
            "summaryJsonPresent": bool(selected_summary_path),
            "sessionCount": len(sessions),
            "resolvedArchiveCount": len(resolutions),
            "categoryCounts": category_counts,
        },
        extra={
            "selectedSummaryJson": str(selected_summary_path) if selected_summary_path else "",
            "indexNames": {str(index): name for index, name in sorted(index_names.items())},
            "prefetch": {
                "prefetchIndexes": sorted(prefetch_indexes),
                "prefetchArchives": [
                    {"index": index, "archive": archive}
                    for index, archive in sorted(prefetch_archives)
                ],
            },
            "resolutions": resolutions,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 JS5 Archive Resolution",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Summary JSON present: `{artifact['summary']['summaryJsonPresent']}`",
        f"- Sessions: `{artifact['summary']['sessionCount']}`",
        f"- Resolved archives: `{artifact['summary']['resolvedArchiveCount']}`",
        f"- Category counts: `{artifact['summary']['categoryCounts']}`",
        "",
        "## Resolutions",
        "",
    ]
    resolutions = artifact.get("resolutions", [])
    if not resolutions:
        lines.append("- No structured JS5 archive activity was available to resolve.")
    else:
        for item in resolutions[:30]:
            lines.append(
                f"- `{item['label']}` category=`{item['category']}` requests=`{item['requestCount']}` "
                f"responseHeaders=`{item['responseHeaderCount']}` prefetched=`{item['prefetchedByDefault']}`"
            )
    lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / JS5_ARCHIVE_RESOLUTION_JSON, artifact)
    (output_dir / JS5_ARCHIVE_RESOLUTION_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, JS5_ARCHIVE_RESOLUTION_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / JS5_ARCHIVE_RESOLUTION_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, JS5_ARCHIVE_RESOLUTION_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
