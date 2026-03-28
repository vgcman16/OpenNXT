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
from run_946_loopback_doctor import DEFAULT_SERVER_LOG, select_cluster
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR


SCRIPT_BURST_JSON = "script-burst-doctor.json"
SCRIPT_BURST_MD = "script-burst-doctor.md"
SCRIPT_BURST_CACHE_KEY = "script-burst-doctor"

SCRIPT_FAMILY_MARKERS: dict[str, tuple[str, str]] = {
    "world-send-forced-fallback-completion-companions": (
        "forced-fallback-completion-companions",
        "scripts=139,14150",
    ),
    "world-open-minimal-supplemental-child": (
        "forced-fallback-supplemental",
        "scripts=8862",
    ),
    "world-send-light-interface-tail": (
        "light-interface-tail",
        "scripts=11145,8420,8310",
    ),
    "world-send-deferred-completion-scripts": (
        "deferred-completion-scripts",
        "scripts=8862,2651,7486,10903,8778,4704,4308,10623",
    ),
    "world-send-deferred-completion-lite-scripts": (
        "deferred-completion-lite-scripts",
        "scripts=8862,2651,7486,10903,8778,4704,4308",
    ),
    "world-send-deferred-completion-core-scripts": (
        "deferred-completion-core-scripts",
        "scripts=8862,2651,8778",
    ),
    "world-send-deferred-completion-10623-batch": (
        "deferred-completion-10623-batch",
        "scripts=10623",
    ),
    "world-send-deferred-completion-announcement-scripts": (
        "announcement-scripts",
        "scripts=1264,3529",
    ),
}

