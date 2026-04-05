from __future__ import annotations

import argparse
import json
import hashlib
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    from tools.run_947_logged_out_js5_session_doctor import (
        DEFAULT_LOG_PATH,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_TOKEN_URL,
        DEFAULT_TAIL_BYTES,
        Js5Request,
        assemble_streamed_responses,
        build_handshake,
        build_init_packets,
        build_request_packet,
        fetch_token,
        load_recent_sessions,
        select_latest_logged_out_session_with_state,
    )
except ImportError:
    from run_947_logged_out_js5_session_doctor import (
        DEFAULT_LOG_PATH,
        DEFAULT_OUTPUT_DIR,
        DEFAULT_TOKEN_URL,
        DEFAULT_TAIL_BYTES,
        Js5Request,
        assemble_streamed_responses,
        build_handshake,
        build_init_packets,
        build_request_packet,
        fetch_token,
        load_recent_sessions,
        select_latest_logged_out_session_with_state,
    )


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR_BURST = WORKSPACE / "data" / "debug" / "js5-logged-out-burst-compare-947"


@dataclass(frozen=True)
class RawCaptureSummary:
    host: str
    port: int
    handshake_response: int
    payload_bytes: int
    combined_sha256: str
    first_64_hex: str
    recv_chunks: int


@dataclass(frozen=True)
class ParseAttemptSummary:
    state: str
    response_count: int
    error: str | None
    last_response_ordinal: int | None
    last_response_request: dict[str, int] | None


@dataclass(frozen=True)
class HexWindow:
    start_offset: int
    end_offset: int
    local_hex: str
    live_hex: str


@dataclass(frozen=True)
class RawCompareSummary:
    state: str
    common_prefix_bytes: int
    first_diff_offset: int | None
    local_remaining_bytes: int
    live_remaining_bytes: int
    window: HexWindow | None


def select_session_with_minimum_requests(
    sessions,
    *,
    build: int,
    require_non_255: bool,
    min_request_count: int,
):
    candidates = []
    for session in sessions:
        if session.build != build or session.logged_out_line is None or not session.requests:
            continue
        if require_non_255 and not any(request.index != 255 for request in session.requests):
            continue
        if session.total_request_count < min_request_count:
            continue
        candidates.append(session)

    if not candidates:
        raise ValueError(
            f"No logged-out JS5 sessions for build {build} satisfied min_request_count={min_request_count}"
        )

    return candidates[-1]


class BytesSocket:
    def __init__(self, payload: bytes) -> None:
        self._payload = memoryview(payload)
        self._offset = 0

    def recv(self, length: int) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        chunk = self._payload[self._offset : self._offset + length].tobytes()
        self._offset += len(chunk)
        return chunk


def capture_burst_raw(
    host: str,
    port: int,
    build: int,
    token: str,
    requests: list[Js5Request],
    timeout_seconds: float,
) -> tuple[RawCaptureSummary, bytes]:
    with socket.create_connection((host, port), timeout=10.0) as sock:
        sock.settimeout(timeout_seconds)
        sock.sendall(build_handshake(build, token))
        handshake_response = sock.recv(1)
        if len(handshake_response) != 1:
            raise ConnectionError(f"No handshake response from {host}:{port}")

        sock.sendall(build_init_packets(build))
        request_burst = b"".join(build_request_packet(request) for request in requests)
        if request_burst:
            sock.sendall(request_burst)

        payload = bytearray()
        recv_chunks = 0
        while True:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            payload.extend(chunk)
            recv_chunks += 1

    combined = handshake_response + bytes(payload)
    return (
        RawCaptureSummary(
            host=host,
            port=port,
            handshake_response=handshake_response[0],
            payload_bytes=len(payload),
            combined_sha256=hashlib.sha256(combined).hexdigest(),
            first_64_hex=combined[:64].hex(),
            recv_chunks=recv_chunks,
        ),
        bytes(payload),
    )


