from __future__ import annotations

import argparse
import re
from collections import Counter
from datetime import timedelta
from pathlib import Path
from typing import Any

from protocol_automation_common import SHARED_DIR, WORKSPACE, load_json, standard_tool_artifact, write_json
from protocol_946_debug_common import WORLD_LOG_DEFAULT, duration_seconds, parse_timestamp


LIVE_VAR_PACKET_DOCTOR_JSON = "live-var-packet-doctor.json"
LIVE_VAR_PACKET_DOCTOR_MD = "live-var-packet-doctor.md"
DEFAULT_GOLDEN_LOG = WORKSPACE / "data" / "debug" / "golden-packets.log"
DEFAULT_LOADING_VAR_GATE_ARTIFACT = SHARED_DIR / "loading-var-gate-doctor.json"
WORLD_LINE_RE = re.compile(r"^(?P<timestamp>\S+)\s+(?P<kind>\S+)(?:\s+(?P<rest>.*))?$")
KV_RE = re.compile(r'([A-Za-z][A-Za-z0-9_-]*)=(".*?"|\S+)')
VARP_EVENT_RE = re.compile(
    r"^timestamp=(?P<timestamp>\S+)\s+direction=(?P<direction>\S+)\s+localSide=(?P<localSide>\S+)\s+"
    r"packet=(?P<packet>VARP_(?:SMALL|LARGE))\s+opcode=(?P<opcode>\d+).*?"
    r"remote=(?P<remote>\S+).*?"
    r"packetValue=Varp(?:Small|Large)\(id=(?P<id>-?\d+), value=(?P<value>-?\d+)\)"
)
IDS_RE = re.compile(r"\bids=(?P<ids>[0-9,]+)")
READY_MARKER_NEEDLE = "ready-signal"
RESET_MARKER = "world-send-reset-client-varcache"
DEFERRED_DEFAULT_VARP_MARKER = "world-send-deferred-default-varps"
DEFER_DEFAULT_VARP_MARKER = "world-defer-default-varps"
MINIMAL_VARCS_MARKER = "world-send-minimal-varcs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Correlate the latest plateau session with golden VARP traffic so candidate loading vars can be "
            "classified as sent, missing, or only sent before ResetClientVarcache."
        )
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--golden-log", type=Path, default=DEFAULT_GOLDEN_LOG)
    parser.add_argument("--loading-var-gate-artifact", type=Path, default=DEFAULT_LOADING_VAR_GATE_ARTIFACT)
    parser.add_argument("--world-tail-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--golden-tail-bytes", type=int, default=16 * 1024 * 1024)
    parser.add_argument("--golden-pad-seconds", type=float, default=5.0)
    parser.add_argument("--include-embedded", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    return parser.parse_args()


def output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "json": output_dir / LIVE_VAR_PACKET_DOCTOR_JSON,
        "markdown": output_dir / LIVE_VAR_PACKET_DOCTOR_MD,
    }


def read_tail_text(path: Path, max_bytes: int) -> str:
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        read_size = min(size, max_bytes)
        handle.seek(size - read_size)
        data = handle.read(read_size)
    text = data.decode("utf-8", errors="ignore")
    if read_size < size:
        newline = text.find("\n")
        if newline >= 0:
            text = text[newline + 1 :]
    return text


def latest_session_lines(world_log: Path, tail_bytes: int) -> list[str]:
    tail_text = read_tail_text(world_log, tail_bytes)
    if not tail_text:
        return []
    lines = [line for line in tail_text.splitlines() if line.strip()]
    appearance_indexes = [
        index
        for index, line in enumerate(lines)
        if " world-stage " in line and " stage=appearance" in line
    ]
    start_index = appearance_indexes[-1] if appearance_indexes else 0
    return lines[start_index:]


