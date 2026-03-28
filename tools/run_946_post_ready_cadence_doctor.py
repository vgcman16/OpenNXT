from __future__ import annotations

import argparse
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
from run_946_loopback_doctor import DEFAULT_SERVER_LOG, select_cluster
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR, list_content_capture_logs


POST_READY_CADENCE_JSON = "post-ready-cadence-doctor.json"
POST_READY_CADENCE_MD = "post-ready-cadence-doctor.md"
POST_READY_CADENCE_CACHE_KEY = "post-ready-cadence-doctor"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Explain what happens after the 946 client accepts the post-bootstrap ready signal, "
            "including how many keepalives and PLAYER_INFO frames are sent before the client loops."
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
        output_dir / POST_READY_CADENCE_JSON,
        output_dir / POST_READY_CADENCE_MD,
    ]


def event_reason(event: dict[str, Any]) -> str:
    return str((event.get("data") or {}).get("reason", ""))


def event_frame(event: dict[str, Any]) -> int | None:
    raw = (event.get("data") or {}).get("frame")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def summarize_attempt(
    world_session: dict[str, Any],
    content_session: dict[str, Any] | None,
    attempt_index: int,
) -> dict[str, Any]:
    events = list(world_session.get("events", []))
    accepted_ready_index = next(
        (index for index, event in enumerate(events) if event.get("kind") == "world-ready-signal"),
        None,
    )
    accepted_ready_event = events[accepted_ready_index] if accepted_ready_index is not None else None
    post_ready_events = events[accepted_ready_index:] if accepted_ready_index is not None else []

    world_sync_events = [event for event in post_ready_events if event.get("kind") == "world-sync-frame"]
    player_info_events = [
        event for event in post_ready_events if event.get("kind") == "world-send-player-info"
    ]
    tick_player_info_events = [
        event for event in player_info_events if event_reason(event) == "tick"
    ]
    keepalive_events = [
        event
        for event in post_ready_events
        if event.get("kind") in {"world-ready-wait-keepalive", "world-hold-keepalive"}
    ]
    send_raw_42_events = [
        event for event in post_ready_events if event.get("kind") == "send-raw" and event.get("opcode") == 42
    ]
    send_raw_131_events = [
        event for event in post_ready_events if event.get("kind") == "send-raw" and event.get("opcode") == 131
    ]
    deferred_tail_event = next(
        (
            event
            for event in post_ready_events
            if event.get("kind") == "world-send-deferred-completion-tail-after-sync"
        ),
        None,
    )

    needs: list[str] = []
    if accepted_ready_event is not None:
        tick_frame_count = len(tick_player_info_events)
        if tick_frame_count <= 1:
            needs.append(
                f"accepted ready at line {accepted_ready_event['lineNumber']}, then only "
                f"{tick_frame_count} tick PLAYER_INFO frame before the attempt ended"
            )
        if len(send_raw_131_events) <= 2:
            needs.append(
                f"accepted ready at line {accepted_ready_event['lineNumber']}, then only "
                f"{len(send_raw_131_events)} NO_TIMEOUT packets before the attempt ended"
            )
        if not content_session or int(content_session.get("archiveRequests", 0) or 0) == 0:
            needs.append(
                "accepted ready never reached a real scene archive request; keep the world channel alive past "
                "reference-table[0]"
            )
        if deferred_tail_event is not None and tick_frame_count <= 1:
            needs.append(
                "accepted ready clears into the deferred completion tail, but the cadence stops after the first "
                "tick follow-up"
            )

    return {
        "attemptIndex": attempt_index,
        "worldSession": session_summary(world_session),
        "acceptedReady": accepted_ready_event is not None,
        "acceptedReadyLine": accepted_ready_event["lineNumber"] if accepted_ready_event else None,
        "acceptedReadyTimestamp": accepted_ready_event["timestamp"] if accepted_ready_event else "",
        "readySource": (accepted_ready_event.get("data") or {}).get("source", "") if accepted_ready_event else "",
        "worldSyncFramesAfterReady": [event_frame(event) for event in world_sync_events if event_frame(event) is not None],
        "playerInfoFramesAfterReady": [
            event_frame(event) for event in player_info_events if event_frame(event) is not None
        ],
        "tickPlayerInfoFramesAfterReady": [
            event_frame(event) for event in tick_player_info_events if event_frame(event) is not None
        ],
        "postReadyKeepaliveKinds": [event["kind"] for event in keepalive_events],
        "sendRaw42CountAfterReady": len(send_raw_42_events),
        "sendRaw131CountAfterReady": len(send_raw_131_events),
        "deferredTailAfterReadyLine": deferred_tail_event["lineNumber"] if deferred_tail_event else None,
        "contentSession": {
            "exists": content_session is not None,
            "firstRequestLabel": (content_session or {}).get("firstRequestLabel", ""),
            "referenceTableRequests": int((content_session or {}).get("referenceTableRequests", 0) or 0),
            "archiveRequests": int((content_session or {}).get("archiveRequests", 0) or 0),
        },
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
    accepted_ready_attempts = [attempt for attempt in attempts if attempt.get("acceptedReady")]
    if not accepted_ready_attempts:
        return {
            "likelyBlocker": "no-accepted-ready-window",
            "recommendation": "The selected cluster never reached an accepted post-bootstrap ready signal window.",
            "needs": ["fresh accepted-ready attempt on the current build"],
        }

    max_tick_player_info_frames = max(
        len(attempt.get("tickPlayerInfoFramesAfterReady", []))
        for attempt in accepted_ready_attempts
    )
    max_no_timeout = max(
        int(attempt.get("sendRaw131CountAfterReady", 0) or 0)
        for attempt in accepted_ready_attempts
    )
    archive_ready_attempts = [
        attempt
        for attempt in accepted_ready_attempts
        if int(((attempt.get("contentSession") or {}).get("archiveRequests", 0) or 0)) > 0
    ]
    latest = accepted_ready_attempts[-1]
    latest_needs = list(latest.get("needs", []))

    if not archive_ready_attempts and max_tick_player_info_frames <= 1 and max_no_timeout <= 2:
        return {
            "likelyBlocker": "post-ready-cadence-too-short",
            "recommendation": (
                "Accepted-ready attempts only sustain a very short post-ready cadence before the client abandons the "
                "world. The server needs to keep NO_TIMEOUT and PLAYER_INFO alive longer after ready acceptance."
            ),
            "needs": latest_needs,
        }

    if not archive_ready_attempts:
        return {
            "likelyBlocker": "post-ready-no-scene-archives",
            "recommendation": (
                "Accepted-ready attempts stay alive longer, but they still never transition into real scene archive "
                "delivery after reference-table[0]."
            ),
            "needs": latest_needs,
        }

    return {
        "likelyBlocker": "post-ready-progress-observed",
        "recommendation": "Accepted-ready attempts progressed into archive delivery; compare the remaining failures against that baseline.",
        "needs": latest_needs,
    }


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact["summary"]
    lines = [
        "# 946 Post-Ready Cadence Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{summary['clusterId']}`",
        f"- Attempts analyzed: `{summary['attemptCount']}`",
        f"- Accepted-ready attempts: `{summary['acceptedReadyAttemptCount']}`",
        f"- Max tick PLAYER_INFO frames after ready: `{summary['maxTickPlayerInfoFramesAfterReady']}`",
        f"- Max NO_TIMEOUT packets after ready: `{summary['maxNoTimeoutPacketsAfterReady']}`",
        f"- Accepted-ready attempts with scene archives: `{summary['acceptedReadyAttemptsWithArchives']}`",
        "",
        "## Verdict",
        "",
        f"- Likely blocker: `{summary['likelyBlocker']}`",
        f"- Recommendation: {summary['recommendation']}",
    ]
    needs = list(summary.get("needs", []))
    if needs:
        lines.extend(["", "## Exact Needs", ""])
        lines.extend(f"- {need}" for need in needs)

    lines.extend(["", "## Attempts", ""])
    for attempt in artifact["attempts"]:
        content = attempt["contentSession"]
        lines.extend(
            [
                f"### Attempt {attempt['attemptIndex']}",
                "",
                f"- Accepted ready: `{attempt['acceptedReady']}`",
                f"- Accepted ready line: `{attempt['acceptedReadyLine']}`",
                f"- Ready source: `{attempt['readySource']}`",
                f"- World sync frames after ready: `{attempt['worldSyncFramesAfterReady']}`",
                f"- Tick PLAYER_INFO frames after ready: `{attempt['tickPlayerInfoFramesAfterReady']}`",
                f"- NO_TIMEOUT packets after ready: `{attempt['sendRaw131CountAfterReady']}`",
                f"- PLAYER_INFO packets after ready: `{attempt['sendRaw42CountAfterReady']}`",
                f"- Deferred tail after ready line: `{attempt['deferredTailAfterReadyLine']}`",
                f"- Content label: `{content['firstRequestLabel']}` refTables=`{content['referenceTableRequests']}` "
                f"archives=`{content['archiveRequests']}`",
            ]
        )
        if attempt["needs"]:
            lines.append("- Needs:")
            lines.extend(f"  - {need}" for need in attempt["needs"])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    cluster_id, _cluster_start, content_sessions, world_sessions = select_cluster(
        args.content_capture_dir,
        args.world_log,
        args.attempt_limit,
        args.cluster_id,
    )
    attempts = build_attempts(world_sessions, content_sessions)
    summary_details = verdict(attempts)
    accepted_ready_attempts = [attempt for attempt in attempts if attempt.get("acceptedReady")]
    status = "ok" if attempts else "partial"
    return standard_tool_artifact(
        tool_name="run_946_post_ready_cadence_doctor",
        status=status,
        inputs={
            "worldLog": str(args.world_log),
            "serverLog": str(args.server_log),
            "contentCaptureDir": str(args.content_capture_dir),
            "clusterId": args.cluster_id or "",
            "attemptLimit": args.attempt_limit,
            "inputFingerprint": input_fingerprint(args),
        },
        artifacts={
            "postReadyCadenceDoctorJson": str(args.output_dir / POST_READY_CADENCE_JSON),
            "postReadyCadenceDoctorMarkdown": str(args.output_dir / POST_READY_CADENCE_MD),
        },
        summary={
            "clusterId": cluster_id,
            "attemptCount": len(attempts),
            "acceptedReadyAttemptCount": len(accepted_ready_attempts),
            "maxTickPlayerInfoFramesAfterReady": max(
                (len(attempt.get("tickPlayerInfoFramesAfterReady", [])) for attempt in accepted_ready_attempts),
                default=0,
            ),
            "maxNoTimeoutPacketsAfterReady": max(
                (int(attempt.get("sendRaw131CountAfterReady", 0) or 0) for attempt in accepted_ready_attempts),
                default=0,
            ),
            "acceptedReadyAttemptsWithArchives": sum(
                1
                for attempt in accepted_ready_attempts
                if int(((attempt.get("contentSession") or {}).get("archiveRequests", 0) or 0)) > 0
            ),
            "likelyBlocker": summary_details["likelyBlocker"],
            "recommendation": summary_details["recommendation"],
            "needs": list(summary_details.get("needs", [])),
        },
        extra={
            "attempts": attempts,
        },
    )


def input_fingerprint(args: argparse.Namespace) -> str:
    content_paths = list_content_capture_logs(args.content_capture_dir)
    return artifact_input_fingerprint(
        "run_946_post_ready_cadence_doctor",
        [args.world_log, args.server_log, *content_paths],
        clusterId=args.cluster_id or "",
        attemptLimit=args.attempt_limit,
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / POST_READY_CADENCE_JSON, artifact)
    (output_dir / POST_READY_CADENCE_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, POST_READY_CADENCE_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / POST_READY_CADENCE_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0
    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, POST_READY_CADENCE_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
