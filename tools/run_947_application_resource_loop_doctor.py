from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

try:
    from tools.run_947_logged_out_js5_session_doctor import (
        DEFAULT_LOG_PATH,
        DEFAULT_TOKEN_URL,
        Js5Request,
        compare_responses,
        fetch_token,
        replay_sequence,
    )
except ImportError:
    from run_947_logged_out_js5_session_doctor import (  # type: ignore
        DEFAULT_LOG_PATH,
        DEFAULT_TOKEN_URL,
        Js5Request,
        compare_responses,
        fetch_token,
        replay_sequence,
    )


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "application-resource-loop-doctor-947-current"


@dataclass(frozen=True)
class LoopSession:
    remote: str
    first_line: int
    last_line: int
    request_count: int
    requests: list[Js5Request]


@dataclass(frozen=True)
class LoopCycle:
    cycle_length: int
    repeat_count: int
    requests: list[Js5Request]
    tail_skew: int
    window_end_offset: int
    cycle_first_line: int
    cycle_last_line: int


def request_marker(request: Js5Request) -> tuple[int, int, int, bool, str]:
    return (request.index, request.archive, request.opcode, request.priority, request.kind)


def canonicalize_cycle_requests(requests: list[Js5Request]) -> list[Js5Request]:
    if not requests:
        return []

    markers = [request_marker(request) for request in requests]
    best_index = min(
        range(len(requests)),
        key=lambda index: tuple(markers[index:] + markers[:index]),
    )
    return requests[best_index:] + requests[:best_index]


def parse_recent_reference_requests(
    log_path: Path,
    build: int,
    max_requests_per_remote: int,
) -> list[LoopSession]:
    import re

    request_re = re.compile(
        r"Queued js5 request #(?P<request_id>\d+) from (?P<remote>\S+): "
        r"opcode=(?P<opcode>\d+), priority=(?P<priority>true|false), nxt=(?P<nxt>true|false), "
        r"build=(?P<build>\d+), occurrence=(?P<occurrence>\d+), "
        r"(?P<kind>reference-table|archive)\(index=(?P<index>\d+), archive=(?P<archive>\d+)\), "
        r"available=(?P<available>true|false)"
    )

    sessions: dict[str, dict[str, object]] = {}
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            match = request_re.search(raw_line)
            if not match:
                continue
            if int(match.group("build")) != build:
                continue

            remote = match.group("remote")
            state = sessions.setdefault(
                remote,
                {
                    "first_line": line_number,
                    "last_line": line_number,
                    "count": 0,
                    "requests": deque(maxlen=max_requests_per_remote),
                },
            )
            state["last_line"] = line_number
            state["count"] = int(state["count"]) + 1

            request = Js5Request(
                line_number=line_number,
                request_id=int(match.group("request_id")),
                remote=remote,
                opcode=int(match.group("opcode")),
                priority=match.group("priority") == "true",
                nxt=match.group("nxt") == "true",
                build=int(match.group("build")),
                occurrence=int(match.group("occurrence")),
                kind=match.group("kind"),
                index=int(match.group("index")),
                archive=int(match.group("archive")),
                available=match.group("available") == "true",
            )
            requests = state["requests"]
            assert isinstance(requests, deque)
            requests.append(request)

    return [
        LoopSession(
            remote=remote,
            first_line=int(state["first_line"]),
            last_line=int(state["last_line"]),
            request_count=int(state["count"]),
            requests=list(state["requests"]),
        )
        for remote, state in sessions.items()
    ]


