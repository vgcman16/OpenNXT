from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from protocol_automation_common import (
    SHARED_DIR,
    artifact_input_fingerprint,
    cache_hit,
    ensure_directory,
    load_json,
    record_cache_entry,
    stable_json_text,
    standard_tool_artifact,
    write_json,
)
from protocol_946_debug_common import WORLD_LOG_DEFAULT, session_summary
from run_946_loopback_doctor import select_cluster
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR


DISCONNECT_PIVOT_JSON = "disconnect-pivot-doctor.json"
DISCONNECT_PIVOT_MD = "disconnect-pivot-doctor.md"
DISCONNECT_PIVOT_CACHE_KEY = "disconnect-pivot-doctor"
DEFAULT_SERVER_LOG = Path("tmp-manual-js5.err.log")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose the exact packet family dominating the final post-ready window before the "
            "946 client disconnects from the world."
        )
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--content-capture-dir", type=Path, default=DEFAULT_CONTENT_CAPTURE_DIR)
    parser.add_argument("--server-log", type=Path, default=DEFAULT_SERVER_LOG)
    parser.add_argument("--cluster-id")
    parser.add_argument("--attempt-limit", type=int, default=12)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / DISCONNECT_PIVOT_JSON,
        output_dir / DISCONNECT_PIVOT_MD,
    ]


def input_fingerprint(args: argparse.Namespace) -> str:
    return artifact_input_fingerprint(
        "run_946_disconnect_pivot_doctor",
        [
            Path(__file__),
            Path(__file__).with_name("protocol_automation_common.py"),
            Path(__file__).with_name("protocol_946_debug_common.py"),
            Path(__file__).with_name("run_946_loopback_doctor.py"),
            args.world_log,
            args.server_log,
        ],
        clusterId=args.cluster_id or "",
        attemptLimit=args.attempt_limit,
    )


def summarize_attempt(
    world_session: dict[str, Any],
    content_session: dict[str, Any] | None,
    attempt_index: int,
) -> dict[str, Any]:
    events = list(world_session.get("events", []))
    disconnect_index = next(
        (index for index, event in enumerate(events) if event.get("kind") == "world-channel-inactive"),
        None,
    )
    if disconnect_index is None:
        disconnect_index = len(events) - 1
    tail_start_index = next(
        (
            index
            for index, event in enumerate(events)
            if event.get("kind") == "world-send-deferred-completion-tail-after-sync"
        ),
        None,
    )
    if tail_start_index is None:
        tail_start_index = max(0, disconnect_index - 80)

    pivot_events = events[tail_start_index : disconnect_index + 1]
    server_send_raw = [event for event in pivot_events if event.get("kind") == "send-raw"]
    opcode_counts = Counter(
        event.get("opcode") for event in server_send_raw if isinstance(event.get("opcode"), int)
    )
    marker_counts = Counter(
        event.get("kind")
        for event in pivot_events
        if isinstance(event.get("kind"), str) and event.get("kind", "").startswith("world-")
    )
    dominant_opcode = None
    dominant_count = 0
    if opcode_counts:
        dominant_opcode, dominant_count = opcode_counts.most_common(1)[0]

    content_summary = {
        "exists": content_session is not None,
        "firstRequestLabel": (content_session or {}).get("firstRequestLabel", ""),
        "referenceTableRequests": int((content_session or {}).get("referenceTableRequests", 0) or 0),
        "archiveRequests": int((content_session or {}).get("archiveRequests", 0) or 0),
    }

    likely_pivot = "post-ready-unclassified"
    needs: list[str] = []
    if dominant_opcode == 59 and dominant_count >= 40:
        likely_pivot = "if-setevents-burst-before-disconnect"
        needs.append(
            f"trim or defer the post-ready IF_SETEVENTS burst; opcode 59 appears {dominant_count} times "
            "in the disconnect window"
        )
    if marker_counts.get("world-send-deferred-completion-event-delta", 0) > 0:
        needs.append("keep deferred completion event-delta out of the first post-ready disconnect window")
    if content_summary["referenceTableRequests"] > 0 and content_summary["archiveRequests"] == 0:
        needs.append("first non-reference /ms archive request after reference-table[0]")
    if marker_counts.get("world-send-player-info", 0) <= 3:
        needs.append("keep the world channel alive longer after the first post-ready PLAYER_INFO frames")

    return {
        "attemptIndex": attempt_index,
        "worldSession": session_summary(world_session),
        "disconnectLine": pivot_events[-1]["lineNumber"] if pivot_events else None,
        "pivotStartLine": pivot_events[0]["lineNumber"] if pivot_events else None,
        "pivotEventCount": len(pivot_events),
        "dominantServerOpcode": dominant_opcode,
        "dominantServerOpcodeCount": dominant_count,
        "serverOpcodeCountsInPivot": dict(sorted(opcode_counts.items())),
        "markerCountsInPivot": dict(sorted(marker_counts.items())),
        "likelyPivot": likely_pivot,
        "contentSession": content_summary,
        "needs": list(dict.fromkeys(needs)),
    }


