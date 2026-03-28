from __future__ import annotations

import argparse
import re
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
from protocol_946_debug_common import WORLD_LOG_DEFAULT, session_summary
from run_946_loopback_doctor import DEFAULT_SERVER_LOG, select_cluster
from run_946_scene_delivery_aid import DEFAULT_CONTENT_CAPTURE_DIR


READY_SIGNAL_JSON = "ready-signal-doctor.json"
READY_SIGNAL_MD = "ready-signal-doctor.md"
READY_SIGNAL_CACHE_KEY = "ready-signal-doctor"

LOGIN_ATTEMPT_RE = re.compile(r"Attempted game login:\s+(?P<player>[^,]+),")
CHANNEL_CLOSE_RE = re.compile(r"closed after bootstrap stage (?P<stage>[\w-]+)")
WAIT_READY_RE = re.compile(r"Waiting for post-bootstrap world-ready signal before sending initial world sync for (?P<player>\S+)")
SKIP_READY_RE = re.compile(r"Skipping post-bootstrap world-ready wait for (?P<player>\S+) because (?P<reason>.+)")
LATCH_READY_RE = re.compile(
    r"Latching (?:decoded client opcode|unidentified client opcode)\s+(?P<opcode>\d+).+world-ready candidate"
)
ACCEPT_READY_RE = re.compile(
    r"Treating unidentified opcode (?P<opcode>\d+) as (?:late )?post-bootstrap world-ready signal"
)
IGNORE_READY_RE = re.compile(
    r"Ignoring unidentified client opcode (?P<opcode>\d+).+awaitingMapBuildComplete=(?P<awaiting_map>\w+),?\s+awaitingWorldReadySignal=(?P<awaiting_ready>\w+)"
)
READY_FALLBACK_RE = re.compile(r"World-ready signal not received for (?P<player>\S+) after (?P<ticks>\d+) ticks")
MAP_BUILD_FALLBACK_RE = re.compile(r"MAP_BUILD_COMPLETE not received for (?P<player>\S+) after (?P<ticks>\d+) ticks")
BOOTSTRAP_FINISHED_RE = re.compile(r"Finished world bootstrap for (?P<player>\S+)")

READY_SIGNAL_OPCODES = {17, 48, 50}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Explain 946 post-bootstrap ready-signal behavior per attempt, including when the "
            "client sent opcodes 17/48/50 after the server had already cleared the ready wait."
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
        output_dir / READY_SIGNAL_JSON,
        output_dir / READY_SIGNAL_MD,
    ]


def empty_attempt(player: str, login_line: int) -> dict[str, Any]:
    return {
        "player": player,
        "loginLine": login_line,
        "closeLine": None,
        "closeStage": "",
        "bootstrapFinished": False,
        "waitReadyCount": 0,
        "skipReadyReasons": [],
        "latchedReadyOpcodes": [],
        "acceptedReadyOpcodes": [],
        "ignoredReadyOpcodes": [],
        "ignoredReadyDetails": [],
        "readyFallbackTicks": [],
        "mapBuildFallbackTicks": [],
    }