def find_repeating_suffix(
    requests: list[Js5Request],
    min_cycle_length: int = 2,
    max_cycle_length: int = 64,
    min_repeats: int = 3,
    max_tail_skew: int | None = None,
) -> LoopCycle | None:
    if len(requests) < min_cycle_length * min_repeats:
        return None

    markers = [request_marker(request) for request in requests]
    max_length = min(max_cycle_length, len(markers) // min_repeats)
    if max_tail_skew is None:
        max_tail_skew = max_cycle_length

    latest_considered_end = len(markers)
    earliest_considered_end = max(min_cycle_length * min_repeats, len(markers) - max_tail_skew)
    best_cycle: LoopCycle | None = None

    for cycle_length in range(min_cycle_length, max_length + 1):
        minimum_end = cycle_length * min_repeats
        for end_offset in range(latest_considered_end, earliest_considered_end - 1, -1):
            if end_offset < minimum_end:
                continue

            cycle_markers = markers[end_offset - cycle_length : end_offset]
            repeat_count = 1
            offset = end_offset - cycle_length * 2
            while offset >= 0 and markers[offset : offset + cycle_length] == cycle_markers:
                repeat_count += 1
                offset -= cycle_length

            if repeat_count < min_repeats:
                continue

            candidate = LoopCycle(
                cycle_length=cycle_length,
                repeat_count=repeat_count,
                requests=canonicalize_cycle_requests(requests[end_offset - cycle_length : end_offset]),
                tail_skew=len(markers) - end_offset,
                window_end_offset=end_offset,
                cycle_first_line=requests[end_offset - cycle_length].line_number,
                cycle_last_line=requests[end_offset - 1].line_number,
            )
            if best_cycle is None or (
                -candidate.tail_skew,
                candidate.repeat_count * candidate.cycle_length,
                candidate.cycle_length,
                candidate.repeat_count,
                candidate.window_end_offset,
            ) > (
                -best_cycle.tail_skew,
                best_cycle.repeat_count * best_cycle.cycle_length,
                best_cycle.cycle_length,
                best_cycle.repeat_count,
                best_cycle.window_end_offset,
            ):
                best_cycle = candidate

    return best_cycle


def select_latest_loop_session(
    sessions: Iterable[LoopSession],
    min_cycle_length: int,
    max_cycle_length: int,
    min_repeats: int,
) -> tuple[LoopSession, LoopCycle]:
    candidates: list[tuple[LoopSession, LoopCycle]] = []
    for session in sessions:
        cycle = find_repeating_suffix(
            session.requests,
            min_cycle_length=min_cycle_length,
            max_cycle_length=max_cycle_length,
            min_repeats=min_repeats,
        )
        if cycle is None:
            continue
        candidates.append((session, cycle))

    if not candidates:
        raise ValueError("No recent 947 loop session had a repeating request cycle near the tail")

    candidates.sort(
        key=lambda item: (
            item[0].last_line,
            item[1].repeat_count,
            item[1].cycle_length,
        ),
        reverse=True,
    )
    return candidates[0]


def render_markdown(session: LoopSession, cycle: LoopCycle, local_summary, live_summary, compare, local_responses, live_responses) -> str:
    response_lines: list[str] = []
    for index, (local_response, live_response) in enumerate(zip(local_responses, live_responses), start=1):
        state = (
            "match"
            if local_response.header == live_response.header
            and local_response.sha256 == live_response.sha256
            and local_response.response_size == live_response.response_size
            else "mismatch"
        )
        response_lines.append(
            "- `#{ordinal}` archive=`{archive}` state=`{state}` localBytes=`{local_bytes}` "
            "liveBytes=`{live_bytes}` localSha=`{local_sha}` liveSha=`{live_sha}`".format(
                ordinal=index,
                archive=local_response.request.archive,
                state=state,
                local_bytes=local_response.response_size,
                live_bytes=live_response.response_size,
                local_sha=local_response.sha256,
                live_sha=live_response.sha256,
            )
        )

    return "\n".join(
        [
            "# 947 Application Resource Loop Doctor",
            "",
            f"- Remote session: `{session.remote}`",
            f"- Session first line: `{session.first_line}`",
            f"- Session last line: `{session.last_line}`",
            f"- Session request count: `{session.request_count}`",
            f"- Captured recent requests: `{len(session.requests)}`",
            f"- Repeating cycle length: `{cycle.cycle_length}`",
            f"- Repeating cycle count near tail: `{cycle.repeat_count}`",
            f"- Tail skew requests: `{cycle.tail_skew}`",
            f"- Cycle first line: `{cycle.cycle_first_line}`",
            f"- Cycle last line: `{cycle.cycle_last_line}`",
            f"- Local replay mode: `{local_summary.replay_mode}`",
            f"- Live replay mode: `{live_summary.replay_mode}`",
            f"- Local response bytes: `{local_summary.total_response_bytes}`",
            f"- Live response bytes: `{live_summary.total_response_bytes}`",
            f"- Compare state: `{compare.state}`",
            f"- First mismatch ordinal: `{compare.first_mismatch_ordinal}`",
            f"- First mismatch request: `{compare.first_mismatch_request}`",
            "",
            "## Cycle Requests",
            "",
            *[
                f"- `#{ordinal}` archive=`{request.archive}` occurrence=`{request.occurrence}` line=`{request.line_number}`"
                for ordinal, request in enumerate(cycle.requests, start=1)
            ],
            "",
            "## Response Compare",
            "",
            *response_lines,
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Detect the current repeating 947 logged-out JS5 application-resource loop from the server log, "
            "replay one full repeated cycle against local and live JS5, and report the first mismatching archive."
        )
    )
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--build", type=int, default=947)
    parser.add_argument("--token-url", default=DEFAULT_TOKEN_URL)
    parser.add_argument("--local-host", default="127.0.0.1")
    parser.add_argument("--local-port", type=int, default=43596)
    parser.add_argument("--live-host", default="content.runescape.com")
    parser.add_argument("--live-port", type=int, default=43594)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument("--max-requests-per-remote", type=int, default=512)
    parser.add_argument("--min-cycle-length", type=int, default=2)
    parser.add_argument("--max-cycle-length", type=int, default=64)
    parser.add_argument("--min-repeats", type=int, default=3)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    build, token = fetch_token(args.token_url)
    if build != args.build:
        raise ValueError(f"Token URL build {build} does not match requested build {args.build}")

    sessions = parse_recent_reference_requests(
        args.log_path,
        build=args.build,
        max_requests_per_remote=args.max_requests_per_remote,
    )
    session, cycle = select_latest_loop_session(
        sessions,
        min_cycle_length=args.min_cycle_length,
        max_cycle_length=args.max_cycle_length,
        min_repeats=args.min_repeats,
    )

    local_summary, local_responses = replay_sequence(
        host=args.local_host,
        port=args.local_port,
        build=args.build,
        token=token,
        requests=cycle.requests,
        timeout_seconds=args.timeout_seconds,
    )
    live_summary, live_responses = replay_sequence(
        host=args.live_host,
        port=args.live_port,
        build=args.build,
        token=token,
        requests=cycle.requests,
        timeout_seconds=args.timeout_seconds,
    )
    compare = compare_responses(local_responses, live_responses)

    artifact = {
        "tool": "run_947_application_resource_loop_doctor",
        "schemaVersion": 1,
        "logPath": str(args.log_path),
        "selectedSession": asdict(session),
        "loopCycle": {
            "cycleLength": cycle.cycle_length,
            "repeatCount": cycle.repeat_count,
            "tailSkew": cycle.tail_skew,
            "windowEndOffset": cycle.window_end_offset,
            "cycleFirstLine": cycle.cycle_first_line,
            "cycleLastLine": cycle.cycle_last_line,
            "requests": [asdict(request) for request in cycle.requests],
        },
        "localSummary": asdict(local_summary),
        "liveSummary": asdict(live_summary),
        "compare": asdict(compare),
        "localResponses": [asdict(response) for response in local_responses],
        "liveResponses": [asdict(response) for response in live_responses],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "application-resource-loop-doctor.json"
    md_path = args.output_dir / "application-resource-loop-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(session, cycle, local_summary, live_summary, compare, local_responses, live_responses),
        encoding="utf-8",
    )
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
