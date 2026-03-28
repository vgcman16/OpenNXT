from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from protocol_automation_common import SHARED_DIR, ensure_directory, load_json, stable_json_text, write_json
from protocol_946_debug_common import (
    BUILD_ID,
    WORLD_LOG_DEFAULT,
    find_latest_session,
    observed_client_opcode_events,
    parse_world_log,
    sample_previews,
    stage_counts,
)


OPCODE = 113
VERDICT_JSON = "opcode-113-verdict.json"
VERDICT_MD = "opcode-113-verdict.md"
ACTIVE_SUB_JSON = SHARED_DIR / "active-sub-analysis.json"
FOCUS_TOKENS = {"getfocus", "setfocus", "getforegroundwindow", "getasynckeystate", "sendmessage", "postmessage"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Classify RS3 946 client opcode 113 from existing sender and handoff evidence.")
    parser.add_argument("--opcode", type=int, default=OPCODE)
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--sender-analysis-json", type=Path, default=SHARED_DIR / "sender-analysis.json")
    parser.add_argument("--handoff-json", type=Path, default=SHARED_DIR / "handoff-analysis.json")
    parser.add_argument("--active-sub-json", type=Path, default=ACTIVE_SUB_JSON)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    return parser.parse_args()


def normalize_address(value: str | None) -> str:
    if not value:
        return ""
    cleaned = value.strip().lower()
    return cleaned[2:] if cleaned.startswith("0x") else cleaned


def find_sender_entry(sender_analysis: dict[str, Any], opcode: int) -> dict[str, Any]:
    for entry in sender_analysis.get("senders", []):
        if isinstance(entry, dict) and entry.get("opcode") == opcode:
            return entry
    return {}


def find_handoff_suspect(handoff_analysis: dict[str, Any], opcode: int) -> dict[str, Any]:
    for entry in handoff_analysis.get("suspects", []):
        if isinstance(entry, dict) and entry.get("opcode") == opcode:
            return entry
    return {}


def parse_preview_bytes(preview: str) -> list[int]:
    if not preview or len(preview) % 2 != 0:
        return []
    try:
        return list(bytes.fromhex(preview))
    except ValueError:
        return []


def collect_live_events(world_log: Path, opcode: int) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    if not world_log.exists():
        return None, []
    events = parse_world_log(world_log)
    session = find_latest_session(events)
    observed = observed_client_opcode_events(session).get(opcode, []) if session else []
    return session, observed


def summarize_live_values(events: list[dict[str, Any]], fallback: dict[str, Any]) -> dict[str, Any]:
    previews = [str(event.get("preview", "")) for event in events if event.get("preview")]
    if not previews:
        previews = [str(item.get("preview", "")) for item in fallback.get("samplePreviews", []) if item.get("preview")]
    preview_bytes = [parse_preview_bytes(preview) for preview in previews]
    preview_bytes = [entry for entry in preview_bytes if entry]
    unique_tails = sorted({f"0x{entry[3]:02x}" for entry in preview_bytes if len(entry) >= 4})
    zero_prefixed = [entry for entry in preview_bytes if len(entry) >= 4 and entry[:3] == [0, 0, 0]]
    stage_counts_value = stage_counts(events) if events else dict(fallback.get("observedStageCounts", {}))
    samples = sample_previews(events) if events else list(fallback.get("samplePreviews", []))
    return {
        "observedCount": len(events) if events else int(fallback.get("observedCount", 0)),
        "observedStageCounts": stage_counts_value,
        "samplePreviews": samples,
        "uniquePreviews": sorted(set(previews))[:16],
        "uniqueTailBytes": unique_tails,
        "zeroPrefixedSampleCount": len(zero_prefixed),
        "allParsedSamplesUseZeroPrefix": bool(preview_bytes) and len(zero_prefixed) == len(preview_bytes),
        "matchesPayloadHypothesis": bool(preview_bytes) and len(zero_prefixed) == len(preview_bytes),
    }


def assess_trigger(sender_entry: dict[str, Any], live_summary: dict[str, Any]) -> dict[str, Any]:
    body = str(sender_entry.get("decompiledBody", ""))
    body_lower = body.lower()
    named_tokens = {str(token).lower() for token in sender_entry.get("descriptorEvidence", {}).get("namedTokens", [])}
    caller_text = " ".join(str(line).lower() for line in sender_entry.get("callerChain", []))

    timer_evidence: list[str] = []
    if "+ 10000" in body:
        timer_evidence.append("Containing function sets a +10000 timer threshold before enabling the send flag.")
    if "0x77c0" in body and "0x77b8" in body:
        timer_evidence.append("Function toggles a dedicated pending flag/state pair at +0x77c0/+0x77b8.")
    timer_value = "yes" if timer_evidence else "unknown"

    focus_evidence: list[str] = []
    matched_focus_tokens = sorted(token for token in named_tokens if token in FOCUS_TOKENS)
    if matched_focus_tokens:
        focus_evidence.append(f"Named tokens explicitly mention focus/window APIs: {matched_focus_tokens}.")
    if any(token in caller_text for token in FOCUS_TOKENS):
        focus_evidence.append("Caller chain mentions focus/window APIs.")
    focus_value = "yes" if focus_evidence else "unknown"

    handshake_evidence: list[str] = []
    interfaces_count = int(live_summary["observedStageCounts"].get("interfaces", 0))
    rebuild_count = int(live_summary["observedStageCounts"].get("rebuild", 0))
    if interfaces_count >= 5:
        handshake_evidence.append("Opcode 113 repeats heavily during the interfaces stage instead of appearing as a one-shot bootstrap handshake.")
    if timer_value == "yes":
        handshake_evidence.append("Timer gating points to periodic state transmission rather than a single world-ready transition.")
    if rebuild_count <= 1 and interfaces_count > rebuild_count:
        handshake_evidence.append("The live burst is dominated by interfaces-stage repeats after rebuild.")
    handshake_value = "unlikely" if handshake_evidence else "unknown"

    return {
        "timerDriven": {"value": timer_value, "evidence": timer_evidence},
        "focusWindowStateDriven": {"value": focus_value, "evidence": focus_evidence},
        "worldHandshakeDriven": {"value": handshake_value, "evidence": handshake_evidence},
    }


def summarize_payload(sender_entry: dict[str, Any], live_summary: dict[str, Any]) -> dict[str, Any]:
    body = str(sender_entry.get("decompiledBody", ""))
    fields: list[dict[str, Any]] = []
    notes: list[str] = []
    writer_pattern = "unknown"

    if "FUN_1400bbb90" in body:
        fields.append(
            {
                "index": 0,
                "width": 2,
                "kind": "little-endian ushort",
                "source": "FUN_1400bbb90()",
                "notes": "The function writes the low byte first and the high byte second.",
            }
        )
    if "+ 0x55c" in body:
        fields.append(
            {
                "index": 1,
                "width": 1,
                "kind": "transformed state byte",
                "source": "*(session + 0x55c)",
                "notes": "The byte is clamped and then written with a -0x80 transform.",
            }
        )
    if "*(undefined1 *)(*(longlong *)(local_20 + 0x18) + *(longlong *)(local_20 + 0x20)) = 0;" in body:
        writer_pattern = "zero-prefix + little-endian ushort + transformed state byte"
        notes.append("The packet writer zeroes the leading byte before writing the two-byte value and trailing state byte.")

    if live_summary["matchesPayloadHypothesis"]:
        notes.append("Observed previews stay zero-prefixed and only the last byte varies in sampled live traffic.")

    return {
        "observedPacketSize": 4,
        "writerPattern": writer_pattern,
        "fields": fields,
        "notes": notes,
    }


def build_address_validation(sender_entry: dict[str, Any]) -> dict[str, Any]:
    requested_address = normalize_address(sender_entry.get("requestedSenderAddress") or sender_entry.get("senderAddress"))
    resolved_entry = normalize_address(sender_entry.get("resolvedFunctionEntry"))
    return {
        "requestedSenderFunction": sender_entry.get("requestedSenderFunction") or sender_entry.get("senderFunction") or "",
        "requestedSenderAddress": requested_address,
        "resolvedFunctionName": sender_entry.get("resolvedFunctionName", ""),
        "resolvedFunctionEntry": resolved_entry,
        "matchesRequestedAddress": bool(requested_address) and requested_address == resolved_entry,
        "callerLookupFunction": sender_entry.get("callerLookupFunction", ""),
        "callerLookupAddress": normalize_address(sender_entry.get("callerLookupAddress")),
        "callerLookupSource": sender_entry.get("callerLookupSource", ""),
    }


def decide_verdict(
    sender_entry: dict[str, Any],
    trigger_assessment: dict[str, Any],
    live_summary: dict[str, Any],
) -> tuple[str, list[str], str]:
    rationale: list[str] = []
    observed_count = int(live_summary.get("observedCount", 0))
    interfaces_count = int(live_summary.get("observedStageCounts", {}).get("interfaces", 0))
    timer_driven = trigger_assessment["timerDriven"]["value"] == "yes"
    handshake_unlikely = trigger_assessment["worldHandshakeDriven"]["value"] == "unlikely"
    has_caller_proof = bool(sender_entry.get("callerRefs"))
    payload_matches = bool(live_summary.get("matchesPayloadHypothesis"))

    if timer_driven:
        rationale.extend(trigger_assessment["timerDriven"]["evidence"])
    if handshake_unlikely:
        rationale.extend(trigger_assessment["worldHandshakeDriven"]["evidence"])

    if timer_driven and handshake_unlikely and payload_matches and observed_count >= 3 and interfaces_count >= 2:
        rationale.append("The live burst looks periodic and state-bearing rather than like a single handshake gate.")
        return "state-report", rationale, "medium"

    if has_caller_proof and not handshake_unlikely:
        rationale.append("Caller proof ties the packet to a specific code path that still looks handoff-relevant.")
        return "likely-blocker", rationale, "medium"

    rationale.append("The containing function is readable, but caller/context proof is still too thin to promote or dismiss it conclusively.")
    return "uncertain-needs-caller-proof", rationale, "medium"


def next_lead(verdict: str, active_sub_analysis: dict[str, Any]) -> dict[str, Any]:
    if verdict != "state-report":
        return {}
    target_116 = {}
    for entry in active_sub_analysis.get("targets", []):
        if isinstance(entry, dict) and entry.get("opcode") == 116:
            target_116 = entry
            break
    reason = (
        "Opcode 116 already exports a usable active-sub shape and becomes the next missing UI-path lead once 113 is ruled out."
    )
    if target_116:
        reason = (
            f"Opcode 116 exported {target_116.get('exportedFieldTypes', [])} with {target_116.get('confidence', 'unknown')} confidence, "
            "so it is the next concrete world-UI handoff candidate after ruling out 113."
        )
    return {
        "opcode": 116,
        "side": "server",
        "reason": reason,
    }


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    sender_analysis = load_json(args.sender_analysis_json, {})
    handoff_analysis = load_json(args.handoff_json, {})
    active_sub_analysis = load_json(args.active_sub_json, {})
    sender_entry = find_sender_entry(sender_analysis, args.opcode)
    handoff_entry = find_handoff_suspect(handoff_analysis, args.opcode)
    _, live_events = collect_live_events(args.world_log, args.opcode)

    status = "ok"
    notes: list[str] = []
    if not sender_entry:
        status = "partial"
        notes.append("Sender analysis does not currently include opcode 113.")
    if sender_entry and sender_entry.get("status") != "clean":
        status = "partial"
        notes.append("Sender analysis for opcode 113 is not clean.")
    if not handoff_entry:
        status = "partial"
        notes.append("Handoff analysis does not currently include opcode 113.")

    live_summary = summarize_live_values(live_events, sender_entry.get("packetSizeEvidence", {}))
    trigger_assessment = assess_trigger(sender_entry, live_summary)
    payload_summary = summarize_payload(sender_entry, live_summary)
    address_validation = build_address_validation(sender_entry)
    verdict, rationale, confidence = decide_verdict(sender_entry, trigger_assessment, live_summary)
    if not address_validation["matchesRequestedAddress"] and address_validation["resolvedFunctionEntry"]:
        notes.append(
            f"Requested sender address {address_validation['requestedSenderAddress']} resolves inside "
            f"{address_validation['resolvedFunctionName']} @ {address_validation['resolvedFunctionEntry']}."
        )
    if not sender_entry.get("callerRefs"):
        notes.append("Caller proof remains thin; the verdict relies primarily on the containing-function body plus live packet values.")
    if verdict == "state-report":
        notes.append("Opcode 67 remains out of scope here; it is still a separate parser/export recovery task.")

    return {
        "build": BUILD_ID,
        "opcode": args.opcode,
        "status": status,
        "verdict": verdict,
        "confidence": confidence,
        "sources": {
            "senderAnalysisJson": str(args.sender_analysis_json),
            "handoffAnalysisJson": str(args.handoff_json),
            "activeSubAnalysisJson": str(args.active_sub_json),
            "worldLog": str(args.world_log),
        },
        "addressValidation": address_validation,
        "triggerAssessment": trigger_assessment,
        "payloadSummary": payload_summary,
        "liveValueCorrelation": live_summary,
        "handoffContext": {
            "suspectClass": handoff_entry.get("suspectClass", ""),
            "coverageStatus": handoff_entry.get("coverageStatus", ""),
            "observedStageCounts": handoff_entry.get("observedStageCounts", live_summary.get("observedStageCounts", {})),
            "firstSeenStage": handoff_entry.get("firstSeenStage", ""),
            "lastSeenStage": handoff_entry.get("lastSeenStage", ""),
        },
        "senderContext": {
            "senderFunction": sender_entry.get("senderFunction", ""),
            "senderAddress": sender_entry.get("senderAddress", ""),
            "resolvedFunctionName": sender_entry.get("resolvedFunctionName", ""),
            "resolvedFunctionEntry": sender_entry.get("resolvedFunctionEntry", ""),
            "callerLookupFunction": sender_entry.get("callerLookupFunction", ""),
            "callerLookupAddress": sender_entry.get("callerLookupAddress", ""),
            "callerLookupSource": sender_entry.get("callerLookupSource", ""),
            "callerRefs": sender_entry.get("callerRefs", []),
        },
        "rationale": rationale,
        "nextLead": next_lead(verdict, active_sub_analysis),
        "notes": notes,
    }


def render_markdown(artifact: dict[str, Any]) -> str:
    lines = [
        "# Opcode 113 Verdict",
        "",
        f"- Build: `{artifact['build']}`",
        f"- Status: `{artifact['status']}`",
        f"- Verdict: `{artifact['verdict']}`",
        f"- Confidence: `{artifact['confidence']}`",
        "",
        "## Address Validation",
        "",
        f"- Requested sender: `{artifact['addressValidation']['requestedSenderFunction']}` `{artifact['addressValidation']['requestedSenderAddress']}`",
        f"- Resolved containing function: `{artifact['addressValidation']['resolvedFunctionName']}` `{artifact['addressValidation']['resolvedFunctionEntry']}`",
        f"- Caller lookup: source=`{artifact['addressValidation']['callerLookupSource']}` target=`{artifact['addressValidation']['callerLookupFunction']}` `{artifact['addressValidation']['callerLookupAddress']}`",
        "",
        "## Trigger Assessment",
        "",
        f"- Timer driven: `{artifact['triggerAssessment']['timerDriven']['value']}`",
        f"- Focus/window-state driven: `{artifact['triggerAssessment']['focusWindowStateDriven']['value']}`",
        f"- World-handshake driven: `{artifact['triggerAssessment']['worldHandshakeDriven']['value']}`",
        "",
        "## Payload",
        "",
        f"- Observed packet size: `{artifact['payloadSummary']['observedPacketSize']}`",
        f"- Writer pattern: `{artifact['payloadSummary']['writerPattern']}`",
        "",
        "## Live Correlation",
        "",
        f"- Observed count: `{artifact['liveValueCorrelation']['observedCount']}`",
        f"- Stage counts: `{artifact['liveValueCorrelation']['observedStageCounts']}`",
        f"- Unique previews: `{artifact['liveValueCorrelation']['uniquePreviews']}`",
        f"- Unique tail bytes: `{artifact['liveValueCorrelation']['uniqueTailBytes']}`",
        f"- Zero-prefixed samples: `{artifact['liveValueCorrelation']['zeroPrefixedSampleCount']}`",
        f"- Matches payload hypothesis: `{artifact['liveValueCorrelation']['matchesPayloadHypothesis']}`",
        "",
        "## Rationale",
        "",
    ]
    for item in artifact.get("rationale", []):
        lines.append(f"- {item}")
    next_lead_entry = artifact.get("nextLead") or {}
    if next_lead_entry:
        lines.extend(
            [
                "",
                "## Next Lead",
                "",
                f"- Opcode `{next_lead_entry['opcode']}` `{next_lead_entry['side']}`",
                f"- Reason: {next_lead_entry['reason']}",
            ]
        )
    if artifact.get("notes"):
        lines.extend(["", "## Notes", ""])
        for note in artifact["notes"]:
            lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    ensure_directory(output_dir)
    json_path = output_dir / VERDICT_JSON
    md_path = output_dir / VERDICT_MD
    write_json(json_path, artifact)
    md_path.write_text(render_markdown(artifact), encoding="utf-8")
    return {
        "json": str(json_path),
        "markdown": str(md_path),
    }


def main() -> int:
    args = parse_args()
    artifact = build_artifact(args)
    paths = write_artifacts(args.output_dir, artifact)
    print(stable_json_text({"status": artifact["status"], "artifacts": paths}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