def attempt_parse_payload(payload: bytes, requests: list[Js5Request]) -> ParseAttemptSummary:
    try:
        responses, _ = assemble_streamed_responses(BytesSocket(payload), requests)
    except Exception as exc:  # noqa: BLE001 - diagnostics tool should preserve the exact parser failure
        return ParseAttemptSummary(
            state="parse-failed",
            response_count=0,
            error=f"{type(exc).__name__}: {exc}",
            last_response_ordinal=None,
            last_response_request=None,
        )

    last_response = responses[-1] if responses else None
    return ParseAttemptSummary(
        state="parsed",
        response_count=len(responses),
        error=None,
        last_response_ordinal=last_response.ordinal if last_response else None,
        last_response_request=(
            {"index": last_response.request.index, "archive": last_response.request.archive}
            if last_response
            else None
        ),
    )


def build_hex_window(local: bytes, live: bytes, offset: int, window_bytes: int = 32) -> HexWindow:
    start = max(0, offset - window_bytes)
    end = min(max(len(local), len(live)), offset + window_bytes)
    return HexWindow(
        start_offset=start,
        end_offset=end,
        local_hex=local[start:end].hex(),
        live_hex=live[start:end].hex(),
    )


def compare_raw_bytes(local: bytes, live: bytes, window_bytes: int = 32) -> RawCompareSummary:
    limit = min(len(local), len(live))
    common_prefix = 0
    while common_prefix < limit and local[common_prefix] == live[common_prefix]:
        common_prefix += 1

    if len(local) == len(live) and common_prefix == len(local):
        return RawCompareSummary(
            state="match",
            common_prefix_bytes=common_prefix,
            first_diff_offset=None,
            local_remaining_bytes=0,
            live_remaining_bytes=0,
            window=None,
        )

    diff_offset = common_prefix
    state = "mismatch"
    if common_prefix == len(local) and len(local) < len(live):
        state = "local-prefix-of-live"
    elif common_prefix == len(live) and len(live) < len(local):
        state = "live-prefix-of-local"

    return RawCompareSummary(
        state=state,
        common_prefix_bytes=common_prefix,
        first_diff_offset=diff_offset,
        local_remaining_bytes=len(local) - common_prefix,
        live_remaining_bytes=len(live) - common_prefix,
        window=build_hex_window(local, live, diff_offset, window_bytes=window_bytes),
    )


