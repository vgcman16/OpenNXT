from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
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
from protocol_946_debug_common import (
    WORLD_LOG_DEFAULT,
    POST_LOGIN_STAGE_ORDER,
    build_session,
    build_index,
    load_phase_inputs,
    load_session_input,
    observed_server_opcode_events,
    sample_previews,
    session_summary,
)


INTERFACE_DIFF_JSON = "interface-diff.json"
INTERFACE_DIFF_MD = "interface-diff.md"
INTERFACE_DIFF_CACHE_KEY = "interface-diff"
HEAD_MODEL_NAMES = {"IF_SETPLAYERHEAD", "IF_SETPLAYERMODEL_SELF", "IF_SETNPCHEAD"}
ACTIVE_PLAYER_OPCODE = 116
ACTIVE_PLAYER_PACKET_NAME = "IF_OPENSUB_ACTIVE_PLAYER"
ACTIVE_PLAYER_OPEN_KIND = "world-open-active-player"
ACTIVE_PLAYER_SKIP_KIND = "world-skip-active-player"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare two local RS3 946 bootstrap sessions and rank likely missing UI state."
    )
    parser.add_argument("--good-session", type=Path)
    parser.add_argument("--bad-session", type=Path)
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--good-window")
    parser.add_argument("--bad-window")
    parser.add_argument("--bootstrap-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / INTERFACE_DIFF_JSON,
        output_dir / INTERFACE_DIFF_MD,
    ]


def ensure_session_arguments(args: argparse.Namespace) -> None:
    using_explicit_sessions = args.good_session is not None or args.bad_session is not None
    if using_explicit_sessions:
        if args.good_session is None or args.bad_session is None:
            raise SystemExit("Supply both --good-session and --bad-session when using explicit session files.")
        return
    if not args.good_window or not args.bad_window:
        raise SystemExit("Supply either explicit session files or --world-log with both --good-window and --bad-window.")


def packet_maps() -> tuple[dict[tuple[str, int], dict[str, Any]], ...]:
    inputs = load_phase_inputs()
    return (
        build_index(inputs["verifiedPackets"]),
        build_index(inputs["generatedPackets"]),
        build_index(inputs["evidenceIndex"]),
        build_index(inputs["phase3Candidates"]),
    )


def packet_metadata(side: str, opcode: int, indexes: tuple[dict[tuple[str, int], dict[str, Any]], ...]) -> dict[str, Any]:
    for index in indexes:
        entry = index.get((side, opcode))
        if entry:
            return entry
    return {}


def categorize_packet(name: str, family: str, candidate_names: list[str]) -> str | None:
    if any(candidate.startswith("IF_OPENSUB_ACTIVE_") for candidate in candidate_names):
        return "activeSubBindings"
    if name == "IF_OPENTOP":
        return "rootInterfaces"
    if name.startswith("IF_OPENSUB_ACTIVE_"):
        return "activeSubBindings"
    if name in HEAD_MODEL_NAMES:
        return "headModelBindings"
    if name in {"IF_OPENSUB", "IF_CLOSESUB", "IF_SETHIDE"} or name.startswith("IF_"):
        return "childInterfaces"
    if name.startswith("CLIENT_SETVARC") or name.startswith("VAR") or "SCRIPT" in name or family == "VAR":
        return "uiState"
    return None


def summarize_session(session: dict[str, Any] | None, indexes: tuple[dict[tuple[str, int], dict[str, Any]], ...]) -> dict[str, Any]:
    counters = {
        "rootInterfaces": Counter(),
        "childInterfaces": Counter(),
        "activeSubBindings": Counter(),
        "headModelBindings": Counter(),
        "uiState": Counter(),
    }
    samples: dict[str, list[dict[str, Any]]] = {key: [] for key in counters}
    if not session:
        return {
            "summary": session_summary(session),
            "categories": {key: {} for key in counters},
            "samples": samples,
        }

    for opcode, events in observed_server_opcode_events(session).items():
        meta = packet_metadata("server", opcode, indexes)
        name = str(meta.get("packetName") or meta.get("suggestedName") or "")
        family = str(meta.get("family") or meta.get("familyLabel") or "")
        candidate_names = [candidate for candidate in meta.get("exactCandidateNames", []) if isinstance(candidate, str)]
        category = categorize_packet(name, family, candidate_names)
        if not category:
            continue
        label = name or (candidate_names[0] if candidate_names else f"opcode-{opcode}")
        counters[category][label] += len(events)
        if not samples[category]:
            samples[category] = sample_previews(events, limit=3)

    return {
        "summary": session_summary(session),
        "categories": {key: dict(sorted(counter.items())) for key, counter in counters.items()},
        "samples": samples,
    }


