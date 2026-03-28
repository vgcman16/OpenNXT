from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "reference-table-doctor-947"
DEFAULT_LOG_DIR = WORKSPACE / "data" / "debug" / "lobby-tls-terminator"
DEFAULT_ARCHIVES = [2, 3, 12, 16, 17, 18, 19, 21, 22, 24, 26, 28, 29, 49, 57, 58, 60, 61, 62, 65, 66]

SEND_LINE_RE = re.compile(
    r"^raw-client->remote\s+(?P<label>[^ ]+)\s+bytes=(?P<byte_count>\d+)\s+hex=(?P<hex>[0-9a-fA-F ]+)\s*$"
)


@dataclass(frozen=True)
class SendChunk:
    label: str
    byte_count: int
    payload: bytes


@dataclass(frozen=True)
class DiffSummary:
    state: str
    common_prefix_bytes: int
    first_diff_offset: int | None
    local_remaining_bytes: int
    live_remaining_bytes: int


@dataclass(frozen=True)
class ArchiveResult:
    archive: int
    local_bytes: int
    live_bytes: int
    local_sha256: str
    live_sha256: str
    diff: DiffSummary


def parse_send_chunks(log_text: str) -> list[SendChunk]:
    chunks: list[SendChunk] = []
    for line in log_text.splitlines():
        match = SEND_LINE_RE.match(line.strip())
        if not match:
            continue
        payload = bytes.fromhex(match.group("hex"))
        byte_count = int(match.group("byte_count"))
        if len(payload) != byte_count:
            raise ValueError(
                f"Chunk {match.group('label')} declared {byte_count} bytes but decoded {len(payload)} bytes"
            )
        chunks.append(SendChunk(match.group("label"), byte_count, payload))
    if not chunks:
        raise ValueError("No raw-client->remote chunks were found in the supplied session log")
    return chunks


