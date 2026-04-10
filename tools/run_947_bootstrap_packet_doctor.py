from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_SESSION_LOG_DIR = WORKSPACE / "data" / "debug" / "lobby-tls-terminator"
DEFAULT_BOOTSTRAP_JSONL = WORKSPACE / "data" / "debug" / "world-bootstrap-packets.jsonl"
DEFAULT_PROXY_DUMP_ROOT = WORKSPACE / "data" / "proxy" / "dumps"
TARGET_OPCODES = (28, 50, 82)
TARGET_PACKET_NAMES = {
    28: "CLIENT_BOOTSTRAP_BLOB_28",
    50: "CLIENT_BOOTSTRAP_CONTROL_50",
    82: "CLIENT_BOOTSTRAP_CONTROL_82",
}

REQUEST_HEADER_RE = re.compile(
    r"^tls-client->remote request-header\[\d+\] line=(?P<request_line>.+?) "
    r"contentLength=(?P<content_length>\d+) headerBytes=(?P<header_bytes>\d+)$"
)
RESPONSE_HEADER_RE = re.compile(
    r"^remote->tls-client response-header\[\d+\] status=(?P<status>.+?) "
    r"contentLength=(?P<content_length>\d+) headerBytes=(?P<header_bytes>\d+)$"
)
CHUNK_RE = re.compile(
    r"^(?P<direction>tls-client->remote|remote->tls-client) (?P<label>[^ ]+) "
    r"bytes=(?P<byte_count>\d+) hex=(?P<hex>[0-9a-fA-F ]+)$"
)


@dataclass(frozen=True)
class ContainedMsEvidence:
    session_log: str
    request_line: str
    request_content_length: int
    request_header_bytes: int
    response_status: str
    response_content_length: int
    response_header_bytes: int
    response_body_preview_hex: str
    response_body_preview_length: int
    response_chunk_body_length: int
    response_chunk_hex: str


@dataclass(frozen=True)
class PacketCapture:
    source: str
    timestamp: str | None
    timestamp_epoch_millis: int | None
    packet: str
    opcode: int
    payload_size: int
    payload_hex: str
    preview_hex: str
    bootstrap_stage: str | None
    username: str | None
    player_index: int | None
    decode_summary: dict[str, Any]
    expectation: dict[str, Any]
    mismatch_flags: list[str]


@dataclass(frozen=True)
class PacketAnalysis:
    opcode: int
    packet: str
    capture_count: int
    captures: list[PacketCapture]
    missing: bool


def latest_session_log(log_dir: Path) -> Path:
    candidates = sorted(log_dir.glob("session-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No session logs found in {log_dir}")
    return candidates[0]


def parse_contained_ms_session_log(session_log: Path) -> ContainedMsEvidence:
    request_line = None
    request_content_length = None
    request_header_bytes = None
    response_status = None
    response_content_length = None
    response_header_bytes = None
    response_chunk = None

    text = session_log.read_text(encoding="utf-8", errors="replace")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        request_match = REQUEST_HEADER_RE.match(line)
        if request_match:
            request_line = request_match.group("request_line")
            request_content_length = int(request_match.group("content_length"))
            request_header_bytes = int(request_match.group("header_bytes"))
            continue
        response_match = RESPONSE_HEADER_RE.match(line)
        if response_match:
            response_status = response_match.group("status")
            response_content_length = int(response_match.group("content_length"))
            response_header_bytes = int(response_match.group("header_bytes"))
            continue
        chunk_match = CHUNK_RE.match(line)
        if chunk_match and chunk_match.group("direction") == "remote->tls-client" and response_chunk is None:
            response_chunk = bytes.fromhex(chunk_match.group("hex"))

    if request_line is None:
        raise ValueError(f"No contained request-header line found in {session_log}")
    if response_status is None or response_content_length is None or response_header_bytes is None:
        raise ValueError(f"No contained response-header line found in {session_log}")
    if response_chunk is None:
        raise ValueError(f"No remote->tls-client hex chunk found in {session_log}")

    header_end = response_chunk.find(b"\r\n\r\n")
    response_body = response_chunk[header_end + 4 :] if header_end >= 0 else b""
    response_body_preview = response_body[:64].hex()

    return ContainedMsEvidence(
        session_log=str(session_log),
        request_line=request_line,
        request_content_length=request_content_length,
        request_header_bytes=request_header_bytes,
        response_status=response_status,
        response_content_length=response_content_length,
        response_header_bytes=response_header_bytes,
        response_body_preview_hex=response_body_preview,
        response_body_preview_length=min(len(response_body), 64),
        response_chunk_body_length=len(response_body),
        response_chunk_hex=response_chunk.hex(),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize the contained 947 /ms bootstrap proof and extract evidence-grade opcode 28/50/82 "
            "packet captures from the new world-bootstrap JSONL artifact."
        )
    )
    parser.add_argument("--session-log", type=Path, default=None)
    parser.add_argument("--bootstrap-jsonl", type=Path, default=DEFAULT_BOOTSTRAP_JSONL)
    parser.add_argument("--proxy-dump-root", type=Path, default=DEFAULT_PROXY_DUMP_ROOT)
    parser.add_argument("--out-json", type=Path, default=None)
    return parser.parse_args(argv)


