from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from statistics import median
from types import SimpleNamespace
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
from protocol_946_debug_common import WORLD_LOG_DEFAULT, build_session, load_all_sessions, session_summary
from run_946_curated_compare import DEFAULT_LABELS_PATH, load_labels, label_entry_for_window, session_window
from run_946_scene_delivery_aid import (
    DEFAULT_CLIENTERROR_DIR,
    DEFAULT_CONTENT_CAPTURE_DIR,
    DEFAULT_JS5_SESSION_DIR,
    DEFAULT_RUNTIME_TRACE_DIR,
    DEFAULT_CHECKSUM_COMPARE_JSON,
    DEFAULT_PREFETCH_COMPARE_JSON,
    build_artifact as build_scene_delivery_artifact,
)


PLATEAU_DIFF_JSON = "plateau-diff.json"
PLATEAU_DIFF_MD = "plateau-diff.md"
PLATEAU_DIFF_CACHE_KEY = "plateau-diff"
TRACKED_CLIENT_OPCODES = (17, 28, 48, 50, 82, 83, 95, 106, 113)
TRACKED_SERVER_OPCODES = (39, 42, 45, 50, 67, 106, 116, 131)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two long-lived 946 post-interfaces plateau sessions for black-screen divergence."
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--left-window")
    parser.add_argument("--right-window")
    parser.add_argument("--labels", type=Path, default=DEFAULT_LABELS_PATH)
    parser.add_argument("--js5-session-dir", type=Path, default=DEFAULT_JS5_SESSION_DIR)
    parser.add_argument("--runtime-trace-dir", type=Path, default=DEFAULT_RUNTIME_TRACE_DIR)
    parser.add_argument("--clienterror-dir", type=Path, default=DEFAULT_CLIENTERROR_DIR)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / PLATEAU_DIFF_JSON,
        output_dir / PLATEAU_DIFF_MD,
    ]


def plateau_session(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return None
    events = session.get("events", [])
    start_index = None
    for index, event in enumerate(events):
        if event.get("kind") == "world-stage" and event.get("stage") == "interfaces":
            start_index = index
            break
    if start_index is None:
        return session
    return build_session(events[start_index:])


def choose_default_windows_from_sessions(sessions: list[dict[str, Any]], labels_path: Path) -> tuple[str | None, str | None]:
    if not sessions:
        return None, None
    labels = load_labels(labels_path).get("entries", {})
    seed_window = None
    stable_window = None
    for session in sessions:
        window = session_window(session)
        label = label_entry_for_window(labels, window)
        if not label:
            continue
        if label.get("role") == "seed":
            seed_window = window
        if label.get("normalizedOutcome") == "stable_interfaces" and stable_window is None:
            stable_window = window
    left_window = seed_window or stable_window or session_window(sessions[0])
    right_window = session_window(sessions[-1])
    return left_window, right_window


def load_selected_sessions(args: argparse.Namespace) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, str | None]:
    sessions = load_all_sessions(args.world_log)
    left_window = args.left_window
    right_window = args.right_window
    if not left_window or not right_window:
        default_left, default_right = choose_default_windows_from_sessions(sessions, args.labels)
        left_window = left_window or default_left
        right_window = right_window or default_right
    if not left_window or not right_window:
        return None, None, left_window, right_window
    session_index = {session_window(session): session for session in sessions}
    left_session = session_index.get(left_window)
    right_session = session_index.get(right_window)
    if right_session is None and sessions:
        right_session = sessions[-1]
        right_window = session_window(right_session)
    return left_session, right_session, left_window, right_window


def tracked_opcode_counts(session: dict[str, Any] | None, *, kind: str, tracked: tuple[int, ...]) -> dict[str, int]:
    counts = Counter()
    if not session:
        return {str(opcode): 0 for opcode in tracked}
    for event in session.get("events", []):
        if event.get("kind") != kind:
            continue
        opcode = event.get("opcode")
        if isinstance(opcode, int) and opcode in tracked:
            counts[str(opcode)] += 1
    return {str(opcode): counts.get(str(opcode), 0) for opcode in tracked}


def marker_counts(session: dict[str, Any] | None) -> dict[str, int]:
    counts = Counter()
    if not session:
        return {}
    for event in session.get("events", []):
        kind = event.get("kind")
        if isinstance(kind, str) and kind.startswith("world-"):
            counts[kind] += 1
    return dict(sorted(counts.items()))