def render_markdown(
    *,
    log_path: Path,
    log_bytes_scanned: int,
    selection_state: str,
    requests: list[Js5Request],
    local_summary: RawCaptureSummary,
    live_summary: RawCaptureSummary,
    local_parse: ParseAttemptSummary,
    live_parse: ParseAttemptSummary,
    compare: RawCompareSummary,
) -> str:
    return "\n".join(
        [
            "# 947 Logged-Out JS5 Burst Compare",
            "",
            f"- Log path: `{log_path}`",
            f"- Log bytes scanned: `{log_bytes_scanned}`",
            f"- Selection state: `{selection_state}`",
            f"- Requests replayed: `{len(requests)}`",
            f"- First request: `{requests[0].kind}(index={requests[0].index}, archive={requests[0].archive})`",
            f"- Last request: `{requests[-1].kind}(index={requests[-1].index}, archive={requests[-1].archive})`",
            f"- Local payload bytes: `{local_summary.payload_bytes}`",
            f"- Live payload bytes: `{live_summary.payload_bytes}`",
            f"- Local SHA-256: `{local_summary.combined_sha256}`",
            f"- Live SHA-256: `{live_summary.combined_sha256}`",
            f"- Compare state: `{compare.state}`",
            f"- Common prefix bytes: `{compare.common_prefix_bytes}`",
            f"- First diff offset: `{compare.first_diff_offset}`",
            f"- Local parse state: `{local_parse.state}` responses=`{local_parse.response_count}` error=`{local_parse.error}`",
            f"- Live parse state: `{live_parse.state}` responses=`{live_parse.response_count}` error=`{live_parse.error}`",
            "",
            "## First Requests",
            "",
            *[
                f"- `{request.kind}` opcode=`{request.opcode}` index=`{request.index}` archive=`{request.archive}` line=`{request.line_number}`"
                for request in requests[:20]
            ],
            "",
            "## Hex Window",
            "",
            (
                f"- Offset range: `{compare.window.start_offset}..{compare.window.end_offset}`\n"
                f"- Local: `{compare.window.local_hex}`\n"
                f"- Live: `{compare.window.live_hex}`"
                if compare.window
                else "- Streams matched fully."
            ),
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Capture the latest logged-out 947 JS5 request burst as raw bytes from local and retail "
            "targets, then report the first wire-level divergence."
        )
    )
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR_BURST)
    parser.add_argument("--build", type=int, default=947)
    parser.add_argument("--token-url", default=DEFAULT_TOKEN_URL)
    parser.add_argument("--local-host", default="127.0.0.1")
    parser.add_argument("--local-port", type=int, default=43596)
    parser.add_argument("--live-host", default="content.runescape.com")
    parser.add_argument("--live-port", type=int, default=43594)
    parser.add_argument("--timeout-seconds", type=float, default=3.0)
    parser.add_argument("--max-requests", type=int, default=256)
    parser.add_argument("--min-request-count", type=int, default=1)
    parser.add_argument("--tail-bytes", type=int, default=DEFAULT_TAIL_BYTES)
    parser.add_argument("--allow-255-only", action="store_true")
    parser.add_argument("--window-bytes", type=int, default=32)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    build, token = fetch_token(args.token_url)
    requested_build = args.build if args.build else build
    if build != requested_build:
        raise ValueError(f"Token URL build {build} does not match requested build {requested_build}")

    requested_non_255 = not args.allow_255_only
    try:
        sessions, scanned_bytes = load_recent_sessions(
            args.log_path,
            build=requested_build,
            require_non_255=requested_non_255,
            tail_bytes=args.tail_bytes,
            request_capture_limit=args.max_requests,
        )
        selection = select_latest_logged_out_session_with_state(
            sessions,
            build=requested_build,
            require_non_255=requested_non_255,
        )
    except ValueError:
        if not requested_non_255:
            raise
        sessions, scanned_bytes = load_recent_sessions(
            args.log_path,
            build=requested_build,
            require_non_255=False,
            tail_bytes=args.tail_bytes,
            request_capture_limit=args.max_requests,
        )
        selection = select_latest_logged_out_session_with_state(
            sessions,
            build=requested_build,
            require_non_255=False,
        )

    selected_session = selection.session
    if args.min_request_count > 1:
        selected_session = select_session_with_minimum_requests(
            sessions,
            build=requested_build,
            require_non_255=requested_non_255,
            min_request_count=args.min_request_count,
        )

    requests = selected_session.requests[: args.max_requests]
    if not requests:
        raise ValueError("Selected session has no requests to replay")

    local_summary, local_payload = capture_burst_raw(
        host=args.local_host,
        port=args.local_port,
        build=requested_build,
        token=token,
        requests=requests,
        timeout_seconds=args.timeout_seconds,
    )
    live_summary, live_payload = capture_burst_raw(
        host=args.live_host,
        port=args.live_port,
        build=requested_build,
        token=token,
        requests=requests,
        timeout_seconds=args.timeout_seconds,
    )
    local_parse = attempt_parse_payload(local_payload, requests)
    live_parse = attempt_parse_payload(live_payload, requests)
    compare = compare_raw_bytes(local_payload, live_payload, window_bytes=args.window_bytes)

    artifact = {
        "tool": "run_947_logged_out_js5_burst_compare",
        "schemaVersion": 1,
        "logPath": str(args.log_path),
        "logBytesScanned": scanned_bytes,
        "selectionState": selection.state,
        "selectedSession": {
            "remote": selected_session.remote,
            "build": selected_session.build,
            "sessionId": selected_session.session_id,
            "handshakeLine": selected_session.handshake_line,
            "loggedOutLine": selected_session.logged_out_line,
            "requestCount": selected_session.total_request_count,
            "capturedRequestCount": len(selected_session.requests),
        },
        "replayedRequests": [asdict(request) for request in requests],
        "localSummary": asdict(local_summary),
        "liveSummary": asdict(live_summary),
        "localParse": asdict(local_parse),
        "liveParse": asdict(live_parse),
        "compare": {
            **asdict(compare),
            "window": asdict(compare.window) if compare.window is not None else None,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "logged-out-js5-burst-compare.json"
    md_path = args.output_dir / "logged-out-js5-burst-compare.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(
            log_path=args.log_path,
            log_bytes_scanned=scanned_bytes,
            selection_state=selection.state,
            requests=requests,
            local_summary=local_summary,
            live_summary=live_summary,
            local_parse=local_parse,
            live_parse=live_parse,
            compare=compare,
        ),
        encoding="utf-8",
    )
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
