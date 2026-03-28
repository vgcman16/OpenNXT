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
from typing import Iterable


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "js5-bootstrap-wire-doctor"
DEFAULT_LOG_DIR = WORKSPACE / "data" / "debug" / "lobby-tls-terminator"

SEND_LINE_RE = re.compile(
    r"^raw-client->remote\s+(?P<label>[^ ]+)\s+bytes=(?P<byte_count>\d+)\s+hex=(?P<hex>[0-9a-fA-F ]+)\s*$"
)


@dataclass(frozen=True)
class SendChunk:
    label: str
    byte_count: int
    payload: bytes


@dataclass(frozen=True)
class ReplayCapture:
    host: str
    port: int
    sent_bytes: int
    received_bytes: int
    sha256: str
    first_64_hex: str
    capture_path: str


@dataclass(frozen=True)
class DiffSummary:
    state: str
    common_prefix_bytes: int
    first_diff_offset: int | None
    local_remaining_bytes: int
    live_remaining_bytes: int


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
        chunks.append(
            SendChunk(
                label=match.group("label"),
                byte_count=byte_count,
                payload=payload,
            )
        )
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
        if "raw-client->remote" in text:
            return candidate
    raise ValueError(f"No raw-bootstrap session logs were found in {log_dir}")


def replay_capture(
    host: str,
    port: int,
    chunks: Iterable[SendChunk],
    recv_timeout_seconds: float,
    inter_chunk_delay_seconds: float,
    output_path: Path,
) -> ReplayCapture:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    received = bytearray()
    sent_total = 0

    with socket.create_connection((host, port), timeout=10.0) as sock:
        sock.settimeout(recv_timeout_seconds)

        for chunk in chunks:
            sock.sendall(chunk.payload)
            sent_total += len(chunk.payload)
            if inter_chunk_delay_seconds > 0:
                time.sleep(inter_chunk_delay_seconds)

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

    output_path.write_bytes(received)
    return ReplayCapture(
        host=host,
        port=port,
        sent_bytes=sent_total,
        received_bytes=len(received),
        sha256=hashlib.sha256(received).hexdigest(),
        first_64_hex=received[:64].hex(),
        capture_path=str(output_path),
    )


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


def render_markdown(
    session_log: Path,
    chunks: list[SendChunk],
    local_capture: ReplayCapture,
    live_capture: ReplayCapture,
    diff: DiffSummary,
) -> str:
    return "\n".join(
        [
            "# 947 JS5 Bootstrap Wire Doctor",
            "",
            f"- Session log: `{session_log}`",
            f"- Sent chunk count: `{len(chunks)}`",
            f"- Sent bytes total: `{sum(chunk.byte_count for chunk in chunks)}`",
            f"- Local target: `{local_capture.host}:{local_capture.port}`",
            f"- Local received bytes: `{local_capture.received_bytes}`",
            f"- Live target: `{live_capture.host}:{live_capture.port}`",
            f"- Live received bytes: `{live_capture.received_bytes}`",
            f"- Diff state: `{diff.state}`",
            f"- Common prefix bytes: `{diff.common_prefix_bytes}`",
            f"- First diff offset: `{diff.first_diff_offset}`",
            f"- Local remaining bytes after prefix: `{diff.local_remaining_bytes}`",
            f"- Live remaining bytes after prefix: `{diff.live_remaining_bytes}`",
            "",
            "## First Send Chunks",
            "",
            *[
                f"- `{chunk.label}` `{chunk.byte_count}` bytes `{chunk.payload[:32].hex()}`"
                for chunk in chunks[:8]
            ],
            "",
            "## Captures",
            "",
            f"- Local SHA-256: `{local_capture.sha256}`",
            f"- Local capture: `{local_capture.capture_path}`",
            f"- Local first 64 bytes: `{local_capture.first_64_hex}`",
            f"- Live SHA-256: `{live_capture.sha256}`",
            f"- Live capture: `{live_capture.capture_path}`",
            f"- Live first 64 bytes: `{live_capture.first_64_hex}`",
        ]
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a captured 947 JS5 bootstrap byte sequence against local and live targets. "
            "The local default points at the direct backend JS5 listener (43596), which is where the raw-game route terminates."
        )
    )
    parser.add_argument("--session-log", type=Path, default=None, help="Path to a lobby-tls-terminator raw-game session log")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for artifacts")
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
    log_text = session_log.read_text(encoding="utf-8")
    chunks = parse_send_chunks(log_text)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    local_bin = output_dir / "local-response.bin"
    live_bin = output_dir / "live-response.bin"

    local_capture = replay_capture(
        host=args.local_host,
        port=args.local_port,
        chunks=chunks,
        recv_timeout_seconds=args.recv_timeout_seconds,
        inter_chunk_delay_seconds=args.inter_chunk_delay_seconds,
        output_path=local_bin,
    )
    live_capture = replay_capture(
        host=args.live_host,
        port=args.live_port,
        chunks=chunks,
        recv_timeout_seconds=args.recv_timeout_seconds,
        inter_chunk_delay_seconds=args.inter_chunk_delay_seconds,
        output_path=live_bin,
    )

    diff = compare_bytes(local_bin.read_bytes(), live_bin.read_bytes())
    artifact = {
        "tool": "run_947_js5_bootstrap_wire_doctor",
        "schemaVersion": 1,
        "sessionLog": str(session_log),
        "sentChunks": [
            {
                "label": chunk.label,
                "byteCount": chunk.byte_count,
                "hex": chunk.payload.hex(),
            }
            for chunk in chunks
        ],
        "localCapture": asdict(local_capture),
        "liveCapture": asdict(live_capture),
        "diff": asdict(diff),
    }

    json_path = output_dir / "js5-bootstrap-wire-doctor.json"
    md_path = output_dir / "js5-bootstrap-wire-doctor.md"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(session_log, chunks, local_capture, live_capture, diff), encoding="utf-8")
    print(str(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
