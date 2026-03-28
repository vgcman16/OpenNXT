from __future__ import annotations

import argparse
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
from protocol_946_debug_common import WORLD_LOG_DEFAULT, load_all_sessions, session_summary


PARITY_JSON = "forced-fallback-parity-doctor.json"
PARITY_MD = "forced-fallback-parity-doctor.md"
PARITY_CACHE_KEY = "forced-fallback-parity-doctor"
WORLD_PLAYER_SOURCE = (
    WORKSPACE
    / "src"
    / "main"
    / "kotlin"
    / "com"
    / "opennxt"
    / "model"
    / "world"
    / "WorldPlayer.kt"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the stable/full WorldPlayer bootstrap families against the forced MAP_BUILD fallback "
            "and report which interface/script families are still absent or deferred too late for scene start."
        )
    )
    parser.add_argument("--world-log", type=Path, default=WORLD_LOG_DEFAULT)
    parser.add_argument("--world-player-source", type=Path, default=WORLD_PLAYER_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=SHARED_DIR)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def output_paths(output_dir: Path) -> list[Path]:
    return [
        output_dir / PARITY_JSON,
        output_dir / PARITY_MD,
    ]


def input_fingerprint(args: argparse.Namespace) -> str:
    return artifact_input_fingerprint(
        "run_946_forced_fallback_parity_doctor",
        [
            Path(__file__),
            Path(__file__).with_name("protocol_automation_common.py"),
            Path(__file__).with_name("protocol_946_debug_common.py"),
            args.world_log,
            args.world_player_source,
        ],
    )


def find_line(lines: list[str], needle: str) -> int | None:
    for index, line in enumerate(lines, start=1):
        if needle in line:
            return index
    return None


def find_latest_session(
    sessions: list[dict[str, Any]],
    *,
    contains: str,
    excludes: str | None = None,
) -> dict[str, Any] | None:
    for session in reversed(sessions):
        raw_events = [event.get("raw", "") for event in session.get("events", [])]
        if not any(contains in raw for raw in raw_events):
            continue
        if excludes and any(excludes in raw for raw in raw_events):
            continue
        return session
    return None


def session_has(session: dict[str, Any] | None, marker: str) -> bool:
    if not session:
        return False
    return any(marker in event.get("raw", "") for event in session.get("events", []))


def marker_line(session: dict[str, Any] | None, marker: str) -> int | None:
    if not session:
        return None
    for event in session.get("events", []):
        if marker in event.get("raw", ""):
            return int(event.get("lineNumber", 0) or 0)
    return None


