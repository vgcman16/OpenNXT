from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import socket
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_SERVER_LOG_CANDIDATES = (
    WORKSPACE / "tmp-manual-js5.err.log",
    WORKSPACE / "tmp-runserver.err.log",
)
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "js5-logged-out-session-doctor-947"
DEFAULT_TOKEN_URL = "http://127.0.0.1:8080/jav_config.ws"
DEFAULT_TAIL_BYTES = 128 * 1024 * 1024
JS5_BLOCK_BYTES = 102400

HANDSHAKE_RE = re.compile(
    r"Decoded js5 handshake for session#(?P<session>\d+) from (?P<remote>\S+) with build=(?P<build>\d+)\.(?P<minor>\d+)"
)
LOGGED_OUT_RE = re.compile(
    r"JS5 logged out state from (?P<remote>\S+) for build=(?P<build>\d+)"
)
REQUEST_RE = re.compile(
    r"Queued js5 request #(?P<request_id>\d+) from (?P<remote>\S+): "
    r"opcode=(?P<opcode>\d+), priority=(?P<priority>true|false), nxt=(?P<nxt>true|false), "
    r"build=(?P<build>\d+), occurrence=(?P<occurrence>\d+), "
    r"(?P<kind>reference-table|archive)\(index=(?P<index>\d+), archive=(?P<archive>\d+)\), "
    r"available=(?P<available>true|false)"
)
PARAM_RE = re.compile(r"^param=(?P<key>\d+)=(?P<value>.*)$")


def resolve_default_log_path() -> Path:
    existing = [path for path in DEFAULT_SERVER_LOG_CANDIDATES if path.exists()]
    if existing:
        def score(path: Path) -> tuple[int, float, int]:
            stats = path.stat()
            size = stats.st_size
            score_value = 0
            try:
                with path.open("rb") as handle:
                    tail_window = min(size, 4 * 1024 * 1024)
                    if tail_window < size:
                        handle.seek(size - tail_window)
                    tail_text = handle.read(tail_window).decode("utf-8", errors="replace")
                if "Queued js5 request #" in tail_text:
                    score_value += 4
                if "Decoded js5 handshake" in tail_text:
                    score_value += 2
                if "reference-table(index=255" in tail_text:
                    score_value += 8
            except OSError:
                pass
            return (score_value, stats.st_mtime, size)

        existing.sort(key=score, reverse=True)
        return existing[0]
    return DEFAULT_SERVER_LOG_CANDIDATES[0]


DEFAULT_LOG_PATH = resolve_default_log_path()


@dataclass(frozen=True)
class Js5Request:
    line_number: int
    request_id: int
    remote: str
    opcode: int
    priority: bool
    nxt: bool
    build: int
    occurrence: int
    kind: str
    index: int
    archive: int
    available: bool


@dataclass
class Js5Session:
    remote: str
    build: int | None = None
    session_id: int | None = None
    handshake_line: int | None = None
    logged_out_line: int | None = None
    requests: list[Js5Request] | None = None
    total_request_count: int = 0

    def __post_init__(self) -> None:
        if self.requests is None:
            self.requests = []


@dataclass(frozen=True)
class ResponseHeader:
    index: int
    archive: int
    priority: bool
    compression: int
    file_size: int

    @property
    def body_length(self) -> int:
        return self.file_size + (4 if self.compression != 0 else 0)

    @property
    def container_bytes(self) -> int:
        return self.file_size + 5 + (4 if self.compression != 0 else 0)


@dataclass(frozen=True)
class ResponseRecord:
    ordinal: int
    request: Js5Request
    header: ResponseHeader
    response_size: int
    sha256: str
    raw_hex_prefix: str


@dataclass(frozen=True)
class ReplaySummary:
    host: str
    port: int
    handshake_response: int
    response_count: int
    total_response_bytes: int
    combined_sha256: str
    first_64_hex: str
    replay_mode: str = "burst"