def current_expectation(opcode: int) -> dict[str, Any]:
    if opcode == 28:
        return {
            "shape": "variable",
            "entryCountOffset": 0,
            "notes": "opaque bootstrap blob",
        }
    if opcode == 50:
        return {
            "shape": "fixed",
            "expectedSize": 4,
            "decode": "unsigned-int-be",
        }
    if opcode == 82:
        return {
            "shape": "fixed",
            "expectedSize": 3,
            "decode": "unsigned-medium-be",
        }
    return {}


def current_decode_summary(opcode: int, payload: bytes) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "payloadSize": len(payload),
    }
    if opcode == 28:
        summary["kind"] = "opaque-variable-blob"
        summary["entryCount"] = payload[0] if payload else None
    elif opcode == 50:
        summary["kind"] = "unsigned-int-be"
        summary["value"] = int.from_bytes(payload, "big", signed=False) if len(payload) == 4 else None
        summary["valueHex"] = payload.hex()
    elif opcode == 82:
        summary["kind"] = "unsigned-medium-be"
        summary["value"] = int.from_bytes(payload, "big", signed=False) if len(payload) == 3 else None
        summary["valueHex"] = payload.hex()
    return summary


def mismatch_flags_for_payload(opcode: int, payload: bytes) -> list[str]:
    if opcode == 28:
        return ["empty-payload"] if not payload else []
    if opcode == 50 and len(payload) != 4:
        return [f"expected-size-4-got-{len(payload)}"]
    if opcode == 82 and len(payload) != 3:
        return [f"expected-size-3-got-{len(payload)}"]
    return []


def load_bootstrap_captures(bootstrap_jsonl: Path) -> list[PacketCapture]:
    if not bootstrap_jsonl.is_file():
        raise FileNotFoundError(f"Bootstrap JSONL not found: {bootstrap_jsonl}")

    captures: list[PacketCapture] = []
    with bootstrap_jsonl.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            opcode = int(payload["opcode"])
            if opcode not in TARGET_OPCODES:
                continue
            captures.append(
                PacketCapture(
                    source="bootstrap-jsonl",
                    timestamp=payload.get("timestamp"),
                    timestamp_epoch_millis=payload.get("timestampEpochMillis"),
                    packet=str(payload.get("packet") or TARGET_PACKET_NAMES.get(opcode, f"opcode-{opcode}")),
                    opcode=opcode,
                    payload_size=int(payload["payloadSize"]),
                    payload_hex=str(payload["payloadHex"]),
                    preview_hex=str(payload.get("previewHex") or "") or str(payload["payloadHex"])[:48],
                    bootstrap_stage=payload.get("bootstrapStage"),
                    username=payload.get("username") or payload.get("loginUsername"),
                    player_index=payload.get("playerIndex"),
                    decode_summary=dict(payload.get("decodeSummary") or {}),
                    expectation=dict(payload.get("expectation") or current_expectation(opcode)),
                    mismatch_flags=list(payload.get("mismatchFlags") or []),
                )
            )
    return captures