def diff_counters(good: dict[str, int], bad: dict[str, int]) -> dict[str, dict[str, int]]:
    good_counter = Counter(good)
    bad_counter = Counter(bad)
    missing_in_bad = dict(sorted((good_counter - bad_counter).items()))
    extra_in_bad = dict(sorted((bad_counter - good_counter).items()))
    return {
        "missingInBad": missing_in_bad,
        "extraInBad": extra_in_bad,
    }


def parse_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def event_data(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("data")
    return payload if isinstance(payload, dict) else {}


def active_player_session_summary(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {
            "activePlayer116Sent": False,
            "bootstrapMarkerPresent": False,
            "packetRegistered": None,
            "configEnabled": None,
            "skipReasons": [],
            "sendSamples": [],
            "markerSamples": [],
        }

    open_events = [event for event in session["events"] if event.get("kind") == ACTIVE_PLAYER_OPEN_KIND]
    skip_events = [event for event in session["events"] if event.get("kind") == ACTIVE_PLAYER_SKIP_KIND]
    send_events = [
        event
        for event in session["events"]
        if event.get("kind") == "send-raw"
        and event.get("opcode") == ACTIVE_PLAYER_OPCODE
        and event.get("stage") == "interfaces"
    ]

    packet_registered = None
    config_enabled = None
    for event in open_events + skip_events:
        data = event_data(event)
        packet_registered = parse_bool(data.get("packetRegistered")) if packet_registered is None else packet_registered
        config_enabled = parse_bool(data.get("configEnabled")) if config_enabled is None else config_enabled

    skip_reasons = sorted(
        {
            str(event_data(event).get("reason"))
            for event in skip_events
            if event_data(event).get("reason")
        }
    )

    marker_samples = []
    for event in open_events[:3]:
        data = event_data(event)
        marker_samples.append(
            {
                "lineNumber": event.get("lineNumber"),
                "stage": event.get("stage"),
                "subInterfaceId": data.get("subInterfaceId"),
                "childComponentId": data.get("childComponentId"),
                "targetComponentId": data.get("targetComponentId"),
                "packetRegistered": data.get("packetRegistered"),
                "configEnabled": data.get("configEnabled"),
            }
        )

    return {
        "activePlayer116Sent": bool(send_events),
        "bootstrapMarkerPresent": bool(open_events),
        "packetRegistered": packet_registered,
        "configEnabled": config_enabled,
        "skipReasons": skip_reasons,
        "sendSamples": sample_previews(send_events, limit=3),
        "markerSamples": marker_samples,
    }


def detect_active_player_roles(good_summary: dict[str, Any], bad_summary: dict[str, Any]) -> tuple[str, str]:
    good_on = good_summary["bootstrapMarkerPresent"] or good_summary["activePlayer116Sent"] or good_summary["configEnabled"] is True
    bad_on = bad_summary["bootstrapMarkerPresent"] or bad_summary["activePlayer116Sent"] or bad_summary["configEnabled"] is True
    good_off = good_summary["configEnabled"] is False or "experimental-opensub-disabled" in good_summary["skipReasons"]
    bad_off = bad_summary["configEnabled"] is False or "experimental-opensub-disabled" in bad_summary["skipReasons"]

    enabled_label = "unknown"
    disabled_label = "unknown"
    if good_on and not bad_on:
        enabled_label = "goodSession"
    elif bad_on and not good_on:
        enabled_label = "badSession"

    if good_off and not bad_off:
        disabled_label = "goodSession"
    elif bad_off and not good_off:
        disabled_label = "badSession"

    return enabled_label, disabled_label


def downstream_delta_counts(diff_categories: dict[str, dict[str, dict[str, int]]]) -> dict[str, int]:
    ignored_labels = {ACTIVE_PLAYER_PACKET_NAME}
    counts: dict[str, int] = {}
    for category, delta in diff_categories.items():
        total = 0
        for side in ("missingInBad", "extraInBad"):
            for label, count in delta[side].items():
                if label in ignored_labels:
                    continue
                total += count
        counts[category] = total
    return counts


def classify_interface_stage_delta(diff_categories: dict[str, dict[str, dict[str, int]]]) -> str:
    counts = downstream_delta_counts(diff_categories)
    total = sum(counts.values())
    if total == 0:
        return "none"
    if counts.get("rootInterfaces", 0) > 0 or counts.get("activeSubBindings", 0) > 0:
        return "material"
    if counts.get("headModelBindings", 0) > 0:
        return "material"
    if counts.get("childInterfaces", 0) >= 2 or total >= 4:
        return "material"
    return "minor"


def build_verdict(
    good_active: dict[str, Any],
    bad_active: dict[str, Any],
    diff_categories: dict[str, dict[str, dict[str, int]]],
    *,
    sessions_complete: bool,
) -> tuple[dict[str, str], dict[str, Any]]:
    enabled_label, disabled_label = detect_active_player_roles(good_active, bad_active)
    active_player_sent = "yes" if (good_active["activePlayer116Sent"] or bad_active["activePlayer116Sent"]) else "no"
    bootstrap_marker_present = "yes" if (good_active["bootstrapMarkerPresent"] or bad_active["bootstrapMarkerPresent"]) else "no"
    interface_stage_delta = classify_interface_stage_delta(diff_categories)

    if not sessions_complete:
        handoff_outcome_changed = "unknown"
    elif active_player_sent != "yes" or bootstrap_marker_present != "yes":
        handoff_outcome_changed = "unknown"
    elif interface_stage_delta == "material":
        handoff_outcome_changed = "yes"
    else:
        handoff_outcome_changed = "no"

    return (
        {
            "activePlayer116Sent": active_player_sent,
            "bootstrapMarkerPresent": bootstrap_marker_present,
            "interfaceStageDelta": interface_stage_delta,
            "handoffOutcomeChanged": handoff_outcome_changed,
        },
        {
            "goodSession": good_active,
            "badSession": bad_active,
            "detectedEnabledSession": enabled_label,
            "detectedDisabledSession": disabled_label,
        },
    )


def rank_findings(diff_categories: dict[str, dict[str, dict[str, int]]]) -> list[dict[str, Any]]:
    priorities = {
        "activeSubBindings": 60,
        "headModelBindings": 55,
        "rootInterfaces": 50,
        "childInterfaces": 40,
        "uiState": 25,
    }
    findings: list[dict[str, Any]] = []
    for category, delta in diff_categories.items():
        for label, count in delta["missingInBad"].items():
            findings.append(
                {
                    "category": category,
                    "label": label,
                    "score": priorities.get(category, 10) + count,
                    "reason": f"present in good session but missing in bad ({count} event(s))",
                }
            )
        for label, count in delta["extraInBad"].items():
            findings.append(
                {
                    "category": category,
                    "label": label,
                    "score": priorities.get(category, 10) // 2 + count,
                    "reason": f"extra in bad session ({count} event(s))",
                }
            )
    findings.sort(key=lambda item: (-item["score"], item["category"], item["label"]))
    return findings[:20]


def resolve_session_inputs(args: argparse.Namespace) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    bootstrap_only = bool(getattr(args, "bootstrap_only", False))
    if args.good_session is not None and args.bad_session is not None:
        good_session = load_session_input(args.good_session, args.good_window)
        bad_session = load_session_input(args.bad_session, args.bad_window)
        inputs = {
            "mode": "session-files",
            "goodSession": str(args.good_session),
            "badSession": str(args.bad_session),
            "goodWindow": args.good_window,
            "badWindow": args.bad_window,
            "bootstrapOnly": bootstrap_only,
        }
        return good_session, bad_session, inputs

    good_session = load_session_input(args.world_log, args.good_window)
    bad_session = load_session_input(args.world_log, args.bad_window)
    inputs = {
        "mode": "world-log-windows",
        "worldLog": str(args.world_log),
        "goodWindow": args.good_window,
        "badWindow": args.bad_window,
        "bootstrapOnly": bootstrap_only,
    }
    return good_session, bad_session, inputs


def filter_bootstrap_session(session: dict[str, Any] | None) -> dict[str, Any] | None:
    if not session:
        return None
    allowed_stages = set(POST_LOGIN_STAGE_ORDER)
    filtered_events = [
        event
        for event in session["events"]
        if (event.get("stage") in allowed_stages)
        or (event.get("kind") == "world-stage" and event.get("stage") in allowed_stages)
    ]
    return build_session(filtered_events)


def analyze_interface_diff(args: argparse.Namespace) -> dict[str, Any]:
    indexes = packet_maps()
    good_session, bad_session, session_inputs = resolve_session_inputs(args)
    if bool(getattr(args, "bootstrap_only", False)):
        good_session = filter_bootstrap_session(good_session)
        bad_session = filter_bootstrap_session(bad_session)
    good_summary = summarize_session(good_session, indexes)
    bad_summary = summarize_session(bad_session, indexes)
    diff_categories = {
        category: diff_counters(good_summary["categories"][category], bad_summary["categories"][category])
        for category in good_summary["categories"]
    }
    findings = rank_findings(diff_categories)
    status = "ok" if good_session and bad_session else "partial"
    good_active = active_player_session_summary(good_session)
    bad_active = active_player_session_summary(bad_session)
    verdict, active_player_comparison = build_verdict(
        good_active,
        bad_active,
        diff_categories,
        sessions_complete=bool(good_session and bad_session),
    )
    return standard_tool_artifact(
        tool_name="run_946_interface_diff",
        status=status,
        inputs=session_inputs,
        artifacts=output_artifact_map(args.output_dir, INTERFACE_DIFF_JSON, INTERFACE_DIFF_MD),
        summary={
            "goodSessionExists": bool(good_session),
            "badSessionExists": bool(bad_session),
            "topFindingCount": len(findings),
            "interfaceStageDelta": verdict["interfaceStageDelta"],
            "handoffOutcomeChanged": verdict["handoffOutcomeChanged"],
        },
        extra={
            "goodSession": good_summary,
            "badSession": bad_summary,
            "activePlayerComparison": active_player_comparison,
            "verdict": verdict,
            "diff": diff_categories,
            "topFindings": findings,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    good_summary = artifact["goodSession"]["summary"]
    bad_summary = artifact["badSession"]["summary"]
    lines = [
        "# 946 Interface Diff",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Good session: `{good_summary['startLine']}` -> `{good_summary['endLine']}`",
        f"- Bad session: `{bad_summary['startLine']}` -> `{bad_summary['endLine']}`",
        "",
        "## Verdict",
        "",
        f"- `activePlayer116Sent`: `{artifact['verdict']['activePlayer116Sent']}`",
        f"- `bootstrapMarkerPresent`: `{artifact['verdict']['bootstrapMarkerPresent']}`",
        f"- `interfaceStageDelta`: `{artifact['verdict']['interfaceStageDelta']}`",
        f"- `handoffOutcomeChanged`: `{artifact['verdict']['handoffOutcomeChanged']}`",
        f"- Detected enabled session: `{artifact['activePlayerComparison']['detectedEnabledSession']}`",
        f"- Detected disabled session: `{artifact['activePlayerComparison']['detectedDisabledSession']}`",
        "",
        "## Top Findings",
        "",
    ]
    if artifact["topFindings"]:
        for finding in artifact["topFindings"]:
            lines.append(
                f"- `{finding['category']}` `{finding['label']}` score=`{finding['score']}` {finding['reason']}"
            )
    else:
        lines.append("- No structural diffs detected.")
    lines.extend(["", "## Session Summaries", ""])
    for label, summary in (("Good", good_summary), ("Bad", bad_summary)):
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- Duration: `{summary['durationSeconds']}`")
        lines.append(f"- Event count: `{summary['eventCount']}`")
        lines.append(f"- Stage sequence: `{summary['stageSequence']}`")
        lines.append(f"- Server opcodes: `{summary['serverOpcodeCounts']}`")
        lines.append(f"- Marker counts: `{summary['markerCounts']}`")
        lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / INTERFACE_DIFF_JSON, artifact)
    (output_dir / INTERFACE_DIFF_MD).write_text(render_markdown(artifact), encoding="utf-8")


def input_fingerprint(args: argparse.Namespace) -> str:
    bootstrap_only = bool(getattr(args, "bootstrap_only", False))
    relevant_paths = [
        WORKSPACE / "tools" / "run_946_interface_diff.py",
        WORKSPACE / "tools" / "protocol_automation_common.py",
        WORKSPACE / "tools" / "protocol_946_debug_common.py",
        SHARED_DIR / "verified-packets.json",
        SHARED_DIR / "evidence-index.json",
        SHARED_DIR.parent / "phase3" / "nameCandidates.json",
        SHARED_DIR.parent / "phase5" / "generatedPackets.json",
    ]
    extra: dict[str, Any]
    if args.good_session is not None and args.bad_session is not None:
        relevant_paths.extend([args.good_session, args.bad_session])
        extra = {
            "mode": "session-files",
            "good_window": args.good_window,
            "bad_window": args.bad_window,
            "bootstrap_only": bootstrap_only,
        }
    else:
        relevant_paths.append(args.world_log)
        extra = {
            "mode": "world-log-windows",
            "good_window": args.good_window,
            "bad_window": args.bad_window,
            "bootstrap_only": bootstrap_only,
        }
    return artifact_input_fingerprint("run_946_interface_diff", relevant_paths, **extra)


def main() -> int:
    args = parse_args()
    ensure_session_arguments(args)
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, INTERFACE_DIFF_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / INTERFACE_DIFF_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = analyze_interface_diff(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, INTERFACE_DIFF_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