@dataclass(frozen=True)
class CompareSummary:
    state: str
    compared_responses: int
    first_mismatch_ordinal: int | None
    first_mismatch_request: dict[str, int] | None
    local_remaining_responses: int
    live_remaining_responses: int


@dataclass(frozen=True)
class SessionSelection:
    session: Js5Session
    state: str


@dataclass
class ReplayRequestState:
    ordinal: int
    request: Js5Request
    started: bool = False
    header: ResponseHeader | None = None
    container_received: int = 0
    block_offset: int = 0
    raw_response: bytearray | None = None

    def __post_init__(self) -> None:
        if self.raw_response is None:
            self.raw_response = bytearray()


def parse_jav_config_token(config_text: str) -> tuple[int, str]:
    build: int | None = None
    static_token: str | None = None
    session_token: str | None = None
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if line.startswith("server_version="):
            build = int(line.split("=", 1)[1])
            continue
        match = PARAM_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        if key == "10":
            static_token = match.group("value")
        elif key == "29":
            session_token = match.group("value")
    token = session_token or static_token
    if build is None or token is None:
        raise ValueError("jav_config.ws is missing server_version or a js5 token (param=29/param=10)")
    return build, token


def fetch_token(token_url: str) -> tuple[int, str]:
    from urllib.request import urlopen

    with urlopen(token_url, timeout=10) as response:
        text = response.read().decode("iso-8859-1", "replace")
    return parse_jav_config_token(text)


def parse_sessions_from_lines(lines: Iterable[str], request_capture_limit: int | None = None) -> list[Js5Session]:
    sessions_by_remote: dict[str, Js5Session] = {}
    ordered_remotes: list[str] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        handshake_match = HANDSHAKE_RE.search(line)
        if handshake_match:
            remote = handshake_match.group("remote")
            session = sessions_by_remote.get(remote)
            if session is None:
                session = Js5Session(remote=remote)
                sessions_by_remote[remote] = session
                ordered_remotes.append(remote)
            session.build = int(handshake_match.group("build"))
            session.session_id = int(handshake_match.group("session"))
            session.handshake_line = line_number
            continue

        logged_out_match = LOGGED_OUT_RE.search(line)
        if logged_out_match:
            remote = logged_out_match.group("remote")
            session = sessions_by_remote.get(remote)
            if session is None:
                session = Js5Session(remote=remote)
                sessions_by_remote[remote] = session
                ordered_remotes.append(remote)
            session.build = int(logged_out_match.group("build"))
            session.logged_out_line = line_number
            continue

        request_match = REQUEST_RE.search(line)
        if request_match:
            remote = request_match.group("remote")
            session = sessions_by_remote.get(remote)
            if session is None:
                session = Js5Session(remote=remote)
                sessions_by_remote[remote] = session
                ordered_remotes.append(remote)
            request = Js5Request(
                line_number=line_number,
                request_id=int(request_match.group("request_id")),
                remote=remote,
                opcode=int(request_match.group("opcode")),
                priority=request_match.group("priority") == "true",
                nxt=request_match.group("nxt") == "true",
                build=int(request_match.group("build")),
                occurrence=int(request_match.group("occurrence")),
                kind=request_match.group("kind"),
                index=int(request_match.group("index")),
                archive=int(request_match.group("archive")),
                available=request_match.group("available") == "true",
            )
            if session.build is None:
                session.build = request.build
            session.total_request_count += 1
            if request_capture_limit is None or len(session.requests) < request_capture_limit:
                session.requests.append(request)

    return [sessions_by_remote[remote] for remote in ordered_remotes]


def parse_sessions(log_text: str) -> list[Js5Session]:
    return parse_sessions_from_lines(log_text.splitlines())


def iter_log_tail_lines(path: Path, tail_bytes: int) -> Iterable[str]:
    file_size = path.stat().st_size
    with path.open("rb") as handle:
        if tail_bytes > 0 and tail_bytes < file_size:
            handle.seek(file_size - tail_bytes)
            handle.readline()

        text_stream = io.TextIOWrapper(handle, encoding="utf-8", errors="replace")
        for line in text_stream:
            yield line