def scene_snapshot(args: argparse.Namespace, window: str | None) -> dict[str, Any]:
    if not window:
        return {}
    return build_scene_delivery_artifact(
        SimpleNamespace(
            world_log=args.world_log,
            world_window=window,
            content_capture_dir=getattr(args, "content_capture_dir", DEFAULT_CONTENT_CAPTURE_DIR),
            js5_session_dir=args.js5_session_dir,
            runtime_trace_dir=args.runtime_trace_dir,
            clienterror_dir=args.clienterror_dir,
            checksum_report_json=DEFAULT_CHECKSUM_COMPARE_JSON,
            prefetch_report_json=DEFAULT_PREFETCH_COMPARE_JSON,
            output_dir=args.output_dir,
        )
    )


def delta_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, dict[str, int]]:
    left_counter = Counter(left)
    right_counter = Counter(right)
    return {
        "missingInRight": dict(sorted((left_counter - right_counter).items())),
        "extraInRight": dict(sorted((right_counter - left_counter).items())),
    }


def summarize_session(session: dict[str, Any] | None) -> dict[str, Any]:
    summary = session_summary(session)
    return {
        **summary,
        "trackedClientOpcodes": tracked_opcode_counts(session, kind="recv-raw", tracked=TRACKED_CLIENT_OPCODES),
        "trackedServerOpcodes": tracked_opcode_counts(session, kind="send-raw", tracked=TRACKED_SERVER_OPCODES),
        "markerCounts": marker_counts(session),
    }


def median_count(values: list[int]) -> int | None:
    return int(median(values)) if values else None


def build_hypotheses(left_scene: dict[str, Any], right_scene: dict[str, Any], left_summary: dict[str, Any], right_summary: dict[str, Any]) -> list[dict[str, Any]]:
    left_state = ((left_scene.get("summary") or {}).get("sceneDeliveryState")) or "unknown"
    right_state = ((right_scene.get("summary") or {}).get("sceneDeliveryState")) or "unknown"
    left_archives = int(((left_scene.get("summary") or {}).get("archiveRequestsObserved")) or 0)
    right_archives = int(((right_scene.get("summary") or {}).get("archiveRequestsObserved")) or 0)
    left_ready = left_summary.get("markerCounts", {}).get("world-ready-signal", 0) > 0
    right_ready = right_summary.get("markerCounts", {}).get("world-ready-signal", 0) > 0
    left_runtime = (((left_scene.get("runtimeTrace") or {}).get("summary")) or {})
    right_runtime = (((right_scene.get("runtimeTrace") or {}).get("summary")) or {})

    asset_score = 20
    asset_reason = "No strong JS5 asset-delivery divergence was observed."
    if left_archives > 0 and right_archives == 0:
        asset_score = 90
        asset_reason = "Left plateau observed real archive delivery while the right plateau never progressed past non-archive JS5 traffic."
    elif right_state in {"capture-missing", "client-never-opened-js5", "reference-tables-only"}:
        asset_score = 75
        asset_reason = f"Right plateau remained in `{right_state}`, which still points at asset-delivery or capture timing."

    settle_score = 25
    settle_reason = "Runtime traces do not show a strong post-asset settle difference yet."
    if right_state in {"archive-delivery-observed", "archive-delivery-observed-but-runtime-stalled"}:
        settle_score = 80
        settle_reason = "Archive delivery overlapped the right plateau, so the remaining lead is scene settle or render state after assets arrive."
    elif (right_runtime.get("timeoutCount") or 0) > (left_runtime.get("timeoutCount") or 0):
        settle_score = 60
        settle_reason = "The right runtime trace timed out more often after interfaces, suggesting the client stayed alive while scene settle stalled."

    divergence_score = 30
    divergence_reason = "Marker and opcode deltas are small."
    if left_ready != right_ready:
        divergence_score = 85
        divergence_reason = "The sessions disagree on the post-bootstrap ready signal, which points at a state divergence after interfaces."
    elif left_summary.get("eventCount", 0) != right_summary.get("eventCount", 0):
        divergence_score = 55
        divergence_reason = "The plateau event counts diverge materially even though both sessions reached interfaces."

    hypotheses = [
        {"kind": "asset-delivery stall", "score": asset_score, "reason": asset_reason},
        {"kind": "scene settle stall", "score": settle_score, "reason": settle_reason},
        {"kind": "post-bootstrap state divergence", "score": divergence_score, "reason": divergence_reason},
    ]
    return sorted(hypotheses, key=lambda item: (-item["score"], item["kind"]))


