from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import lzma
import re
import socket
import sqlite3
import sys
import time
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.request import urlopen


WORKSPACE = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = WORKSPACE / "data" / "debug" / "reference-table-doctor-947"
DEFAULT_TLS_LOG_DIR = WORKSPACE / "data" / "debug" / "lobby-tls-terminator"
DEFAULT_SERVER_LOG = WORKSPACE / "tmp-manual-js5.err.log"
DEFAULT_CACHE_DIR = WORKSPACE / "data" / "cache"
DEFAULT_TOKEN_URL = "http://127.0.0.1:8080/jav_config.ws"
DEFAULT_ARCHIVES = [2, 3, 12, 16, 17, 18, 19, 21, 22, 24, 26, 28, 29, 49, 57, 58, 60, 61, 62, 65, 66]
JS5_BLOCK_BYTES = 102400
REQUEST_LOG_RE = re.compile(
    r"Queued js5 request #(?P<request_id>\d+) from (?P<remote>\S+): "
    r"opcode=(?P<opcode>\d+), priority=(?P<priority>true|false), nxt=(?P<nxt>true|false), "
    r"build=(?P<build>\d+), occurrence=(?P<occurrence>\d+), "
    r"reference-table\(index=255, archive=(?P<archive>\d+)\), available=(?P<available>true|false)"
)
SEND_LINE_RE = re.compile(
    r"^raw-client->remote\s+(?P<label>[^ ]+)\s+bytes=(?P<byte_count>\d+)\s+hex=(?P<hex>[0-9a-fA-F ]+)\s*$"
)
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
PARAM_RE = re.compile(r"^param=(?P<key>\d+)=(?P<value>.*)$")


@dataclass(frozen=True)
class SendChunk:
    label: str
    byte_count: int
    payload: bytes


@dataclass(frozen=True)
class ReplayRequest:
    opcode: int
    priority: bool
    index: int
    archive: int
    build: int


@dataclass(frozen=True)
class DiffSummary:
    state: str
    common_prefix_bytes: int
    first_diff_offset: int | None
    local_remaining_bytes: int
    live_remaining_bytes: int


@dataclass(frozen=True)
class HexDiffWindow:
    start_offset: int
    end_offset: int
    local_hex: str
    live_hex: str


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
class ParsedJs5Reply:
    handshake_response: int
    header: ResponseHeader
    frame_bytes: bytes
    payload_bytes: bytes
    trailing_bytes: bytes


@dataclass(frozen=True)
class ContainerInfo:
    compression: int
    compressed_size: int
    decompressed_size: int
    version: int | None
    payload_bytes: bytes
    compressed_payload_bytes: bytes


@dataclass(frozen=True)
class ChecksumTableEntry:
    index: int
    crc: int
    version: int
    files: int
    size: int
    whirlpool_hex: str


@dataclass(frozen=True)
class ChecksumTableDump:
    entry_count: int
    entries: dict[int, ChecksumTableEntry]
    signature_hex: str


@dataclass(frozen=True)
class LocalReferenceTableInfo:
    archive: int
    path: str
    raw_bytes: int
    raw_sha256: str
    raw_crc32: int
    stored_crc32: int | None
    raw_version: int | None
    stored_version: int | None


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


@dataclass(frozen=True)
class ArchiveResult:
    archive: int
    local_handshake_response: int
    live_handshake_response: int
    local_frame_bytes: int
    live_frame_bytes: int
    local_payload_bytes: int
    live_payload_bytes: int
    local_frame_sha256: str
    live_frame_sha256: str
    local_payload_sha256: str
    live_payload_sha256: str
    frame_diff: DiffSummary
    payload_diff: DiffSummary
    frame_diff_window: HexDiffWindow | None
    payload_diff_window: HexDiffWindow | None
    local_header: dict[str, int | bool]
    live_header: dict[str, int | bool]
    mismatch_flags: list[str]
    local_master_entry: dict[str, int | str] | None
    live_master_entry: dict[str, int | str] | None
    local_reference_table: dict[str, int | str | None] | None


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


def latest_raw_game_session_log(log_dir: Path) -> Path:
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