def parse_server_attempts(server_log: Path) -> list[dict[str, Any]]:
    if not server_log.exists():
        return []
    attempts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    lines = server_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        login_match = LOGIN_ATTEMPT_RE.search(line)
        if login_match:
            if current is not None:
                attempts.append(current)
            current = empty_attempt(login_match.group("player"), line_number)
            continue
        if current is None:
            continue

        if BOOTSTRAP_FINISHED_RE.search(line):
            current["bootstrapFinished"] = True

        if WAIT_READY_RE.search(line):
            current["waitReadyCount"] += 1

        skip_match = SKIP_READY_RE.search(line)
        if skip_match:
            current["skipReadyReasons"].append(skip_match.group("reason"))

        latch_match = LATCH_READY_RE.search(line)
        if latch_match:
            current["latchedReadyOpcodes"].append(int(latch_match.group("opcode")))

        accept_match = ACCEPT_READY_RE.search(line)
        if accept_match:
            current["acceptedReadyOpcodes"].append(int(accept_match.group("opcode")))

        ignore_match = IGNORE_READY_RE.search(line)
        if ignore_match:
            opcode = int(ignore_match.group("opcode"))
            if opcode in READY_SIGNAL_OPCODES:
                current["ignoredReadyOpcodes"].append(opcode)
                current["ignoredReadyDetails"].append(
                    {
                        "opcode": opcode,
                        "awaitingMapBuildComplete": ignore_match.group("awaiting_map") == "true",
                        "awaitingWorldReadySignal": ignore_match.group("awaiting_ready") == "true",
                        "lineNumber": line_number,
                    }
                )

        ready_fallback_match = READY_FALLBACK_RE.search(line)
        if ready_fallback_match:
            current["readyFallbackTicks"].append(int(ready_fallback_match.group("ticks")))

        map_build_fallback_match = MAP_BUILD_FALLBACK_RE.search(line)
        if map_build_fallback_match:
            current["mapBuildFallbackTicks"].append(int(map_build_fallback_match.group("ticks")))

        close_match = CHANNEL_CLOSE_RE.search(line)
        if close_match:
            current["closeLine"] = line_number
            current["closeStage"] = close_match.group("stage")
            attempts.append(current)
            current = None

    if current is not None:
        attempts.append(current)
    return attempts


def summarize_attempt(world_session: dict[str, Any], server_attempt: dict[str, Any] | None, attempt_index: int) -> dict[str, Any]:
    server_attempt = server_attempt or {}
    skip_ready_reasons = list(server_attempt.get("skipReadyReasons", []))
    latched = list(server_attempt.get("latchedReadyOpcodes", []))
    accepted = list(server_attempt.get("acceptedReadyOpcodes", []))
    ignored = list(server_attempt.get("ignoredReadyOpcodes", []))

    needs: list[str] = []
    if skip_ready_reasons and ignored:
        needs.append(
            "keep awaitingWorldReadySignal alive long enough to consume later client ready packets "
            f"{sorted(set(ignored))} instead of ignoring them after forced fallback"
        )
    elif skip_ready_reasons and not latched:
        needs.append("delay forced-fallback initial sync until a post-bootstrap ready burst arrives")
    elif latched and not accepted:
        needs.append("consume the latched world-ready opcode instead of leaving it pending across close")
    elif accepted:
        needs.append("compare post-ready world sync tail against a non-looping baseline; ready signal was consumed")

    if server_attempt.get("closeStage") == "interfaces":
        needs.append("keep the world channel alive past interfaces after the first ready-aware sync")

    return {
        "attemptIndex": attempt_index,
        "worldSession": session_summary(world_session),
        "serverAttempt": {
            "player": server_attempt.get("player", ""),
            "loginLine": server_attempt.get("loginLine"),
            "closeLine": server_attempt.get("closeLine"),
            "closeStage": server_attempt.get("closeStage", ""),
            "bootstrapFinished": bool(server_attempt.get("bootstrapFinished")),
            "waitReadyCount": int(server_attempt.get("waitReadyCount", 0) or 0),
            "skipReadyReasons": skip_ready_reasons,
            "latchedReadyOpcodes": latched,
            "acceptedReadyOpcodes": accepted,
            "ignoredReadyOpcodes": ignored,
            "ignoredReadyDetails": list(server_attempt.get("ignoredReadyDetails", [])),
            "readyFallbackTicks": list(server_attempt.get("readyFallbackTicks", [])),
            "mapBuildFallbackTicks": list(server_attempt.get("mapBuildFallbackTicks", [])),
        },
        "needs": list(dict.fromkeys(needs)),
    }


