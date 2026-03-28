from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

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
    build_index,
    load_phase_inputs,
    load_all_sessions,
    parse_timestamp,
    session_summary,
    unresolved_client_candidates,
)
from run_946_loopback_doctor import select_cluster
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR, list_content_capture_logs


POST_SCENE_OPCODE_JSON = "post-scene-opcode-doctor.json"
POST_SCENE_OPCODE_MD = "post-scene-opcode-doctor.md"
POST_SCENE_OPCODE_CACHE_KEY = "post-scene-opcode-doctor"

READY_SIGNAL_KINDS = {
    "world-accept-late-scene-ready-signal",
    "world-send-late-scene-ready-followup",
}
KNOWN_STATUS_OPCODES = {17, 48, 83, 113}
CONTROL50_THRESHOLD = 125
SENDER_ADDR_RE = re.compile(r"FUN_(?P<addr>[0-9A-Fa-f]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose unresolved client opcodes that appear after late-scene ready acceptance "
            "and explain whether they look like harmless input/status traffic or packets that "
            "still need explicit server handling."
        )
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--content-capture-dir", type=Path, default=DEFAULT_CONTENT_CAPTURE_DIR)
    parser.add_argument("--cluster-id")
    parser.add_argument("--attempt-limit", type=int, default=12)
    parser.add_argument("--decomp-log-dir", type=Path, default=WORKSPACE.parent / "ghidra-projects")
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / POST_SCENE_OPCODE_JSON,
        output_dir / POST_SCENE_OPCODE_MD,
    ]


def aggregated_content_summary(cluster_sessions: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        cluster_sessions,
        key=lambda session: (
            session.get("startTimestamp", ""),
            session.get("sessionId") or 0,
        ),
    )
    first_request_label = ""
    for session in ordered:
        label = str(session.get("firstRequestLabel", "") or "")
        if label:
            first_request_label = label
            break
    route_counts = Counter(str(session.get("sessionRoute", "") or "") for session in ordered)
    return {
        "sessionCount": len(ordered),
        "routeCounts": dict(sorted((route, count) for route, count in route_counts.items() if route)),
        "referenceTableRequests": sum(int(session.get("referenceTableRequests", 0) or 0) for session in ordered),
        "archiveRequests": sum(int(session.get("archiveRequests", 0) or 0) for session in ordered),
        "requestCount": sum(int(session.get("requestCount", 0) or 0) for session in ordered),
        "responseBytes": sum(int(session.get("responseBytes", 0) or 0) for session in ordered),
        "firstRequestLabel": first_request_label,
        "sampleRequests": [
            request
            for session in ordered
            for request in list(session.get("sampleRequests", []))[:2]
        ][:6],
    }


def find_post_scene_start(session: dict[str, Any]) -> tuple[int | None, str]:
    events = session.get("events", [])
    accepted_lines = [
        event["lineNumber"]
        for event in events
        if event.get("kind") == "world-accept-late-scene-ready-signal"
    ]
    if accepted_lines:
        return accepted_lines[-1], "late-scene-ready-accepted"

    threshold_lines: list[int] = []
    for event in events:
        if event.get("kind") != "world-client-bootstrap-control":
            continue
        value = event.get("data", {}).get("value")
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            continue
        if parsed >= CONTROL50_THRESHOLD:
            threshold_lines.append(event["lineNumber"])
    if threshold_lines:
        return threshold_lines[-1], f"control50>={CONTROL50_THRESHOLD}"

    return None, "none"


def build_opcode_evidence_index() -> dict[tuple[str, int], dict[str, Any]]:
    phase_inputs = load_phase_inputs()
    entries: list[dict[str, Any]] = []
    for key in ("phase3Candidates", "generatedPackets", "verifiedPackets", "evidenceIndex"):
        entries.extend(entry for entry in phase_inputs.get(key, []) if isinstance(entry, dict))
    index: dict[tuple[str, int], dict[str, Any]] = {}
    for entry in entries:
        side = str(entry.get("side", "")).lower()
        opcode = entry.get("opcode")
        if side and isinstance(opcode, int):
            index.setdefault((side, opcode), entry)
    return index


