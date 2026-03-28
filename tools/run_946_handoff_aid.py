from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from protocol_automation_common import PHASE_DIRS, SHARED_DIR, ensure_directory, stable_json_text, write_json
from protocol_946_debug_common import (
    BUILD_ID,
    DECOMP_LOG_DIR_DEFAULT,
    HIGH_SIGNAL_HANDOFF_OPCODES,
    PLAYER_INFO_ENCODER,
    PLAYER_INFO_OPCODE,
    WORLD_LOG_DEFAULT,
    build_index,
    candidate_decomp_logs_for_selection,
    decomp_status_for_path,
    evidence_sender_fields,
    find_latest_session,
    load_phase_inputs,
    load_sender_analysis,
    load_session_input,
    observed_client_opcode_events,
    parse_world_log,
    phase3_sender_fields,
    sample_previews,
    session_summary,
    stage_counts,
    unresolved_client_candidates,
)


HANDOFF_JSON = "handoff-analysis.json"
HANDOFF_MD = "handoff-analysis.md"
HANDOFF_DIFF_JSON = "handoff-diff.json"
HANDOFF_DIFF_MD = "handoff-diff.md"
RUNTIME_HANDLED_KINDS = {
    "world-client-bootstrap-blob",
    "world-client-bootstrap-control",
    "world-client-display-config",
    "world-recv-serverperm-varcs",
}
RUNTIME_IGNORED_KINDS = {
    "world-ignore-client-compat",
    "world-ignore-client-timed",
    "world-ready-signal-skipped",
}
RUNTIME_UNHANDLED_KINDS = {"world-unhandled-client-compat"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize the latest RS3 946 post-login handoff window.")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--decomp-log-dir", type=Path, default=DECOMP_LOG_DIR_DEFAULT)
    parser.add_argument("--opcode", type=int, action="append", default=[])
    parser.add_argument("--sender-analysis-json", type=Path, default=SHARED_DIR / "sender-analysis.json")
    parser.add_argument("--auto-decompile-top", type=int, default=0)
    parser.add_argument("--compare-left", type=Path)
    parser.add_argument("--compare-right", type=Path)
    parser.add_argument("--compare-left-window")
    parser.add_argument("--compare-right-window")
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    return parser.parse_args()


def coverage_status(
    opcode: int,
    evidence_entry: dict[str, Any] | None,
    generated_index: dict[tuple[str, int], dict[str, Any]],
    verified_index: dict[tuple[str, int], dict[str, Any]],
) -> str:
    if ("client", opcode) in verified_index:
        return "verified"
    if ("client", opcode) in generated_index:
        return "generated"
    if evidence_entry and evidence_entry.get("hasManualRegistration") and evidence_entry.get("packetName"):
        return "manual"
    return "unresolved"