def build_attempts(
    world_sessions: list[dict[str, Any]],
    content_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    pair_count = min(len(world_sessions), len(content_sessions))
    paired_content_sessions = content_sessions[-pair_count:] if pair_count else []
    content_lookup_offset = len(world_sessions) - pair_count

    for world_index, world_session in enumerate(world_sessions):
        content_session = None
        if world_index >= content_lookup_offset and paired_content_sessions:
            content_session = paired_content_sessions[world_index - content_lookup_offset]
        attempts.append(summarize_attempt(world_session, content_session, world_index + 1))
    return attempts


def verdict(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if not attempts:
        return {
            "likelyBlocker": "no-attempts",
            "recommendation": "No matching world attempts were available for disconnect-pivot analysis.",
            "needs": ["fresh world attempt with world-bootstrap and content capture"],
        }

    burst_attempts = [
        attempt
        for attempt in attempts
        if attempt.get("likelyPivot") == "if-setevents-burst-before-disconnect"
    ]
    latest = attempts[-1]
    latest_needs = list(latest.get("needs", []))
    if burst_attempts:
        return {
            "likelyBlocker": "post-ready-if-setevents-burst",
            "recommendation": (
                "The final post-ready window is dominated by opcode 59 IF_SETEVENTS traffic, followed by "
                "disconnects before any real scene archive request arrives."
            ),
            "needs": latest_needs,
        }
    return {
        "likelyBlocker": "post-ready-disconnect-unclassified",
        "recommendation": "The client still disconnects after ready acceptance, but no single dominant server opcode was isolated.",
        "needs": latest_needs,
    }


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact["summary"]
    lines = [
        "# 946 Disconnect Pivot Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{summary['clusterId']}`",
        f"- Attempts analyzed: `{summary['attemptCount']}`",
        f"- Attempts with IF_SETEVENTS pivot: `{summary['ifSeteventsBurstAttemptCount']}`",
        f"- Latest dominant opcode: `{summary['latestDominantServerOpcode']}`",
        f"- Latest dominant opcode count: `{summary['latestDominantServerOpcodeCount']}`",
        "",
        "## Verdict",
        "",
        f"- Likely blocker: `{artifact['verdict']['likelyBlocker']}`",
        f"- Recommendation: {artifact['verdict']['recommendation']}",
        "",
        "## Exact Needs",
        "",
    ]
    for need in artifact["verdict"].get("needs", []):
        lines.append(f"- {need}")

    lines.extend(["", "## Attempts", ""])
    for attempt in artifact["attempts"]:
        lines.extend(
            [
                f"### Attempt {attempt['attemptIndex']}",
                "",
                f"- Likely pivot: `{attempt['likelyPivot']}`",
                f"- World window: `{attempt['worldSession'].get('window', '')}`",
                f"- Pivot lines: `{attempt['pivotStartLine']}:{attempt['disconnectLine']}`",
                f"- Dominant opcode: `{attempt['dominantServerOpcode']}` x `{attempt['dominantServerOpcodeCount']}`",
                f"- Content first request: `{(attempt['contentSession'] or {}).get('firstRequestLabel', '')}`",
                f"- Archive requests: `{(attempt['contentSession'] or {}).get('archiveRequests', 0)}`",
                f"- Opcode counts: `{attempt['serverOpcodeCountsInPivot']}`",
                f"- Marker counts: `{attempt['markerCountsInPivot']}`",
            ]
        )
        for need in attempt.get("needs", []):
            lines.append(f"- Needs: {need}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    cluster_id, _, content_sessions, world_sessions = select_cluster(
        args.content_capture_dir,
        args.world_log,
        args.attempt_limit,
        args.cluster_id,
    )
    attempts = build_attempts(world_sessions, content_sessions)
    final_verdict = verdict(attempts)
    latest = attempts[-1] if attempts else {}
    summary = {
        "clusterId": cluster_id,
        "attemptCount": len(attempts),
        "ifSeteventsBurstAttemptCount": sum(
            1 for attempt in attempts if attempt.get("likelyPivot") == "if-setevents-burst-before-disconnect"
        ),
        "latestDominantServerOpcode": latest.get("dominantServerOpcode"),
        "latestDominantServerOpcodeCount": latest.get("dominantServerOpcodeCount", 0),
    }
    return {
        "status": "ok",
        "summary": summary,
        "verdict": final_verdict,
        "attempts": attempts,
    }


def main() -> None:
    args = parse_args()
    ensure_directory(args.output_dir)
    json_path, md_path = output_paths(args.output_dir)
    outputs = [json_path, md_path]
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, DISCONNECT_PIVOT_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(json_path, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return

    artifact = analyze(args)
    markdown = render_markdown(artifact)
    write_json(json_path, artifact)
    md_path.write_text(markdown, encoding="utf-8")
    record_cache_entry(cache_manifest, DISCONNECT_PIVOT_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(
        stable_json_text(
            {
                "status": artifact["status"],
                "artifacts": {DISCONNECT_PIVOT_CACHE_KEY: str(md_path)},
            }
        ),
        end="",
    )


if __name__ == "__main__":
    main()