def build_family_rows(source_lines: list[str], forced_session: dict[str, Any] | None) -> list[dict[str, Any]]:
    families = [
        {
            "name": "restored-world-panels",
            "kind": "full-only-open-family",
            "status": "missing-on-forced-fallback",
            "whyItMatters": "This is the first large world-side interface deck that the full bootstrap opens after the minimal child. The forced fallback still returns before opening it.",
            "needs": "materialize the restored world panel deck or a narrower subset that advances the client beyond reference-table[0]",
            "sourceStartNeedle": "player.interfaces.open(id = 1464, parent = 1477, component = 109, walkable = true)",
            "sourceEndNeedle": "sendInterfaceBootstrapScript(script = 8862, args = arrayOf(5, 1))",
            "memberSummary": "1464,1458,1461,1884,1885,1887,1886,1460,1881,1888,1883,1449,1882,1452 plus 8862(3,4,5)",
            "runtimeMarker": "world-open-restored-interface",
        },
        {
            "name": "utility-panel-deck",
            "kind": "full-only-open-family",
            "status": "missing-on-forced-fallback",
            "whyItMatters": "The full bootstrap follows the restored world panels with utility/status panels and their 8862 bootstrap scripts. Forced fallback restores only the minimal varcs, not the interfaces that consume them.",
            "needs": "materialize the utility/status panel deck or the smallest subset that actually gates scene start",
            "sourceStartNeedle": "player.interfaces.open(id = 550, parent = 1477, component = 475, walkable = true)",
            "sourceEndNeedle": "player.interfaces.events(id = 1894, component = 16, from = 0, to = 2, mask = 2)",
            "memberSummary": "550,1427,1110,590,1416,1519,1588,1678,190,1854,1894 plus 8862(14,15,16,9,10,27,28,29,31,32)",
            "runtimeMarker": "world-send-forced-fallback-utility-panel-deck",
        },
        {
            "name": "scene-bridge-family",
            "kind": "forced-fallback-bridge",
            "status": "present",
            "whyItMatters": "This bridge was previously missing and is now restored on the forced fallback path.",
            "needs": "keep this family intact while testing later scene-start families",
            "sourceStartNeedle": "private fun openForcedFallbackSceneStartBridge(includeEvents: Boolean = true) {",
            "sourceEndNeedle": "private fun sendForcedFallbackCompletionCompanions() {",
            "memberSummary": "1431,568,1465,1919 plus events 60/94",
            "runtimeMarker": "world-open-forced-fallback-scene-bridge",
        },
        {
            "name": "late-light-tail-scripts",
            "kind": "forced-fallback-deferred-family",
            "status": "deferred-on-forced-fallback",
            "whyItMatters": "The full bootstrap runs these scripts when the light tail opens. Forced fallback still waits until scene-start control50 phase 3.",
            "needs": "decide whether these scripts must move earlier than scene-start phase 3 on the forced path",
            "sourceStartNeedle": "private fun sendDeferredSceneStartLightTailScripts() {",
            "sourceEndNeedle": "private fun sendDeferredSceneStartFinalEventDelta() {",
            "memberSummary": "scripts 11145,8420,8310",
            "runtimeMarker": "world-send-deferred-light-tail-scripts-after-scene-start",
        },
        {
            "name": "announcement-bundle",
            "kind": "forced-fallback-deferred-family",
            "status": "deferred-on-forced-fallback",
            "whyItMatters": "The full path sends the announcement bundle during deferred completion. Forced fallback still defers it until final late-ready.",
            "needs": "keep it deferred only if earlier delivery reintroduces loops; otherwise consider moving it closer to the full path",
            "sourceStartNeedle": "private fun sendDeferredCompletionAnnouncementScripts() {",
            "sourceEndNeedle": "private fun sendDeferredLateWorldCompletionEventDelta() {",
            "memberSummary": "scripts 1264,3529",
            "runtimeMarker": "world-send-deferred-completion-announcement-scripts-after-late-ready",
        },
        {
            "name": "completion-script-batch",
            "kind": "forced-fallback-deferred-family",
            "status": "present",
            "whyItMatters": "The forced path now restores the full deferred completion script batch, including 5559 and 3957.",
            "needs": "leave this intact unless a later trace proves one script is still ordered too late",
            "sourceStartNeedle": "private fun sendDeferredCompletionFullScripts() {",
            "sourceEndNeedle": "private fun sendLateRootInterfaceEventsIfConfigured(): Boolean {",
            "memberSummary": "8862,2651,7486,10903,8778,4704,4308,10623,5559,3957",
            "runtimeMarker": "world-send-forced-fallback-deferred-completion-scripts",
        },
    ]

    rows: list[dict[str, Any]] = []
    for family in families:
        start_line = find_line(source_lines, family["sourceStartNeedle"])
        end_line = find_line(source_lines, family["sourceEndNeedle"])
        row = {
            "name": family["name"],
            "kind": family["kind"],
            "status": family["status"],
            "whyItMatters": family["whyItMatters"],
            "needs": family["needs"],
            "memberSummary": family["memberSummary"],
            "source": {
                "path": str(WORLD_PLAYER_SOURCE),
                "startLine": start_line,
                "endLine": end_line,
            },
            "runtimeMarker": family["runtimeMarker"],
            "runtimeObserved": session_has(forced_session, family["runtimeMarker"]) if family["runtimeMarker"] else None,
            "runtimeLine": marker_line(forced_session, family["runtimeMarker"]) if family["runtimeMarker"] else None,
        }
        rows.append(row)
    return rows


def build_verdict(families: list[dict[str, Any]], forced_session: dict[str, Any] | None) -> dict[str, Any]:
    missing = [family for family in families if family.get("status") == "missing-on-forced-fallback"]
    deferred = [family for family in families if family.get("status") == "deferred-on-forced-fallback"]
    latest_blocker = "no-forced-fallback-session"
    recommendation = "No forced fallback session was found in the world log."
    needs = ["fresh forced MAP_BUILD fallback session with world trace"]

    if forced_session:
        latest_blocker = "forced-fallback-family-gap-before-scene-archives"
        recommendation = (
            "The forced fallback path is still materially smaller than the stable/full bootstrap. "
            "The next concrete gap is the full-only restored interface families that never materialize before scene loading should start."
        )
        needs = []
        if missing:
            needs.append(missing[0]["needs"])
        if len(missing) > 1:
            needs.append(missing[1]["needs"])
        if deferred:
            needs.append(deferred[0]["needs"])
        needs = list(dict.fromkeys(needs))

    return {
        "latestLikelyBlocker": latest_blocker,
        "recommendation": recommendation,
        "needs": needs,
    }