def latest_contained_ms_session_log(log_dir: Path) -> Path | None:
    candidates = sorted(log_dir.glob("session-*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "/ms?m=0&a=255" in text and "request-header[" in text:
            return candidate
    return None


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
    with urlopen(token_url, timeout=10) as response:
        text = response.read().decode("iso-8859-1", "replace")
    return parse_jav_config_token(text)


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


def build_reference_request(template: bytes, archive: int) -> bytes:
    if archive < 0 or archive > 0xFFFFFFFF:
        raise ValueError(f"Archive id out of range: {archive}")
    payload = bytearray(template)
    payload[2:6] = archive.to_bytes(4, "big")
    return bytes(payload)


def build_request_packet(request: ReplayRequest) -> bytes:
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


def replay_reference_request(
    host: str,
    port: int,
    build: int,
    token: str,
    archive: int,
    recv_timeout_seconds: float,
) -> bytes:
    request = ReplayRequest(opcode=1, priority=True, index=255, archive=archive, build=build)
    with socket.create_connection((host, port), timeout=10.0) as sock:
        sock.settimeout(recv_timeout_seconds)
        sock.sendall(build_handshake(build, token))
        handshake_response = sock.recv(1)
        if len(handshake_response) != 1:
            raise ConnectionError(f"No handshake response from {host}:{port}")

        sock.sendall(build_init_packets(build))
        sock.sendall(build_request_packet(request))

        envelope = read_exact(sock, 5)
        prefix = read_exact(sock, 5)
        header = parse_response_header(envelope + prefix)
        raw_response = bytearray(handshake_response)
        raw_response.extend(envelope)
        raw_response.extend(prefix)

        remaining_container_bytes = header.container_bytes - 5
        first_chunk_bytes = min(JS5_BLOCK_BYTES - 10, remaining_container_bytes)
        if first_chunk_bytes > 0:
            raw_response.extend(read_exact(sock, first_chunk_bytes))
            remaining_container_bytes -= first_chunk_bytes

        while remaining_container_bytes > 0:
            raw_response.extend(read_exact(sock, 5))
            chunk_bytes = min(JS5_BLOCK_BYTES - 5, remaining_container_bytes)
            raw_response.extend(read_exact(sock, chunk_bytes))
            remaining_container_bytes -= chunk_bytes

    return bytes(raw_response)


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


def derive_hot_archives(server_log_text: str, include_master: bool = True) -> list[int]:
    counts: dict[int, int] = {}
    order: list[int] = []
    for raw_line in server_log_text.splitlines():
        match = REQUEST_LOG_RE.search(raw_line)
        if not match or match.group("available") != "true":
            continue
        archive = int(match.group("archive"))
        if archive not in counts:
            order.append(archive)
            counts[archive] = 0
        counts[archive] += 1

    hot = [archive for archive in order if counts.get(archive, 0) > 1]
    if not hot:
        hot = order[:]
    if not hot:
        hot = DEFAULT_ARCHIVES[:]
    if include_master and 255 not in hot:
        hot.append(255)
    return hot


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


def parse_js5_reply(received: bytes) -> ParsedJs5Reply:
    if len(received) < 11:
        raise ValueError(f"Expected at least 11 reply bytes, got {len(received)}")

    handshake_response = received[0]
    view = memoryview(received[1:])
    if len(view) < 10:
        raise ValueError(f"Reply did not contain a JS5 response after handshake byte: {received.hex()}")

    envelope = bytes(view[0:5])
    prefix = bytes(view[5:10])
    header = parse_response_header(envelope + prefix)
    payload = bytearray(prefix)
    frame = bytearray(envelope)
    frame.extend(prefix)
    offset = 10

    remaining_container_bytes = header.container_bytes - 5
    first_chunk_bytes = min(JS5_BLOCK_BYTES - 10, remaining_container_bytes)
    if len(view) < offset + first_chunk_bytes:
        raise ValueError(
            f"Incomplete first JS5 body chunk for archive {header.archive}: "
            f"needed {first_chunk_bytes}, have {len(view) - offset}"
        )
    if first_chunk_bytes > 0:
        first_body = bytes(view[offset : offset + first_chunk_bytes])
        payload.extend(first_body)
        frame.extend(first_body)
        offset += first_chunk_bytes
        remaining_container_bytes -= first_chunk_bytes

    while remaining_container_bytes > 0:
        if len(view) < offset + 5:
            raise ValueError(
                f"Incomplete continuation envelope for archive {header.archive}: "
                f"needed 5 bytes, have {len(view) - offset}"
            )
        continuation_envelope = bytes(view[offset : offset + 5])
        offset += 5
        frame.extend(continuation_envelope)
        chunk_bytes = min(JS5_BLOCK_BYTES - 5, remaining_container_bytes)
        if len(view) < offset + chunk_bytes:
            raise ValueError(
                f"Incomplete continuation chunk for archive {header.archive}: "
                f"needed {chunk_bytes}, have {len(view) - offset}"
            )
        continuation_body = bytes(view[offset : offset + chunk_bytes])
        offset += chunk_bytes
        payload.extend(continuation_body)
        frame.extend(continuation_body)
        remaining_container_bytes -= chunk_bytes

    trailing_bytes = bytes(view[offset:])
    return ParsedJs5Reply(
        handshake_response=handshake_response,
        header=header,
        frame_bytes=bytes(frame),
        payload_bytes=bytes(payload),
        trailing_bytes=trailing_bytes,
    )


def decompress_rs_bzip2(compressed_payload: bytes) -> bytes:
    return bz2.decompress(b"BZh1" + compressed_payload)


def decompress_rs_lzma(compressed_payload: bytes) -> bytes:
    if len(compressed_payload) < 5:
        raise ValueError(f"LZMA payload too short: {len(compressed_payload)} bytes")
    props = compressed_payload[:5]
    body = compressed_payload[5:]
    property_byte = props[0]
    pb = property_byte // (9 * 5)
    remainder = property_byte % (9 * 5)
    lp = remainder // 9
    lc = remainder % 9
    dictionary_size = int.from_bytes(props[1:5], "little")
    return lzma.decompress(
        body,
        format=lzma.FORMAT_RAW,
        filters=[
            {
                "id": lzma.FILTER_LZMA1,
                "dict_size": dictionary_size,
                "lc": lc,
                "lp": lp,
                "pb": pb,
            }
        ],
    )


def decode_container(data: bytes) -> ContainerInfo:
    if len(data) < 5:
        raise ValueError(f"Container is too short: {len(data)} bytes")
    compression = data[0]
    compressed_size = int.from_bytes(data[1:5], "big")
    offset = 5
    decompressed_size = 0
    if compression != 0:
        if len(data) < 9:
            raise ValueError(f"Compressed container missing decompressed length: {len(data)} bytes")
        decompressed_size = int.from_bytes(data[5:9], "big")
        offset = 9
    end = offset + compressed_size
    if len(data) < end:
        raise ValueError(
            f"Container declared {compressed_size} compressed bytes but only {len(data) - offset} remain"
        )
    compressed_payload = data[offset:end]
    trailer = data[end:]
    version = int.from_bytes(trailer[:2], "big") if len(trailer) >= 2 else None

    if compression == 0:
        payload = compressed_payload
    elif compression == 1:
        payload = decompress_rs_bzip2(compressed_payload)
    elif compression == 2:
        payload = zlib.decompress(compressed_payload, zlib.MAX_WBITS | 16)
    elif compression == 3:
        payload = decompress_rs_lzma(compressed_payload)
    else:
        raise ValueError(f"Unsupported container compression type: {compression}")

    return ContainerInfo(
        compression=compression,
        compressed_size=compressed_size,
        decompressed_size=decompressed_size,
        version=version,
        payload_bytes=payload,
        compressed_payload_bytes=compressed_payload,
    )


def decode_checksum_table_payload(payload: bytes) -> ChecksumTableDump:
    if not payload:
        raise ValueError("Checksum payload is empty")
    entry_count = payload[0]
    entries_size = 1 + entry_count * (4 + 4 + 4 + 4 + 64)
    if len(payload) < entries_size:
        raise ValueError(f"Checksum payload too short: {len(payload)} bytes < {entries_size}")

    entries: dict[int, ChecksumTableEntry] = {}
    offset = 1
    for index in range(entry_count):
        crc = int.from_bytes(payload[offset : offset + 4], "big", signed=False)
        offset += 4
        version = int.from_bytes(payload[offset : offset + 4], "big", signed=False)
        offset += 4
        files = int.from_bytes(payload[offset : offset + 4], "big", signed=False)
        offset += 4
        size = int.from_bytes(payload[offset : offset + 4], "big", signed=False)
        offset += 4
        whirlpool = payload[offset : offset + 64]
        offset += 64
        entries[index] = ChecksumTableEntry(
            index=index,
            crc=crc,
            version=version,
            files=files,
            size=size,
            whirlpool_hex=whirlpool.hex(),
        )

    return ChecksumTableDump(
        entry_count=entry_count,
        entries=entries,
        signature_hex=payload[offset:].hex(),
    )


def load_local_reference_table_info(cache_dir: Path, archive: int) -> LocalReferenceTableInfo | None:
    path = cache_dir / f"js5-{archive}.jcache"
    if not path.is_file():
        return None

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT DATA, VERSION, CRC FROM cache_index WHERE KEY = 1"
        ).fetchone()
    if row is None:
        return None

    raw = bytes(row[0])
    container = decode_container(raw)
    return LocalReferenceTableInfo(
        archive=archive,
        path=str(path),
        raw_bytes=len(raw),
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_crc32=zlib.crc32(raw) & 0xFFFFFFFF,
        stored_crc32=int(row[2]) & 0xFFFFFFFF if row[2] is not None else None,
        raw_version=container.version,
        stored_version=int(row[1]) if row[1] is not None else None,
    )


def build_hex_diff_window(
    local_bytes: bytes,
    live_bytes: bytes,
    diff: DiffSummary,
    window_bytes: int,
) -> HexDiffWindow | None:
    if diff.first_diff_offset is None:
        return None
    start = max(0, diff.first_diff_offset - window_bytes)
    end = min(max(len(local_bytes), len(live_bytes)), diff.first_diff_offset + window_bytes)
    return HexDiffWindow(
        start_offset=start,
        end_offset=end,
        local_hex=local_bytes[start:end].hex(),
        live_hex=live_bytes[start:end].hex(),
    )


def checksum_entry_to_dict(entry: ChecksumTableEntry | None) -> dict[str, int | str] | None:
    if entry is None:
        return None
    return {
        "crc": entry.crc,
        "crcHex": f"{entry.crc:08x}",
        "version": entry.version,
        "versionHex": f"{entry.version:08x}",
        "files": entry.files,
        "size": entry.size,
        "whirlpoolHex": entry.whirlpool_hex,
    }


def local_reference_table_to_dict(info: LocalReferenceTableInfo | None) -> dict[str, int | str | None] | None:
    if info is None:
        return None
    return {
        "path": info.path,
        "rawBytes": info.raw_bytes,
        "rawSha256": info.raw_sha256,
        "rawCrc32": info.raw_crc32,
        "rawCrc32Hex": f"{info.raw_crc32:08x}",
        "storedCrc32": info.stored_crc32,
        "storedCrc32Hex": f"{info.stored_crc32:08x}" if info.stored_crc32 is not None else None,
        "rawVersion": info.raw_version,
        "storedVersion": info.stored_version,
    }


def classify_archive(
    archive: int,
    payload_diff: DiffSummary,
    local_master_entry: ChecksumTableEntry | None,
    live_master_entry: ChecksumTableEntry | None,
    local_reference_table: LocalReferenceTableInfo | None,
    local_reply: ParsedJs5Reply,
    live_reply: ParsedJs5Reply,
) -> list[str]:
    flags: list[str] = []

    if local_reply.handshake_response != live_reply.handshake_response:
        flags.append("handshake-response-mismatch")
    if local_reply.header != live_reply.header:
        flags.append("response-header-mismatch")
    if local_reply.trailing_bytes or live_reply.trailing_bytes:
        flags.append("unexpected-trailing-bytes")

    if archive == 255:
        if payload_diff.state != "match":
            flags.append("raw-master-table-body-disagrees-with-retail")
        return flags

    if payload_diff.state != "match":
        flags.append("local-reference-table-body-disagrees-with-retail")

    if local_master_entry is None:
        flags.append("local-master-entry-missing")
    if live_master_entry is None:
        flags.append("retail-master-entry-missing")

    if local_master_entry is not None and live_master_entry is not None:
        if (
            local_master_entry.crc != live_master_entry.crc
            or local_master_entry.version != live_master_entry.version
            or local_master_entry.files != live_master_entry.files
            or local_master_entry.size != live_master_entry.size
        ):
            flags.append("master-entry-disagrees-with-retail")

    if local_master_entry is not None and local_reference_table is not None:
        if (
            local_master_entry.crc != local_reference_table.raw_crc32
            or (
                local_reference_table.raw_version is not None
                and local_master_entry.version != local_reference_table.raw_version
            )
        ):
            flags.append("local-master-entry-disagrees-with-local-table")

    return flags


def archive_sort_key(archive: int) -> tuple[int, int]:
    return (1, archive) if archive == 255 else (0, archive)


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
    )


def render_markdown(
    session_log: Path,
    server_log: Path,
    archives: list[int],
    results: list[ArchiveResult],
    first_mismatch: ArchiveResult | None,
    ms_evidence: ContainedMsEvidence | None,
) -> str:
    lines = [
        "# 947 Reference Table Doctor",
        "",
        f"- Raw-game session log: `{session_log}`",
        f"- Server log: `{server_log}`",
        f"- Archive count: `{len(archives)}`",
        f"- First mismatch archive: `{first_mismatch.archive if first_mismatch else 'none'}`",
        f"- All compared replies matched: `{first_mismatch is None}`",
        "",
    ]

    if ms_evidence is not None:
        lines.extend(
            [
                "## Secondary /ms Evidence",
                "",
                f"- Session log: `{ms_evidence.session_log}`",
                f"- Request line: `{ms_evidence.request_line}`",
                f"- Response status: `{ms_evidence.response_status}`",
                f"- Response body preview: `{ms_evidence.response_body_preview_hex}`",
                "",
            ]
        )

    lines.extend(["## Archive Results", ""])
    for result in results:
        lines.append(
            "- archive `{archive}` frameState=`{frame}` payloadState=`{payload}` flags=`{flags}` frameFirstDiff=`{fd}` payloadFirstDiff=`{pd}`".format(
                archive=result.archive,
                frame=result.frame_diff.state,
                payload=result.payload_diff.state,
                flags=",".join(result.mismatch_flags) if result.mismatch_flags else "none",
                fd=result.frame_diff.first_diff_offset,
                pd=result.payload_diff.first_diff_offset,
            )
        )

    if first_mismatch is not None:
        lines.extend(
            [
                "",
                "## First Mismatch Detail",
                "",
                f"- Archive: `{first_mismatch.archive}`",
                f"- Flags: `{','.join(first_mismatch.mismatch_flags) if first_mismatch.mismatch_flags else 'none'}`",
                f"- Local master entry: `{json.dumps(first_mismatch.local_master_entry, sort_keys=True) if first_mismatch.local_master_entry else 'null'}`",
                f"- Live master entry: `{json.dumps(first_mismatch.live_master_entry, sort_keys=True) if first_mismatch.live_master_entry else 'null'}`",
                f"- Local table truth: `{json.dumps(first_mismatch.local_reference_table, sort_keys=True) if first_mismatch.local_reference_table else 'null'}`",
            ]
        )

    return "\n".join(lines)


def render_text_summary(results: list[ArchiveResult], first_mismatch: ArchiveResult | None) -> str:
    lines = [
        f"firstMismatchArchive={first_mismatch.archive if first_mismatch else 'none'}",
        f"allMatched={'true' if first_mismatch is None else 'false'}",
        f"mismatchCount={sum(1 for result in results if result.mismatch_flags or result.payload_diff.state != 'match' or result.frame_diff.state != 'match')}",
        "",
    ]
    for result in results:
        lines.extend(
            [
                f"archive={result.archive}",
                f"  frameState={result.frame_diff.state}",
                f"  payloadState={result.payload_diff.state}",
                f"  flags={','.join(result.mismatch_flags) if result.mismatch_flags else 'none'}",
                f"  localFrameSha256={result.local_frame_sha256}",
                f"  liveFrameSha256={result.live_frame_sha256}",
                f"  localPayloadSha256={result.local_payload_sha256}",
                f"  livePayloadSha256={result.live_payload_sha256}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay hot 947 raw JS5 reference-table requests against local and live targets, decode "
            "raw 255/255 master entries, and classify whether the mismatch lives in the master table, "
            "the reference-table bodies, or their relationship."
        )
    )
    parser.add_argument("--session-log", type=Path, default=None, help="Path to a raw-game session log")
    parser.add_argument("--server-log", type=Path, default=DEFAULT_SERVER_LOG, help="Path to the live server log")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--archives", default=None, help="Optional comma-separated archive override")
    parser.add_argument("--local-host", default="127.0.0.1")
    parser.add_argument("--local-port", type=int, default=43596)
    parser.add_argument("--live-host", default="content.runescape.com")
    parser.add_argument("--live-port", type=int, default=43594)
    parser.add_argument("--recv-timeout-seconds", type=float, default=1.5)
    parser.add_argument("--inter-chunk-delay-seconds", type=float, default=0.02)
    parser.add_argument("--diff-window-bytes", type=int, default=32)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--include-master", action=argparse.BooleanOptionalAction, default=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session_log = args.session_log or latest_raw_game_session_log(DEFAULT_TLS_LOG_DIR)
    build, token = fetch_token(DEFAULT_TOKEN_URL)

    server_log = args.server_log
    server_log_text = server_log.read_text(encoding="utf-8", errors="replace")
    archives = parse_archives(args.archives) if args.archives else derive_hot_archives(
        server_log_text,
        include_master=args.include_master,
    )
    if args.include_master and 255 not in archives:
        archives.append(255)
    archives = sorted(dict.fromkeys(archives), key=archive_sort_key)

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    replay_by_archive: dict[int, tuple[ParsedJs5Reply, ParsedJs5Reply]] = {}
    for archive in archives:
        local_bytes = replay_reference_request(
            args.local_host,
            args.local_port,
            build,
            token,
            archive,
            args.recv_timeout_seconds,
        )
        live_bytes = replay_reference_request(
            args.live_host,
            args.live_port,
            build,
            token,
            archive,
            args.recv_timeout_seconds,
        )

        local_reply = parse_js5_reply(local_bytes)
        live_reply = parse_js5_reply(live_bytes)
        replay_by_archive[archive] = (local_reply, live_reply)

        archive_dir = output_dir / f"archive-{archive}"
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "local.reply.bin").write_bytes(local_reply.frame_bytes)
        (archive_dir / "live.reply.bin").write_bytes(live_reply.frame_bytes)
        (archive_dir / "local.payload.bin").write_bytes(local_reply.payload_bytes)
        (archive_dir / "live.payload.bin").write_bytes(live_reply.payload_bytes)
        if local_reply.trailing_bytes:
            (archive_dir / "local.trailing.bin").write_bytes(local_reply.trailing_bytes)
        if live_reply.trailing_bytes:
            (archive_dir / "live.trailing.bin").write_bytes(live_reply.trailing_bytes)

    local_master_table = None
    live_master_table = None
    if 255 in replay_by_archive:
        local_master_container = decode_container(replay_by_archive[255][0].payload_bytes)
        live_master_container = decode_container(replay_by_archive[255][1].payload_bytes)
        local_master_table = decode_checksum_table_payload(local_master_container.payload_bytes)
        live_master_table = decode_checksum_table_payload(live_master_container.payload_bytes)

    results: list[ArchiveResult] = []
    first_mismatch: ArchiveResult | None = None
    for archive in archives:
        local_reply, live_reply = replay_by_archive[archive]
        frame_diff = compare_bytes(local_reply.frame_bytes, live_reply.frame_bytes)
        payload_diff = compare_bytes(local_reply.payload_bytes, live_reply.payload_bytes)
        local_entry = None if local_master_table is None or archive == 255 else local_master_table.entries.get(archive)
        live_entry = None if live_master_table is None or archive == 255 else live_master_table.entries.get(archive)
        local_reference_info = None if archive == 255 else load_local_reference_table_info(args.cache_dir, archive)
        mismatch_flags = classify_archive(
            archive=archive,
            payload_diff=payload_diff,
            local_master_entry=local_entry,
            live_master_entry=live_entry,
            local_reference_table=local_reference_info,
            local_reply=local_reply,
            live_reply=live_reply,
        )
        result = ArchiveResult(
            archive=archive,
            local_handshake_response=local_reply.handshake_response,
            live_handshake_response=live_reply.handshake_response,
            local_frame_bytes=len(local_reply.frame_bytes),
            live_frame_bytes=len(live_reply.frame_bytes),
            local_payload_bytes=len(local_reply.payload_bytes),
            live_payload_bytes=len(live_reply.payload_bytes),
            local_frame_sha256=hashlib.sha256(local_reply.frame_bytes).hexdigest(),
            live_frame_sha256=hashlib.sha256(live_reply.frame_bytes).hexdigest(),
            local_payload_sha256=hashlib.sha256(local_reply.payload_bytes).hexdigest(),
            live_payload_sha256=hashlib.sha256(live_reply.payload_bytes).hexdigest(),
            frame_diff=frame_diff,
            payload_diff=payload_diff,
            frame_diff_window=build_hex_diff_window(
                local_reply.frame_bytes,
                live_reply.frame_bytes,
                frame_diff,
                args.diff_window_bytes,
            ),
            payload_diff_window=build_hex_diff_window(
                local_reply.payload_bytes,
                live_reply.payload_bytes,
                payload_diff,
                args.diff_window_bytes,
            ),
            local_header=asdict(local_reply.header),
            live_header=asdict(live_reply.header),
            mismatch_flags=mismatch_flags,
            local_master_entry=checksum_entry_to_dict(local_entry),
            live_master_entry=checksum_entry_to_dict(live_entry),
            local_reference_table=local_reference_table_to_dict(local_reference_info),
        )
        if first_mismatch is None and (
            result.frame_diff.state != "match"
            or result.payload_diff.state != "match"
            or result.mismatch_flags
        ):
            first_mismatch = result
        results.append(result)

    ms_evidence = None
    ms_session_log = latest_contained_ms_session_log(DEFAULT_TLS_LOG_DIR)
    if ms_session_log is not None:
        try:
            ms_evidence = parse_contained_ms_session_log(ms_session_log)
        except Exception:
            ms_evidence = None

    artifact = {
        "tool": "run_947_reference_table_doctor",
        "schemaVersion": 2,
        "sessionLog": str(session_log),
        "serverLog": str(server_log),
        "build": build,
        "tokenSourceUrl": DEFAULT_TOKEN_URL,
        "archives": archives,
        "templateHex": None,
        "containedMsEvidence": asdict(ms_evidence) if ms_evidence is not None else None,
        "localMasterTable": (
            {
                "entryCount": local_master_table.entry_count,
                "signatureHex": local_master_table.signature_hex,
                "entries": {str(index): asdict(entry) for index, entry in local_master_table.entries.items()},
            }
            if local_master_table is not None
            else None
        ),
        "liveMasterTable": (
            {
                "entryCount": live_master_table.entry_count,
                "signatureHex": live_master_table.signature_hex,
                "entries": {str(index): asdict(entry) for index, entry in live_master_table.entries.items()},
            }
            if live_master_table is not None
            else None
        ),
        "results": [
            {
                **asdict(result),
                "frame_diff": asdict(result.frame_diff),
                "payload_diff": asdict(result.payload_diff),
                "frame_diff_window": asdict(result.frame_diff_window) if result.frame_diff_window else None,
                "payload_diff_window": asdict(result.payload_diff_window) if result.payload_diff_window else None,
            }
            for result in results
        ],
        "summary": {
            "firstMismatchArchive": first_mismatch.archive if first_mismatch else None,
            "allMatched": first_mismatch is None,
            "mismatchCount": sum(
                1
                for result in results
                if result.frame_diff.state != "match"
                or result.payload_diff.state != "match"
                or result.mismatch_flags
            ),
            "mismatchArchives": [
                result.archive
                for result in results
                if result.frame_diff.state != "match"
                or result.payload_diff.state != "match"
                or result.mismatch_flags
            ],
        },
    }
    json_path = output_dir / "reference-table-doctor.json"
    md_path = output_dir / "reference-table-doctor.md"
    txt_path = output_dir / "reference-table-doctor.txt"
    json_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    md_path.write_text(
        render_markdown(session_log, server_log, archives, results, first_mismatch, ms_evidence),
        encoding="utf-8",
    )
    txt_path.write_text(render_text_summary(results, first_mismatch), encoding="utf-8")
    print(json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