def resolve_sender_name(candidate: dict[str, Any], evidence_entry: dict[str, Any]) -> str:
    candidate_evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
    evidence_targets = evidence_entry.get("targets") if isinstance(evidence_entry.get("targets"), dict) else {}
    return str(
        candidate_evidence.get("primarySenderName")
        or candidate_evidence.get("primarySender")
        or evidence_targets.get("primarySenderName")
        or evidence_targets.get("primarySender")
        or ""
    )


def sender_decomp_path(decomp_log_dir: Path, sender_name: str) -> Path | None:
    match = SENDER_ADDR_RE.search(sender_name)
    if not match:
        return None
    return decomp_log_dir / f"decomp-{match.group('addr').lower()}.log"


def classify_sender(candidate: dict[str, Any], decomp_text: str) -> dict[str, Any]:
    size = candidate.get("size")
    if not decomp_text:
        return {
            "classification": "unknown",
            "responseExpectation": "unknown",
            "derivedFields": [],
            "evidence": "No local decompile log was available for this opcode sender.",
        }

    has_float_coords = (
        ("*(float *)" in decomp_text and (" + 4)" in decomp_text or " + 8)" in decomp_text))
        or "(int)(float)" in decomp_text
    )
    has_delta = "param_1 + 0x20" in decomp_text and ("0x7fff" in decomp_text or "0xffff" in decomp_text)
    has_flags = "+ 0x28)" in decomp_text or "+ 0x2c)" in decomp_text or "iVar2 != 0" in decomp_text

    if size == 6 and has_float_coords and has_delta:
        return {
            "classification": "pointer-input-press-delta",
            "responseExpectation": "no-direct-server-response-expected",
            "derivedFields": [
                "two bounded screen/world coordinates",
                "capped elapsed-delta field",
                "pressed-or-state high bit",
            ],
            "evidence": (
                "The sender packs two float-derived coordinates plus a capped age delta into a 6-byte payload, "
                "with one high-bit flag toggled from a boolean state."
            ),
        }

    if size == 7 and has_float_coords and has_delta and has_flags:
        return {
            "classification": "pointer-input-state",
            "responseExpectation": "no-direct-server-response-expected",
            "derivedFields": [
                "capped elapsed-delta field",
                "compact flags byte",
                "two bounded coordinates",
            ],
            "evidence": (
                "The sender packs a short delta, a one-byte state/flags field, and two float-derived coordinates "
                "into a 7-byte payload."
            ),
        }

    if size in (1, 2, 4) and has_delta:
        return {
            "classification": "client-status-or-timing",
            "responseExpectation": "usually-no-direct-server-response",
            "derivedFields": ["timing/delta field"],
            "evidence": "The sender mostly tracks elapsed client-side state rather than requesting bulk content.",
        }

    return {
        "classification": "unknown",
        "responseExpectation": "unknown",
        "derivedFields": [],
        "evidence": "The local decompile log did not match a known input/status packing pattern yet.",
    }


def summarize_unresolved_opcode(
    opcode: int,
    events: list[dict[str, Any]],
    unresolved_candidates: dict[int, dict[str, Any]],
    opcode_evidence: dict[tuple[str, int], dict[str, Any]],
    decomp_log_dir: Path,
) -> dict[str, Any]:
    candidate = unresolved_candidates.get(opcode, {})
    evidence_entry = opcode_evidence.get(("client", opcode), {})
    sender_name = resolve_sender_name(candidate, evidence_entry)
    decomp_path = sender_decomp_path(decomp_log_dir, sender_name)
    decomp_text = ""
    if decomp_path and decomp_path.exists():
        decomp_text = decomp_path.read_text(encoding="utf-8", errors="ignore").replace("\x00", "")
    classification = classify_sender(candidate, decomp_text)

    return {
        "opcode": opcode,
        "count": len(events),
        "sizes": sorted({int(event.get("bytes", 0) or 0) for event in events if event.get("bytes") is not None}),
        "samples": [
            {
                "lineNumber": event["lineNumber"],
                "bytes": event.get("bytes"),
                "preview": event.get("preview", ""),
            }
            for event in events[:4]
        ],
        "candidate": {
            "size": candidate.get("size"),
            "suggestedName": candidate.get("suggestedName", ""),
            "confidence": candidate.get("confidence", ""),
            "signatureHash": ((candidate.get("crossBuild") or {}).get("signatureHash", "")),
        },
        "sender": {
            "name": sender_name,
            "decompPath": str(decomp_path) if decomp_path else "",
            "decompAvailable": bool(decomp_text),
        },
        "classification": classification["classification"],
        "responseExpectation": classification["responseExpectation"],
        "derivedFields": classification["derivedFields"],
        "evidence": classification["evidence"],
    }


