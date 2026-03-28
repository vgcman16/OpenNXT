from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

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
from protocol_946_debug_common import WORLD_LOG_DEFAULT
from run_946_loopback_doctor import build_attempts, parse_server_attempts, select_cluster
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR


ATTEMPT_DIFF_JSON = "attempt-diff.json"
ATTEMPT_DIFF_MD = "attempt-diff.md"
ATTEMPT_DIFF_CACHE_KEY = "attempt-diff"
DEFAULT_SERVER_LOG = WORKSPACE / "tmp-manual-js5.err.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diff 946 loopback attempts so the exact last world/interface/content tail is visible instead of only a mismatch count."
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
        output_dir / ATTEMPT_DIFF_JSON,
        output_dir / ATTEMPT_DIFF_MD,
    ]


def summarize_event(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data", {}) or {}
    summary = {
        "lineNumber": event.get("lineNumber"),
        "timestamp": event.get("timestamp", ""),
        "kind": event.get("kind", ""),
        "stage": event.get("stage", ""),
    }
    opcode = event.get("opcode")
    if isinstance(opcode, int):
        summary["opcode"] = opcode
    byte_count = event.get("bytes")
    if isinstance(byte_count, int):
        summary["bytes"] = byte_count
    preview = event.get("preview")
    if preview:
        summary["preview"] = preview
    for key in ("reason", "source", "script", "id", "component", "mode", "chunkX", "chunkY"):
        value = data.get(key)
        if value not in (None, ""):
            summary[key] = value
    return summary


def select_tail(
    world_session: dict[str, Any],
    *,
    predicate,
    limit: int,
) -> list[dict[str, Any]]:
    events = world_session.get("events", []) or []
    filtered = [event for event in events if predicate(event)]
    return [summarize_event(event) for event in filtered[-limit:]]


def event_token(event: dict[str, Any]) -> str:
    kind = event.get("kind", "")
    opcode = event.get("opcode")
    if isinstance(opcode, int):
        return f"{kind}:{opcode}"
    reason = event.get("reason")
    if reason:
        return f"{kind}:{reason}"
    return kind


def tail_signature(world_tail: list[dict[str, Any]], server_tail: list[dict[str, Any]], client_tail: list[dict[str, Any]]) -> str:
    payload = {
        "world": [event_token(event) for event in world_tail],
        "server": [event_token(event) for event in server_tail],
        "client": [event_token(event) for event in client_tail],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def common_suffix(sequences: Iterable[list[str]]) -> list[str]:
    materialized = [sequence for sequence in sequences if sequence]
    if not materialized:
        return []
    reversed_sequences = [list(reversed(sequence)) for sequence in materialized]
    suffix: list[str] = []
    for values in zip(*reversed_sequences):
        if len(set(values)) != 1:
            break
        suffix.append(values[0])
    return list(reversed(suffix))


def enrich_attempts(
    world_sessions: list[dict[str, Any]],
    base_attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for index, attempt in enumerate(base_attempts):
        world_session = world_sessions[index]
        world_tail = select_tail(
            world_session,
            predicate=lambda event: event.get("kind", "").startswith("world-") and event.get("kind") != "world-stage",
            limit=10,
        )
        server_tail = select_tail(world_session, predicate=lambda event: event.get("kind") == "send-raw", limit=10)
        client_tail = select_tail(world_session, predicate=lambda event: event.get("kind") == "recv-raw", limit=10)
        signature = tail_signature(world_tail, server_tail, client_tail)
        enriched.append(
            {
                **attempt,
                "worldTail": world_tail,
                "serverTail": server_tail,
                "clientTail": client_tail,
                "tailSignature": signature,
            }
        )
    return enriched


def summarize_signature_groups(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        grouped.setdefault(attempt.get("tailSignature", ""), []).append(attempt)
    rows: list[dict[str, Any]] = []
    for signature, members in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        exemplar = members[0]
        rows.append(
            {
                "signature": signature,
                "attemptIndexes": [member.get("attemptIndex") for member in members],
                "count": len(members),
                "outcomes": sorted({member.get("outcome", "") for member in members}),
                "disconnectStages": sorted(
                    {
                        ((member.get("serverAttempt") or {}).get("closeStage") or "")
                        for member in members
                    }
                ),
                "pairedContentFirstRequestLabels": sorted(
                    {
                        ((member.get("pairedContentSession") or {}).get("firstRequestLabel") or "<missing>")
                        for member in members
                    }
                ),
                "worldTail": exemplar.get("worldTail", []),
                "serverTail": exemplar.get("serverTail", []),
                "clientTail": exemplar.get("clientTail", []),
            }
        )
    return rows


def summarize_differences(attempts: list[dict[str, Any]], signature_groups: list[dict[str, Any]]) -> list[str]:
    differences: list[str] = []
    if not attempts:
        return differences
    outcomes = sorted({attempt.get("outcome", "") for attempt in attempts})
    if len(outcomes) == 1:
        differences.append(f"all attempts end with the same outcome: {outcomes[0]}")
    else:
        differences.append(f"attempt outcomes vary: {', '.join(outcomes)}")

    close_stages = sorted(
        {
            ((attempt.get("serverAttempt") or {}).get("closeStage") or "<missing>")
            for attempt in attempts
        }
    )
    if len(close_stages) == 1:
        differences.append(f"every paired server attempt closes at bootstrap stage {close_stages[0]}")
    else:
        differences.append(f"disconnect stages vary: {', '.join(close_stages)}")

    content_labels = [
        ((attempt.get("pairedContentSession") or {}).get("firstRequestLabel") or "<missing>")
        for attempt in attempts
    ]
    label_counts = Counter(content_labels)
    differences.append(
        "paired content labels: " + ", ".join(f"{label} x{count}" for label, count in sorted(label_counts.items()))
    )

    raw_pairs = Counter(
        f"{((attempt.get('pairedLoginRawSession') or {}).get('toRemoteBytes', 0))}->{((attempt.get('pairedLoginRawSession') or {}).get('fromRemoteBytes', 0))}"
        for attempt in attempts
    )
    differences.append(
        "paired raw login byte-shapes: " + ", ".join(f"{label} x{count}" for label, count in sorted(raw_pairs.items()))
    )

    if len(signature_groups) == 1:
        differences.append(
            f"all attempts share one exact tail signature across world markers and raw packet tails ({signature_groups[0]['count']} attempts)"
        )
    else:
        differences.append(
            "tail signatures split into "
            + ", ".join(f"{group['count']}x attempts {group['attemptIndexes']}" for group in signature_groups[:4])
        )
    return differences


def build_exact_needs(attempts: list[dict[str, Any]], signature_groups: list[dict[str, Any]]) -> list[str]:
    if not attempts:
        return ["fresh post-login world attempt to diff; the current cluster contains no world sessions"]

    needs: list[str] = []
    if all(int((attempt.get("pairedContentSession") or {}).get("archiveRequests", 0) or 0) <= 0 for attempt in attempts):
        content_labels = [
            ((attempt.get("pairedContentSession") or {}).get("firstRequestLabel") or "<missing>")
            for attempt in attempts
        ]
        if "reference-table[0]" in content_labels:
            needs.append("first non-reference /ms request after reference-table[0]; scene archive delivery still never starts")
        else:
            needs.append("fresh content capture on the looping attempt cluster; no paired scene archive request exists yet")

    close_stages = {
        ((attempt.get("serverAttempt") or {}).get("closeStage") or "")
        for attempt in attempts
        if attempt.get("serverAttempt")
    }
    if close_stages == {"interfaces"}:
        dominant = signature_groups[0] if signature_groups else {}
        world_tail_tokens = [event_token(event) for event in dominant.get("worldTail", [])]
        common_tail = common_suffix([world_tail_tokens]) if world_tail_tokens else []
        tail_text = " -> ".join(common_tail[-4:]) if common_tail else "interfaces tail"
        needs.append(f"first surviving step after {tail_text}; the channel still drops at interfaces on the dominant signature")

    missing_content_attempts = [
        attempt.get("attemptIndex")
        for attempt in attempts
        if not (attempt.get("pairedContentSession") or {})
    ]
    if missing_content_attempts:
        needs.append(
            "content pairing disappears on attempts "
            + ", ".join(str(index) for index in missing_content_attempts[:6])
            + "; capture the exact first content session that should follow the interface tail on those later attempts"
        )

    dominant_group = signature_groups[0] if signature_groups else {}
    if dominant_group:
        world_tokens = [event_token(event) for event in dominant_group.get("worldTail", [])]
        server_tokens = [event_token(event) for event in dominant_group.get("serverTail", [])]
        if world_tokens:
            needs.append(
                "compare the dominant world-tail signature against a non-looping baseline: "
                + " -> ".join(world_tokens[-5:])
            )
        if server_tokens:
            needs.append(
                "compare the last server raw tail against a non-looping baseline: "
                + " -> ".join(server_tokens[-5:])
            )

    deduped: list[str] = []
    for item in needs:
        if item not in deduped:
            deduped.append(item)
    return deduped


def build_verdict(attempts: list[dict[str, Any]], signature_groups: list[dict[str, Any]]) -> dict[str, Any]:
    needs = build_exact_needs(attempts, signature_groups)
    if not attempts:
        return {
            "likelyBlocker": "no-world-attempts",
            "recommendation": "There is nothing post-login to diff yet. Reproduce the loopback and rerun the tool.",
            "needs": needs,
        }

    archives_seen = sum(int((attempt.get("pairedContentSession") or {}).get("archiveRequests", 0) or 0) for attempt in attempts)
    close_stages = {
        ((attempt.get("serverAttempt") or {}).get("closeStage") or "")
        for attempt in attempts
        if attempt.get("serverAttempt")
    }
    if archives_seen <= 0 and close_stages == {"interfaces"} and len(signature_groups) == 1:
        return {
            "likelyBlocker": "deterministic-interfaces-tail-loopback",
            "recommendation": "The looping cluster is now deterministic: the client reaches interfaces, emits the same final world/raw tail, and drops before any scene archive request appears.",
            "needs": needs,
        }
    if archives_seen <= 0 and close_stages == {"interfaces"}:
        return {
            "likelyBlocker": "interfaces-tail-variant-loopback",
            "recommendation": "The client still dies at interfaces, but there are multiple tail signatures. Diff the dominant signatures instead of changing routing again.",
            "needs": needs,
        }
    return {
        "likelyBlocker": "mixed-loopback-cluster",
        "recommendation": "The cluster no longer has one clean deterministic tail; inspect the signature groups below and compare them with a non-looping run.",
        "needs": needs,
    }


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    requested_cluster_id = getattr(args, "cluster_id", None)
    cluster_id, cluster_start, cluster_sessions, world_sessions = select_cluster(
        args.content_capture_dir,
        args.world_log,
        args.attempt_limit,
        requested_cluster_id,
    )
    server_attempts = parse_server_attempts(args.server_log)
    base_attempts = build_attempts(world_sessions, server_attempts, cluster_sessions)
    attempts = enrich_attempts(world_sessions, base_attempts)
    signature_groups = summarize_signature_groups(attempts)
    differences = summarize_differences(attempts, signature_groups)
    verdict = build_verdict(attempts, signature_groups)
    world_tail_suffix = common_suffix([[event_token(event) for event in attempt.get("worldTail", [])] for attempt in attempts])
    server_tail_suffix = common_suffix([[event_token(event) for event in attempt.get("serverTail", [])] for attempt in attempts])

    latest_attempt = attempts[-1] if attempts else {}
    status = "ok" if attempts else "partial"
    return standard_tool_artifact(
        tool_name="run_946_attempt_diff",
        status=status,
        inputs={
            "worldLog": str(args.world_log),
            "contentCaptureDir": str(args.content_capture_dir),
            "serverLog": str(args.server_log),
            "clusterId": requested_cluster_id or "",
            "attemptLimit": args.attempt_limit,
            "inputFingerprint": input_fingerprint(args),
        },
        artifacts={
            "attemptDiffJson": str(args.output_dir / ATTEMPT_DIFF_JSON),
            "attemptDiffMarkdown": str(args.output_dir / ATTEMPT_DIFF_MD),
        },
        summary={
            "clusterId": cluster_id,
            "attemptCount": len(attempts),
            "uniqueTailSignatureCount": len(signature_groups),
            "likelyBlocker": verdict.get("likelyBlocker", ""),
            "latestOutcome": latest_attempt.get("outcome", ""),
            "latestDisconnectStage": ((latest_attempt.get("serverAttempt") or {}).get("closeStage") or ""),
            "latestContentFirstRequestLabel": ((latest_attempt.get("pairedContentSession") or {}).get("firstRequestLabel") or ""),
            "latestArchiveRequests": int((latest_attempt.get("pairedContentSession") or {}).get("archiveRequests", 0) or 0),
            "commonWorldTailSuffix": world_tail_suffix[-6:],
            "commonServerTailSuffix": server_tail_suffix[-6:],
        },
        extra={
            "cluster": {
                "clusterId": cluster_id,
                "clusterStartTimestamp": cluster_start.isoformat() if isinstance(cluster_start, datetime) else "",
                "contentSessionCount": len(cluster_sessions),
                "worldAttemptCount": len(world_sessions),
            },
            "attempts": attempts,
            "signatureGroups": signature_groups,
            "differences": differences,
            "verdict": verdict,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {}) or {}
    verdict = artifact.get("verdict", {}) or {}
    lines = [
        "# 946 Attempt Diff Doctor",
        "",
        f"- Status: `{artifact.get('status', '')}`",
        f"- Cluster id: `{summary.get('clusterId', '')}`",
        f"- Attempts analyzed: `{summary.get('attemptCount', 0)}`",
        f"- Unique tail signatures: `{summary.get('uniqueTailSignatureCount', 0)}`",
        f"- Latest outcome: `{summary.get('latestOutcome', '')}`",
        f"- Latest disconnect stage: `{summary.get('latestDisconnectStage', '')}`",
        f"- Latest content label: `{summary.get('latestContentFirstRequestLabel', '')}`",
        "",
        "## Verdict",
        "",
        f"- Likely blocker: `{verdict.get('likelyBlocker', 'unknown')}`",
        f"- Recommendation: {verdict.get('recommendation', 'No recommendation available.')}",
        "",
        "## Exact Needs",
        "",
    ]
    for item in verdict.get("needs", []) or ["No exact needs recorded."]:
        lines.append(f"- {item}")

    lines.extend(["", "## Cluster Diffs", ""])
    for item in artifact.get("differences", []) or []:
        lines.append(f"- {item}")

    lines.extend(["", "## Signature Groups", ""])
    groups = artifact.get("signatureGroups", []) or []
    if not groups:
        lines.append("- No signature groups were produced.")
    for index, group in enumerate(groups, start=1):
        lines.append(f"### Signature {index}")
        lines.append("")
        lines.append(f"- Attempts: `{group.get('attemptIndexes', [])}`")
        lines.append(f"- Outcomes: `{group.get('outcomes', [])}`")
        lines.append(f"- Disconnect stages: `{group.get('disconnectStages', [])}`")
        lines.append(f"- Content labels: `{group.get('pairedContentFirstRequestLabels', [])}`")
        if group.get("worldTail"):
            lines.append("- World tail:")
            for event in group["worldTail"]:
                details = []
                if "opcode" in event:
                    details.append(f"opcode={event['opcode']}")
                if "bytes" in event:
                    details.append(f"bytes={event['bytes']}")
                if "reason" in event:
                    details.append(f"reason={event['reason']}")
                lines.append(
                    f"  - line {event.get('lineNumber')}: {event.get('kind')} {event.get('stage', '')} {' '.join(details).strip()}".rstrip()
                )
        if group.get("serverTail"):
            lines.append("- Server raw tail:")
            for event in group["serverTail"]:
                details = []
                if "opcode" in event:
                    details.append(f"opcode={event['opcode']}")
                if "bytes" in event:
                    details.append(f"bytes={event['bytes']}")
                lines.append(
                    f"  - line {event.get('lineNumber')}: {event.get('kind')} {event.get('stage', '')} {' '.join(details).strip()}".rstrip()
                )
        if group.get("clientTail"):
            lines.append("- Client raw tail:")
            for event in group["clientTail"]:
                details = []
                if "opcode" in event:
                    details.append(f"opcode={event['opcode']}")
                if "bytes" in event:
                    details.append(f"bytes={event['bytes']}")
                lines.append(
                    f"  - line {event.get('lineNumber')}: {event.get('kind')} {event.get('stage', '')} {' '.join(details).strip()}".rstrip()
                )
        lines.append("")

    lines.extend(["## Attempts", ""])
    attempts = artifact.get("attempts", []) or []
    if not attempts:
        lines.append("- No attempts available.")
    for attempt in attempts:
        server_attempt = attempt.get("serverAttempt") or {}
        content = attempt.get("pairedContentSession") or {}
        raw_session = attempt.get("pairedLoginRawSession") or {}
        lines.append(f"### Attempt {attempt.get('attemptIndex')}")
        lines.append("")
        lines.append(f"- Outcome: `{attempt.get('outcome', '')}`")
        lines.append(f"- Disconnect stage: `{server_attempt.get('closeStage', '')}`")
        lines.append(
            f"- Paired content: `{content.get('firstRequestLabel', '<missing>')}` archives=`{content.get('archiveRequests', 0)}` refTables=`{content.get('referenceTableRequests', 0)}`"
        )
        lines.append(
            f"- Paired raw login bytes: `{raw_session.get('toRemoteBytes', 0)}->{raw_session.get('fromRemoteBytes', 0)}`"
        )
        lines.append(f"- Tail signature: `{attempt.get('tailSignature', '')}`")
        lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    content_logs = sorted(args.content_capture_dir.glob("session-*.log"))
    return artifact_input_fingerprint(
        "run_946_attempt_diff",
        [
            WORKSPACE / "tools" / "run_946_attempt_diff.py",
            WORKSPACE / "tools" / "run_946_loopback_doctor.py",
            WORKSPACE / "tools" / "protocol_946_debug_common.py",
            WORKSPACE / "tools" / "run_946_scene_delivery_aid.py",
            args.world_log,
            args.server_log,
            *content_logs[-256:],
        ],
        clusterId=getattr(args, "cluster_id", "") or "",
        attemptLimit=args.attempt_limit,
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / ATTEMPT_DIFF_JSON, artifact)
    (output_dir / ATTEMPT_DIFF_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, ATTEMPT_DIFF_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / ATTEMPT_DIFF_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, ATTEMPT_DIFF_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
