from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
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
from run_946_scene_delivery_aid import (
    DEFAULT_CONTENT_CAPTURE_DIR,
    list_content_capture_logs,
    parse_content_capture_log,
    safe_parse_timestamp,
)


LOOPBACK_JSON = "loopback-doctor.json"
LOOPBACK_MD = "loopback-doctor.md"
LOOPBACK_CACHE_KEY = "loopback-doctor"
DEFAULT_SERVER_LOG = WORKSPACE / "tmp-manual-js5.err.log"
SESSION_STAMP_RE = re.compile(r"session-\d+-(?P<stamp>\d{8}-\d{6})\.log$")
SESSION_ID_RE = re.compile(r"session#(?P<id>\d+)")
SESSION_START_RE = re.compile(r"session#(?P<id>\d+) start=(?P<timestamp>\S+)")
SESSION_END_RE = re.compile(r"session#(?P<id>\d+) end=(?P<timestamp>\S+)")
SESSION_ROUTE_RE = re.compile(r"session#(?P<id>\d+) session-route=(?P<route>[\w-]+)")
SESSION_MODE_RE = re.compile(r"session#(?P<id>\d+) mode=(?P<mode>[\w-]+)")
SESSION_BYTES_RE = re.compile(
    r"session#(?P<id>\d+) bytes (?P<direction>[a-z\-]+)->remote=(?P<to_remote>\d+) remote->(?P=direction)=(?P<from_remote>\d+)"
)
LOGIN_ATTEMPT_RE = re.compile(r"Attempted game login:\s+(?P<player>[^,]+),")
CHANNEL_CLOSE_RE = re.compile(r"closed after bootstrap stage (?P<stage>[\w-]+)")
BOOTSTRAP_FINISHED_RE = re.compile(r"Finished world bootstrap for (?P<player>\S+)")
READY_WAIT_SKIP_RE = re.compile(r"Skipping post-bootstrap world-ready wait for (?P<player>\S+)")
WAITING_MAP_BUILD_RE = re.compile(r"Waiting for MAP_BUILD_COMPLETE before continuing world bootstrap for (?P<player>\S+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Correlate 946 login/world loopback attempts and explain exactly what each looping run still needs."
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
        output_dir / LOOPBACK_JSON,
        output_dir / LOOPBACK_MD,
    ]


def parse_cluster_stamp(path: Path) -> str:
    match = SESSION_STAMP_RE.match(path.name)
    return match.group("stamp") if match else ""