def matched_cluster_sessions(world_session: dict[str, Any], cluster_sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = parse_timestamp(world_session.get("startTimestamp", ""))
    end = parse_timestamp(world_session.get("endTimestamp", ""))
    if not start or not end:
        return cluster_sessions
    lower_bound = start - timedelta(seconds=10)
    upper_bound = end + timedelta(seconds=45)
    matched = [
        session
        for session in cluster_sessions
        if session.get("start") is not None and lower_bound <= session["start"] <= upper_bound
    ]
    return matched or cluster_sessions


def summarize_attempt(
    session: dict[str, Any],
    cluster_sessions: list[dict[str, Any]],
    unresolved_candidates: dict[int, dict[str, Any]],
    opcode_evidence: dict[tuple[str, int], dict[str, Any]],
    decomp_log_dir: Path,
    attempt_index: int,
) -> dict[str, Any]:
    start_line, start_reason = find_post_scene_start(session)
    events = session.get("events", [])
    if start_line is None:
        post_scene_events = []
    else:
        post_scene_events = [event for event in events if event["lineNumber"] >= start_line]

    client_events = [event for event in post_scene_events if event.get("kind") == "recv-raw"]
    client_opcode_counts = Counter(
        int(event["opcode"])
        for event in client_events
        if isinstance(event.get("opcode"), int)
    )
    unresolved_by_opcode: dict[int, list[dict[str, Any]]] = {}
    for event in client_events:
        opcode = event.get("opcode")
        if not isinstance(opcode, int):
            continue
        if opcode in KNOWN_STATUS_OPCODES:
            continue
        unresolved_by_opcode.setdefault(opcode, []).append(event)

    unresolved = [
        summarize_unresolved_opcode(opcode, opcode_events, unresolved_candidates, opcode_evidence, decomp_log_dir)
        for opcode, opcode_events in sorted(
            unresolved_by_opcode.items(),
            key=lambda item: (-len(item[1]), item[0]),
        )
    ]

    paired_sessions = matched_cluster_sessions(session, cluster_sessions)
    content_summary = aggregated_content_summary(paired_sessions)
    late_ready_accepts = [
        {
            "lineNumber": event["lineNumber"],
            "opcode": event.get("opcode"),
            "preview": event.get("preview", ""),
            "timestamp": event.get("timestamp", ""),
        }
        for event in post_scene_events
        if event.get("kind") == "world-accept-late-scene-ready-signal"
    ]

    needs: list[str] = []
    if start_line is None:
        needs.append("accept and retain a late-scene ready signal before diagnosing deeper plateau traffic")
    if content_summary["archiveRequests"] == 0:
        needs.append("first non-reference /ms archive request after late-scene-ready acceptance")
    if unresolved and all(
        entry["responseExpectation"].startswith("no-direct-server-response")
        or entry["responseExpectation"] == "usually-no-direct-server-response"
        for entry in unresolved
    ):
        needs.append("continue server-side scene-start/content progression after late ready; current unresolved client packets look like input/status traffic")
    elif unresolved:
        needs.append("name or handle the remaining unresolved client opcode families after late ready")

    return {
        "attemptIndex": attempt_index,
        "worldSession": session_summary(session),
        "postSceneStartLine": start_line,
        "postSceneStartReason": start_reason,
        "lateReadyAccepts": late_ready_accepts,
        "clientOpcodeCountsAfterPostSceneStart": dict(sorted(client_opcode_counts.items())),
        "knownStatusOpcodeCounts": {
            opcode: client_opcode_counts.get(opcode, 0)
            for opcode in sorted(KNOWN_STATUS_OPCODES)
            if client_opcode_counts.get(opcode, 0)
        },
        "unresolvedClientOpcodes": unresolved,
        "pairedContentSummary": content_summary,
        "needs": list(dict.fromkeys(needs)),
    }


def build_verdict(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if not attempts:
        return {
            "likelyBlocker": "no-world-attempts",
            "recommendation": "No post-login world attempts were matched to the current content cluster yet.",
            "needs": ["fresh accepted-ready plateau attempt"],
        }

    latest = attempts[-1]
    unresolved = latest.get("unresolvedClientOpcodes", [])
    content = latest.get("pairedContentSummary", {})
    archive_requests = int(content.get("archiveRequests", 0) or 0)
    if unresolved and archive_requests == 0 and all(
        entry["responseExpectation"].startswith("no-direct-server-response")
        or entry["responseExpectation"] == "usually-no-direct-server-response"
        for entry in unresolved
    ):
        return {
            "likelyBlocker": "post-scene-server-stall-after-ready",
            "recommendation": (
                "The unresolved post-scene client opcodes look like compact pointer/status traffic, "
                "so the plateau is more likely a missing server-side scene/content progression step "
                "than a packet family that still needs an explicit server reply."
            ),
            "needs": latest.get("needs", []),
        }
    if unresolved:
        return {
            "likelyBlocker": "unresolved-post-scene-client-opcodes",
            "recommendation": (
                "The late plateau still contains unresolved client opcode families whose semantics are not "
                "strongly classified yet."
            ),
            "needs": latest.get("needs", []),
        }
    if archive_requests == 0:
        return {
            "likelyBlocker": "accepted-ready-no-scene-archives",
            "recommendation": (
                "Late ready was accepted, but content never advanced beyond reference-table traffic."
            ),
            "needs": latest.get("needs", []),
        }
    return {
        "likelyBlocker": "post-scene-opcodes-not-dominant",
        "recommendation": "The current plateau is no longer dominated by unresolved post-scene client opcode families.",
        "needs": latest.get("needs", []),
    }


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    cluster_id, cluster_start, cluster_sessions, world_sessions = select_cluster(
        args.content_capture_dir,
        args.world_log,
        args.attempt_limit,
        args.cluster_id,
    )
    phase_inputs = load_phase_inputs()
    generated_index = build_index(phase_inputs.get("generatedPackets", []))
    verified_index = build_index(phase_inputs.get("verifiedPackets", []))
    unresolved_candidates = unresolved_client_candidates(
        phase_inputs.get("phase3Candidates", []),
        generated_index,
        verified_index,
    )
    opcode_evidence = build_opcode_evidence_index()

    attempts = [
        summarize_attempt(
            session,
            cluster_sessions,
            unresolved_candidates,
            opcode_evidence,
            args.decomp_log_dir,
            index + 1,
        )
        for index, session in enumerate(world_sessions)
    ]
    verdict = build_verdict(attempts)
    latest = attempts[-1] if attempts else {}
    unresolved_opcodes = latest.get("unresolvedClientOpcodes", [])

    return standard_tool_artifact(
        tool_name="run_946_post_scene_opcode_doctor",
        status="ok" if attempts else "partial",
        inputs={
            "worldLog": str(args.world_log),
            "contentCaptureDir": str(args.content_capture_dir),
            "clusterId": cluster_id,
            "decompLogDir": str(args.decomp_log_dir),
        },
        artifacts={
            "postSceneOpcodeDoctorJson": str(args.output_dir / POST_SCENE_OPCODE_JSON),
            "postSceneOpcodeDoctorMarkdown": str(args.output_dir / POST_SCENE_OPCODE_MD),
        },
        summary={
            "clusterId": cluster_id,
            "attemptCount": len(attempts),
            "latestLikelyBlocker": verdict["likelyBlocker"],
            "latestPostSceneStartReason": latest.get("postSceneStartReason", ""),
            "latestUnresolvedOpcodeCount": len(unresolved_opcodes),
            "latestArchiveRequests": (latest.get("pairedContentSummary") or {}).get("archiveRequests", 0),
        },
        extra={
            "cluster": {
                "id": cluster_id,
                "startTimestamp": cluster_start.isoformat() if cluster_start else "",
                "contentSessionCount": len(cluster_sessions),
            },
            "verdict": verdict,
            "attempts": attempts,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# 946 Post Scene Opcode Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{artifact['summary'].get('clusterId', '')}`",
        f"- Attempts analyzed: `{artifact['summary'].get('attemptCount', 0)}`",
        f"- Latest likely blocker: `{artifact['summary'].get('latestLikelyBlocker', '')}`",
        f"- Latest unresolved opcode count: `{artifact['summary'].get('latestUnresolvedOpcodeCount', 0)}`",
        "",
        "## Verdict",
        "",
        f"- Recommendation: {artifact.get('verdict', {}).get('recommendation', 'No recommendation recorded.')}",
        "",
        "## Exact Needs",
        "",
    ]
    for need in artifact.get("verdict", {}).get("needs", []):
        lines.append(f"- {need}")

    lines.extend(["", "## Attempts", ""])
    for attempt in artifact.get("attempts", []):
        lines.extend(
            [
                f"### Attempt {attempt['attemptIndex']}",
                "",
                f"- World window: `{attempt['worldSession']['startLine']}:{attempt['worldSession']['endLine']}`",
                f"- Post-scene start: `{attempt.get('postSceneStartReason', '')}` at line `{attempt.get('postSceneStartLine')}`",
                f"- Known status opcodes after post-scene start: `{attempt.get('knownStatusOpcodeCounts', {})}`",
                f"- Paired content first request: `{attempt.get('pairedContentSummary', {}).get('firstRequestLabel', '')}`",
                f"- Paired archive requests: `{attempt.get('pairedContentSummary', {}).get('archiveRequests', 0)}`",
            ]
        )
        unresolved = attempt.get("unresolvedClientOpcodes", [])
        if unresolved:
            lines.extend(["", "- Unresolved post-scene client opcodes:"])
            for entry in unresolved:
                fields = ", ".join(entry.get("derivedFields", [])) or "none recorded"
                lines.append(
                    f"  - opcode `{entry['opcode']}` x `{entry['count']}` classification=`{entry['classification']}` "
                    f"response=`{entry['responseExpectation']}` sender=`{entry['sender']['name']}`"
                )
                lines.append(f"    fields: {fields}")
                lines.append(f"    evidence: {entry['evidence']}")
        if attempt.get("needs"):
            lines.extend(["", "- Needs:"])
            for need in attempt["needs"]:
                lines.append(f"  - {need}")
        lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    recent_capture_logs = list_content_capture_logs(args.content_capture_dir)[-24:]
    decomp_logs = sorted(args.decomp_log_dir.glob("decomp-*.log"))[:64] if args.decomp_log_dir.exists() else []
    return artifact_input_fingerprint(
        "run_946_post_scene_opcode_doctor",
        [
            WORKSPACE / "tools" / "run_946_post_scene_opcode_doctor.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            WORKSPACE / "tools" / "protocol_946_debug_common.py",
            WORKSPACE / "tools" / "run_946_loopback_doctor.py",
            args.world_log,
            SHARED_DIR / "evidence-index.json",
            SHARED_DIR / "verified-packets.json",
            WORKSPACE / "data" / "prot" / "946" / "generated" / "phase3" / "nameCandidates.json",
            WORKSPACE / "data" / "prot" / "946" / "generated" / "phase5" / "generatedPackets.json",
            *recent_capture_logs,
            *decomp_logs,
        ],
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / POST_SCENE_OPCODE_JSON, artifact)
    (output_dir / POST_SCENE_OPCODE_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, POST_SCENE_OPCODE_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / POST_SCENE_OPCODE_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, POST_SCENE_OPCODE_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
