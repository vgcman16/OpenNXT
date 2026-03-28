from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from statistics import median
from types import SimpleNamespace
from typing import Any

from protocol_automation_common import SHARED_DIR, WORKSPACE, ensure_directory, load_json, stable_json_text, write_json
from protocol_946_debug_common import BUILD_ID, PLAYER_INFO_OPCODE, WORLD_LOG_DEFAULT, load_all_sessions, session_summary
from run_946_interface_diff import analyze_interface_diff


CURATED_COMPARE_JSON = "curated-compare.json"
CURATED_COMPARE_MD = "curated-compare.md"
DEFAULT_LABELS_PATH = WORKSPACE / "data" / "prot" / "946" / "curated-session-labels.json"
TRACKED_CLIENT_OPCODES = [17, 28, 48, 50, 82, 83, 95, 106, 113]
TRACKED_SERVER_OPCODES = [39, 42, 45, 50, 67, 106, 116, 131]
MANUAL_OUTCOME_MAP = {
    "stable": "stable_interfaces",
    "stable_interfaces": "stable_interfaces",
    "loop": "short_loop",
    "short_loop": "short_loop",
    "crash": "short_loop",
    "rebuild-fail": "rebuild_fail",
    "rebuild_fail": "rebuild_fail",
}
MUTUALLY_EXCLUSIVE_GROUPS = {
    "deferred_completion_script_mode": {
        "deferred_completion_scripts",
        "deferred_completion_lite_scripts",
        "deferred_completion_10623_batch",
        "deferred_completion_core_scripts",
        "skip_deferred_completion_scripts",
    },
    "active_player_mode": {
        "active_player_116_sent",
        "active_player_skipped",
    },
}
FEATURE_GROUPS = {
    feature: group
    for group, features in MUTUALLY_EXCLUSIVE_GROUPS.items()
    for feature in features
}
OBSERVATIONAL_PREFIXES = ("client_opcode_", "server_opcode_")
BAD_OUTCOMES = {"short_loop", "rebuild_fail"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare all recorded 946 bootstrap sessions and synthesize a best-known stable baseline.")
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--good-count", type=int, default=5)
    parser.add_argument("--bad-count", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    return parser.parse_args()


def session_window(session: dict[str, Any]) -> str:
    return f"{session['startLine']}:{session['endLine']}"


def normalize_manual_outcome(value: str | None) -> str | None:
    if not value:
        return None
    return MANUAL_OUTCOME_MAP.get(value.strip().lower())


def normalize_role(value: str | None) -> str | None:
    if not value:
        return None
    role = value.strip().lower()
    return role if role in {"seed", "stable", "bad", "crash"} else None


def load_labels(path: Path | None) -> dict[str, Any]:
    if not path:
        return {
            "path": None,
            "format": "none",
            "present": False,
            "entries": {},
        }

    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return {
            "path": str(path),
            "format": "invalid",
            "present": False,
            "entries": {},
        }

    raw_entries = payload.get("sessions") if isinstance(payload.get("sessions"), dict) else payload
    if not isinstance(raw_entries, dict):
        return {
            "path": str(path),
            "format": "invalid",
            "present": False,
            "entries": {},
        }

    saw_simple = False
    saw_rich = False
    entries: dict[str, dict[str, Any]] = {}
    for window, value in raw_entries.items():
        if not isinstance(window, str):
            continue
        if isinstance(value, str):
            saw_simple = True
            label = value.strip().lower()
            note = None
            role = None
        elif isinstance(value, dict):
            saw_rich = True
            label_value = value.get("label")
            label = label_value.strip().lower() if isinstance(label_value, str) else ""
            note = value.get("note") if isinstance(value.get("note"), str) else None
            role = normalize_role(value.get("role") if isinstance(value.get("role"), str) else None)
        else:
            continue

        normalized = normalize_manual_outcome(label)
        if not normalized:
            continue

        entries[window] = {
            "label": label,
            "normalizedOutcome": normalized,
            "note": note,
            "role": role,
        }

    if saw_simple and saw_rich:
        label_format = "mixed-map"
    elif saw_rich:
        label_format = "rich-map"
    elif saw_simple:
        label_format = "simple-map"
    else:
        label_format = "none"

    return {
        "path": str(path),
        "format": label_format,
        "present": bool(entries),
        "entries": entries,
    }


def label_entry_for_window(labels: dict[str, Any], window: str) -> dict[str, Any] | None:
    if not labels:
        return None
    value = labels.get(window)
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        normalized = normalize_manual_outcome(value)
        if not normalized:
            return None
        return {
            "label": value.strip().lower(),
            "normalizedOutcome": normalized,
            "note": None,
            "role": None,
        }
    return None


def has_marker(summary: dict[str, Any], marker: str) -> bool:
    return summary.get("markerCounts", {}).get(marker, 0) > 0


def any_marker(summary: dict[str, Any], *markers: str) -> bool:
    return any(has_marker(summary, marker) for marker in markers)


def event_matches(
    session: dict[str, Any],
    *,
    kind: str,
    data_key: str | None = None,
    data_value: str | None = None,
) -> bool:
    for event in session.get("events", []):
        if event.get("kind") != kind:
            continue
        if data_key is None:
            return True
        payload = event.get("data")
        if not isinstance(payload, dict):
            continue
        if payload.get(data_key) == data_value:
            return True
    return False


def player_info_metrics(session: dict[str, Any]) -> dict[str, Any]:
    send_events = [
        event
        for event in session.get("events", [])
        if event.get("kind") == "send-raw" and event.get("opcode") == PLAYER_INFO_OPCODE
    ]
    sizes = [event["bytes"] for event in send_events if isinstance(event.get("bytes"), int)]
    first_large_send = next((size for size in sizes if size > 3), None)
    repeated_tiny = sum(1 for size in sizes if size == 3)
    return {
        "count": len(send_events),
        "firstLargeSendSize": first_large_send,
        "repeatedTinyFrameCount": repeated_tiny,
        "largestSize": max(sizes) if sizes else None,
        "smallestSize": min(sizes) if sizes else None,
        "fullInitialPlayerInfo": first_large_send is not None,
        "sustainedPlayerInfo": len(send_events) >= 25 or repeated_tiny >= 10,
    }


def build_feature_fingerprint(session: dict[str, Any]) -> dict[str, Any]:
    summary = session_summary(session)
    player_info = player_info_metrics(session)
    client_counts = {opcode: summary["clientOpcodeCounts"].get(opcode, 0) for opcode in TRACKED_CLIENT_OPCODES}
    server_counts = {opcode: summary["serverOpcodeCounts"].get(opcode, 0) for opcode in TRACKED_SERVER_OPCODES}
    presence = {
        "compat_map_build_113": any_marker(summary, "world-compat-map-build", "world-map-build-complete-compat"),
        "ready_signal": has_marker(summary, "world-ready-signal"),
        "ready_signal_fallback": has_marker(summary, "world-ready-signal-fallback"),
        "ready_signal_skipped": has_marker(summary, "world-ready-signal-skipped"),
        "active_player_116_sent": has_marker(summary, "world-open-active-player") or server_counts[116] > 0,
        "active_player_skipped": has_marker(summary, "world-skip-active-player"),
        "world_init_state_sent": any_marker(summary, "world-init-stats", "world-send-reset-client-varcache"),
        "minimal_varcs_sent": has_marker(summary, "world-send-minimal-varcs"),
        "default_varps_sent": any_marker(
            summary,
            "world-defer-default-varps",
            "world-send-deferred-default-varps",
            "world-queued-deferred-default-varps",
        ),
        "full_initial_player_info": player_info["fullInitialPlayerInfo"],
        "sustained_player_info": player_info["sustainedPlayerInfo"],
        "immediate_followup_sync": has_marker(summary, "world-send-immediate-followup-sync"),
        "post_initial_hold": has_marker(summary, "world-post-initial-sync-hold"),
        "trimmed_interface_tail": has_marker(summary, "world-trimmed-interface-tail"),
        "close_loading_overlay": has_marker(summary, "world-close-loading-overlay"),
        "open_minimal_child": has_marker(summary, "world-open-minimal-child"),
        "deferred_completion_structure": has_marker(summary, "world-send-deferred-completion-structure"),
        "deferred_completion_scripts": has_marker(summary, "world-send-deferred-completion-scripts"),
        "deferred_completion_lite_scripts": has_marker(summary, "world-send-deferred-completion-lite-scripts"),
        "deferred_completion_10623_batch": has_marker(summary, "world-send-deferred-completion-10623-batch"),
        "deferred_completion_core_scripts": has_marker(summary, "world-send-deferred-completion-core-scripts"),
        "skip_deferred_completion_scripts": has_marker(summary, "world-skip-deferred-completion-scripts"),
        "deferred_completion_event_delta": has_marker(summary, "world-send-deferred-completion-event-delta"),
        "deferred_completion_tail": has_marker(summary, "world-send-deferred-completion-tail"),
        "deferred_completion_structure_template": has_marker(summary, "world-send-deferred-completion-structure-template"),
        "deferred_completion_scripts_template": has_marker(summary, "world-send-deferred-completion-scripts-template"),
        "deferred_completion_lite_scripts_template": has_marker(summary, "world-send-deferred-completion-lite-scripts-template"),
        "deferred_completion_10623_batch_template": has_marker(summary, "world-send-deferred-completion-10623-batch-template"),
        "deferred_completion_core_scripts_template": has_marker(summary, "world-send-deferred-completion-core-scripts-template"),
        "skip_deferred_completion_scripts_template": has_marker(summary, "world-skip-deferred-completion-scripts-template"),
        "social_init_skipped": has_marker(summary, "world-skip-social-interface-events"),
        "social_init_skipped_template": has_marker(summary, "world-skip-social-interface-events-template"),
        "bootstrap_script_671_skipped": event_matches(
            session,
            kind="world-skip-bootstrap-script",
            data_key="script",
            data_value="671",
        ),
    }
    for opcode, count in client_counts.items():
        presence[f"client_opcode_{opcode}_present"] = count > 0
    for opcode, count in server_counts.items():
        presence[f"server_opcode_{opcode}_present"] = count > 0
    return {
        "presence": presence,
        "clientOpcodeCounts": client_counts,
        "serverOpcodeCounts": server_counts,
        "playerInfo": player_info,
    }


def classify_session_outcome(session: dict[str, Any], labels: dict[str, Any]) -> tuple[str, str, str | None]:
    summary = session_summary(session)
    window = session_window(session)
    label_entry = label_entry_for_window(labels, window)
    if label_entry:
        return label_entry["normalizedOutcome"], "manual", label_entry["label"]

    player_info_count = summary["serverOpcodeCounts"].get(PLAYER_INFO_OPCODE, 0)
    if "interfaces" not in summary["stageSequence"]:
        return "rebuild_fail", "heuristic", None
    if summary["eventCount"] >= 150 or player_info_count >= 25:
        return "stable_interfaces", "heuristic", None
    if summary["eventCount"] < 120 and player_info_count < 10:
        return "short_loop", "heuristic", None
    return "other", "heuristic", None


def session_stability_score(summary: dict[str, Any], player_info: dict[str, Any]) -> int:
    duration = int((summary.get("durationSeconds") or 0) * 10)
    return player_info["count"] * 100 + summary["eventCount"] + duration


def build_session_analysis(session: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any]:
    summary = session_summary(session)
    features = build_feature_fingerprint(session)
    outcome, source, manual_label = classify_session_outcome(session, labels)
    label_entry = label_entry_for_window(labels, session_window(session))
    return {
        "session": session,
        "window": session_window(session),
        "summary": summary,
        "features": features,
        "outcome": outcome,
        "outcomeSource": source,
        "manualLabel": manual_label,
        "manualRole": label_entry.get("role") if label_entry else None,
        "manualNote": label_entry.get("note") if label_entry else None,
        "stabilityScore": session_stability_score(summary, features["playerInfo"]),
    }


def representative_view(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "window": analysis["window"],
        "outcome": analysis["outcome"],
        "outcomeSource": analysis["outcomeSource"],
        "manualLabel": analysis["manualLabel"],
        "manualRole": analysis["manualRole"],
        "manualNote": analysis["manualNote"],
        "stabilityScore": analysis["stabilityScore"],
        "eventCount": analysis["summary"]["eventCount"],
        "durationSeconds": analysis["summary"]["durationSeconds"],
        "stageSequence": analysis["summary"]["stageSequence"],
        "playerInfoCount": analysis["features"]["playerInfo"]["count"],
        "firstLargePlayerInfo": analysis["features"]["playerInfo"]["firstLargeSendSize"],
        "markerCounts": analysis["summary"]["markerCounts"],
    }


def median_or_none(values: list[int | float | None]) -> float | int | None:
    clean = [value for value in values if isinstance(value, (int, float))]
    if not clean:
        return None
    return median(clean)


def rank_feature_signals(analyses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stable = [analysis for analysis in analyses if analysis["outcome"] == "stable_interfaces"]
    short_loop = [analysis for analysis in analyses if analysis["outcome"] == "short_loop"]
    feature_names = sorted(
        {
            feature
            for analysis in stable + short_loop
            for feature, present in analysis["features"]["presence"].items()
            if present
        }
    )
    rankings: list[dict[str, Any]] = []
    stable_total = len(stable)
    short_total = len(short_loop)
    for feature in feature_names:
        stable_count = sum(1 for analysis in stable if analysis["features"]["presence"].get(feature))
        short_count = sum(1 for analysis in short_loop if analysis["features"]["presence"].get(feature))
        stable_prevalence = stable_count / stable_total if stable_total else 0.0
        short_prevalence = short_count / short_total if short_total else 0.0
        delta = stable_prevalence - short_prevalence
        if stable_prevalence >= 0.6 and delta >= 0.4:
            verdict = "helped"
        elif short_prevalence >= 0.6 and delta <= -0.4:
            verdict = "hurt"
        else:
            verdict = "inconclusive"
        rankings.append(
            {
                "feature": feature,
                "stableCount": stable_count,
                "shortLoopCount": short_count,
                "stablePrevalence": round(stable_prevalence, 3),
                "shortLoopPrevalence": round(short_prevalence, 3),
                "delta": round(delta, 3),
                "verdict": verdict,
                "bundleEligible": not feature.startswith(OBSERVATIONAL_PREFIXES),
            }
        )

    verdict_order = {"helped": 0, "hurt": 1, "inconclusive": 2}
    rankings.sort(
        key=lambda item: (
            verdict_order.get(item["verdict"], 99),
            -abs(item["delta"]),
            item["feature"],
        )
    )
    return rankings


def is_labeled_stable(analysis: dict[str, Any]) -> bool:
    return analysis["outcomeSource"] == "manual" and analysis["outcome"] == "stable_interfaces"


def is_labeled_bad(analysis: dict[str, Any]) -> bool:
    return analysis["outcomeSource"] == "manual" and analysis["outcome"] in BAD_OUTCOMES


def sort_representatives(
    analyses: list[dict[str, Any]],
    *,
    reverse: bool,
    preferred_predicate,
) -> list[dict[str, Any]]:
    def key(analysis: dict[str, Any]) -> tuple[Any, ...]:
        preferred = 0 if preferred_predicate(analysis) else 1
        score = -analysis["stabilityScore"] if reverse else analysis["stabilityScore"]
        return preferred, score, analysis["window"]

    return sorted(analyses, key=key)


def choose_seed_session(analyses: list[dict[str, Any]], *, labels_present: bool) -> tuple[dict[str, Any] | None, str]:
    stable = [analysis for analysis in analyses if analysis["outcome"] == "stable_interfaces"]
    labeled_stable = [analysis for analysis in stable if is_labeled_stable(analysis)]
    labeled_seed = [analysis for analysis in labeled_stable if analysis["manualRole"] == "seed"]
    if labeled_seed:
        return max(labeled_seed, key=lambda analysis: (analysis["stabilityScore"], analysis["window"])), "labeled"
    if labeled_stable:
        return max(labeled_stable, key=lambda analysis: (analysis["stabilityScore"], analysis["window"])), "labeled"
    if not stable:
        return None, "heuristic"
    if labels_present:
        return max(stable, key=lambda analysis: (analysis["stabilityScore"], analysis["window"])), "heuristic"
    return max(stable, key=lambda analysis: (analysis["stabilityScore"], analysis["window"])), "heuristic"


def choose_anchor_pair(analyses: list[dict[str, Any]], *, labels_present: bool, seed: dict[str, Any] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    if labels_present:
        labeled_stable = [analysis for analysis in analyses if is_labeled_stable(analysis)]
        labeled_bad = [analysis for analysis in analyses if is_labeled_bad(analysis)]
        if not labeled_stable or not labeled_bad:
            return None, None, "labeled"
        good = seed if seed in labeled_stable else max(
            labeled_stable,
            key=lambda analysis: (
                1 if analysis["manualRole"] == "seed" else 0,
                analysis["stabilityScore"],
                analysis["window"],
            ),
        )
        short_bad = [analysis for analysis in labeled_bad if analysis["outcome"] == "short_loop"]
        bad_pool = short_bad or labeled_bad
        bad = min(
            bad_pool,
            key=lambda analysis: (
                0 if analysis["manualRole"] in {"bad", "crash"} else 1,
                analysis["stabilityScore"],
                analysis["window"],
            ),
        )
        return good, bad, "labeled"

    stable = [analysis for analysis in analyses if analysis["outcome"] == "stable_interfaces"]
    short_loop = [analysis for analysis in analyses if analysis["outcome"] == "short_loop"]
    if not stable or not short_loop:
        return None, None, "heuristic"
    good = seed if seed in stable else max(stable, key=lambda analysis: (analysis["stabilityScore"], analysis["window"]))
    bad = min(short_loop, key=lambda analysis: (analysis["stabilityScore"], analysis["window"]))
    return good, bad, "heuristic"


def build_recommended_bundle(seed: dict[str, Any] | None, rankings: list[dict[str, Any]]) -> dict[str, Any]:
    if not seed:
        return {
            "seedSession": None,
            "recommendedFeatures": [],
            "rejectedFeatures": [],
            "seedFeatureSnapshot": {},
            "rationale": "No bundle recommendation because no stable seed session was available.",
        }

    seed_presence = seed["features"]["presence"]
    seed_group_members = {
        FEATURE_GROUPS[feature]: feature
        for feature, present in seed_presence.items()
        if present and feature in FEATURE_GROUPS
    }

    recommended: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    helped_count = 0
    for entry in rankings:
        if entry["verdict"] != "helped":
            continue
        helped_count += 1
        feature = entry["feature"]
        bundle_entry = {
            "feature": feature,
            "stablePrevalence": entry["stablePrevalence"],
            "shortLoopPrevalence": entry["shortLoopPrevalence"],
            "delta": entry["delta"],
        }
        if not entry["bundleEligible"]:
            rejected.append({**bundle_entry, "reason": "observational-not-bundle-input"})
            continue
        if seed_presence.get(feature):
            recommended.append(bundle_entry)
            continue
        group = FEATURE_GROUPS.get(feature)
        if group and group in seed_group_members:
            rejected.append(
                {
                    **bundle_entry,
                    "reason": f"mutually-exclusive-with-seed:{seed_group_members[group]}",
                }
            )
        else:
            rejected.append({**bundle_entry, "reason": "absent-from-seed"})

    if recommended:
        rationale = "Recommendations are limited to helped, bundle-eligible features that were already present in the chosen seed session."
    elif helped_count == 0:
        rationale = "No bundle recommendation because no feature met the helped threshold."
    else:
        rationale = "No bundle recommendation because the helped features did not coexist in the seed session; synthetic unions were intentionally rejected."

    return {
        "seedSession": representative_view(seed),
        "recommendedFeatures": recommended,
        "rejectedFeatures": rejected,
        "seedFeatureSnapshot": {feature: True for feature, present in seed_presence.items() if present},
        "rationale": rationale,
    }


def write_session_payload(path: Path, session: dict[str, Any]) -> None:
    write_json(path, {"events": session.get("events", [])})


def build_anchor_pair(good: dict[str, Any] | None, bad: dict[str, Any] | None) -> dict[str, Any] | None:
    if not good or not bad:
        return None
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        good_path = root / "good.json"
        bad_path = root / "bad.json"
        write_session_payload(good_path, good["session"])
        write_session_payload(bad_path, bad["session"])
        args = SimpleNamespace(
            good_session=good_path,
            bad_session=bad_path,
            good_window=None,
            bad_window=None,
            output_dir=root,
        )
        diff_artifact = analyze_interface_diff(args)
    return {
        "goodSession": representative_view(good),
        "badSession": representative_view(bad),
        "interfaceDiff": diff_artifact,
    }


def summarize_cohort(
    analyses: list[dict[str, Any]],
    *,
    limit: int,
    reverse: bool,
    preferred_predicate,
) -> dict[str, Any]:
    ordered = sort_representatives(analyses, reverse=reverse, preferred_predicate=preferred_predicate)
    return {
        "count": len(analyses),
        "medianEventCount": median_or_none([analysis["summary"]["eventCount"] for analysis in analyses]),
        "medianDurationSeconds": median_or_none([analysis["summary"]["durationSeconds"] for analysis in analyses]),
        "medianPlayerInfoCount": median_or_none([analysis["features"]["playerInfo"]["count"] for analysis in analyses]),
        "representatives": [representative_view(analysis) for analysis in ordered[:limit]],
    }


def confidence_details(
    *,
    labels_present: bool,
    labeled_stable_count: int,
    labeled_bad_count: int,
    seed_source: str,
    anchor_pair: dict[str, Any] | None,
) -> tuple[str, bool]:
    if labels_present and seed_source == "labeled" and labeled_stable_count >= 2 and labeled_bad_count >= 2 and anchor_pair:
        return "high", True
    if labels_present and seed_source == "labeled" and labeled_stable_count >= 1 and labeled_bad_count >= 1 and anchor_pair:
        return "medium", True
    return "low", False


def analyze_curated_compare(args: argparse.Namespace) -> dict[str, Any]:
    sessions = load_all_sessions(args.world_log)
    labels_path = args.labels or DEFAULT_LABELS_PATH
    labels_meta = load_labels(labels_path)
    label_entries = labels_meta["entries"]
    analyses = [build_session_analysis(session, label_entries) for session in sessions]
    rankings = rank_feature_signals(analyses)
    seed, seed_source = choose_seed_session(analyses, labels_present=labels_meta["present"])
    anchor_good, anchor_bad, anchor_pair_source = choose_anchor_pair(
        analyses,
        labels_present=labels_meta["present"],
        seed=seed,
    )

    by_outcome: dict[str, list[dict[str, Any]]] = {
        "stable_interfaces": [analysis for analysis in analyses if analysis["outcome"] == "stable_interfaces"],
        "short_loop": [analysis for analysis in analyses if analysis["outcome"] == "short_loop"],
        "rebuild_fail": [analysis for analysis in analyses if analysis["outcome"] == "rebuild_fail"],
        "other": [analysis for analysis in analyses if analysis["outcome"] == "other"],
    }

    cohort_summary = {
        "stable_interfaces": summarize_cohort(
            by_outcome["stable_interfaces"],
            limit=args.good_count,
            reverse=True,
            preferred_predicate=is_labeled_stable,
        ),
        "short_loop": summarize_cohort(
            by_outcome["short_loop"],
            limit=args.bad_count,
            reverse=False,
            preferred_predicate=is_labeled_bad,
        ),
        "rebuild_fail": summarize_cohort(
            by_outcome["rebuild_fail"],
            limit=args.bad_count,
            reverse=False,
            preferred_predicate=is_labeled_bad,
        ),
        "other": summarize_cohort(
            by_outcome["other"],
            limit=args.bad_count,
            reverse=False,
            preferred_predicate=lambda analysis: analysis["outcomeSource"] == "manual",
        ),
    }

    bundle = build_recommended_bundle(seed, rankings)
    anchor_pair = build_anchor_pair(anchor_good, anchor_bad)
    label_count = sum(1 for analysis in analyses if analysis["outcomeSource"] == "manual")
    labeled_stable_count = sum(1 for analysis in analyses if is_labeled_stable(analysis))
    labeled_bad_count = sum(1 for analysis in analyses if is_labeled_bad(analysis))
    confidence, advisory_ready = confidence_details(
        labels_present=labels_meta["present"],
        labeled_stable_count=labeled_stable_count,
        labeled_bad_count=labeled_bad_count,
        seed_source=seed_source,
        anchor_pair=anchor_pair,
    )
    status = "ok" if seed else "partial"

    return {
        "build": BUILD_ID,
        "status": status,
        "worldLog": str(args.world_log),
        "sessionCount": len(analyses),
        "labelsPresent": labels_meta["present"],
        "labeledStableCount": labeled_stable_count,
        "labeledBadCount": labeled_bad_count,
        "confidence": confidence,
        "advisoryReady": advisory_ready,
        "seedSource": seed_source,
        "anchorPairSource": anchor_pair_source,
        "recommendationRationale": bundle["rationale"],
        "labels": {
            "path": labels_meta["path"],
            "format": labels_meta["format"],
            "appliedCount": label_count,
        },
        "cohorts": cohort_summary,
        "featureRankings": rankings,
        "bestKnownBaseline": bundle,
        "anchorPair": anchor_pair,
    }


def render_rankings(rankings: list[dict[str, Any]], verdict: str, limit: int = 12) -> list[str]:
    selected = [entry for entry in rankings if entry["verdict"] == verdict][:limit]
    if not selected:
        return ["- None."]
    return [
        (
            f"- `{entry['feature']}` stable=`{entry['stablePrevalence']}` "
            f"short=`{entry['shortLoopPrevalence']}` delta=`{entry['delta']}`"
        )
        for entry in selected
    ]


def render_representatives(entries: list[dict[str, Any]]) -> list[str]:
    if not entries:
        return ["- None."]
    rendered: list[str] = []
    for entry in entries:
        label_bits = []
        if entry.get("manualLabel"):
            label_bits.append(f"label={entry['manualLabel']}")
        if entry.get("manualRole"):
            label_bits.append(f"role={entry['manualRole']}")
        label_suffix = f" {' '.join(label_bits)}" if label_bits else ""
        rendered.append(
            (
                f"- `{entry['window']}` score=`{entry['stabilityScore']}` "
                f"events=`{entry['eventCount']}` duration=`{entry['durationSeconds']}` "
                f"playerInfo=`{entry['playerInfoCount']}`{label_suffix}"
            )
        )
    return rendered


def render_markdown(artifact: dict[str, Any]) -> str:
    seed_session = artifact["bestKnownBaseline"]["seedSession"]
    seed_window = seed_session["window"] if seed_session else None
    lines = [
        "# 946 Curated Historical Compare",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Sessions analyzed: `{artifact['sessionCount']}`",
        f"- Labels present: `{artifact['labelsPresent']}`",
        f"- Labels file: `{artifact['labels']['path']}`",
        f"- Labels format: `{artifact['labels']['format']}`",
        f"- Manual labels applied: `{artifact['labels']['appliedCount']}`",
        f"- Labeled stable sessions: `{artifact['labeledStableCount']}`",
        f"- Labeled bad sessions: `{artifact['labeledBadCount']}`",
        f"- Confidence: `{artifact['confidence']}`",
        f"- Advisory ready: `{artifact['advisoryReady']}`",
        f"- Seed source: `{artifact['seedSource']}`",
        f"- Anchor pair source: `{artifact['anchorPairSource']}`",
        "",
        "## Cohorts",
        "",
    ]
    for cohort_name, cohort in artifact["cohorts"].items():
        lines.extend(
            [
                f"### {cohort_name}",
                "",
                f"- Count: `{cohort['count']}`",
                f"- Median eventCount: `{cohort['medianEventCount']}`",
                f"- Median durationSeconds: `{cohort['medianDurationSeconds']}`",
                f"- Median PLAYER_INFO count: `{cohort['medianPlayerInfoCount']}`",
                "- Representatives:",
            ]
        )
        lines.extend(render_representatives(cohort["representatives"]))
        lines.append("")

    lines.extend(
        [
            "## Best-Known Baseline",
            "",
            f"- Seed session: `{seed_window}`",
            f"- Recommendation rationale: `{artifact['recommendationRationale']}`",
            "",
            "### Recommended Features",
            "",
        ]
    )
    recommended = artifact["bestKnownBaseline"]["recommendedFeatures"]
    if not recommended:
        lines.append("- None.")
    else:
        for entry in recommended:
            lines.append(
                f"- `{entry['feature']}` stable=`{entry['stablePrevalence']}` short=`{entry['shortLoopPrevalence']}` delta=`{entry['delta']}`"
            )
    lines.extend(["", "### Rejected Features", ""])
    rejected = artifact["bestKnownBaseline"]["rejectedFeatures"]
    if not rejected:
        lines.append("- None.")
    else:
        for entry in rejected[:20]:
            lines.append(
                f"- `{entry['feature']}` reason=`{entry['reason']}` stable=`{entry['stablePrevalence']}` short=`{entry['shortLoopPrevalence']}` delta=`{entry['delta']}`"
            )

    lines.extend(["", "## Feature Rankings", "", "### Helped", ""])
    lines.extend(render_rankings(artifact["featureRankings"], "helped"))
    lines.extend(["", "### Hurt", ""])
    lines.extend(render_rankings(artifact["featureRankings"], "hurt"))
    lines.extend(["", "### Inconclusive", ""])
    lines.extend(render_rankings(artifact["featureRankings"], "inconclusive"))

    lines.extend(["", "## Anchor Pair", ""])
    anchor_pair = artifact.get("anchorPair")
    if not anchor_pair:
        lines.append("- No stable/bad anchor pair available.")
    else:
        lines.append(f"- Good session: `{anchor_pair['goodSession']['window']}`")
        lines.append(f"- Bad session: `{anchor_pair['badSession']['window']}`")
        verdict = anchor_pair["interfaceDiff"]["verdict"]
        lines.append(
            f"- Interface diff verdict: `activePlayer116Sent={verdict['activePlayer116Sent']}` "
            f"`bootstrapMarkerPresent={verdict['bootstrapMarkerPresent']}` "
            f"`interfaceStageDelta={verdict['interfaceStageDelta']}` "
            f"`handoffOutcomeChanged={verdict['handoffOutcomeChanged']}`"
        )
        lines.append("- Top structural findings:")
        findings = anchor_pair["interfaceDiff"]["topFindings"]
        if not findings:
            lines.append("- None.")
        else:
            for finding in findings[:8]:
                lines.append(
                    f"- `{finding['category']}` `{finding['label']}` score=`{finding['score']}`"
                )
    lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> dict[str, str]:
    ensure_directory(output_dir)
    json_path = output_dir / CURATED_COMPARE_JSON
    markdown_path = output_dir / CURATED_COMPARE_MD
    write_json(json_path, artifact)
    markdown_path.write_text(render_markdown(artifact), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def main() -> int:
    args = parse_args()
    artifact = analyze_curated_compare(args)
    paths = write_artifacts(args.output_dir, artifact)
    print(stable_json_text({"status": artifact["status"], "artifacts": paths}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