def extract_kv_pairs(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in KV_RE.findall(text):
        if len(value) >= 2 and value[0] == value[-1] == '"':
            result[key] = value[1:-1]
        else:
            result[key] = value
    return result


def parse_ids(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(part) for part in value.split(",") if part.strip().isdigit()]


def parse_latest_session(world_log: Path, tail_bytes: int) -> dict[str, Any]:
    lines = latest_session_lines(world_log, tail_bytes)
    if not lines:
        return {
            "exists": False,
            "lines": [],
            "markerCounts": {},
            "minimalVarcIds": [],
            "resetTimestamps": [],
            "readyAcceptedTimestamps": [],
            "deferredDefaultVarpsObserved": False,
            "deferDefaultVarpsObserved": False,
            "startTimestamp": "",
            "endTimestamp": "",
            "durationSeconds": None,
            "playerName": "",
        }

    marker_counts: Counter[str] = Counter()
    minimal_varc_ids: list[int] = []
    reset_timestamps: list[str] = []
    ready_timestamps: list[str] = []
    player_name = ""
    parsed_lines: list[dict[str, Any]] = []
    start_timestamp = ""
    end_timestamp = ""

    for line in lines:
        match = WORLD_LINE_RE.match(line)
        if not match:
            continue
        timestamp = match.group("timestamp")
        kind = match.group("kind")
        rest = match.group("rest") or ""
        data = extract_kv_pairs(rest)
        if not start_timestamp:
            start_timestamp = timestamp
        end_timestamp = timestamp
        if data.get("name") and not player_name:
            player_name = data["name"]
        if kind.startswith("world-"):
            marker_counts[kind] += 1
        if kind == RESET_MARKER:
            reset_timestamps.append(timestamp)
        elif kind == MINIMAL_VARCS_MARKER:
            ids_match = IDS_RE.search(rest)
            minimal_varc_ids.extend(parse_ids(ids_match.group("ids") if ids_match else data.get("ids")))
        elif kind.startswith("world-accept-") and READY_MARKER_NEEDLE in kind:
            ready_timestamps.append(timestamp)
        parsed_lines.append(
            {
                "timestamp": timestamp,
                "kind": kind,
                "data": data,
                "raw": line,
            }
        )

    return {
        "exists": True,
        "lines": parsed_lines,
        "markerCounts": dict(sorted(marker_counts.items())),
        "minimalVarcIds": sorted(dict.fromkeys(minimal_varc_ids)),
        "resetTimestamps": reset_timestamps,
        "readyAcceptedTimestamps": ready_timestamps,
        "deferredDefaultVarpsObserved": marker_counts.get(DEFERRED_DEFAULT_VARP_MARKER, 0) > 0,
        "deferDefaultVarpsObserved": marker_counts.get(DEFER_DEFAULT_VARP_MARKER, 0) > 0,
        "startTimestamp": start_timestamp,
        "endTimestamp": end_timestamp,
        "durationSeconds": duration_seconds(start_timestamp, end_timestamp) if start_timestamp and end_timestamp else None,
        "playerName": player_name,
    }


def candidate_varps_from_loading_artifact(artifact: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidate_varps = artifact.get("candidateVarps") or {}
    candidate_varbits = artifact.get("candidateVarbits") or {}
    combined: list[dict[str, Any]] = []
    seen: set[int] = set()
    for source_name in ("direct", "heuristic"):
        for entry in candidate_varps.get(source_name, []):
            if not isinstance(entry, dict):
                continue
            varp_id = entry.get("id")
            if not isinstance(varp_id, int) or varp_id in seen:
                continue
            seen.add(varp_id)
            combined.append(
                {
                    "id": varp_id,
                    "source": source_name,
                    "scriptIds": list(entry.get("scriptIds", [])),
                    "accesses": dict(entry.get("accesses", {})),
                    "meaning": dict(entry.get("meaning", {})),
                }
            )

    derived: list[dict[str, Any]] = []
    for source_name in ("direct", "heuristic"):
        for entry in candidate_varbits.get(source_name, []):
            if not isinstance(entry, dict):
                continue
            meaning = entry.get("meaning") if isinstance(entry.get("meaning"), dict) else {}
            base_var = meaning.get("baseVar")
            if not isinstance(base_var, int) or base_var in seen:
                continue
            seen.add(base_var)
            derived.append(
                {
                    "id": base_var,
                    "source": f"varbit-base:{source_name}",
                    "scriptIds": list(entry.get("scriptIds", [])),
                    "accesses": dict(entry.get("accesses", {})),
                    "meaning": {
                        "present": True,
                        "refType": "varp",
                        "id": base_var,
                        "domain": "",
                        "type": "",
                        "forceDefault": False,
                        "backingVarbitCount": 0,
                    },
                    "derivedFromVarbit": int(entry.get("id")) if isinstance(entry.get("id"), int) else None,
                }
            )
    return combined, derived


def parse_varp_events(
    golden_log: Path,
    start_timestamp: str,
    end_timestamp: str,
    tail_bytes: int,
    pad_seconds: float,
    *,
    include_embedded: bool,
) -> tuple[list[dict[str, Any]], int]:
    if not golden_log.exists() or not start_timestamp or not end_timestamp:
        return [], 0
    lower = parse_timestamp(start_timestamp)
    upper = parse_timestamp(end_timestamp)
    if not lower or not upper:
        return [], 0
    lower -= timedelta(seconds=max(pad_seconds / 2.0, 1.0))
    upper += timedelta(seconds=max(pad_seconds, 1.0))

    events: list[dict[str, Any]] = []
    ignored_embedded = 0
    for line in read_tail_text(golden_log, tail_bytes).splitlines():
        match = VARP_EVENT_RE.match(line)
        if not match:
            continue
        timestamp = match.group("timestamp")
        parsed = parse_timestamp(timestamp)
        if not parsed or parsed < lower or parsed > upper:
            continue
        remote = match.group("remote")
        if remote == "embedded" and not include_embedded:
            ignored_embedded += 1
            continue
        events.append(
            {
                "timestamp": timestamp,
                "packet": match.group("packet"),
                "opcode": int(match.group("opcode")),
                "id": int(match.group("id")),
                "value": int(match.group("value")),
                "remote": remote,
                "raw": line,
            }
        )
    return events, ignored_embedded


def compact_meaning(meaning: dict[str, Any]) -> dict[str, Any]:
    if not meaning:
        return {"present": False}
    return {
        "present": bool(meaning.get("present", False)),
        "domain": meaning.get("domain", ""),
        "type": meaning.get("type", ""),
        "forceDefault": bool(meaning.get("forceDefault", False)),
        "backingVarbitCount": int(meaning.get("backingVarbitCount", 0) or 0),
    }


def build_candidate_rows(
    session: dict[str, Any],
    candidates: list[dict[str, Any]],
    derived_candidates: list[dict[str, Any]],
    varp_events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_id: dict[int, list[dict[str, Any]]] = {}
    for event in varp_events:
        by_id.setdefault(event["id"], []).append(event)

    last_reset = parse_timestamp(session["resetTimestamps"][-1]) if session["resetTimestamps"] else None
    last_ready = parse_timestamp(session["readyAcceptedTimestamps"][-1]) if session["readyAcceptedTimestamps"] else None

    def summarize(row: dict[str, Any], *, derived: bool) -> dict[str, Any]:
        varp_id = row["id"]
        observed = by_id.get(varp_id, [])
        after_reset = []
        after_ready = []
        for event in observed:
            event_ts = parse_timestamp(event["timestamp"])
            if last_reset is None or (event_ts and event_ts > last_reset):
                after_reset.append(event)
            if last_ready is None or (event_ts and event_ts > last_ready):
                after_ready.append(event)

        if not observed:
            status = "never-sent"
        elif last_reset is not None and not after_reset:
            status = "sent-before-last-reset-only"
        elif last_ready is not None and not after_ready:
            status = "not-sent-after-ready"
        else:
            status = "sent-after-reset"

        reasons: list[str] = []
        if not observed:
            reasons.append("no VarpSmall/VarpLarge send observed in the latest plateau window")
        else:
            if last_reset is not None and not after_reset:
                reasons.append("all observed sends happened before the latest ResetClientVarcache")
            if last_ready is not None and not after_ready:
                reasons.append("no observed sends happened after the latest accepted ready marker")

        unique_values: list[int] = []
        seen_values: set[int] = set()
        for event in observed:
            value = event["value"]
            if value in seen_values:
                continue
            seen_values.add(value)
            unique_values.append(value)

        packet_counts = Counter(event["packet"] for event in observed)
        return {
            "id": varp_id,
            "status": status,
            "source": row["source"],
            "scriptIds": row.get("scriptIds", []),
            "accesses": row.get("accesses", {}),
            "meaning": compact_meaning(row.get("meaning", {})),
            "derived": derived,
            "derivedFromVarbit": row.get("derivedFromVarbit"),
            "observedCount": len(observed),
            "observedAfterResetCount": len(after_reset),
            "observedAfterReadyCount": len(after_ready),
            "packetCounts": dict(sorted(packet_counts.items())),
            "uniqueValues": unique_values[:8],
            "firstTimestamp": observed[0]["timestamp"] if observed else "",
            "lastTimestamp": observed[-1]["timestamp"] if observed else "",
            "reasons": reasons,
        }

    return (
        [summarize(row, derived=False) for row in candidates],
        [summarize(row, derived=True) for row in derived_candidates],
    )


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    session = parse_latest_session(args.world_log, args.world_tail_bytes)
    loading_artifact = load_json(args.loading_var_gate_artifact, {}) or {}
    candidates, derived_candidates = candidate_varps_from_loading_artifact(loading_artifact)
    varp_events, ignored_embedded_events = parse_varp_events(
        args.golden_log,
        session.get("startTimestamp", ""),
        session.get("endTimestamp", ""),
        args.golden_tail_bytes,
        args.golden_pad_seconds,
        include_embedded=bool(getattr(args, "include_embedded", False)),
    )
    candidate_rows, derived_rows = build_candidate_rows(session, candidates, derived_candidates, varp_events)

    observed_candidate_ids = {row["id"] for row in candidate_rows if row["observedCount"] > 0}
    sent_after_reset_ids = {row["id"] for row in candidate_rows if row["status"] == "sent-after-reset"}
    missing_after_reset = [row for row in candidate_rows if row["status"] != "sent-after-reset"]
    latest_likely_blocker = ((loading_artifact.get("summary") or {}).get("latestLikelyBlocker")) or "unknown"
    if session.get("resetTimestamps") and not sent_after_reset_ids:
        computed_blocker = "post-reset-candidate-varp-gap"
    elif missing_after_reset:
        computed_blocker = "partial-post-reset-candidate-varp-gap"
    else:
        computed_blocker = latest_likely_blocker

    needs: list[str] = []
    if session.get("resetTimestamps") and not session.get("deferredDefaultVarpsObserved"):
        needs.append("default varp handoff after ResetClientVarcache on the accepted-ready plateau path")
    if missing_after_reset:
        ids = ",".join(str(row["id"]) for row in missing_after_reset[:6])
        needs.append(f"candidate varps {ids} are still missing post-reset/send-after-ready evidence")
    if derived_rows:
        missing_derived = [row for row in derived_rows if row["status"] != "sent-after-reset"]
        if missing_derived:
            ids = ",".join(str(row["id"]) for row in missing_derived[:6])
            needs.append(f"base varps {ids} inferred from candidate varbits still lack post-reset evidence")
    if session.get("minimalVarcIds"):
        ids = ",".join(str(varc_id) for varc_id in session["minimalVarcIds"][:8])
        needs.append(f"confirm minimal varcs {ids} are sufficient for scene-start gating on the forced fallback path")
    if not needs:
        needs.append("first non-reference scene archive request after accepted-ready plateau")

    observed_varp_counts = Counter(event["id"] for event in varp_events)
    top_observed = [{"id": varp_id, "count": count} for varp_id, count in observed_varp_counts.most_common(12)]

    summary = {
        "latestLikelyBlocker": computed_blocker,
        "loadingVarGateBlocker": latest_likely_blocker,
        "candidateVarpCount": len(candidate_rows),
        "derivedCandidateBaseVarpCount": len(derived_rows),
        "candidateVarpsObserved": len(observed_candidate_ids),
        "candidateVarpsSentAfterReset": len(sent_after_reset_ids),
        "candidateVarpsMissingAfterReset": len(missing_after_reset),
        "goldenVarpEventCount": len(varp_events),
        "ignoredEmbeddedGoldenVarpEventCount": ignored_embedded_events,
        "resetClientVarcacheObserved": bool(session.get("resetTimestamps")),
        "deferredDefaultVarpsObserved": bool(session.get("deferredDefaultVarpsObserved")),
        "readyAcceptedObserved": bool(session.get("readyAcceptedTimestamps")),
        "minimalVarcIds": session.get("minimalVarcIds", []),
    }

    return standard_tool_artifact(
        tool_name="run_946_live_var_packet_doctor",
        status="ok" if session.get("exists") else "partial",
        inputs={
            "worldLog": str(args.world_log),
            "goldenLog": str(args.golden_log),
            "loadingVarGateArtifact": str(args.loading_var_gate_artifact),
            "includeEmbedded": bool(getattr(args, "include_embedded", False)),
        },
        artifacts={
            "liveVarPacketDoctorJson": str(args.output_dir / LIVE_VAR_PACKET_DOCTOR_JSON),
            "liveVarPacketDoctorMarkdown": str(args.output_dir / LIVE_VAR_PACKET_DOCTOR_MD),
        },
        summary=summary,
        extra={
            "session": session,
            "candidateVarps": candidate_rows,
            "derivedCandidateBaseVarps": derived_rows,
            "observedVarpEvents": varp_events[-32:],
            "observedTopVarps": top_observed,
            "verdict": {
                "likelyBlocker": computed_blocker,
                "needs": needs,
                "recommendation": (
                    "Use this report to verify whether the candidate loading vars were really handed off on the "
                    "latest plateau session. Missing post-reset varp evidence is a cleaner target than blindly "
                    "tweaking late bootstrap scripts."
                ),
            },
        },
    )


def render_candidate_section(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.append("- none")
        lines.append("")
        return lines
    for row in rows:
        meaning = row["meaning"]
        meaning_bits = []
        if meaning.get("domain"):
            meaning_bits.append(f"domain={meaning['domain']}")
        if meaning.get("type"):
            meaning_bits.append(f"type={meaning['type']}")
        meaning_bits.append(f"forceDefault={meaning.get('forceDefault', False)}")
        meaning_bits.append(f"backingVarbits={meaning.get('backingVarbitCount', 0)}")
        if row.get("derivedFromVarbit") is not None:
            meaning_bits.append(f"derivedFromVarbit={row['derivedFromVarbit']}")
        lines.append(
            f"- `varp {row['id']}` status=`{row['status']}` source=`{row['source']}` "
            f"observed=`{row['observedCount']}` afterReset=`{row['observedAfterResetCount']}` "
            f"afterReady=`{row['observedAfterReadyCount']}` values=`{row['uniqueValues']}` "
            f"scripts=`{row['scriptIds']}` {' '.join(meaning_bits)}"
        )
        for reason in row.get("reasons", []):
            lines.append(f"  reason: {reason}")
    lines.append("")
    return lines


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {})
    verdict = artifact.get("verdict", {})
    session = artifact.get("session", {})
    lines = [
        "# 946 Live Var Packet Doctor",
        "",
        f"- Status: `{artifact.get('status', 'unknown')}`",
        f"- Latest likely blocker: `{summary.get('latestLikelyBlocker', 'unknown')}`",
        f"- Candidate varps: `{summary.get('candidateVarpCount', 0)}`",
        f"- Candidate varps observed: `{summary.get('candidateVarpsObserved', 0)}`",
        f"- Candidate varps sent after reset: `{summary.get('candidateVarpsSentAfterReset', 0)}`",
        f"- Candidate varps missing after reset: `{summary.get('candidateVarpsMissingAfterReset', 0)}`",
        f"- Golden VARP events in window: `{summary.get('goldenVarpEventCount', 0)}`",
        f"- Ignored embedded golden VARP events: `{summary.get('ignoredEmbeddedGoldenVarpEventCount', 0)}`",
        f"- ResetClientVarcache observed: `{summary.get('resetClientVarcacheObserved', False)}`",
        f"- Deferred default varps observed: `{summary.get('deferredDefaultVarpsObserved', False)}`",
        f"- Ready accepted observed: `{summary.get('readyAcceptedObserved', False)}`",
        f"- Minimal varcs: `{summary.get('minimalVarcIds', [])}`",
        f"- Session window: `{session.get('startTimestamp', '')}` -> `{session.get('endTimestamp', '')}`",
        "",
        "## Exact Needs",
        "",
    ]
    for need in verdict.get("needs", []):
        lines.append(f"- {need}")
    lines.extend(["", "## Observed Top Varps", ""])
    observed = artifact.get("observedTopVarps", [])
    if not observed:
        lines.append("- none")
    for row in observed:
        lines.append(f"- `varp {row['id']}` count=`{row['count']}`")
    lines.append("")
    lines.extend(render_candidate_section("Candidate Varps", artifact.get("candidateVarps", [])))
    lines.extend(render_candidate_section("Derived Base Varps", artifact.get("derivedCandidateBaseVarps", [])))
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    artifact = build_artifact(args)
    paths = output_paths(args.output_dir)
    write_json(paths["json"], artifact)
    paths["markdown"].write_text(render_markdown(artifact), encoding="utf-8")
    print(render_markdown(artifact), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