def load_recent_sessions(
    log_path: Path,
    build: int,
    require_non_255: bool,
    tail_bytes: int,
    request_capture_limit: int | None = None,
) -> tuple[list[Js5Session], int]:
    file_size = log_path.stat().st_size
    window = min(file_size, max(1, tail_bytes))
    last_error: Exception | None = None

    while True:
        sessions = parse_sessions_from_lines(
            iter_log_tail_lines(log_path, window),
            request_capture_limit=request_capture_limit,
        )
        try:
            select_latest_logged_out_session(
                sessions,
                build=build,
                require_non_255=require_non_255,
            )
            return sessions, window
        except ValueError as exc:
            last_error = exc
            if window >= file_size:
                raise last_error
            window = min(file_size, window * 2)


def select_latest_logged_out_session(
    sessions: Iterable[Js5Session],
    build: int,
    require_non_255: bool,
) -> Js5Session:
    candidates = [
        session
        for session in sessions
        if session.build == build
        and session.logged_out_line is not None
        and session.requests
        and (
            not require_non_255
            or any(request.index != 255 for request in session.requests)
        )
    ]
    if not candidates:
        candidates = [
            session
            for session in sessions
            if session.build == build
            and session.handshake_line is not None
            and session.requests
            and (
                not require_non_255
                or any(request.index != 255 for request in session.requests)
            )
        ]
    if not candidates:
        candidates = [
            session
            for session in sessions
            if session.build == build
            and session.requests
            and (
                not require_non_255
                or any(request.index != 255 for request in session.requests)
            )
        ]
    if not candidates:
        raise ValueError(f"No logged-out JS5 sessions for build {build} matched the requested criteria")
    candidates.sort(
        key=lambda session: (
            session.logged_out_line or session.handshake_line or -1,
            session.total_request_count,
        ),
        reverse=True,
    )
    return candidates[0]


def select_latest_logged_out_session_with_state(
    sessions: Iterable[Js5Session],
    build: int,
    require_non_255: bool,
) -> SessionSelection:
    try:
        session = select_latest_logged_out_session(
            sessions,
            build=build,
            require_non_255=require_non_255,
        )
    except ValueError:
        if not require_non_255:
            raise
        session = select_latest_logged_out_session(
            sessions,
            build=build,
            require_non_255=False,
        )
        return SessionSelection(session=session, state="255-only-fallback")

    return SessionSelection(
        session=session,
        state="non-255" if require_non_255 else "255-only",
    )


def build_handshake(build: int, token: str) -> bytes:
    token_bytes = token.encode("ascii")
    payload_size = 4 + 4 + len(token_bytes) + 1 + 1
    packet = bytearray()
    packet.append(0x0F)
    packet.append(payload_size)
    packet.extend(build.to_bytes(4, "big"))
    packet.extend((1).to_bytes(4, "big"))
    packet.extend(token_bytes)
    packet.append(0)
    packet.append(0)
    return bytes(packet)


def build_init_packets(build: int) -> bytes:
    packet = bytearray()
    packet.extend(bytes([0x06, 0x00, 0x00, 0x05, 0x00, 0x00]))
    packet.extend(build.to_bytes(2, "big"))
    packet.extend((0).to_bytes(2, "big"))
    packet.extend(bytes([0x03, 0x00, 0x00, 0x05, 0x00, 0x00]))
    packet.extend(build.to_bytes(2, "big"))
    packet.extend((0).to_bytes(2, "big"))
    return bytes(packet)


def build_request_packet(request: Js5Request) -> bytes:
    packet = bytearray()
    packet.append(request.opcode & 0xFF)
    packet.append(request.index & 0xFF)
    packet.extend(request.archive.to_bytes(4, "big"))
    packet.extend(request.build.to_bytes(2, "big"))
    packet.extend((0).to_bytes(2, "big"))
    return bytes(packet)