def parse_cluster_start(stamp: str) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_proxy_session(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    session_id = None
    start_timestamp = ""
    end_timestamp = ""
    route = ""
    mode = ""
    to_remote = 0
    from_remote = 0

    for line in text.splitlines():
        if session_id is None:
            match = SESSION_ID_RE.search(line)
            if match:
                session_id = int(match.group("id"))
        start_match = SESSION_START_RE.match(line.strip())
        if start_match:
            start_timestamp = start_match.group("timestamp")
            continue
        end_match = SESSION_END_RE.match(line.strip())
        if end_match:
            end_timestamp = end_match.group("timestamp")
            continue
        route_match = SESSION_ROUTE_RE.match(line.strip())
        if route_match:
            route = route_match.group("route")
            continue
        mode_match = SESSION_MODE_RE.match(line.strip())
        if mode_match:
            mode = mode_match.group("mode")
            continue
        bytes_match = SESSION_BYTES_RE.match(line.strip())
        if bytes_match:
            to_remote = int(bytes_match.group("to_remote"))
            from_remote = int(bytes_match.group("from_remote"))

    summary = {
        "file": str(path),
        "sessionId": session_id,
        "startTimestamp": start_timestamp,
        "endTimestamp": end_timestamp,
        "start": safe_parse_timestamp(start_timestamp),
        "end": safe_parse_timestamp(end_timestamp),
        "sessionRoute": route or mode,
        "mode": mode,
        "toRemoteBytes": to_remote,
        "fromRemoteBytes": from_remote,
        "requestCount": 0,
        "masterReferenceRequests": 0,
        "referenceTableRequests": 0,
        "archiveRequests": 0,
        "responseHeaderCount": 0,
        "responseBytes": 0,
        "sampleRequests": [],
        "firstRequestLabel": "",
        "truncatedResponse": False,
    }
    if summary["sessionRoute"] == "tls-http-content":
        http_summary = parse_content_capture_log(path)
        if http_summary:
            summary.update(
                {
                    "requestCount": int(http_summary.get("requestCount", 0) or 0),
                    "masterReferenceRequests": int(http_summary.get("masterReferenceRequests", 0) or 0),
                    "referenceTableRequests": int(http_summary.get("referenceTableRequests", 0) or 0),
                    "archiveRequests": int(http_summary.get("archiveRequests", 0) or 0),
                    "responseHeaderCount": int(http_summary.get("responseHeaderCount", 0) or 0),
                    "responseBytes": int(http_summary.get("responseBytes", 0) or 0),
                    "sampleRequests": list(http_summary.get("sampleRequests", [])),
                    "firstRequestLabel": (
                        (http_summary.get("httpRequests") or [{}])[0].get("label", "")
                        if http_summary.get("httpRequests")
                        else ""
                    ),
                    "truncatedResponse": bool(http_summary.get("truncatedResponse")),
                }
            )
    return summary


def grouped_clusters(content_capture_dir: Path) -> list[tuple[str, datetime | None, list[dict[str, Any]]]]:
    logs = list_content_capture_logs(content_capture_dir)
    if not logs:
        return []
    grouped: dict[str, list[Path]] = {}
    for path in logs:
        stamp = parse_cluster_stamp(path)
        if not stamp:
            continue
        grouped.setdefault(stamp, []).append(path)
    ordered = []
    for stamp in sorted(grouped):
        cluster_logs = grouped[stamp]
        ordered.append((stamp, parse_cluster_start(stamp), [parse_proxy_session(path) for path in cluster_logs]))
    return ordered


def parse_server_attempts(server_log: Path) -> list[dict[str, Any]]:
    if not server_log.exists():
        return []
    lines = server_log.read_text(encoding="utf-8", errors="ignore").splitlines()
    attempts: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        login_match = LOGIN_ATTEMPT_RE.search(line)
        if login_match:
            if current is not None:
                attempts.append(current)
            current = {
                "player": login_match.group("player"),
                "bootstrapFinished": False,
                "waitingMapBuildComplete": False,
                "skipReadyWait": False,
                "channelClosed": False,
                "closeStage": "",
                "closeLine": "",
            }
            continue
        if current is None:
            continue
        if BOOTSTRAP_FINISHED_RE.search(line):
            current["bootstrapFinished"] = True
        if WAITING_MAP_BUILD_RE.search(line):
            current["waitingMapBuildComplete"] = True
        if READY_WAIT_SKIP_RE.search(line):
            current["skipReadyWait"] = True
        close_match = CHANNEL_CLOSE_RE.search(line)
        if close_match:
            current["channelClosed"] = True
            current["closeStage"] = close_match.group("stage")
            current["closeLine"] = line
            attempts.append(current)
            current = None

    if current is not None:
        attempts.append(current)
    return attempts


def filter_world_sessions(world_log: Path, cluster_start: datetime | None, attempt_limit: int) -> list[dict[str, Any]]:
    sessions = load_all_sessions(world_log)
    if cluster_start is not None:
        filtered = []
        for session in sessions:
            start = safe_parse_timestamp(session.get("startTimestamp", ""))
            if start and start >= cluster_start:
                filtered.append(session)
        sessions = filtered
    return sessions[-attempt_limit:]


def select_cluster(
    content_capture_dir: Path,
    world_log: Path,
    attempt_limit: int,
    requested_cluster_id: str | None,
) -> tuple[str, datetime | None, list[dict[str, Any]], list[dict[str, Any]]]:
    clusters = grouped_clusters(content_capture_dir)
    if not clusters:
        return "", None, [], []
    if requested_cluster_id:
        for cluster_id, cluster_start, cluster_sessions in clusters:
            if cluster_id == requested_cluster_id:
                return cluster_id, cluster_start, cluster_sessions, filter_world_sessions(world_log, cluster_start, attempt_limit)
    best_choice = None
    for cluster_id, cluster_start, cluster_sessions in clusters:
        world_sessions = filter_world_sessions(world_log, cluster_start, attempt_limit)
        candidate = (cluster_id, cluster_start, cluster_sessions, world_sessions)
        if world_sessions:
            best_choice = candidate
    if best_choice is not None:
        return best_choice
    cluster_id, cluster_start, cluster_sessions = clusters[-1]
    return cluster_id, cluster_start, cluster_sessions, filter_world_sessions(world_log, cluster_start, attempt_limit)


def nearest_session(
    sessions: list[dict[str, Any]],
    target: datetime | None,
    *,
    predicate,
    max_delta_seconds: float,
    used_indexes: set[int],
) -> dict[str, Any] | None:
    if target is None:
        return None
    nearest_index = None
    nearest_distance = None
    for index, session in enumerate(sessions):
        if index in used_indexes or not predicate(session):
            continue
        start = session.get("start")
        if start is None:
            continue
        distance = abs((start - target).total_seconds())
        if distance > max_delta_seconds:
            continue
        if nearest_distance is None or distance < nearest_distance:
            nearest_distance = distance
            nearest_index = index
    if nearest_index is None:
        return None
    used_indexes.add(nearest_index)
    return sessions[nearest_index]


def attempt_needs(
    world_session: dict[str, Any],
    server_attempt: dict[str, Any] | None,
    content_session: dict[str, Any] | None,
) -> list[str]:
    needs: list[str] = []
    if content_session and content_session.get("referenceTableRequests", 0) > 0 and content_session.get("archiveRequests", 0) <= 0:
        label = content_session.get("firstRequestLabel") or "reference table"
        needs.append(
            f"first non-reference /ms request after {label}; current content capture has archiveRequests=0"
        )
    if not content_session:
        needs.append("fresh content capture aligned to this world attempt; no nearby tls-http-content session was paired")
    if server_attempt and server_attempt.get("channelClosed"):
        needs.append(
            f"world channel must stay alive past bootstrap stage {server_attempt.get('closeStage') or 'unknown'}"
        )
    if server_attempt and server_attempt.get("bootstrapFinished"):
        needs.append("post-bootstrap scene/archive transition, not more pre-login routing")
    if "interfaces" in (world_session.get("stageSequence") or []) and not (content_session and content_session.get("archiveRequests", 0) > 0):
        needs.append("first real scene archive request after interfaces")
    deduped: list[str] = []
    for item in needs:
        if item not in deduped:
            deduped.append(item)
    return deduped


def attempt_outcome(
    world_session: dict[str, Any],
    server_attempt: dict[str, Any] | None,
    content_session: dict[str, Any] | None,
) -> str:
    if not world_session:
        return "prelogin-stall"
    if content_session and content_session.get("archiveRequests", 0) > 0:
        if content_session.get("truncatedResponse"):
            return "archive-delivery-truncated"
        return "archive-delivery-observed"
    if content_session and content_session.get("referenceTableRequests", 0) > 0:
        if (server_attempt or {}).get("closeStage") == "interfaces":
            return "reference-table-loopback"
        return "reference-tables-only"
    if (server_attempt or {}).get("closeStage") == "interfaces":
        return "interfaces-loopback"
    return "world-loopback-unclassified"


def build_attempts(
    world_sessions: list[dict[str, Any]],
    server_attempts: list[dict[str, Any]],
    cluster_sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    pair_count = min(len(world_sessions), len(server_attempts))
    paired_server_attempts = server_attempts[-pair_count:] if pair_count else []
    server_lookup_offset = len(world_sessions) - pair_count
    used_content_indexes: set[int] = set()
    used_login_raw_indexes: set[int] = set()

    for world_index, world_session in enumerate(world_sessions):
        world_start = safe_parse_timestamp(world_session.get("startTimestamp", ""))
        content_session = nearest_session(
            cluster_sessions,
            world_start,
            predicate=lambda item: item.get("sessionRoute") == "tls-http-content",
            max_delta_seconds=30.0,
            used_indexes=used_content_indexes,
        )
        login_raw_session = nearest_session(
            cluster_sessions,
            world_start,
            predicate=lambda item: item.get("sessionRoute") == "raw-game" and int(item.get("toRemoteBytes", 0) or 0) >= 500,
            max_delta_seconds=8.0,
            used_indexes=used_login_raw_indexes,
        )
        server_attempt = None
        if world_index >= server_lookup_offset and paired_server_attempts:
            server_attempt = paired_server_attempts[world_index - server_lookup_offset]
        needs = attempt_needs(world_session, server_attempt, content_session)
        attempts.append(
            {
                "attemptIndex": world_index + 1,
                "worldSession": session_summary(world_session),
                "serverAttempt": server_attempt or {},
                "pairedContentSession": summarize_proxy_session(content_session),
                "pairedLoginRawSession": summarize_proxy_session(login_raw_session),
                "outcome": attempt_outcome(world_session, server_attempt, content_session),
                "needs": needs,
            }
        )
    return attempts


def summarize_proxy_session(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {}
    return {
        "file": session.get("file"),
        "sessionRoute": session.get("sessionRoute"),
        "startTimestamp": session.get("startTimestamp"),
        "toRemoteBytes": session.get("toRemoteBytes"),
        "fromRemoteBytes": session.get("fromRemoteBytes"),
        "requestCount": session.get("requestCount", 0),
        "masterReferenceRequests": session.get("masterReferenceRequests", 0),
        "referenceTableRequests": session.get("referenceTableRequests", 0),
        "archiveRequests": session.get("archiveRequests", 0),
        "responseHeaderCount": session.get("responseHeaderCount", 0),
        "responseBytes": session.get("responseBytes", 0),
        "firstRequestLabel": session.get("firstRequestLabel", ""),
        "truncatedResponse": session.get("truncatedResponse", False),
    }


def cluster_summary(cluster_id: str, cluster_start: datetime | None, cluster_sessions: list[dict[str, Any]]) -> dict[str, Any]:
    raw_sessions = [session for session in cluster_sessions if session.get("sessionRoute") == "raw-game"]
    http_sessions = [session for session in cluster_sessions if session.get("sessionRoute") == "tls-http-content"]
    return {
        "clusterId": cluster_id,
        "clusterStartTimestamp": cluster_start.isoformat() if cluster_start else "",
        "rawGameSessionCount": len(raw_sessions),
        "contentSessionCount": len(http_sessions),
        "referenceTableRequestCount": sum(int(session.get("referenceTableRequests", 0) or 0) for session in http_sessions),
        "archiveRequestCount": sum(int(session.get("archiveRequests", 0) or 0) for session in http_sessions),
        "responseHeaderCount": sum(int(session.get("responseHeaderCount", 0) or 0) for session in http_sessions),
        "responseBytes": sum(int(session.get("responseBytes", 0) or 0) for session in http_sessions),
    }


def verdict(attempts: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    if not attempts:
        return {
            "likelyBlocker": "prelogin-stall",
            "recommendation": "No post-login world attempts were found for the current launch cluster. Focus on the pre-login loading path first.",
            "needs": ["fresh world session after login"],
        }
    latest = attempts[-1]
    outcome = latest.get("outcome")
    if outcome == "reference-table-loopback":
        return {
            "likelyBlocker": "reference-table-loopback",
            "recommendation": "The client reaches world bootstrap and interfaces, but the paired content capture never progresses beyond reference tables before the world channel closes again.",
            "needs": latest.get("needs", []),
        }
    if outcome == "archive-delivery-truncated":
        return {
            "likelyBlocker": "archive-delivery-truncated",
            "recommendation": "Real scene archive delivery started, but the paired content response ended early. Fix the content path before changing more world packets.",
            "needs": latest.get("needs", []),
        }
    if outcome == "archive-delivery-observed":
        return {
            "likelyBlocker": "post-archive-loopback",
            "recommendation": "Scene archive delivery started before the loopback, so the next gap is after assets begin arriving, not in the pre-login/content routing path.",
            "needs": latest.get("needs", []),
        }
    if summary.get("referenceTableRequestCount", 0) > 0 and summary.get("archiveRequestCount", 0) <= 0:
        return {
            "likelyBlocker": "reference-tables-only-cluster",
            "recommendation": "Across the current launch cluster, content capture shows repeated reference-table fetches with zero real scene archive requests.",
            "needs": latest.get("needs", []),
        }
    return {
        "likelyBlocker": outcome or "unknown",
        "recommendation": "The current launch still loops back, but the missing transition is not yet uniquely identified. Check the paired attempt details below.",
        "needs": latest.get("needs", []),
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
    attempts = build_attempts(world_sessions, server_attempts, cluster_sessions)
    summary = cluster_summary(cluster_id, cluster_start, cluster_sessions)
    loopback_verdict = verdict(attempts, summary)
    latest_attempt = attempts[-1] if attempts else {}

    status = "ok" if attempts else "partial"
    return standard_tool_artifact(
        tool_name="run_946_loopback_doctor",
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
            "loopbackDoctorJson": str(args.output_dir / LOOPBACK_JSON),
            "loopbackDoctorMarkdown": str(args.output_dir / LOOPBACK_MD),
        },
        summary={
            "attemptCount": len(attempts),
            "clusterId": cluster_id,
            "rawGameSessionCount": summary["rawGameSessionCount"],
            "contentSessionCount": summary["contentSessionCount"],
            "referenceTableRequestCount": summary["referenceTableRequestCount"],
            "archiveRequestCount": summary["archiveRequestCount"],
            "latestOutcome": latest_attempt.get("outcome", ""),
            "latestDisconnectStage": (latest_attempt.get("serverAttempt") or {}).get("closeStage", ""),
            "latestNeeds": latest_attempt.get("needs", []),
            "likelyBlocker": loopback_verdict["likelyBlocker"],
        },
        extra={
            "cluster": summary,
            "attempts": attempts,
            "verdict": loopback_verdict,
        },
    )


def render_markdown(artifact: dict[str, Any]) -> str:
    summary = artifact.get("summary", {}) or {}
    verdict_payload = artifact.get("verdict", {}) or {}
    lines = [
        "# 946 Loopback Doctor",
        "",
        f"- Status: `{artifact['status']}`",
        f"- Cluster id: `{summary.get('clusterId', '')}`",
        f"- Attempts analyzed: `{summary.get('attemptCount', 0)}`",
        f"- Raw-game sessions: `{summary.get('rawGameSessionCount', 0)}`",
        f"- Content sessions: `{summary.get('contentSessionCount', 0)}`",
        f"- Reference-table requests: `{summary.get('referenceTableRequestCount', 0)}`",
        f"- Scene archive requests: `{summary.get('archiveRequestCount', 0)}`",
        f"- Latest outcome: `{summary.get('latestOutcome', '')}`",
        f"- Latest disconnect stage: `{summary.get('latestDisconnectStage', '')}`",
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
    attempts = artifact.get("attempts", []) or []
    if not attempts:
        lines.append("- No matching world attempts were found for the latest launch cluster.")
    for attempt in attempts:
        world = attempt.get("worldSession") or {}
        server_attempt = attempt.get("serverAttempt") or {}
        content = attempt.get("pairedContentSession") or {}
        login_raw = attempt.get("pairedLoginRawSession") or {}
        lines.append(f"### Attempt {attempt.get('attemptIndex')}")
        lines.append("")
        lines.append(f"- Outcome: `{attempt.get('outcome', '')}`")
        lines.append(f"- World stages: `{world.get('stageSequence', [])}`")
        lines.append(f"- World window: `{world.get('startLine')}:{world.get('endLine')}`")
        lines.append(f"- Disconnect stage: `{server_attempt.get('closeStage', '')}`")
        lines.append(f"- Bootstrap finished: `{server_attempt.get('bootstrapFinished', False)}`")
        lines.append(f"- Waiting MAP_BUILD_COMPLETE: `{server_attempt.get('waitingMapBuildComplete', False)}`")
        lines.append(f"- Skipped ready wait: `{server_attempt.get('skipReadyWait', False)}`")
        if content:
            lines.append(
                f"- Paired content: `{Path(content.get('file', '')).name}` route=`{content.get('sessionRoute')}` first=`{content.get('firstRequestLabel', '')}` refTables=`{content.get('referenceTableRequests', 0)}` archives=`{content.get('archiveRequests', 0)}`"
            )
        else:
            lines.append("- Paired content: `<missing>`")
        if login_raw:
            lines.append(
                f"- Paired login raw: `{Path(login_raw.get('file', '')).name}` bytes=`{login_raw.get('toRemoteBytes', 0)}->{login_raw.get('fromRemoteBytes', 0)}`"
            )
        else:
            lines.append("- Paired login raw: `<missing>`")
        needs = attempt.get("needs", []) or []
        if needs:
            for item in needs:
                lines.append(f"- Needs: {item}")
        lines.append("")
    return "\n".join(lines)


def input_fingerprint(args: argparse.Namespace) -> str:
    requested_cluster_id = getattr(args, "cluster_id", None)
    content_logs = list_content_capture_logs(args.content_capture_dir)
    return artifact_input_fingerprint(
        "run_946_loopback_doctor",
        [
            WORKSPACE / "tools" / "run_946_loopback_doctor.py",
            WORKSPACE / "tools" / "protocol_automation_common.py",
            WORKSPACE / "tools" / "protocol_946_debug_common.py",
            WORKSPACE / "tools" / "run_946_scene_delivery_aid.py",
            args.world_log,
            args.server_log,
            *content_logs[-256:],
        ],
        clusterId=requested_cluster_id or "",
        attemptLimit=args.attempt_limit,
    )


def write_artifacts(output_dir: Path, artifact: dict[str, Any]) -> None:
    ensure_directory(output_dir)
    write_json(output_dir / LOOPBACK_JSON, artifact)
    (output_dir / LOOPBACK_MD).write_text(render_markdown(artifact), encoding="utf-8")


def main() -> int:
    args = parse_args()
    cache_manifest_path = args.output_dir / "cache-manifest.json"
    cache_manifest = load_json(cache_manifest_path, {}) or {}
    outputs = output_paths(args.output_dir)
    fingerprint = input_fingerprint(args)
    if cache_hit(cache_manifest, LOOPBACK_CACHE_KEY, fingerprint, outputs, force=args.force):
        artifact = load_json(args.output_dir / LOOPBACK_JSON, {}) or {}
        print(stable_json_text({"status": "cached", "artifacts": artifact.get("artifacts", {})}), end="")
        return 0

    artifact = build_artifact(args)
    write_artifacts(args.output_dir, artifact)
    record_cache_entry(cache_manifest, LOOPBACK_CACHE_KEY, fingerprint, outputs)
    write_json(cache_manifest_path, cache_manifest)
    print(stable_json_text({"status": artifact["status"], "artifacts": artifact["artifacts"]}), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