def input_fingerprint(args: argparse.Namespace) -> str:
    left_window = args.left_window or ""
    right_window = args.right_window or ""
    if not left_window or not right_window:
        default_left, default_right = choose_default_windows_from_sessions(load_all_sessions(args.world_log), args.labels)
        left_window = left_window or (default_left or "")
        right_window = right_window or (default_right or "")
    return artifact_input_fingerprint(
        "run_946_plateau_diff",
        [
            WORKSPACE / "tools" / "run_946_plateau_diff.py",
            WORKSPACE / "tools" / "run_946_scene_delivery_aid.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            WORKSPACE / "tools" / "protocol_946_debug_common.py",
            WORKSPACE / "tools" / "run_946_curated_compare.py",
            args.world_log,
            args.labels,
        ],
        leftWindow=left_window,
        rightWindow=right_window,
        js5SessionDir=str(args.js5_session_dir),
        runtimeTraceDir=str(args.runtime_trace_dir),
    )


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    left_session, right_session, left_window, right_window = load_selected_sessions(args)
    left_plateau = plateau_session(left_session)
    right_plateau = plateau_session(right_session)
    left_summary = summarize_session(left_plateau)
    right_summary = summarize_session(right_plateau)
    left_scene = scene_snapshot(args, left_window)
    right_scene = scene_snapshot(args, right_window)
    hypotheses = build_hypotheses(left_scene, right_scene, left_summary, right_summary)
    status = "ok" if left_session and right_session else "blocked"
    return standard_tool_artifact(
        tool_name="run_946_plateau_diff",
        status=status,
        inputs={
            "worldLog": str(args.world_log),
            "leftWindow": left_window or "",
            "rightWindow": right_window or "",
            "labels": str(args.labels),
            "js5SessionDir": str(args.js5_session_dir),
            "runtimeTraceDir": str(args.runtime_trace_dir),
            "inputFingerprint": input_fingerprint(args),
        },
        artifacts=output_artifact_map(args.output_dir, PLATEAU_DIFF_JSON, PLATEAU_DIFF_MD),
        summary={
            "leftWindow": left_window or "",
            "rightWindow": right_window or "",
            "leftSceneState": (left_scene.get("summary") or {}).get("sceneDeliveryState"),
            "rightSceneState": (right_scene.get("summary") or {}).get("sceneDeliveryState"),
            "leftEventCount": left_summary.get("eventCount", 0),
            "rightEventCount": right_summary.get("eventCount", 0),
            "topHypothesis": hypotheses[0]["kind"] if hypotheses else None,
        },
        extra={
            "left": {
                "plateauSummary": left_summary,
                "sceneDelivery": left_scene,
            },
            "right": {
                "plateauSummary": right_summary,
                "sceneDelivery": right_scene,
            },
            "deltas": {
                "clientOpcodes": delta_counts(
                    left_summary.get("trackedClientOpcodes", {}),
                    right_summary.get("trackedClientOpcodes", {}),
                ),
                "serverOpcodes": delta_counts(
                    left_summary.get("trackedServerOpcodes", {}),
                    right_summary.get("trackedServerOpcodes", {}),
                ),
                "markers": delta_counts(
                    left_summary.get("markerCounts", {}),
                    right_summary.get("markerCounts", {}),
                ),
            },
            "hypotheses": hypotheses,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    hypotheses = artifact.get("hypotheses", [])
    lines = [
        "# 946 Plateau Diff",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Left window: `{artifact['summary']['leftWindow']}`",
        f"- Right window: `{artifact['summary']['rightWindow']}`",
        f"- Left scene state: `{artifact['summary']['leftSceneState']}`",
        f"- Right scene state: `{artifact['summary']['rightSceneState']}`",
        f"- Top hypothesis: `{artifact['summary']['topHypothesis']}`",
        "",
        "## Hypotheses",
        "",
    ]
    if not hypotheses:
        lines.append("- No hypotheses available.")
    else:
        for hypothesis in hypotheses:
            lines.append(f"- `{hypothesis['kind']}` score=`{hypothesis['score']}` {hypothesis['reason']}")
    lines.extend(["", "## Client Opcode Delta", ""])
    client_delta = ((artifact.get("deltas") or {}).get("clientOpcodes")) or {}
    if not client_delta:
        lines.append("- No client opcode delta available.")
    else:
        lines.append(f"- Missing in right: `{client_delta.get('missingInRight', {})}`")
        lines.append(f"- Extra in right: `{client_delta.get('extraInRight', {})}`")
    lines.extend(["", "## Server Opcode Delta", ""])
    server_delta = ((artifact.get("deltas") or {}).get("serverOpcodes")) or {}
    if not server_delta:
        lines.append("- No server opcode delta available.")
    else:
        lines.append(f"- Missing in right: `{server_delta.get('missingInRight', {})}`")
        lines.append(f"- Extra in right: `{server_delta.get('extraInRight', {})}`")
    lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / PLATEAU_DIFF_JSON, artifact)
    (output_dir / PLATEAU_DIFF_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, PLATEAU_DIFF_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / PLATEAU_DIFF_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0 if artifact.get("status") != "blocked" else 1

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, PLATEAU_DIFF_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0 if artifact["status"] != "blocked" else 1


if __name__ == "__main__":
    raise SystemExit(main())