def sender_analysis_index(sender_analysis: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not isinstance(sender_analysis, dict):
        return {}
    senders = sender_analysis.get("senders")
    if not isinstance(senders, list):
        return {}
    return {
        int(entry["opcode"]): entry
        for entry in senders
        if isinstance(entry, dict) and isinstance(entry.get("opcode"), int)
    }


def preferred_decomp_log(addresses: list[str], decomp_log_dir: Path) -> Path | None:
    for address in addresses:
        if not address:
            continue
        path = decomp_log_dir / f"decomp-{address}.log"
        if path.exists():
            return path
    return None


def parse_player_info_encoder() -> dict[str, Any]:
    if not PLAYER_INFO_ENCODER.exists():
        return {
            "sourceFile": str(PLAYER_INFO_ENCODER),
            "exists": False,
            "sendAppearanceUpdates": None,
            "notes": [],
        }
    lines = PLAYER_INFO_ENCODER.read_text(encoding="utf-8").splitlines()
    send_appearance_updates = None
    notes: list[str] = []
    for index, line in enumerate(lines):
        if "SEND_APPEARANCE_UPDATES" in line and "=" in line:
            send_appearance_updates = line.rsplit("=", 1)[1].strip().lower() == "true"
        if "The first world frame must include the local player's appearance block" in line:
            note_lines = [line.strip().lstrip("/ ").strip()]
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip().lstrip("/ ").strip()
                if next_line:
                    note_lines.append(next_line)
            notes.append(" ".join(note_lines))
    return {
        "sourceFile": str(PLAYER_INFO_ENCODER),
        "exists": True,
        "sendAppearanceUpdates": send_appearance_updates,
        "notes": notes,
    }


def summarize_player_info(session: dict[str, Any] | None) -> dict[str, Any]:
    encoder_evidence = parse_player_info_encoder()
    if not session:
        return {
            "opcode": PLAYER_INFO_OPCODE,
            "sizes": [],
            "firstLargeSendSize": None,
            "repeatedTinyFrameCount": 0,
            "largestSize": None,
            "smallestSize": None,
            "stageDistribution": {},
            "appearanceBurstPresent": False,
            "repeatedTinyFrames": False,
            "needsReview": False,
            "encoderEvidence": encoder_evidence,
            "samplePreviews": [],
            "recommendedNextAction": "Capture a live handoff window before treating PLAYER_INFO as a current suspect.",
        }

    send_events = [
        event
        for event in session["events"]
        if event["kind"] == "send-raw" and event.get("opcode") == PLAYER_INFO_OPCODE
    ]
    sizes = [event["bytes"] for event in send_events if isinstance(event.get("bytes"), int)]
    first_large_send_size = next((size for size in sizes if size > 3), None)
    repeated_tiny_count = sum(1 for size in sizes if size == 3)
    stage_distribution = stage_counts(send_events)
    sample_events = [event for event in send_events if isinstance(event.get("bytes"), int) and event["bytes"] > 3]
    if not sample_events:
        sample_events = send_events[:3]
    appearance_burst_present = first_large_send_size is not None
    repeated_tiny_frames = repeated_tiny_count >= 3
    needs_review = repeated_tiny_frames and appearance_burst_present
    return {
        "opcode": PLAYER_INFO_OPCODE,
        "sizes": sizes[:128],
        "firstLargeSendSize": first_large_send_size,
        "repeatedTinyFrameCount": repeated_tiny_count,
        "largestSize": max(sizes) if sizes else None,
        "smallestSize": min(sizes) if sizes else None,
        "stageDistribution": stage_distribution,
        "appearanceBurstPresent": appearance_burst_present,
        "repeatedTinyFrames": repeated_tiny_frames,
        "needsReview": needs_review,
        "encoderEvidence": encoder_evidence,
        "samplePreviews": sample_previews(sample_events, limit=3),
        "recommendedNextAction": (
            "Verify why PLAYER_INFO collapses to repeated 3-byte frames after the initial appearance burst."
            if needs_review
            else "PLAYER_INFO does not currently look like the highest-value handoff lead."
        ),
    }


def classify_suspect(suspect: dict[str, Any]) -> str:
    runtime_markers = suspect.get("runtimeMarkers") or {}
    if runtime_markers.get("handled") and not runtime_markers.get("unhandled"):
        return "handled-report"
    if runtime_markers.get("unhandled"):
        return "likely-blocker"
    if runtime_markers.get("ignored") and not runtime_markers.get("handled"):
        return "state-report"
    sender_aid = suspect.get("senderAid") or {}
    body = str(sender_aid.get("decompiledBody", "")).lower()
    named_tokens = [token.lower() for token in sender_aid.get("descriptorEvidence", {}).get("namedTokens", [])]
    if any(token in body for token in ("getfocus", "getforegroundwindow", "getasynckeystate", "sendmessage", "postmessage")):
        return "state-report"
    if any(token in named_tokens for token in ("getfocus", "getforegroundwindow", "getasynckeystate", "sendmessage", "postmessage")):
        return "state-report"
    if len(suspect["observedStageCounts"]) >= 2 or suspect["opcode"] in HIGH_SIGNAL_HANDOFF_OPCODES:
        return "likely-blocker"
    return "unknown"


def recommended_next_action(suspect: dict[str, Any]) -> str:
    sender_name = suspect["senderFunction"]
    suspect_class = suspect["suspectClass"]
    if suspect_class == "handled-report":
        return f"Treat opcode {suspect['opcode']} as handled bootstrap traffic unless a later behavioral diff proves it still needs semantics."
    if suspect_class == "state-report":
        return f"Treat opcode {suspect['opcode']} as a likely state-report until a caller proves it blocks the handoff."
    if sender_name and suspect.get("senderAid", {}).get("status") == "clean":
        return f"Trace {sender_name} against the latest handoff burst and compare its clean sender body to the surviving client-state loop."
    if sender_name and suspect["decompLog"]["status"] in {"warning-only", "error-only", "missing"}:
        return f"Recover a readable decomp for {sender_name} before patching server-side handling of opcode {suspect['opcode']}."
    if suspect_class == "likely-blocker":
        return f"Keep opcode {suspect['opcode']} in the handoff shortlist and compare its stage burst with nearby unresolved suspects."
    return f"Locate the client sender for opcode {suspect['opcode']} before adding another compatibility patch."


def build_suspect_entry(
    *,
    opcode: int,
    candidate: dict[str, Any],
    evidence_entry: dict[str, Any] | None,
    generated_index: dict[tuple[str, int], dict[str, Any]],
    verified_index: dict[tuple[str, int], dict[str, Any]],
    observed_events: list[dict[str, Any]],
    session: dict[str, Any] | None,
    decomp_log_dir: Path,
    sender_aid_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    if evidence_entry:
        primary_sender, primary_sender_name, parser_target, parser_name = evidence_sender_fields(evidence_entry)
    else:
        primary_sender, primary_sender_name, parser_target, parser_name = phase3_sender_fields(candidate)

    matched_log = preferred_decomp_log([primary_sender, parser_target], decomp_log_dir)
    decomp_log = decomp_status_for_path(matched_log)
    if sender_aid_entry:
        decomp_log = {
            "status": sender_aid_entry.get("status", decomp_log["status"]),
            "path": sender_aid_entry.get("artifacts", {}).get("decompileStdoutLog", decomp_log.get("path", "")),
            "snippet": sender_aid_entry.get("decompSnippet", decomp_log.get("snippet", [])),
        }

    packet_name = ""
    suggested_name = str(candidate.get("suggestedName", "") or "")
    if ("client", opcode) in verified_index:
        packet_name = str(verified_index[("client", opcode)].get("packetName", "") or "")
    elif ("client", opcode) in generated_index:
        packet_name = str(generated_index[("client", opcode)].get("packetName", "") or "")
    elif evidence_entry:
        packet_name = str(evidence_entry.get("packetName", "") or "")
    else:
        packet_name = suggested_name

    first_stage = observed_events[0]["stage"] if observed_events else ""
    last_stage = observed_events[-1]["stage"] if observed_events else ""
    runtime_markers = Counter()
    if session:
        for event in session["events"]:
            if event.get("opcode") != opcode:
                continue
            kind = event.get("kind")
            if kind in RUNTIME_HANDLED_KINDS:
                runtime_markers["handled"] += 1
            elif kind in RUNTIME_IGNORED_KINDS:
                runtime_markers["ignored"] += 1
            elif kind in RUNTIME_UNHANDLED_KINDS:
                runtime_markers["unhandled"] += 1
    suspect = {
        "opcode": opcode,
        "side": "client",
        "packetName": packet_name,
        "suggestedName": suggested_name,
        "candidateStatus": str((evidence_entry or {}).get("status") or candidate.get("confidence") or "unresolved"),
        "size": candidate.get("size"),
        "family": str((evidence_entry or {}).get("family") or candidate.get("familyLabel") or ""),
        "coverageStatus": coverage_status(opcode, evidence_entry, generated_index, verified_index),
        "hasManualRegistration": bool((evidence_entry or {}).get("hasManualRegistration", False)),
        "senderFunction": (sender_aid_entry or {}).get("senderFunction") or primary_sender_name,
        "senderAddress": (sender_aid_entry or {}).get("senderAddress") or primary_sender,
        "parserFunction": parser_name,
        "parserTarget": parser_target,
        "decompLog": decomp_log,
        "observedCount": len(observed_events),
        "observedStageCounts": stage_counts(observed_events),
        "firstSeenStage": first_stage,
        "lastSeenStage": last_stage,
        "runtimeMarkers": dict(sorted(runtime_markers.items())),
        "samplePreviews": sample_previews(observed_events),
        "senderAid": sender_aid_entry or {},
    }
    suspect["suspectClass"] = classify_suspect(suspect)
    suspect["recommendedNextAction"] = recommended_next_action(suspect)
    return suspect


def score_suspect(suspect: dict[str, Any]) -> tuple[int, int]:
    stage_count = len(suspect["observedStageCounts"])
    runtime_markers = suspect.get("runtimeMarkers") or {}
    score = stage_count * 10
    score += int(runtime_markers.get("unhandled", 0)) * 20
    score -= int(runtime_markers.get("ignored", 0)) * 4
    if runtime_markers.get("handled"):
        score -= 12
    if suspect["senderFunction"]:
        score += 4
    if suspect["senderAid"].get("status") == "clean":
        score += 8
    elif suspect["decompLog"]["status"] in {"warning-only", "error-only"}:
        score += 2
    if suspect["opcode"] in HIGH_SIGNAL_HANDOFF_OPCODES:
        score += 10
    if suspect["suspectClass"] == "likely-blocker":
        score += 8
    elif suspect["suspectClass"] == "state-report":
        score -= 12
    return score, suspect["opcode"]


def rank_top_targets(suspects: list[dict[str, Any]], player_info: dict[str, Any]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for suspect in suspects:
        score, opcode = score_suspect(suspect)
        ranked.append(
            {
                "kind": "client-opcode",
                "opcode": opcode,
                "score": score,
                "reason": (
                    f"class={suspect['suspectClass']}; stages={len(suspect['observedStageCounts'])}"
                    + (f"; sender={suspect['senderFunction']}" if suspect["senderFunction"] else "")
                ),
                "nextAction": suspect["recommendedNextAction"],
                "suspectClass": suspect["suspectClass"],
            }
        )
    if player_info["needsReview"]:
        ranked.append(
            {
                "kind": "player-info",
                "opcode": PLAYER_INFO_OPCODE,
                "score": 8,
                "reason": "initial appearance burst is followed by sustained 3-byte PLAYER_INFO frames",
                "nextAction": player_info["recommendedNextAction"],
                "suspectClass": "unknown",
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["opcode"], item["kind"]))
    return ranked[:8]


def analyze_handoff(
    *,
    world_log_path: Path,
    decomp_log_dir: Path,
    manual_opcodes: list[int],
    sender_analysis: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    inputs = load_phase_inputs()
    generated_index = build_index(inputs["generatedPackets"])
    verified_index = build_index(inputs["verifiedPackets"])
    evidence_index = build_index(inputs["evidenceIndex"])
    unresolved = unresolved_client_candidates(inputs["phase3Candidates"], generated_index, verified_index)
    sender_index = sender_analysis_index(sender_analysis)

    notes: list[str] = []
    status = "ok"
    events = parse_world_log(world_log_path)
    session = find_latest_session(events) if events else None
    observed_events = observed_client_opcode_events(session)

    if not world_log_path.exists():
        status = "partial"
        notes.append("world-bootstrap-raw.log missing; suspects are limited to generated evidence only.")
    elif not session:
        status = "partial"
        notes.append("No post-login session window found in world-bootstrap-raw.log.")

    suspect_opcodes = set(manual_opcodes)
    suspect_opcodes.update(opcode for opcode in unresolved if opcode in observed_events)
    suspect_opcodes.update(opcode for opcode in HIGH_SIGNAL_HANDOFF_OPCODES if opcode in observed_events)
    suspect_opcodes = {opcode for opcode in suspect_opcodes if opcode in unresolved}

    suspects: list[dict[str, Any]] = []
    used_decomp_logs: list[Path] = []
    for opcode in sorted(suspect_opcodes):
        candidate = unresolved[opcode]
        evidence_entry = evidence_index.get(("client", opcode))
        suspect = build_suspect_entry(
            opcode=opcode,
            candidate=candidate,
            evidence_entry=evidence_entry,
            generated_index=generated_index,
            verified_index=verified_index,
            observed_events=observed_events.get(opcode, []),
            session=session,
            decomp_log_dir=decomp_log_dir,
            sender_aid_entry=sender_index.get(opcode),
        )
        suspects.append(suspect)
        decomp_path = suspect["decompLog"].get("path")
        if decomp_path:
            used_decomp_logs.append(Path(decomp_path))

    used_decomp_logs = sorted({path for path in used_decomp_logs if path})
    player_info = summarize_player_info(session)
    top_targets = rank_top_targets(suspects, player_info)

    if any(suspect["decompLog"]["status"] == "missing" and suspect["senderFunction"] for suspect in suspects):
        notes.append("Some unresolved suspects have sender evidence but no matching decomp log on disk.")
    if any(suspect["senderAid"].get("status") == "clean" for suspect in suspects):
        notes.append("Sender-aid output was used to normalize mixed-encoding decomp evidence.")
    if any(suspect["suspectClass"] == "state-report" for suspect in suspects):
        notes.append("One or more suspects currently look like periodic/state-report traffic rather than a direct handoff blocker.")
    if notes and status == "ok":
        status = "partial"

    artifact = {
        "build": BUILD_ID,
        "status": status,
        "sources": {
            "phase3NameCandidates": str(PHASE_DIRS[3] / "nameCandidates.json"),
            "phase5GeneratedPackets": str(PHASE_DIRS[5] / "generatedPackets.json"),
            "sharedVerifiedPackets": str(SHARED_DIR / "verified-packets.json"),
            "sharedEvidenceIndex": str(SHARED_DIR / "evidence-index.json"),
            "worldLog": str(world_log_path),
            "decompLogDir": str(decomp_log_dir),
            "senderAnalysisJson": str((sender_analysis or {}).get("sources", {}).get("handoffJson", "")) if sender_analysis else "",
            "playerInfoEncoder": str(PLAYER_INFO_ENCODER),
        },
        "session": session_summary(session),
        "suspects": suspects,
        "playerInfo": player_info,
        "topTargets": top_targets,
        "usedDecompLogs": [str(path) for path in used_decomp_logs],
        "notes": notes,
    }
    return artifact, used_decomp_logs


def render_markdown(artifact: dict[str, Any]) -> str:
    session = artifact["session"]
    lines = [
        "# 946 Handoff Analysis",
        "",
        f"- Build: `{artifact['build']}`",
        f"- Status: `{artifact['status']}`",
        f"- Session window: `{session['startLine']}` -> `{session['endLine']}`",
        f"- Session stages: `{', '.join(session['stageSequence']) or 'none'}`",
        "",
        "## Top Targets",
        "",
    ]
    if artifact["topTargets"]:
        for entry in artifact["topTargets"]:
            label = f"opcode {entry['opcode']}" if entry["kind"] == "client-opcode" else "PLAYER_INFO"
            lines.append(f"- `{label}` score=`{entry['score']}` class=`{entry['suspectClass']}` reason=`{entry['reason']}`")
            lines.append(f"  next: {entry['nextAction']}")
    else:
        lines.append("- No handoff targets found in the latest session window")

    player_info = artifact["playerInfo"]
    lines.extend(
        [
            "",
            "## PLAYER_INFO",
            "",
            f"- Opcode: `{player_info['opcode']}`",
            f"- First large send: `{player_info['firstLargeSendSize']}`",
            f"- Repeated 3-byte sends: `{player_info['repeatedTinyFrameCount']}`",
            f"- Size range: `{player_info['smallestSize']}` -> `{player_info['largestSize']}`",
            f"- Stage distribution: `{player_info['stageDistribution']}`",
            f"- Appearance burst present: `{player_info['appearanceBurstPresent']}`",
            f"- Needs review: `{player_info['needsReview']}`",
            f"- Next action: {player_info['recommendedNextAction']}",
            "",
            "## Suspects",
            "",
        ]
    )
    if artifact["suspects"]:
        for suspect in artifact["suspects"]:
            name = suspect["packetName"] or suspect["suggestedName"] or "UNRESOLVED"
            lines.append(f"### Opcode {suspect['opcode']} `{name}`")
            lines.append("")
            lines.append(f"- Coverage status: `{suspect['coverageStatus']}`")
            lines.append(f"- Candidate status: `{suspect['candidateStatus']}`")
            lines.append(f"- Suspect class: `{suspect['suspectClass']}`")
            lines.append(f"- Size: `{suspect['size']}` family=`{suspect['family']}`")
            lines.append(f"- Sender: `{suspect['senderFunction'] or 'unknown'}`")
            lines.append(f"- Decomp log: `{suspect['decompLog']['status']}` `{suspect['decompLog']['path']}`")
            lines.append(f"- Stage counts: `{suspect['observedStageCounts']}`")
            lines.append(f"- Runtime markers: `{suspect.get('runtimeMarkers', {})}`")
            lines.append(f"- First/last stage: `{suspect['firstSeenStage']}` -> `{suspect['lastSeenStage']}`")
            lines.append(f"- Next action: {suspect['recommendedNextAction']}")
            if suspect["samplePreviews"]:
                lines.append("- Sample previews:")
                for sample in suspect["samplePreviews"]:
                    lines.append(
                        f"  - line `{sample['lineNumber']}` stage=`{sample['stage']}` bytes=`{sample['bytes']}` preview=`{sample['preview']}`"
                    )
            sender_aid = suspect.get("senderAid") or {}
            if sender_aid.get("callerChain"):
                lines.append("- Sender aid caller chain:")
                for snippet in sender_aid["callerChain"][:6]:
                    lines.append(f"  - `{snippet}`")
            if suspect["decompLog"]["snippet"]:
                lines.append("- Decomp snippet:")
                for snippet in suspect["decompLog"]["snippet"]:
                    lines.append(f"  - `{snippet}`")
            lines.append("")
    else:
        lines.append("- No unresolved client opcodes from the latest handoff window matched the current filters.")
        lines.append("")

    if artifact["notes"]:
        lines.append("## Notes")
        lines.append("")
        for note in artifact["notes"]:
            lines.append(f"- {note}")
        lines.append("")
    return "\n".join(lines)


def build_handoff_diff(left_session: dict[str, Any] | None, right_session: dict[str, Any] | None) -> dict[str, Any]:
    left_summary = session_summary(left_session)
    right_summary = session_summary(right_session)
    left_events = observed_client_opcode_events(left_session)
    right_events = observed_client_opcode_events(right_session)
    all_opcodes = sorted(set(left_events) | set(right_events))

    only_left = [opcode for opcode in all_opcodes if opcode in left_events and opcode not in right_events]
    only_right = [opcode for opcode in all_opcodes if opcode in right_events and opcode not in left_events]
    changes: list[dict[str, Any]] = []
    for opcode in all_opcodes:
        left_count = len(left_events.get(opcode, []))
        right_count = len(right_events.get(opcode, []))
        if left_count == right_count and stage_counts(left_events.get(opcode, [])) == stage_counts(right_events.get(opcode, [])):
            continue
        changes.append(
            {
                "opcode": opcode,
                "leftCount": left_count,
                "rightCount": right_count,
                "leftStages": stage_counts(left_events.get(opcode, [])),
                "rightStages": stage_counts(right_events.get(opcode, [])),
                "leftSamples": sample_previews(left_events.get(opcode, [])),
                "rightSamples": sample_previews(right_events.get(opcode, [])),
            }
        )
    changes.sort(key=lambda item: (-abs(item["leftCount"] - item["rightCount"]), item["opcode"]))
    return {
        "status": "ok" if left_session and right_session else "partial",
        "leftSession": left_summary,
        "rightSession": right_summary,
        "onlyInLeft": only_left,
        "onlyInRight": only_right,
        "changes": changes,
    }


def render_diff_markdown(diff: dict[str, Any]) -> str:
    lines = [
        "# 946 Handoff Diff",
        "",
        f"- Status: `{diff['status']}`",
        f"- Left window: `{diff['leftSession']['startLine']}` -> `{diff['leftSession']['endLine']}`",
        f"- Right window: `{diff['rightSession']['startLine']}` -> `{diff['rightSession']['endLine']}`",
        "",
        "## Opcode Deltas",
        "",
    ]
    if diff["onlyInLeft"]:
        lines.append(f"- Only in left: `{diff['onlyInLeft']}`")
    if diff["onlyInRight"]:
        lines.append(f"- Only in right: `{diff['onlyInRight']}`")
    if not diff["changes"]:
        lines.append("- No opcode-stage differences found.")
    else:
        for change in diff["changes"][:16]:
            lines.append(
                f"- opcode `{change['opcode']}` left=`{change['leftCount']}` {change['leftStages']} right=`{change['rightCount']}` {change['rightStages']}"
            )
    lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    ensure_directory(output_dir)
    json_path = output_dir / HANDOFF_JSON
    md_path = output_dir / HANDOFF_MD
    write_json(json_path, artifact)
    md_path.write_text(render_markdown(artifact), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def write_diff_artifacts(output_dir: Path, diff: dict[str, Any]) -> dict[str, str]:
    ensure_directory(output_dir)
    json_path = output_dir / HANDOFF_DIFF_JSON
    md_path = output_dir / HANDOFF_DIFF_MD
    write_json(json_path, diff)
    md_path.write_text(render_diff_markdown(diff), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def maybe_run_sender_aid(args: argparse.Namespace, initial_artifact: dict[str, Any]) -> dict[str, Any]:
    if args.auto_decompile_top <= 0:
        return load_sender_analysis(args.sender_analysis_json)
    top_opcodes = [
        int(entry["opcode"])
        for entry in initial_artifact.get("topTargets", [])
        if isinstance(entry, dict)
        and entry.get("kind") == "client-opcode"
        and isinstance(entry.get("opcode"), int)
    ][: args.auto_decompile_top]
    if not top_opcodes:
        return load_sender_analysis(args.sender_analysis_json)

    command = [sys.executable, str(Path(__file__).with_name("run_946_sender_aid.py"))]
    command.extend(["--handoff-json", str(args.output_dir / HANDOFF_JSON)])
    command.extend(["--world-log", str(args.world_log)])
    command.extend(["--decomp-log-dir", str(args.decomp_log_dir)])
    command.extend(["--output-dir", str(args.output_dir)])
    for opcode in top_opcodes:
        command.extend(["--opcode", str(opcode)])
    completed = subprocess.run(
        command,
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return load_sender_analysis(args.sender_analysis_json)
    return load_sender_analysis(args.output_dir / "sender-analysis.json")


def main() -> int:
    args = parse_args()
    sender_analysis = load_sender_analysis(args.sender_analysis_json)
    artifact, _ = analyze_handoff(
        world_log_path=args.world_log,
        decomp_log_dir=args.decomp_log_dir,
        manual_opcodes=sorted(set(args.opcode)),
        sender_analysis=sender_analysis,
    )
    paths = write_artifacts(args.output_dir, artifact)

    if args.auto_decompile_top > 0:
        sender_analysis = maybe_run_sender_aid(args, artifact)
        artifact, _ = analyze_handoff(
            world_log_path=args.world_log,
            decomp_log_dir=args.decomp_log_dir,
            manual_opcodes=sorted(set(args.opcode)),
            sender_analysis=sender_analysis,
        )
        paths = write_artifacts(args.output_dir, artifact)

    diff_paths: dict[str, str] | None = None
    if args.compare_left and args.compare_right:
        diff = build_handoff_diff(
            load_session_input(args.compare_left, args.compare_left_window),
            load_session_input(args.compare_right, args.compare_right_window),
        )
        diff_paths = write_diff_artifacts(args.output_dir, diff)

    output = {"status": artifact["status"], "artifacts": paths}
    if diff_paths:
        output["diffArtifacts"] = diff_paths
    print(stable_json_text(output), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