def read_exact(sock: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        block = sock.recv(length - len(chunks))
        if not block:
            raise ConnectionError(f"Socket closed while waiting for {length} bytes; only received {len(chunks)}")
        chunks.extend(block)
    return bytes(chunks)


def parse_response_header(header_bytes: bytes) -> ResponseHeader:
    if len(header_bytes) != 10:
        raise ValueError(f"Expected 10-byte JS5 response header, got {len(header_bytes)} bytes")
    archive_hash = int.from_bytes(header_bytes[1:5], "big")
    priority = (archive_hash & 0x80000000) == 0
    return ResponseHeader(
        index=header_bytes[0],
        archive=archive_hash & 0x7FFFFFFF,
        priority=priority,
        compression=header_bytes[5],
        file_size=int.from_bytes(header_bytes[6:10], "big"),
    )


def read_response_record(sock: socket.socket, ordinal: int, request: Js5Request) -> tuple[ResponseRecord, bytes]:
    envelope = read_exact(sock, 5)
    archive_hash = int.from_bytes(envelope[1:5], "big")
    priority = (archive_hash & 0x80000000) == 0
    archive = archive_hash & 0x7FFFFFFF
    prefix = read_exact(sock, 5)

    header = ResponseHeader(
        index=envelope[0],
        archive=archive,
        priority=priority,
        compression=prefix[0],
        file_size=int.from_bytes(prefix[1:5], "big"),
    )

    raw_response = bytearray()
    raw_response.extend(envelope)
    raw_response.extend(prefix)

    remaining_container_bytes = header.container_bytes - 5
    first_chunk_bytes = min(102400 - 10, remaining_container_bytes)
    if first_chunk_bytes > 0:
        first_body = read_exact(sock, first_chunk_bytes)
        raw_response.extend(first_body)
        remaining_container_bytes -= first_chunk_bytes

    while remaining_container_bytes > 0:
        continuation_envelope = read_exact(sock, 5)
        raw_response.extend(continuation_envelope)
        chunk_bytes = min(102400 - 5, remaining_container_bytes)
        continuation_body = read_exact(sock, chunk_bytes)
        raw_response.extend(continuation_body)
        remaining_container_bytes -= chunk_bytes

    response = ResponseRecord(
        ordinal=ordinal,
        request=request,
        header=header,
        response_size=len(raw_response),
        sha256=hashlib.sha256(raw_response).hexdigest(),
        raw_hex_prefix=bytes(raw_response[:32]).hex(),
    )
    return response, bytes(raw_response)


def replay_requests_individually(
    host: str,
    port: int,
    build: int,
    token: str,
    requests: list[Js5Request],
    timeout_seconds: float,
) -> tuple[ReplaySummary, list[ResponseRecord]]:
    responses: list[ResponseRecord] = []
    combined = bytearray()
    handshake_response_value: int | None = None

    for ordinal, request in enumerate(requests, start=1):
        with socket.create_connection((host, port), timeout=10.0) as sock:
            sock.settimeout(timeout_seconds)
            sock.sendall(build_handshake(build, token))
            handshake_response = sock.recv(1)
            if len(handshake_response) != 1:
                raise ConnectionError(f"No handshake response from {host}:{port}")
            if handshake_response_value is None:
                handshake_response_value = handshake_response[0]
            combined.extend(handshake_response)

            sock.sendall(build_init_packets(build))
            sock.sendall(build_request_packet(request))
            response, response_stream = read_response_record(sock, ordinal, request)
            responses.append(response)
            combined.extend(response_stream)

    combined_bytes = bytes(combined)
    summary = ReplaySummary(
        host=host,
        port=port,
        handshake_response=handshake_response_value if handshake_response_value is not None else -1,
        response_count=len(responses),
        total_response_bytes=len(combined_bytes),
        combined_sha256=hashlib.sha256(combined_bytes).hexdigest(),
        first_64_hex=combined_bytes[:64].hex(),
        replay_mode="per-request",
    )
    return summary, responses


def enqueue_request_state(
    pending_by_key: dict[tuple[bool, int, int], list[ReplayRequestState]],
    state: ReplayRequestState,
) -> None:
    key = (state.request.priority, state.request.index, state.request.archive)
    pending_by_key.setdefault(key, []).append(state)


def next_request_state_for_envelope(
    pending_by_key: dict[tuple[bool, int, int], list[ReplayRequestState]],
    priority: bool,
    index: int,
    archive: int,
) -> ReplayRequestState:
    key = (priority, index, archive)
    candidates = pending_by_key.get(key)
    if not candidates:
        raise IllegalStateException(f"server sent file we were not requesting: [{priority}, {index}, {archive}]")

    for state in candidates:
        if state.started and state.header is not None and state.container_received < state.header.container_bytes:
            return state
    for state in candidates:
        if not state.started:
            return state

    raise IllegalStateException(f"all request states already completed for [{priority}, {index}, {archive}]")


class IllegalStateException(RuntimeError):
    pass


def assemble_streamed_responses(
    sock: socket.socket,
    requests: list[Js5Request],
) -> tuple[list[ResponseRecord], bytes]:
    pending_by_key: dict[tuple[bool, int, int], list[ReplayRequestState]] = {}
    completed: dict[int, ResponseRecord] = {}
    current: ReplayRequestState | None = None
    combined_stream = bytearray()

    for ordinal, request in enumerate(requests, start=1):
        state = ReplayRequestState(ordinal=ordinal, request=request)
        enqueue_request_state(pending_by_key, state)

    while len(completed) < len(requests):
        if current is None:
            envelope = read_exact(sock, 5)
            combined_stream.extend(envelope)
            archive_hash = int.from_bytes(envelope[1:5], "big")
            priority = (archive_hash & 0x80000000) == 0
            archive = archive_hash & 0x7FFFFFFF
            current = next_request_state_for_envelope(
                pending_by_key,
                priority=priority,
                index=envelope[0],
                archive=archive,
            )
            current.started = True
            current.raw_response.extend(envelope)
            current.block_offset = 5
            continue

        if current.header is None:
            prefix = read_exact(sock, 5)
            combined_stream.extend(prefix)
            current.raw_response.extend(prefix)
            current.header = ResponseHeader(
                index=current.request.index,
                archive=current.request.archive,
                priority=current.request.priority,
                compression=prefix[0],
                file_size=int.from_bytes(prefix[1:5], "big"),
            )
            current.container_received = 5
            current.block_offset = 10
            if current.container_received == current.header.container_bytes:
                completed[current.ordinal] = ResponseRecord(
                    ordinal=current.ordinal,
                    request=current.request,
                    header=current.header,
                    response_size=len(current.raw_response),
                    sha256=hashlib.sha256(bytes(current.raw_response)).hexdigest(),
                    raw_hex_prefix=bytes(current.raw_response[:32]).hex(),
                )
                current = None
            continue

        remaining_container_bytes = current.header.container_bytes - current.container_received
        chunk_bytes = min(JS5_BLOCK_BYTES - current.block_offset, remaining_container_bytes)
        if chunk_bytes > 0:
            body = read_exact(sock, chunk_bytes)
            combined_stream.extend(body)
            current.raw_response.extend(body)
            current.container_received += chunk_bytes
            current.block_offset += chunk_bytes

        if current.container_received == current.header.container_bytes:
            completed[current.ordinal] = ResponseRecord(
                ordinal=current.ordinal,
                request=current.request,
                header=current.header,
                response_size=len(current.raw_response),
                sha256=hashlib.sha256(bytes(current.raw_response)).hexdigest(),
                raw_hex_prefix=bytes(current.raw_response[:32]).hex(),
            )
            current = None
        elif current.block_offset == JS5_BLOCK_BYTES:
            current.block_offset = 0
            current = None

    return [completed[ordinal] for ordinal in sorted(completed)], bytes(combined_stream)


def replay_sequence(
    host: str,
    port: int,
    build: int,
    token: str,
    requests: list[Js5Request],
    timeout_seconds: float,
) -> tuple[ReplaySummary, list[ResponseRecord]]:
    responses: list[ResponseRecord] = []
    combined = bytearray()

    with socket.create_connection((host, port), timeout=10.0) as sock:
        sock.settimeout(timeout_seconds)
        sock.sendall(build_handshake(build, token))
        handshake_response = sock.recv(1)
        if len(handshake_response) != 1:
            raise ConnectionError(f"No handshake response from {host}:{port}")
        combined.extend(handshake_response)

        sock.sendall(build_init_packets(build))
        request_burst = b"".join(build_request_packet(request) for request in requests)
        if request_burst:
            sock.sendall(request_burst)

        try:
            responses, response_stream = assemble_streamed_responses(sock, requests)
        except (ConnectionError, IllegalStateException, TimeoutError, ValueError, socket.timeout):
            return replay_requests_individually(
                host=host,
                port=port,
                build=build,
                token=token,
                requests=requests,
                timeout_seconds=timeout_seconds,
            )
        combined.extend(response_stream)

    combined_bytes = bytes(combined)
    summary = ReplaySummary(
        host=host,
        port=port,
        handshake_response=combined_bytes[0],
        response_count=len(responses),
        total_response_bytes=len(combined_bytes),
        combined_sha256=hashlib.sha256(combined_bytes).hexdigest(),
        first_64_hex=combined_bytes[:64].hex(),
        replay_mode="burst",
    )
    return summary, responses


def compare_responses(local: list[ResponseRecord], live: list[ResponseRecord]) -> CompareSummary:
    compared = min(len(local), len(live))
    for index in range(compared):
        local_response = local[index]
        live_response = live[index]
        if local_response.request.index != live_response.request.index or local_response.request.archive != live_response.request.archive:
            return CompareSummary(
                state="request-sequence-mismatch",
                compared_responses=index,
                first_mismatch_ordinal=index + 1,
                first_mismatch_request={
                    "index": local_response.request.index,
                    "archive": local_response.request.archive,
                },
                local_remaining_responses=len(local) - index,
                live_remaining_responses=len(live) - index,
            )
        if (
            local_response.header != live_response.header
            or local_response.sha256 != live_response.sha256
            or local_response.response_size != live_response.response_size
        ):
            return CompareSummary(
                state="response-mismatch",
                compared_responses=index,
                first_mismatch_ordinal=index + 1,
                first_mismatch_request={
                    "index": local_response.request.index,
                    "archive": local_response.request.archive,
                },
                local_remaining_responses=len(local) - index,
                live_remaining_responses=len(live) - index,
            )

    if len(local) == len(live):
        return CompareSummary(
            state="match",
            compared_responses=compared,
            first_mismatch_ordinal=None,
            first_mismatch_request=None,
            local_remaining_responses=0,
            live_remaining_responses=0,
        )

    state = "local-prefix-of-live" if len(local) < len(live) else "live-prefix-of-local"
    mismatch_request = None
    if len(local) > compared:
        mismatch_request = {
            "index": local[compared].request.index,
            "archive": local[compared].request.archive,
        }
    elif len(live) > compared:
        mismatch_request = {
            "index": live[compared].request.index,
            "archive": live[compared].request.archive,
        }
    return CompareSummary(
        state=state,
        compared_responses=compared,
        first_mismatch_ordinal=compared + 1 if mismatch_request else None,
        first_mismatch_request=mismatch_request,
        local_remaining_responses=len(local) - compared,
        live_remaining_responses=len(live) - compared,
    )


def render_markdown(
    log_path: Path,
    log_bytes_scanned: int,
    selection_state: str,
    session: Js5Session,
    requests: list[Js5Request],
    local_summary: ReplaySummary,
    live_summary: ReplaySummary,
    compare: CompareSummary,
) -> str:
    unique_indexes = sorted({request.index for request in requests})
    return "\n".join(
        [
            "# 947 Logged-Out JS5 Session Doctor",
            "",
            f"- Log path: `{log_path}`",
            f"- Log bytes scanned: `{log_bytes_scanned}`",
            f"- Remote session: `{session.remote}`",
            f"- Build: `{session.build}`",
            f"- Logged-out line: `{session.logged_out_line}`",
            f"- Selection state: `{selection_state}`",
            f"- Session request count: `{session.total_request_count}`",
            f"- Requests replayed: `{len(requests)}`",
            f"- Unique indexes: `{','.join(str(index) for index in unique_indexes)}`",
            f"- First request: `{requests[0].kind}(index={requests[0].index}, archive={requests[0].archive})`",
            f"- Last request: `{requests[-1].kind}(index={requests[-1].index}, archive={requests[-1].archive})`",
            f"- Local replay mode: `{local_summary.replay_mode}`",
            f"- Live replay mode: `{live_summary.replay_mode}`",
            f"- Local combined bytes: `{local_summary.total_response_bytes}`",
            f"- Live combined bytes: `{live_summary.total_response_bytes}`",
            f"- Local combined SHA-256: `{local_summary.combined_sha256}`",
            f"- Live combined SHA-256: `{live_summary.combined_sha256}`",
            f"- Compare state: `{compare.state}`",
            f"- Compared responses: `{compare.compared_responses}`",
            f"- First mismatch ordinal: `{compare.first_mismatch_ordinal}`",
            f"- First mismatch request: `{compare.first_mismatch_request}`",
            "",
            "## First Requests",
            "",
            *[
                f"- `{request.kind}` opcode=`{request.opcode}` index=`{request.index}` archive=`{request.archive}` line=`{request.line_number}`"
                for request in requests[:20]
            ],
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay the latest logged-out 947 JS5 request sequence from the server log against "
            "live and local targets, block-by-block, and report the first mismatching archive."
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
    parser.add_argument("--max-requests", type=int, default=256)
    parser.add_argument("--tail-bytes", type=int, default=DEFAULT_TAIL_BYTES)
    parser.add_argument("--allow-255-only", action="store_true")
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

    session = selection.session
    requests = session.requests[: args.max_requests]
    if not requests:
        raise ValueError("Selected session has no requests to replay")

    local_summary, local_responses = replay_sequence(
        host=args.local_host,
        port=args.local_port,
        build=requested_build,
        token=token,
        requests=requests,
        timeout_seconds=args.timeout_seconds,
    )
    live_summary, live_responses = replay_sequence(
        host=args.live_host,
        port=args.live_port,
        build=requested_build,
        token=token,
        requests=requests,
        timeout_seconds=args.timeout_seconds,
    )
    compare = compare_responses(local_responses, live_responses)

    artifact = {
        "tool": "run_947_logged_out_js5_session_doctor",
        "schemaVersion": 1,
        "logPath": str(args.log_path),
        "logBytesScanned": scanned_bytes,
        "selectionState": selection.state,
        "selectedSession": {
            "remote": session.remote,
            "build": session.build,
            "sessionId": session.session_id,
            "handshakeLine": session.handshake_line,
            "loggedOutLine": session.logged_out_line,
            "requestCount": session.total_request_count,
            "capturedRequestCount": len(session.requests),
        },
        "replayedRequests": [asdict(request) for request in requests],
        "localSummary": asdict(local_summary),
        "liveSummary": asdict(live_summary),
        "compare": asdict(compare),
        "localResponses": [asdict(response) for response in local_responses],
        "liveResponses": [asdict(response) for response in live_responses],
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "logged-out-js5-session-doctor.json"
    md_path = args.output_dir / "logged-out-js5-session-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(
            args.log_path,
            scanned_bytes,
            selection.state,
            session,
            requests,
            local_summary,
            live_summary,
            compare,
        ),
        encoding="utf-8",
    )
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