def build_artifact(args: argparse.Namespace) -> dict[str, Any]:
    sessions = load_all_sessions(args.world_log)
    forced_session = find_latest_session(sessions, contains="world-force-minimal-interface-bootstrap")
    full_session = find_latest_session(
        sessions,
        contains="world-open-restored-interface",
        excludes="world-force-minimal-interface-bootstrap",
    )
    source_lines = args.world_player_source.read_text(encoding="utf-8").splitlines()
    families = build_family_rows(source_lines, forced_session)
    verdict = build_verdict(families, forced_session)

    return standard_tool_artifact(
        tool_name="run_946_forced_fallback_parity_doctor",
        status="ok" if forced_session else "partial",
        inputs={
            "worldLog": str(args.world_log),
            "worldPlayerSource": str(args.world_player_source),
        },
        artifacts={
            "forcedFallbackParityDoctorJson": str(args.output_dir / PARITY_JSON),
            "forcedFallbackParityDoctorMarkdown": str(args.output_dir / PARITY_MD),
        },
        summary={
            "latestLikelyBlocker": verdict["latestLikelyBlocker"],
            "forcedFallbackSessionFound": forced_session is not None,
            "fullBootstrapSessionFound": full_session is not None,
            "missingFamilyCount": sum(1 for family in families if family["status"] == "missing-on-forced-fallback"),
            "deferredFamilyCount": sum(1 for family in families if family["status"] == "deferred-on-forced-fallback"),
        },
        extra={
            "verdict": verdict,
            "forcedFallbackSession": session_summary(forced_session) if forced_session else {},
            "fullBootstrapSession": session_summary(full_session) if full_session else {},
            "families": families,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {}) or {}
    verdict = artifact.get("verdict", {}) or {}
    lines = [
        "# 946 Forced Fallback Parity Doctor",
        "",
        f"- Status: `{artifact.get('status', 'unknown')}`",
        f"- Latest likely blocker: `{summary.get('latestLikelyBlocker', '')}`",
        f"- Forced fallback session found: `{summary.get('forcedFallbackSessionFound', False)}`",
        f"- Full bootstrap session found: `{summary.get('fullBootstrapSessionFound', False)}`",
        f"- Missing family count: `{summary.get('missingFamilyCount', 0)}`",
        f"- Deferred family count: `{summary.get('deferredFamilyCount', 0)}`",
        "",
        "## Verdict",
        "",
        f"- Recommendation: {verdict.get('recommendation', 'n/a')}",
        "",
        "## Exact Needs",
        "",
    ]
    for need in verdict.get("needs", []) or []:
        lines.append(f"- {need}")

    lines.extend(
        [
            "",
            "## Families",
            "",
        ]
    )
    for family in artifact.get("families", []) or []:
        source = family.get("source", {}) or {}
        lines.extend(
            [
                f"### {family.get('name', '')}",
                "",
                f"- Kind: `{family.get('kind', '')}`",
                f"- Status: `{family.get('status', '')}`",
                f"- Members: `{family.get('memberSummary', '')}`",
                f"- Why it matters: {family.get('whyItMatters', '')}",
                f"- Needs: {family.get('needs', '')}",
                (
                    f"- Source: `{source.get('path', '')}:{source.get('startLine', '?')}`"
                    + (f" -> `{source.get('endLine', '?')}`" if source.get("endLine") else "")
                ),
            ]
        )
        runtime_marker = family.get("runtimeMarker")
        if runtime_marker:
            lines.append(f"- Runtime marker: `{runtime_marker}` observed=`{family.get('runtimeObserved')}`")
            if family.get("runtimeLine"):
                lines.append(f"- Runtime line: `{family.get('runtimeLine')}`")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    args = parse_args()
    ensure_directory(args.output_dir)

    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    fingerprint = input_fingerprint(args)
    outputs = output_paths(args.output_dir)
    if cache_hit(cache_manifest, PARITY_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / PARITY_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return

    artifact = build_artifact(args)
    artifact["cache"] = {"key": PARITY_CACHE_KEY, "fingerprint": fingerprint}
    write_json(args.output_dir / PARITY_JSON, artifact)
    (args.output_dir / PARITY_MD).write_text(render_markdown(artifact), encoding="utf-8")
    record_cache_entry(cache_manifest, PARITY_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")


if __name__ == "__main__":
    main()