def build_attempts(world_sessions: list[dict[str, Any]], server_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    pair_count = min(len(world_sessions), len(server_attempts))
    paired_server_attempts = server_attempts[-pair_count:] if pair_count else []
    server_lookup_offset = len(world_sessions) - pair_count

    for world_index, world_session in enumerate(world_sessions):
        server_attempt = None
        if world_index >= server_lookup_offset and paired_server_attempts:
            server_attempt = paired_server_attempts[world_index - server_lookup_offset]
        attempts.append(summarize_attempt(world_session, server_attempt, world_index + 1))
    return attempts


def verdict(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    if not attempts:
        return {
            "likelyBlocker": "no-world-attempts",
            "recommendation": "No world attempts were matched to the current cluster yet.",
            "needs": ["fresh post-login world attempt"],
        }

    skipped_and_ignored = [
        attempt
        for attempt in attempts
        if attempt["serverAttempt"].get("skipReadyReasons") and attempt["serverAttempt"].get("ignoredReadyOpcodes")
    ]
    latched_and_accepted = [
        attempt
        for attempt in attempts
        if attempt["serverAttempt"].get("latchedReadyOpcodes") and attempt["serverAttempt"].get("acceptedReadyOpcodes")
    ]
    skipped_without_latch = [
        attempt
        for attempt in attempts
        if attempt["serverAttempt"].get("skipReadyReasons") and not attempt["serverAttempt"].get("latchedReadyOpcodes")
    ]

    latest = attempts[-1]
    latest_needs = latest.get("needs", [])
    if skipped_and_ignored:
        return {
            "likelyBlocker": "ready-signal-cleared-too-early",
            "recommendation": (
                "The forced fallback clears the post-bootstrap ready wait, then later client ready opcodes "
                "17/48/50 arrive and are ignored before the channel closes."
            ),
            "needs": latest_needs,
        }
    if skipped_without_latch:
        return {
            "likelyBlocker": "ready-signal-never-latched",
            "recommendation": (
                "Most attempts skip the ready wait without ever latching a compatible client ready opcode. "
                "Keep the forced fallback alive long enough to observe the first ready burst."
            ),
            "needs": latest_needs,
        }
    if latched_and_accepted:
        return {
            "likelyBlocker": "ready-signal-accepted-but-loop-persisted",
            "recommendation": (
                "The client ready signal is being latched and consumed on at least one attempt, so the next gap is "
                "after the ready transition, not in the latch itself."
            ),
            "needs": latest_needs,
        }
    return {
        "likelyBlocker": "ready-signal-unclassified",
        "recommendation": "Ready-signal behavior was observed, but the latest cluster does not fit a single dominant pattern yet.",
        "needs": latest_needs,
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
    attempts = build_attempts(world_sessions, server_attempts)
    ready_verdict = verdict(attempts)

    skipped_ready_count = sum(1 for attempt in attempts if attempt["serverAttempt"].get("skipReadyReasons"))
    waited_ready_count = sum(1 for attempt in attempts if attempt["serverAttempt"].get("waitReadyCount", 0) > 0)
    ignored_ready_count = sum(len(attempt["serverAttempt"].get("ignoredReadyOpcodes", [])) for attempt in attempts)
    accepted_ready_count = sum(len(attempt["serverAttempt"].get("acceptedReadyOpcodes", [])) for attempt in attempts)
    latched_ready_count = sum(len(attempt["serverAttempt"].get("latchedReadyOpcodes", [])) for attempt in attempts)

    status = "ok" if attempts else "partial"
    return standard_tool_artifact(
        tool_name="run_946_ready_signal_doctor",
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
            "readySignalDoctorJson": str(args.output_dir / READY_SIGNAL_JSON),
            "readySignalDoctorMarkdown": str(args.output_dir / READY_SIGNAL_MD),
        },
        summary={
            "clusterId": cluster_id,
            "attemptCount": len(attempts),
            "skippedReadyWaitCount": skipped_ready_count,
            "waitedReadyCount": waited_ready_count,
            "latchedReadyOpcodeCount": latched_ready_count,
            "acceptedReadyOpcodeCount": accepted_ready_count,
            "ignoredReadyOpcodeCount": ignored_ready_count,
            "likelyBlocker": ready_verdict["likelyBlocker"],
        },
        extra={
            "cluster": {
                "clusterId": cluster_id,
                "clusterStartTimestamp": cluster_start.isoformat() if cluster_start else "",
                "contentSessionCount": len(cluster_sessions),
                "worldSessionCount": len(world_sessions),
            },
            "attempts": attempts,
            "verdict": ready_verdict,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {}) or {}
    verdict_payload = artifact.get("verdict", {}) or {}
    lines = [
        "# 946 Ready Signal Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{summary.get('clusterId', '')}`",
        f"- Attempts analyzed: `{summary.get('attemptCount', 0)}`",
        f"- Skipped ready wait: `{summary.get('skippedReadyWaitCount', 0)}`",
        f"- Waited for ready signal: `{summary.get('waitedReadyCount', 0)}`",
        f"- Latched ready opcodes: `{summary.get('latchedReadyOpcodeCount', 0)}`",
        f"- Accepted ready opcodes: `{summary.get('acceptedReadyOpcodeCount', 0)}`",
        f"- Ignored ready opcodes: `{summary.get('ignoredReadyOpcodeCount', 0)}`",
        "",
        "## Verdict",
        "",
        f"- Likely blocker: `{verdict_payload.get('likelyBlocker', 'unknown')}`",
        f"- Recommendation: {verdict_payload.get('recommendation', 'No recommendation available.')}",
        "",
        "## Exact Needs",
        "",
    ]
    needs = verdict_payload.get("needs", []) or []
    if needs:
        for item in needs:
            lines.append(f"- {item}")
    else:
        lines.append("- No additional needs recorded.")
    lines.extend(["", "## Attempts", ""])
    for attempt in artifact.get("attempts", []) or []:
        server_attempt = attempt.get("serverAttempt") or {}
        world = attempt.get("worldSession") or {}
        lines.append(f"### Attempt {attempt.get('attemptIndex')}")
        lines.append("")
        lines.append(f"- World stages: `{world.get('stageSequence', [])}`")
        lines.append(f"- Disconnect stage: `{server_attempt.get('closeStage', '')}`")
        lines.append(f"- Waited for ready: `{server_attempt.get('waitReadyCount', 0) > 0}`")
        lines.append(f"- Skipped ready wait reasons: `{server_attempt.get('skipReadyReasons', [])}`")
        lines.append(f"- Latched ready opcodes: `{server_attempt.get('latchedReadyOpcodes', [])}`")
        lines.append(f"- Accepted ready opcodes: `{server_attempt.get('acceptedReadyOpcodes', [])}`")
        lines.append(f"- Ignored ready opcodes: `{server_attempt.get('ignoredReadyOpcodes', [])}`")
        if server_attempt.get("ignoredReadyDetails"):
            for item in server_attempt["ignoredReadyDetails"]:
                lines.append(
                    "- Ignored detail: "
                    f"opcode={item.get('opcode')} awaitingMapBuildComplete={item.get('awaitingMapBuildComplete')} "
                    f"awaitingWorldReadySignal={item.get('awaitingWorldReadySignal')} line={item.get('lineNumber')}"
                )
        for need in attempt.get("needs", []) or []:
            lines.append(f"- Needs: {need}")
        lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    requested_cluster_id = getattr(args, "cluster_id", None)
    return artifact_input_fingerprint(
        "run_946_ready_signal_doctor",
        [
            WORKSPACE / "tools" / "run_946_ready_signal_doctor.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            WORKSPACE / "tools" / "protocol_946_debug_common.py",
            WORKSPACE / "tools" / "run_946_loopback_doctor.py",
            args.world_log,
            args.server_log,
        ],
        clusterId=requested_cluster_id or "",
        attemptLimit=args.attempt_limit,
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / READY_SIGNAL_JSON, artifact)
    (output_dir / READY_SIGNAL_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, READY_SIGNAL_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / READY_SIGNAL_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, READY_SIGNAL_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
