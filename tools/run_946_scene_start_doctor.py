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
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR


SCENE_START_JSON = "scene-start-doctor.json"
SCENE_START_MD = "scene-start-doctor.md"
SCENE_START_CACHE_KEY = "scene-start-doctor"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Explain the accepted-ready 946 plateau: whether rebuild/region advertisement happened "
            "before the client's first 50/82/50 burst, whether the loading overlay was closed, and "
            "whether content ever advanced past reference-table[0]."
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
        output_dir / SCENE_START_JSON,
        output_dir / SCENE_START_MD,
    ]


def input_fingerprint(args: argparse.Namespace) -> str:
    return artifact_input_fingerprint(
        "run_946_scene_start_doctor",
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


def first_event(session: dict[str, Any], kind: str) -> dict[str, Any] | None:
    return next((event for event in session.get("events", []) if event.get("kind") == kind), None)


def world_control_events(session: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        event
        for event in session.get("events", [])
        if event.get("kind") == "world-client-bootstrap-control" and isinstance(event.get("opcode"), int)
    ]


def raw_client_signal_events(session: dict[str, Any], ready_line: int | None) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for event in session.get("events", []):
        line_number = int(event.get("lineNumber", 0) or 0)
        if ready_line is not None and line_number <= ready_line:
            continue
        if event.get("kind") not in {"recv-raw", "world-ignore-client-compat"}:
            continue
        opcode = event.get("opcode")
        if opcode not in {17, 83}:
            continue
        signals.append(
            {
                "kind": event.get("kind", ""),
                "opcode": opcode,
                "lineNumber": line_number,
                "bytes": event.get("bytes"),
                "preview": event.get("preview", ""),
            }
        )
    return signals


def event_snapshot(event: dict[str, Any] | None) -> dict[str, Any]:
    if not event:
        return {
            "present": False,
            "lineNumber": None,
            "timestamp": "",
            "kind": "",
            "data": {},
        }
    return {
        "present": True,
        "lineNumber": event.get("lineNumber"),
        "timestamp": event.get("timestamp", ""),
        "kind": event.get("kind", ""),
        "data": event.get("data", {}),
    }


def summarize_attempt(
    world_session: dict[str, Any],
    content_session: dict[str, Any] | None,
    attempt_index: int,
) -> dict[str, Any]:
    rebuild = first_event(world_session, "world-send-rebuild-tail")
    ready = first_event(world_session, "world-ready-signal")
    ready_latched = first_event(world_session, "world-ready-signal-latched")
    overlay_close = first_event(world_session, "world-close-loading-overlay")
    initial_sync = next(
        (
            event
            for event in world_session.get("events", [])
            if event.get("kind") == "world-send-player-info" and event.get("data", {}).get("reason") == "initial"
        ),
        None,
    )
    initial_followup = next(
        (
            event
            for event in world_session.get("events", [])
            if event.get("kind") == "world-send-player-info" and event.get("data", {}).get("reason") == "initial-followup"
        ),
        None,
    )
    deferred_tail = first_event(world_session, "world-send-deferred-completion-tail-after-sync")
    controls = world_control_events(world_session)
    ready_line = ready.get("lineNumber") if ready else None
    first_control_line = min((event.get("lineNumber") for event in controls if event.get("lineNumber")), default=None)
    rebuild_before_controls = bool(
        rebuild and first_control_line is not None and int(rebuild.get("lineNumber", 0) or 0) < int(first_control_line)
    )
    rebuild_before_ready = bool(
        rebuild and ready and int(rebuild.get("lineNumber", 0) or 0) < int(ready.get("lineNumber", 0) or 0)
    )
    post_ready_signals = raw_client_signal_events(world_session, ready_line)
    content_summary = {
        "exists": content_session is not None,
        "firstRequestLabel": (content_session or {}).get("firstRequestLabel", ""),
        "requestCount": int((content_session or {}).get("requestCount", 0) or 0),
        "referenceTableRequests": int((content_session or {}).get("referenceTableRequests", 0) or 0),
        "archiveRequests": int((content_session or {}).get("archiveRequests", 0) or 0),
        "responseHeaderCount": int((content_session or {}).get("responseHeaderCount", 0) or 0),
        "responseBytes": int((content_session or {}).get("responseBytes", 0) or 0),
    }

    needs: list[str] = []
    if first_control_line is not None and not rebuild_before_controls:
        needs.append("send region/build advertisement before the first client 50/82/50 bootstrap burst")
    if ready and not overlay_close:
        needs.append("explicit loading-overlay close on the accepted-ready minimal branch")
    if content_summary["referenceTableRequests"] > 0 and content_summary["archiveRequests"] <= 0:
        needs.append("first non-reference /ms archive request after reference-table[0]")
    if ready and not post_ready_signals:
        needs.append("post-ready client 17/83 signal capture to confirm the plateau stays alive after world sync")

    likely_blocker = "scene-start-unclassified"
    if ready and rebuild_before_controls and content_summary["referenceTableRequests"] > 0 and content_summary["archiveRequests"] <= 0:
        likely_blocker = "accepted-ready-no-scene-archives"
    elif ready and not overlay_close:
        likely_blocker = "accepted-ready-overlay-not-closed"
    elif ready and not rebuild_before_controls:
        likely_blocker = "region-advertised-too-late"

    return {
        "attemptIndex": attempt_index,
        "worldSession": session_summary(world_session),
        "rebuild": event_snapshot(rebuild),
        "readyLatched": event_snapshot(ready_latched),
        "readyAccepted": event_snapshot(ready),
        "closeLoadingOverlay": event_snapshot(overlay_close),
        "initialWorldSync": event_snapshot(initial_sync),
        "initialFollowupWorldSync": event_snapshot(initial_followup),
        "deferredCompletionTailAfterSync": event_snapshot(deferred_tail),
        "controlBursts": [
            {
                "lineNumber": event.get("lineNumber"),
                "opcode": event.get("opcode"),
                "value": event.get("data", {}).get("value", ""),
                "timestamp": event.get("timestamp", ""),
            }
            for event in controls[:8]
        ],
        "rebuildBeforeReadyAccepted": rebuild_before_ready,
        "rebuildBeforeBootstrapControls": rebuild_before_controls,
        "postReadyClientSignals": post_ready_signals[:12],
        "contentSession": content_summary,
        "likelyBlocker": likely_blocker,
        "needs": list(dict.fromkeys(needs)),
    }


def build_attempts(world_sessions: list[dict[str, Any]], content_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
            "recommendation": "No matching post-login world attempts were available for scene-start analysis.",
            "needs": ["fresh accepted-ready world attempt with content capture"],
        }

    latest = attempts[-1]
    latest_needs = list(latest.get("needs", []))
    likely = latest.get("likelyBlocker")
    if likely == "accepted-ready-no-scene-archives":
        recommendation = (
            "The server advertises rebuild/region before the first 50/82/50 burst, the client accepts ready, "
            "and the plateau stays alive, but content never advances past reference-table[0]."
        )
    elif likely == "accepted-ready-overlay-not-closed":
        recommendation = (
            "The accepted-ready minimal branch never emits the loading-overlay close marker, so the client may be "
            "stuck waiting behind a branch-specific loading handoff even though ready was accepted."
        )
    elif likely == "region-advertised-too-late":
        recommendation = (
            "Client bootstrap controls start before the server has clearly advertised the rebuild/region payload, "
            "so the scene start may still be racing the world handoff."
        )
    else:
        recommendation = "The accepted-ready plateau still needs a cleaner scene-start correlation before the next code patch."
    return {
        "likelyBlocker": likely,
        "recommendation": recommendation,
        "needs": latest_needs,
    }


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact["summary"]
    lines = [
        "# 946 Scene Start Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{summary['clusterId']}`",
        f"- Attempts analyzed: `{summary['attemptCount']}`",
        f"- Latest likely blocker: `{artifact['verdict']['likelyBlocker']}`",
        f"- Latest rebuild before first 50/82/50 burst: `{summary['latestRebuildBeforeBootstrapControls']}`",
        f"- Latest close-loading-overlay present: `{summary['latestHasCloseLoadingOverlay']}`",
        f"- Latest content first request: `{summary['latestContentFirstRequestLabel']}`",
        f"- Latest archive requests: `{summary['latestArchiveRequests']}`",
        "",
        "## Verdict",
        "",
        f"- Recommendation: {artifact['verdict']['recommendation']}",
        "",
        "## Exact Needs",
        "",
    ]
    for need in artifact["verdict"].get("needs", []):
        lines.append(f"- {need}")

    lines.extend(["", "## Attempts", ""])
    for attempt in artifact["attempts"]:
        rebuild = attempt["rebuild"]
        ready = attempt["readyAccepted"]
        overlay = attempt["closeLoadingOverlay"]
        lines.extend(
            [
                f"### Attempt {attempt['attemptIndex']}",
                "",
                f"- Likely blocker: `{attempt['likelyBlocker']}`",
                f"- World window: `{attempt['worldSession'].get('startLine')}:{attempt['worldSession'].get('endLine')}`",
                f"- Rebuild line: `{rebuild['lineNumber']}`",
                f"- Ready line: `{ready['lineNumber']}`",
                f"- Close loading overlay line: `{overlay['lineNumber']}`",
                f"- Rebuild before ready: `{attempt['rebuildBeforeReadyAccepted']}`",
                f"- Rebuild before bootstrap controls: `{attempt['rebuildBeforeBootstrapControls']}`",
                f"- Control burst: `{attempt['controlBursts']}`",
                f"- Post-ready client signals: `{attempt['postReadyClientSignals']}`",
                f"- Content first request: `{attempt['contentSession']['firstRequestLabel']}`",
                f"- Reference table requests: `{attempt['contentSession']['referenceTableRequests']}`",
                f"- Archive requests: `{attempt['contentSession']['archiveRequests']}`",
                f"- Content response bytes: `{attempt['contentSession']['responseBytes']}`",
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
        "attemptsWithReadyAccepted": sum(1 for attempt in attempts if attempt["readyAccepted"]["present"]),
        "attemptsWithRebuildBeforeBootstrapControls": sum(1 for attempt in attempts if attempt["rebuildBeforeBootstrapControls"]),
        "attemptsWithCloseLoadingOverlay": sum(1 for attempt in attempts if attempt["closeLoadingOverlay"]["present"]),
        "latestRebuildBeforeBootstrapControls": bool(latest.get("rebuildBeforeBootstrapControls")),
        "latestHasCloseLoadingOverlay": bool((latest.get("closeLoadingOverlay") or {}).get("present")),
        "latestContentFirstRequestLabel": ((latest.get("contentSession") or {}).get("firstRequestLabel", "")),
        "latestArchiveRequests": int((latest.get("contentSession") or {}).get("archiveRequests", 0) or 0),
    }
    return standard_tool_artifact(
        tool_name="run_946_scene_start_doctor",
        status="ok" if attempts else "partial",
        inputs={
            "worldLog": str(args.world_log),
            "contentCaptureDir": str(args.content_capture_dir),
            "serverLog": str(args.server_log),
            "clusterId": args.cluster_id or "",
            "attemptLimit": args.attempt_limit,
            "inputFingerprint": input_fingerprint(args),
        },
        artifacts={
            "sceneStartDoctorJson": str(args.output_dir / SCENE_START_JSON),
            "sceneStartDoctorMarkdown": str(args.output_dir / SCENE_START_MD),
        },
        summary=summary,
        extra={
            "attempts": attempts,
            "verdict": final_verdict,
        },
    )


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    fingerprint = input_fingerprint(args)
    outputs = output_paths(args.output_dir)
    if cache_hit(cache_manifest, SCENE_START_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / SCENE_START_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = analyze(args)
    markdown = render_markdown(artifact)
    ensure_directory(args.output_dir)
    write_json(args.output_dir / SCENE_START_JSON, artifact)
    (args.output_dir / SCENE_START_MD).write_text(markdown, encoding="utf-8")
    record_cache_entry(cache_manifest, SCENE_START_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