SKIP_SCRIPT_MARKERS: dict[str, str] = {
    "world-skip-forced-fallback-completion-companions": "forced-fallback-completion-companions",
    "world-skip-forced-fallback-light-tail-scripts": "light-interface-tail",
    "world-skip-forced-fallback-deferred-completion-scripts": "deferred-completion-scripts",
    "world-skip-forced-fallback-announcement-scripts": "announcement-scripts",
    "world-skip-deferred-completion-announcement-scripts": "announcement-scripts",
    "world-skip-interface-bootstrap-script": "generic-skipped-script",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose which RUNCLIENTSCRIPT families dominate the final post-ready disconnect window "
            "for the 946 client."
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
    return [output_dir / SCRIPT_BURST_JSON, output_dir / SCRIPT_BURST_MD]


def input_fingerprint(args: argparse.Namespace) -> str:
    return artifact_input_fingerprint(
        "run_946_script_burst_doctor",
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
    runclientscript_packets = [
        event
        for event in pivot_events
        if event.get("kind") == "send-raw" and event.get("opcode") == 141
    ]
    size_counts = Counter(
        event.get("bytes") for event in runclientscript_packets if isinstance(event.get("bytes"), int)
    )
    marker_counts = Counter(
        event.get("kind")
        for event in pivot_events
        if isinstance(event.get("kind"), str) and event.get("kind", "").startswith("world-")
    )
    skipped_families = sorted(
        {
            family
            for event in pivot_events
            for marker, family in SKIP_SCRIPT_MARKERS.items()
            if event.get("kind") == marker
        }
    )

    script_families: list[dict[str, Any]] = []
    for marker, (family, summary) in SCRIPT_FAMILY_MARKERS.items():
        count = marker_counts.get(marker, 0)
        if count:
            script_families.append(
                {
                    "family": family,
                    "summary": summary,
                    "marker": marker,
                    "count": count,
                }
            )

    dominant_opcode = 141 if runclientscript_packets else None
    dominant_count = len(runclientscript_packets)
    likely_pivot = "post-ready-script-unclassified"
    needs: list[str] = []
    if dominant_count >= 20:
        likely_pivot = "runclientscript-burst-before-disconnect"
        if any(family["family"] == "light-interface-tail" for family in script_families) and "light-interface-tail" not in skipped_families:
            needs.append("trim or defer the forced-fallback light-tail RUNCLIENTSCRIPT set (11145,8420,8310)")
        if any(
            family["family"] in {
                "deferred-completion-scripts",
                "deferred-completion-lite-scripts",
                "deferred-completion-core-scripts",
                "deferred-completion-10623-batch",
            }
            for family in script_families
        ) and "deferred-completion-scripts" not in skipped_families:
            needs.append(
                "trim or defer the deferred completion RUNCLIENTSCRIPT batch "
                "(8862,2651,7486,10903,8778,4704,4308,10623)"
            )
        if any(family["family"] == "announcement-scripts" for family in script_families) and "announcement-scripts" not in skipped_families:
            needs.append("trim or defer the announcement RUNCLIENTSCRIPT pair (1264,3529)")
        if any(family["family"] == "forced-fallback-completion-companions" for family in script_families) and "forced-fallback-completion-companions" not in skipped_families:
            needs.append(
                "trim or defer the forced-fallback completion companion block "
                "(ids 1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639; scripts 139,14150)"
            )

    if (
        any(family["family"] == "forced-fallback-completion-companions" for family in script_families)
        and "forced-fallback-completion-companions" not in skipped_families
        and not any("forced-fallback completion companion block" in need for need in needs)
    ):
        needs.append(
            "trim or defer the forced-fallback completion companion block "
            "(ids 1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639; scripts 139,14150)"
        )

    if content_session and int(content_session.get("referenceTableRequests", 0) or 0) > 0:
        if int(content_session.get("archiveRequests", 0) or 0) == 0:
            needs.append("first non-reference /ms archive request after reference-table[0]")

    return {
        "attemptIndex": attempt_index,
        "worldSession": session_summary(world_session),
        "pivotStartLine": pivot_events[0]["lineNumber"] if pivot_events else None,
        "disconnectLine": pivot_events[-1]["lineNumber"] if pivot_events else None,
        "dominantServerOpcode": dominant_opcode,
        "dominantServerOpcodeCount": dominant_count,
        "runClientScriptPacketSizes": dict(sorted(size_counts.items())),
        "scriptFamilies": script_families,
        "skippedScriptFamilies": skipped_families,
        "likelyPivot": likely_pivot,
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
    if not attempts:
        return {
            "likelyBlocker": "no-attempts",
            "recommendation": "No matching world attempts were available for script-burst analysis.",
            "needs": ["fresh world attempt with world-bootstrap and content capture"],
        }

    burst_attempts = [
        attempt for attempt in attempts if attempt.get("likelyPivot") == "runclientscript-burst-before-disconnect"
    ]
    latest = attempts[-1]
    latest_needs = list(latest.get("needs", []))
    if burst_attempts:
        return {
            "likelyBlocker": "post-ready-runclientscript-burst",
            "recommendation": (
                "The forced-fallback disconnect window is now dominated by RUNCLIENTSCRIPT traffic rather than "
                "IF_SETEVENTS. The remaining script families should be trimmed or deferred."
            ),
            "needs": latest_needs,
        }
    return {
        "likelyBlocker": "post-ready-script-unclassified",
        "recommendation": "RUNCLIENTSCRIPT traffic is present, but the latest cluster does not yet isolate one script family as the blocker.",
        "needs": latest_needs,
    }


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact["summary"]
    lines = [
        "# 946 Script Burst Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{summary['clusterId']}`",
        f"- Attempts analyzed: `{summary['attemptCount']}`",
        f"- Attempts with RUNCLIENTSCRIPT burst: `{summary['runClientScriptBurstAttemptCount']}`",
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
                f"- Pivot lines: `{attempt['pivotStartLine']}:{attempt['disconnectLine']}`",
                f"- Dominant opcode: `{attempt['dominantServerOpcode']}` x `{attempt['dominantServerOpcodeCount']}`",
                f"- RUNCLIENTSCRIPT packet sizes: `{attempt['runClientScriptPacketSizes']}`",
                f"- Content first request: `{(attempt['contentSession'] or {}).get('firstRequestLabel', '')}`",
                f"- Archive requests: `{(attempt['contentSession'] or {}).get('archiveRequests', 0)}`",
            ]
        )
        skipped_families = attempt.get("skippedScriptFamilies") or []
        if skipped_families:
            lines.append(f"- Skipped script families: `{skipped_families}`")
        if attempt.get("scriptFamilies"):
            lines.append("- Script families:")
            for family in attempt["scriptFamilies"]:
                lines.append(
                    f"  - `{family['family']}` via `{family['marker']}` x `{family['count']}` `{family['summary']}`"
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
        "runClientScriptBurstAttemptCount": sum(
            1 for attempt in attempts if attempt.get("likelyPivot") == "runclientscript-burst-before-disconnect"
        ),
        "latestDominantServerOpcode": latest.get("dominantServerOpcode"),
        "latestDominantServerOpcodeCount": latest.get("dominantServerOpcodeCount", 0),
    }
    return standard_tool_artifact(
        tool_name="run_946_script_burst_doctor",
        status="ok",
        inputs={
            "worldLog": str(args.world_log),
            "contentCaptureDir": str(args.content_capture_dir),
            "serverLog": str(args.server_log),
            "clusterId": cluster_id,
            "attemptLimit": args.attempt_limit,
        },
        artifacts={
            "scriptBurstDoctorJson": str((args.output_dir / SCRIPT_BURST_JSON).resolve()),
            "scriptBurstDoctorMarkdown": str((args.output_dir / SCRIPT_BURST_MD).resolve()),
        },
        summary=summary,
        extra={
            "attempts": attempts,
            "verdict": final_verdict,
        },
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / SCRIPT_BURST_JSON, artifact)
    (output_dir / SCRIPT_BURST_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, SCRIPT_BURST_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / SCRIPT_BURST_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = analyze(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, SCRIPT_BURST_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