def latest_proxy_client_dump(proxy_dump_root: Path) -> Path | None:
    if not proxy_dump_root.exists():
        return None
    candidates = sorted(proxy_dump_root.rglob("clientprot.bin"), key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def load_proxy_dump_fallback(proxy_dump_root: Path) -> list[PacketCapture]:
    bin_path = latest_proxy_client_dump(proxy_dump_root)
    if bin_path is None:
        return []

    records: list[tuple[int, int, bytes]] = []
    data = bin_path.read_bytes()
    offset = 0
    while offset + 14 <= len(data):
        timestamp, opcode_short, payload_size = struct.unpack_from(">qhi", data, offset)
        offset += 14
        if payload_size < 0 or offset + payload_size > len(data):
            break
        payload = data[offset : offset + payload_size]
        offset += payload_size
        records.append((timestamp, opcode_short & 0xFFFF, payload))

    captures: list[PacketCapture] = []
    for timestamp, opcode, payload in records:
        if opcode not in TARGET_OPCODES:
            continue
        captures.append(
            PacketCapture(
                source="proxy-dump",
                timestamp=None,
                timestamp_epoch_millis=timestamp,
                packet=TARGET_PACKET_NAMES.get(opcode, f"opcode-{opcode}"),
                opcode=opcode,
                payload_size=len(payload),
                payload_hex=payload.hex(),
                preview_hex=payload[:24].hex(),
                bootstrap_stage=None,
                username=None,
                player_index=None,
                decode_summary=current_decode_summary(opcode, payload),
                expectation=current_expectation(opcode),
                mismatch_flags=mismatch_flags_for_payload(opcode, payload),
            )
        )
    return captures


def select_captures(bootstrap_jsonl: Path, proxy_dump_root: Path | None) -> tuple[str, list[PacketCapture]]:
    captures: list[PacketCapture] = []
    source = "none"
    if bootstrap_jsonl.is_file():
        captures = load_bootstrap_captures(bootstrap_jsonl)
        source = "bootstrap-jsonl"
    if captures:
        return source, captures
    if proxy_dump_root is not None:
        captures = load_proxy_dump_fallback(proxy_dump_root)
        if captures:
            return "proxy-dump", captures
    return source, []


def analyze_packets(captures: list[PacketCapture]) -> list[PacketAnalysis]:
    analyses: list[PacketAnalysis] = []
    for opcode in TARGET_OPCODES:
        grouped = [capture for capture in captures if capture.opcode == opcode]
        analyses.append(
            PacketAnalysis(
                opcode=opcode,
                packet=TARGET_PACKET_NAMES[opcode],
                capture_count=len(grouped),
                captures=grouped,
                missing=not grouped,
            )
        )
    return analyses


def infer_likely_blocker(analyses: list[PacketAnalysis]) -> str:
    if all(analysis.missing for analysis in analyses):
        return "missing-bootstrap-packet-captures"
    if any(capture.mismatch_flags for analysis in analyses for capture in analysis.captures):
        return "bootstrap-packet-shape-mismatch"
    return "bootstrap-packet-captures-look-consistent"


def render_text(evidence: ContainedMsEvidence, capture_source: str, analyses: list[PacketAnalysis], likely_blocker: str) -> str:
    lines = [
        "# 947 Bootstrap Packet Doctor",
        "",
        "## Contained /ms Evidence",
        f"- Session log: `{evidence.session_log}`",
        f"- Request line: `{evidence.request_line}`",
        f"- Response status: `{evidence.response_status}`",
        f"- Response content length: `{evidence.response_content_length}`",
        f"- Response body preview (first {evidence.response_body_preview_length} bytes): `{evidence.response_body_preview_hex}`",
        "",
        "## Bootstrap Packet Evidence",
        f"- Capture source: `{capture_source}`",
        f"- Likely blocker: `{likely_blocker}`",
        "",
    ]

    for analysis in analyses:
        lines.append(f"### {analysis.packet} (opcode {analysis.opcode})")
        if analysis.missing:
            lines.append("- No capture records found.")
            lines.append("")
            continue
        lines.append(f"- Capture count: `{analysis.capture_count}`")
        for index, capture in enumerate(analysis.captures, start=1):
            lines.append(f"- Capture {index} timestamp: `{capture.timestamp or capture.timestamp_epoch_millis}`")
            lines.append(f"- Capture {index} stage: `{capture.bootstrap_stage}`")
            lines.append(f"- Capture {index} username: `{capture.username}`")
            lines.append(f"- Capture {index} payload size: `{capture.payload_size}`")
            lines.append(f"- Capture {index} payload hex: `{capture.payload_hex}`")
            lines.append(f"- Capture {index} decode summary: `{json.dumps(capture.decode_summary, sort_keys=True)}`")
            lines.append(f"- Capture {index} expectation: `{json.dumps(capture.expectation, sort_keys=True)}`")
            mismatch_text = ", ".join(capture.mismatch_flags) if capture.mismatch_flags else "none"
            lines.append(f"- Capture {index} mismatch flags: `{mismatch_text}`")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_log = args.session_log or latest_session_log(DEFAULT_SESSION_LOG_DIR)
    evidence = parse_contained_ms_session_log(session_log)
    capture_source, captures = select_captures(args.bootstrap_jsonl, args.proxy_dump_root)
    analyses = analyze_packets(captures)
    likely_blocker = infer_likely_blocker(analyses)

    artifact = {
        "tool": "run_947_bootstrap_packet_doctor",
        "schemaVersion": 1,
        "likelyBlocker": likely_blocker,
        "captureSource": capture_source,
        "containedMsEvidence": asdict(evidence),
        "packets": [asdict(analysis) for analysis in analyses],
    }

    report = render_text(evidence, capture_source, analyses, likely_blocker)
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