def latest_session_log(log_dir: Path) -> Path:
    candidates = sorted(log_dir.glob("session-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No session logs found in {log_dir}")
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "raw-client->remote" in text and "session-route=raw-game" in text:
            return candidate
    raise ValueError(f"No raw-game session logs were found in {log_dir}")


def select_handshake_and_template(chunks: list[SendChunk]) -> tuple[list[SendChunk], bytes]:
    if len(chunks) < 5:
        raise ValueError("Expected at least five raw-client->remote chunks in the session log")
    handshake = chunks[:4]
    template = chunks[4].payload
    if len(template) < 6:
        raise ValueError("Reference request template is too short")
    if template[0] not in (0x00, 0x01, 0x21, 0x22) or template[1] != 0xFF:
        raise ValueError(f"Unexpected reference request template: {template.hex()}")
    return handshake, template


def build_reference_request(template: bytes, archive: int) -> bytes:
    if archive < 0 or archive > 0xFFFFFFFF:
        raise ValueError(f"Archive id out of range: {archive}")
    payload = bytearray(template)
    payload[2:6] = archive.to_bytes(4, "big")
    return bytes(payload)


def replay_reference_request(
    host: str,
    port: int,
    handshake_chunks: list[SendChunk],
    request_payload: bytes,
    recv_timeout_seconds: float,
    inter_chunk_delay_seconds: float,
) -> bytes:
    received = bytearray()
    with socket.create_connection((host, port), timeout=10.0) as sock:
        sock.settimeout(recv_timeout_seconds)
        for chunk in handshake_chunks:
            sock.sendall(chunk.payload)
            if inter_chunk_delay_seconds > 0:
                time.sleep(inter_chunk_delay_seconds)
        sock.sendall(request_payload)
        while True:
            try:
                block = sock.recv(65536)
            except socket.timeout:
                break
            except OSError as exc:
                if getattr(exc, "winerror", None) in {10053, 10054}:
                    break
                raise
            if not block:
                break
            received.extend(block)
    return bytes(received)


def compare_bytes(local_bytes: bytes, live_bytes: bytes) -> DiffSummary:
    common_prefix = 0
    limit = min(len(local_bytes), len(live_bytes))
    while common_prefix < limit and local_bytes[common_prefix] == live_bytes[common_prefix]:
        common_prefix += 1

    if len(local_bytes) == len(live_bytes) and common_prefix == len(local_bytes):
        state = "match"
        first_diff = None
    elif common_prefix == len(local_bytes) and len(live_bytes) > len(local_bytes):
        state = "local-prefix-of-live"
        first_diff = common_prefix
    elif common_prefix == len(live_bytes) and len(local_bytes) > len(live_bytes):
        state = "live-prefix-of-local"
        first_diff = common_prefix
    else:
        state = "mismatch"
        first_diff = common_prefix

    return DiffSummary(
        state=state,
        common_prefix_bytes=common_prefix,
        first_diff_offset=first_diff,
        local_remaining_bytes=len(local_bytes) - common_prefix,
        live_remaining_bytes=len(live_bytes) - common_prefix,
    )


def parse_archives(value: str) -> list[int]:
    items = []
    for token in value.split(","):
        stripped = token.strip()
        if not stripped:
            continue
        items.append(int(stripped, 10))
    if not items:
        raise ValueError("At least one archive id is required")
    return items


def render_markdown(
    session_log: Path,
    archives: list[int],
    results: list[ArchiveResult],
    first_mismatch: ArchiveResult | None,
) -> str:
    lines = [
        "# 947 Reference Table Doctor",
        "",
        f"- Session log: `{session_log}`",
        f"- Archive count: `{len(archives)}`",
        f"- First mismatch archive: `{first_mismatch.archive if first_mismatch else 'none'}`",
        f"- All compared replies matched: `{first_mismatch is None}`",
        "",
        "## Archive Results",
        "",
    ]
    for result in results:
        lines.append(
            "- archive `{archive}` local=`{local}` live=`{live}` state=`{state}` firstDiff=`{diff}`".format(
                archive=result.archive,
                local=result.local_bytes,
                live=result.live_bytes,
                state=result.diff.state,
                diff=result.diff.first_diff_offset,
            )
        )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay individual 947 raw JS5 reference-table requests against local and live "
            "targets and report the first mismatching archive."
        )
    )
    parser.add_argument("--session-log", type=Path, default=None, help="Path to a raw-game session log")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archives", default=",".join(str(item) for item in DEFAULT_ARCHIVES))
    parser.add_argument("--local-host", default="127.0.0.1")
    parser.add_argument("--local-port", type=int, default=43596)
    parser.add_argument("--live-host", default="content.runescape.com")
    parser.add_argument("--live-port", type=int, default=43594)
    parser.add_argument("--recv-timeout-seconds", type=float, default=1.5)
    parser.add_argument("--inter-chunk-delay-seconds", type=float, default=0.02)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_log = args.session_log or latest_session_log(DEFAULT_LOG_DIR)
    chunks = parse_send_chunks(session_log.read_text(encoding="utf-8", errors="replace"))
    handshake, template = select_handshake_and_template(chunks)
    archives = parse_archives(args.archives)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[ArchiveResult] = []
    first_mismatch: ArchiveResult | None = None
    for archive in archives:
        request_payload = build_reference_request(template, archive)
        local_bytes = replay_reference_request(
            args.local_host,
            args.local_port,
            handshake,
            request_payload,
            args.recv_timeout_seconds,
            args.inter_chunk_delay_seconds,
        )
        live_bytes = replay_reference_request(
            args.live_host,
            args.live_port,
            handshake,
            request_payload,
            args.recv_timeout_seconds,
            args.inter_chunk_delay_seconds,
        )
        local_capture_path = output_dir / f"archive-{archive}-local.bin"
        live_capture_path = output_dir / f"archive-{archive}-live.bin"
        local_capture_path.write_bytes(local_bytes)
        live_capture_path.write_bytes(live_bytes)
        result = ArchiveResult(
            archive=archive,
            local_bytes=len(local_bytes),
            live_bytes=len(live_bytes),
            local_sha256=hashlib.sha256(local_bytes).hexdigest(),
            live_sha256=hashlib.sha256(live_bytes).hexdigest(),
            diff=compare_bytes(local_bytes, live_bytes),
        )
        if first_mismatch is None and result.diff.state != "match":
            first_mismatch = result
        results.append(result)

    artifact = {
        "tool": "run_947_reference_table_doctor",
        "schemaVersion": 1,
        "sessionLog": str(session_log),
        "archives": archives,
        "templateHex": template.hex(),
        "results": [
            {
                **asdict(result),
                "diff": asdict(result.diff),
            }
            for result in results
        ],
        "summary": {
            "firstMismatchArchive": first_mismatch.archive if first_mismatch else None,
            "allMatched": first_mismatch is None,
            "mismatchCount": sum(1 for result in results if result.diff.state != "match"),
        },
    }
    json_path = output_dir / "reference-table-doctor.json"
    md_path = output_dir / "reference-table-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(session_log, archives, results, first_mismatch), encoding="utf-8")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
