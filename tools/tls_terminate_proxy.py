import argparse
import atexit
import hashlib
import ipaddress
import re
import select
import socket
import ssl
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12


HTTP_HEADER_TERMINATOR = b"\r\n\r\n"
HTTP_METHOD_PREFIXES = (b"GET ", b"POST ", b"HEAD ", b"OPTIONS ", b"PUT ", b"DELETE ", b"PATCH ")
ORIGINAL_HOST_HEADER = "X-OpenNXT-Original-Host"
JS5_HANDSHAKE_PREFIX = b"\x0f"
TLS_HTTP_CONTENT_ROUTE = "tls-http-content"
TLS_SECURE_GAME_ROUTE = "tls-secure-game"
RAW_GAME_ROUTE = "raw-game"
TLS_FIRST_APPDATA_TIMEOUT_SECONDS = 1.5
TLS_CLIENT_HELLO_PEEK_LIMIT = 4096
TLS_ROUTE_MODE_MITM = "mitm"
TLS_ROUTE_MODE_PASSTHROUGH = "passthrough"
TLS_ROUTE_MODE_INSPECT = "inspect-after-handshake"
TLS_ROUTE_MODE_TERMINATE = "terminate"
RAW_PRELOGIN_CLIENT_BYTE_CAP = 64
LISTENER_BACKLOG = 128
DEFAULT_CONTENT_CLIENTHELLO_SHA256 = {
    "4ac01a273c0d4fc383c0e417852def9251aa8142a08a857cb30b68de92861cc3",
    "66539cad7effbf482fa8708ef9a4c5d850a434cd826ff5566d580140f61313c6",
}
CONTENT_CLIENTHELLO_LOG_SCAN_LIMIT = 512
SESSION_PREFIX_RE = re.compile(r"session#(\d+)\s")
DEFAULT_TLS_MITM_HOSTS = {
    "content.runescape.com",
    "rs.config.runescape.com",
}


def parse_listen_hosts(value: str) -> list[str]:
    hosts = [item.strip() for item in str(value).split(",") if item.strip()]
    return hosts or ["127.0.0.1"]


def socket_family_for_host(host: str) -> socket.AddressFamily:
    return socket.AF_INET6 if ":" in host else socket.AF_INET


def create_listener(host: str, port: int, accept_timeout: float) -> socket.socket:
    family = socket_family_for_host(host)
    listener = socket.socket(family, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        try:
            listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        except (AttributeError, OSError):
            pass
        listener.bind((host, port, 0, 0))
    else:
        listener.bind((host, port))
    listener.listen(LISTENER_BACKLOG)
    listener.settimeout(accept_timeout)
    return listener


def preview_hex(data: bytes, limit: int = 512) -> str:
    return " ".join(f"{b:02x}" for b in data[:limit])


def looks_like_tls_client_hello(data: bytes) -> bool:
    if len(data) < 5:
        return False
    content_type = data[0]
    major = data[1]
    minor = data[2]
    return content_type == 0x16 and major == 0x03 and minor in (0x00, 0x01, 0x02, 0x03, 0x04)


def peek_tls_client_hello(client_sock: socket.socket, limit: int = TLS_CLIENT_HELLO_PEEK_LIMIT) -> bytes:
    initial = client_sock.recv(5, socket.MSG_PEEK)
    if not looks_like_tls_client_hello(initial):
        return initial
    if len(initial) < 5:
        return initial
    record_length = int.from_bytes(initial[3:5], "big")
    target = min(limit, 5 + max(record_length, 0))
    try:
        return client_sock.recv(target, socket.MSG_PEEK)
    except OSError:
        return initial


def parse_tls_client_hello_sni(data: bytes) -> str | None:
    if len(data) < 5 or not looks_like_tls_client_hello(data):
        return None
    record_length = int.from_bytes(data[3:5], "big")
    record_end = 5 + record_length
    if len(data) < record_end:
        return None
    if data[5] != 0x01:
        return None
    if len(data) < 9:
        return None
    handshake_length = int.from_bytes(data[6:9], "big")
    handshake_end = 9 + handshake_length
    if len(data) < handshake_end:
        return None

    offset = 9
    if offset + 2 + 32 > handshake_end:
        return None
    offset += 2  # legacy_version
    offset += 32  # random

    session_id_length = data[offset]
    offset += 1
    offset += session_id_length
    if offset + 2 > handshake_end:
        return None

    cipher_suites_length = int.from_bytes(data[offset : offset + 2], "big")
    offset += 2 + cipher_suites_length
    if offset >= handshake_end:
        return None

    compression_methods_length = data[offset]
    offset += 1 + compression_methods_length
    if offset + 2 > handshake_end:
        return None

    extensions_length = int.from_bytes(data[offset : offset + 2], "big")
    offset += 2
    extensions_end = min(handshake_end, offset + extensions_length)
    while offset + 4 <= extensions_end:
        extension_type = int.from_bytes(data[offset : offset + 2], "big")
        extension_length = int.from_bytes(data[offset + 2 : offset + 4], "big")
        offset += 4
        if offset + extension_length > extensions_end:
            return None
        if extension_type == 0x0000:
            if extension_length < 2:
                return None
            name_list_length = int.from_bytes(data[offset : offset + 2], "big")
            cursor = offset + 2
            name_list_end = min(offset + 2 + name_list_length, offset + extension_length)
            while cursor + 3 <= name_list_end:
                name_type = data[cursor]
                name_length = int.from_bytes(data[cursor + 1 : cursor + 3], "big")
                cursor += 3
                if cursor + name_length > name_list_end:
                    return None
                if name_type == 0:
                    try:
                        return data[cursor : cursor + name_length].decode("ascii", errors="ignore") or None
                    except UnicodeDecodeError:
                        return None
                cursor += name_length
            return None
        offset += extension_length
    return None


def build_tls_mitm_hosts(args) -> set[str]:
    hosts = {item.lower() for item in DEFAULT_TLS_MITM_HOSTS}
    for candidate in [getattr(args, "tls_remote_host", None), *getattr(args, "tls_extra_mitm_host", [])]:
        normalized = str(candidate or "").strip().lower()
        if normalized:
            hosts.add(normalized)
    return hosts


def normalize_tls_server_name(server_name: str | None) -> str:
    return (server_name or "").strip().lower()


def is_world_tls_sni(server_name: str | None) -> bool:
    normalized = normalize_tls_server_name(server_name)
    return bool(normalized) and normalized.startswith("world") and normalized.endswith(".runescape.com")


def is_lobby_tls_sni(server_name: str | None) -> bool:
    normalized = normalize_tls_server_name(server_name)
    return bool(normalized) and normalized.startswith("lobby") and normalized.endswith(".runescape.com")


def is_content_tls_sni(server_name: str | None) -> bool:
    normalized = normalize_tls_server_name(server_name)
    return bool(normalized) and normalized.startswith("content") and normalized.endswith(".runescape.com")


def build_tls_http_route_hosts(args) -> set[str]:
    hosts = {item.lower() for item in DEFAULT_TLS_MITM_HOSTS}
    for candidate in [getattr(args, "tls_remote_host", None), *getattr(args, "tls_extra_mitm_host", [])]:
        normalized = normalize_tls_server_name(candidate)
        if normalized and not is_world_tls_sni(normalized):
            hosts.add(normalized)
    return hosts


def resolve_tls_http_upstream_host(server_name: str | None, args) -> str:
    normalized = normalize_tls_server_name(server_name)
    http_hosts = build_tls_http_route_hosts(args)
    if normalized and (normalized in http_hosts or is_content_tls_sni(normalized)):
        return normalized
    fallback = str(args.tls_remote_host or args.remote_host or "").strip().lower()
    return fallback or normalized


def is_http_tls_sni(server_name: str | None, args) -> bool:
    normalized = normalize_tls_server_name(server_name)
    if not normalized or normalized == "localhost" or is_world_tls_sni(normalized):
        return False
    if is_lobby_tls_sni(normalized) or is_content_tls_sni(normalized):
        return True
    return normalized in build_tls_http_route_hosts(args)


def should_mitm_tls_clienthello(server_name: str | None, args) -> bool:
    return is_http_tls_sni(server_name, args)


def extract_session_id(raw_line: str) -> str | None:
    match = SESSION_PREFIX_RE.match(raw_line)
    if not match:
        return None
    return match.group(1)


def load_known_content_clienthello_sha256(log_dir: Path) -> set[str]:
    fingerprints = {item.lower() for item in DEFAULT_CONTENT_CLIENTHELLO_SHA256}
    try:
        log_paths = sorted(
            log_dir.glob("session-*.log"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:CONTENT_CLIENTHELLO_LOG_SCAN_LIMIT]
    except OSError:
        return fingerprints

    for log_path in log_paths:
        try:
            session_fingerprints: dict[str, str] = {}
            active_session_id: str | None = None
            with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
                for raw_line in handle:
                    session_id = extract_session_id(raw_line)
                    if session_id is not None:
                        active_session_id = session_id
                    if "tls-clienthello-sha256=" in raw_line:
                        fingerprint_session_id = session_id or active_session_id
                        if fingerprint_session_id is None:
                            continue
                        fingerprint = raw_line.split("tls-clienthello-sha256=", 1)[1].split(" ", 1)[0].strip().lower()
                        if fingerprint:
                            session_fingerprints[fingerprint_session_id] = fingerprint
                        continue
                    if "tls-client->remote first-chunk-" not in raw_line:
                        continue
                    if "hex=47 45 54 20" not in raw_line:
                        continue
                    fingerprint = session_fingerprints.get(active_session_id or "")
                    if fingerprint:
                        fingerprints.add(fingerprint)
        except OSError:
            continue
    return fingerprints


def decide_tls_route_from_clienthello(
    server_name: str | None,
    clienthello_sha256: str | None,
    args,
) -> tuple[str | None, str, str]:
    if args.tls_passthrough:
        return TLS_SECURE_GAME_ROUTE, TLS_ROUTE_MODE_PASSTHROUGH, "tls-passthrough"
    normalized = normalize_tls_server_name(server_name)
    if normalized == "localhost":
        # The full ClientHello includes a fresh random per connection, so hashing
        # the whole record is not a stable classifier. Inspect localhost sessions
        # after the TLS handshake instead of guessing and misrouting /ms traffic
        # into the secure-game backend.
        return TLS_HTTP_CONTENT_ROUTE, TLS_ROUTE_MODE_INSPECT, "clienthello-localhost-inspect"
    if is_world_tls_sni(normalized):
        return TLS_SECURE_GAME_ROUTE, TLS_ROUTE_MODE_TERMINATE, "clienthello-world-sni"
    if should_mitm_tls_clienthello(normalized, args):
        return TLS_HTTP_CONTENT_ROUTE, TLS_ROUTE_MODE_MITM, "clienthello-content-sni"
    if server_name:
        return TLS_SECURE_GAME_ROUTE, TLS_ROUTE_MODE_PASSTHROUGH, "clienthello-noncontent-sni"
    return TLS_SECURE_GAME_ROUTE, TLS_ROUTE_MODE_PASSTHROUGH, "clienthello-no-sni"


def looks_like_http_request(data: bytes) -> bool:
    return any(data.startswith(prefix) for prefix in HTTP_METHOD_PREFIXES)


def looks_like_js5_handshake_prefix(data: bytes) -> bool:
    return bool(data) and data.startswith(JS5_HANDSHAKE_PREFIX)


def classify_tls_client_prefix_route(data: bytes) -> str | None:
    if not data:
        return None
    if looks_like_http_request(data):
        return TLS_HTTP_CONTENT_ROUTE
    if any(prefix.startswith(data) for prefix in HTTP_METHOD_PREFIXES):
        return None
    return TLS_SECURE_GAME_ROUTE


def classify_tls_application_data(data: bytes) -> str:
    if looks_like_http_request(data):
        return TLS_HTTP_CONTENT_ROUTE
    return TLS_SECURE_GAME_ROUTE


def decide_tls_first_appdata_route(
    client_data: bytes | None,
    backend_data: bytes | None,
    *,
    timed_out: bool = False,
    eof: bool = False,
) -> tuple[str, str]:
    if client_data:
        if looks_like_http_request(client_data):
            return TLS_HTTP_CONTENT_ROUTE, "client-http"
        return TLS_SECURE_GAME_ROUTE, "client-nonhttp"
    if backend_data:
        return TLS_SECURE_GAME_ROUTE, "backend"
    if timed_out:
        return TLS_SECURE_GAME_ROUTE, "timeout"
    if eof:
        return TLS_SECURE_GAME_ROUTE, "eof"
    return TLS_SECURE_GAME_ROUTE, "timeout"


def resolve_secure_game_target(args, *, decrypted_secure_game: bool) -> tuple[str, int, str]:
    if decrypted_secure_game:
        decrypted_host = getattr(args, "secure_game_decrypted_host", None) or args.remote_host
        decrypted_port = int(getattr(args, "secure_game_decrypted_port", 0) or 0) or int(args.remote_port)
        return decrypted_host, decrypted_port, "plain"
    if not getattr(args, "secure_game_tls_passthrough", False):
        return args.remote_host, args.remote_port, "plain"

    passthrough_host = getattr(args, "secure_game_passthrough_host", None) or args.remote_host
    passthrough_port = int(getattr(args, "secure_game_passthrough_port", 0) or 0) or int(args.remote_port)
    return passthrough_host, passthrough_port, "tls passthrough"


def resolve_tls_retail_connect_host(remote_host: str, remote_port: int) -> str:
    try:
        candidates = socket.getaddrinfo(remote_host, remote_port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return remote_host

    for _, _, _, _, sockaddr in candidates:
        candidate_host = sockaddr[0]
        try:
            if not ipaddress.ip_address(candidate_host).is_loopback:
                return candidate_host
        except ValueError:
            continue
    return remote_host


def configure_server_ssl_context(ssl_context: ssl.SSLContext) -> ssl.SSLContext:
    # Stay as close as possible to Python's default TLS server profile. The
    # broader experimental tuning regressed localhost MITM handshakes that had
    # previously completed successfully with the default context.
    try:
        ssl_context.set_servername_callback(
            lambda sock, server_name, _context: setattr(sock, "_opennxt_sni", server_name)
        )
    except (AttributeError, NotImplementedError, ValueError):
        pass
    return ssl_context


def should_accept_more_sessions(session_id: int, max_sessions: int) -> bool:
    if max_sessions <= 0:
        return True
    return session_id < max_sessions


def should_stop_for_idle_timeout(
    *,
    last_accept: datetime,
    now: datetime,
    idle_timeout_seconds: int,
    session_count: int,
) -> bool:
    if idle_timeout_seconds <= 0 or session_count <= 0:
        return False
    return (now - last_accept).total_seconds() >= idle_timeout_seconds


def filter_presented_chain(additional_certificates):
    filtered = []
    for cert in list(additional_certificates or []):
        subject = getattr(cert, "subject", None)
        issuer = getattr(cert, "issuer", None)
        if subject is not None and issuer is not None and subject == issuer:
            continue
        filtered.append(cert)
    return filtered


def rewrite_http_request(
    data: bytes,
    upstream_host: str,
    *,
    original_host: str | None = None,
) -> tuple[bytes, bool]:
    if not upstream_host or not looks_like_http_request(data):
        return data, False
    header_end = data.find(HTTP_HEADER_TERMINATOR)
    if header_end < 0:
        return data, False

    header_blob = data[:header_end].decode("latin1", errors="ignore")
    remainder = data[header_end + len(HTTP_HEADER_TERMINATOR) :]
    header_lines = header_blob.split("\r\n")
    if not header_lines:
        return data, False

    rewritten_lines = [header_lines[0]]
    saw_host = False
    saw_connection = False
    saw_original_host = False
    changed = False
    normalized_upstream = normalize_tls_server_name(upstream_host)
    normalized_original_host = normalize_tls_server_name(original_host)
    should_preserve_original_host = (
        normalized_original_host is not None
        and normalized_original_host != normalized_upstream
    )

    for line in header_lines[1:]:
        lower = line.lower()
        if lower.startswith("host:"):
            saw_host = True
            desired = f"Host: {upstream_host}"
            rewritten_lines.append(desired)
            changed = changed or line != desired
            continue
        if lower.startswith("connection:"):
            saw_connection = True
            rewritten_lines.append(line)
            continue
        if lower.startswith(f"{ORIGINAL_HOST_HEADER.lower()}:"):
            saw_original_host = True
            if should_preserve_original_host:
                desired = f"{ORIGINAL_HOST_HEADER}: {normalized_original_host}"
                rewritten_lines.append(desired)
                changed = changed or line != desired
            else:
                changed = True
            continue
        rewritten_lines.append(line)

    if not saw_host:
        rewritten_lines.append(f"Host: {upstream_host}")
        changed = True
    if not saw_connection:
        rewritten_lines.append("Connection: keep-alive")
        changed = True
    if should_preserve_original_host and not saw_original_host:
        rewritten_lines.append(f"{ORIGINAL_HOST_HEADER}: {normalized_original_host}")
        changed = True

    rewritten = "\r\n".join(rewritten_lines).encode("latin1") + HTTP_HEADER_TERMINATOR + remainder
    return rewritten, changed


def record_chunk(lines, prefix, byte_counter, first_chunks, lock, data: bytes) -> None:
    with lock:
        byte_counter[0] += len(data)
        first_chunks[0] += 1
        chunk_index = first_chunks[0]
        chunk_preview_limit = 60 if prefix.startswith("raw-") or prefix.startswith("remote->raw-") else 5
        if chunk_index <= chunk_preview_limit:
            lines.append(
                f"{prefix} first-chunk-{chunk_index} bytes={len(data)} hex={preview_hex(data)}"
            )
        elif len(data) >= 1024:
            lines.append(f"{prefix} chunk={len(data)}")


def send_buffered_data(dst, data: bytes, lines, prefix, byte_counter, first_chunks, lock) -> None:
    if not data:
        return
    record_chunk(lines, prefix, byte_counter, first_chunks, lock, data)
    dst.sendall(data)


def should_disable_pump_timeouts(mode: str, session_route: str | None) -> bool:
    return mode == "raw" or session_route == TLS_SECURE_GAME_ROUTE


def disable_stream_timeouts_for_pump(*streams) -> None:
    for stream in streams:
        if stream is None:
            continue
        try:
            stream.settimeout(None)
        except (AttributeError, OSError):
            continue


def pump(src, dst, lines, prefix, byte_counter, first_chunks, lock, shutdown_target=True):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            record_chunk(lines, prefix, byte_counter, first_chunks, lock, data)
            dst.sendall(data)
    except OSError as exc:
        with lock:
            lines.append(f"{prefix} error={type(exc).__name__}: {exc}")
    finally:
        if shutdown_target:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def pump_with_byte_cap(
    src,
    dst,
    lines,
    prefix,
    byte_counter,
    first_chunks,
    lock,
    *,
    byte_cap: int,
    linger_before_shutdown_seconds: float = 0.0,
    shutdown_target=True,
):
    cap_reached = False
    try:
        while True:
            remaining = max(byte_cap - byte_counter[0], 0)
            if remaining <= 0:
                cap_reached = True
                break

            data = src.recv(65536)
            if not data:
                break

            if len(data) > remaining:
                data = data[:remaining]
                cap_reached = True

            record_chunk(lines, prefix, byte_counter, first_chunks, lock, data)
            dst.sendall(data)

            if cap_reached or byte_counter[0] >= byte_cap:
                cap_reached = True
                break
    except OSError as exc:
        with lock:
            lines.append(f"{prefix} error={type(exc).__name__}: {exc}")
    finally:
        if cap_reached:
            with lock:
                lines.append(f"{prefix} byte-cap-reached={byte_cap}")
            if shutdown_target and linger_before_shutdown_seconds > 0:
                time.sleep(max(linger_before_shutdown_seconds, 0.0))
        if shutdown_target:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def parse_http_response_header(data: bytes) -> dict[str, Any] | None:
    if not data.startswith(b"HTTP/"):
        return None
    header_end = data.find(HTTP_HEADER_TERMINATOR)
    if header_end < 0:
        return None

    header_blob = data[:header_end].decode("latin1", errors="ignore")
    header_lines = header_blob.split("\r\n")
    if not header_lines:
        return None

    headers: dict[str, str] = {}
    for line in header_lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    content_length = None
    if "content-length" in headers:
        try:
            content_length = int(headers["content-length"])
        except ValueError:
            content_length = None

    return {
        "statusLine": header_lines[0],
        "headerBytes": header_end + len(HTTP_HEADER_TERMINATOR),
        "contentLength": content_length,
        "headers": headers,
    }


def parse_http_request_header(data: bytes) -> dict[str, Any] | None:
    if not looks_like_http_request(data):
        return None
    header_end = data.find(HTTP_HEADER_TERMINATOR)
    if header_end < 0:
        return None

    header_blob = data[:header_end].decode("latin1", errors="ignore")
    header_lines = header_blob.split("\r\n")
    if not header_lines:
        return None

    request_line = header_lines[0]
    parts = request_line.split(" ", 2)
    if len(parts) < 3:
        return None

    headers: dict[str, str] = {}
    for line in header_lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()

    content_length = 0
    if "content-length" in headers:
        try:
            content_length = max(int(headers["content-length"]), 0)
        except ValueError:
            content_length = 0

    return {
        "requestLine": request_line,
        "method": parts[0],
        "path": parts[1],
        "version": parts[2],
        "headerBytes": header_end + len(HTTP_HEADER_TERMINATOR),
        "contentLength": content_length,
        "expectedTotalBytes": header_end + len(HTTP_HEADER_TERMINATOR) + content_length,
        "headers": headers,
    }


class HttpResponseProgress:
    def __init__(self) -> None:
        self._header_buffer = bytearray()
        self.status_line: str | None = None
        self.header_bytes: int | None = None
        self.content_length: int | None = None
        self.total_bytes = 0

    def observe(self, data: bytes) -> dict[str, Any] | None:
        self.total_bytes += len(data)
        if self.header_bytes is not None:
            return None
        self._header_buffer.extend(data)
        parsed = parse_http_response_header(bytes(self._header_buffer))
        if parsed is None:
            return None
        self.status_line = parsed["statusLine"]
        self.header_bytes = parsed["headerBytes"]
        self.content_length = parsed["contentLength"]
        return parsed

    def expected_total_bytes(self) -> int | None:
        if self.header_bytes is None or self.content_length is None:
            return None
        return self.header_bytes + self.content_length

    def is_complete(self) -> bool:
        expected = self.expected_total_bytes()
        return expected is not None and self.total_bytes >= expected

    def finish(self, *, stream_closed: bool, error: Exception | None = None) -> dict[str, Any]:
        expected_total = self.expected_total_bytes()
        truncated = expected_total is not None and self.total_bytes < expected_total
        return {
            "statusLine": self.status_line,
            "headerBytes": self.header_bytes,
            "contentLength": self.content_length,
            "expectedTotalBytes": expected_total,
            "totalBytes": self.total_bytes,
            "complete": expected_total is not None and self.total_bytes >= expected_total,
            "truncated": truncated,
            "streamClosed": stream_closed,
            "error": f"{type(error).__name__}: {error}" if error is not None else None,
        }


class HttpResponseSequenceTracker:
    def __init__(self) -> None:
        self._pending = bytearray()
        self._current_index = 0
        self._current_status_line: str | None = None
        self._current_header_bytes: int | None = None
        self._current_content_length: int | None = None
        self._current_expected_total: int | None = None

    def observe(self, data: bytes) -> list[dict[str, Any]]:
        if data:
            self._pending.extend(data)

        events: list[dict[str, Any]] = []
        while True:
            if self._current_header_bytes is None:
                parsed = parse_http_response_header(bytes(self._pending))
                if parsed is None:
                    break
                self._current_index += 1
                self._current_status_line = parsed["statusLine"]
                self._current_header_bytes = parsed["headerBytes"]
                self._current_content_length = parsed["contentLength"]
                self._current_expected_total = None
                if self._current_content_length is not None:
                    self._current_expected_total = self._current_header_bytes + self._current_content_length
                events.append(
                    {
                        "type": "header",
                        "responseIndex": self._current_index,
                        "statusLine": self._current_status_line,
                        "headerBytes": self._current_header_bytes,
                        "contentLength": self._current_content_length,
                    }
                )
                if self._current_expected_total is None:
                    break

            if self._current_expected_total is None or len(self._pending) < self._current_expected_total:
                break

            events.append(
                {
                    "type": "complete",
                    "responseIndex": self._current_index,
                    "statusLine": self._current_status_line,
                    "headerBytes": self._current_header_bytes,
                    "contentLength": self._current_content_length,
                    "expectedTotalBytes": self._current_expected_total,
                    "totalBytes": self._current_expected_total,
                    "complete": True,
                    "truncated": False,
                }
            )
            del self._pending[: self._current_expected_total]
            self._current_status_line = None
            self._current_header_bytes = None
            self._current_content_length = None
            self._current_expected_total = None

        return events

    def finish(self, *, stream_closed: bool, error: Exception | None = None) -> dict[str, Any] | None:
        if self._current_header_bytes is None:
            return None
        total_bytes = len(self._pending)
        truncated = self._current_expected_total is not None and total_bytes < self._current_expected_total
        return {
            "responseIndex": self._current_index,
            "statusLine": self._current_status_line,
            "headerBytes": self._current_header_bytes,
            "contentLength": self._current_content_length,
            "expectedTotalBytes": self._current_expected_total,
            "totalBytes": total_bytes,
            "complete": self._current_expected_total is not None and total_bytes >= self._current_expected_total,
            "truncated": truncated,
            "streamClosed": stream_closed,
            "error": f"{type(error).__name__}: {error}" if error is not None else None,
        }


def forward_initial_raw_bytes(client_stream, remote_stream, initial_peek, lines, prefix, byte_counter, first_chunks, lock):
    if not initial_peek:
        return 0
    initial_data = client_stream.recv(len(initial_peek))
    if not initial_data:
        return 0
    remote_stream.sendall(initial_data)
    record_chunk(lines, prefix, byte_counter, first_chunks, lock, initial_data)
    return len(initial_data)


def pump_http_response(src, dst, lines, prefix, byte_counter, first_chunks, lock, shutdown_target=True):
    tracker = HttpResponseSequenceTracker()
    stream_closed = False
    error = None
    try:
        while True:
            data = src.recv(65536)
            if not data:
                stream_closed = True
                break
            record_chunk(lines, prefix, byte_counter, first_chunks, lock, data)
            dst.sendall(data)
            for event in tracker.observe(data):
                with lock:
                    if event["type"] == "header":
                        lines.append(
                            f"{prefix} response-header[{event['responseIndex']}] "
                            f"status={event['statusLine']} contentLength={event['contentLength']} "
                            f"headerBytes={event['headerBytes']}"
                        )
                    elif event["type"] == "complete":
                        lines.append(
                            f"{prefix} response-complete[{event['responseIndex']}]="
                            f"{event['complete']} bytes={event['totalBytes']} "
                            f"expected={event['expectedTotalBytes']}"
                        )
    except OSError as exc:
        error = exc
        with lock:
            lines.append(f"{prefix} error={type(exc).__name__}: {exc}")
    finally:
        summary = tracker.finish(stream_closed=stream_closed, error=error)
        if summary is not None and summary["expectedTotalBytes"] is not None:
            with lock:
                lines.append(
                    f"{prefix} response-complete[{summary['responseIndex']}]={summary['complete']} "
                    f"bytes={summary['totalBytes']} expected={summary['expectedTotalBytes']}"
                )
                if summary["truncated"]:
                    lines.append(
                        f"{prefix} response-truncated[{summary['responseIndex']}] "
                        f"bytes={summary['totalBytes']} expected={summary['expectedTotalBytes']} "
                        f"streamClosed={summary['streamClosed']}"
                    )
        if shutdown_target:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def pump_http_requests(
    src,
    dst,
    lines,
    prefix,
    byte_counter,
    first_chunks,
    lock,
    *,
    upstream_host: str,
    original_host: str | None = None,
    initial_buffer: bytes = b"",
    shutdown_target=True,
):
    pending = bytearray(initial_buffer)
    request_index = 0

    def flush_complete_requests() -> None:
        nonlocal request_index
        while pending:
            parsed = parse_http_request_header(bytes(pending))
            if parsed is None:
                break
            expected_total = parsed["expectedTotalBytes"]
            if len(pending) < expected_total:
                break

            request_index += 1
            request_bytes = bytes(pending[:expected_total])
            del pending[:expected_total]
            rewritten_request, changed = rewrite_http_request(
                request_bytes,
                upstream_host,
                original_host=original_host,
            )

            with lock:
                lines.append(
                    f"{prefix} request-header[{request_index}] "
                    f"line={parsed['requestLine']} contentLength={parsed['contentLength']} "
                    f"headerBytes={parsed['headerBytes']}"
                )
                lines.append(
                    f"{prefix} request-rewritten[{request_index}]={changed} host={upstream_host}"
                )

            record_chunk(lines, prefix, byte_counter, first_chunks, lock, rewritten_request)
            dst.sendall(rewritten_request)

            with lock:
                lines.append(
                    f"{prefix} request-complete[{request_index}]=True "
                    f"bytes={len(rewritten_request)} expected={expected_total}"
                )

    try:
        flush_complete_requests()
        while True:
            data = src.recv(65536)
            if not data:
                break
            pending.extend(data)
            flush_complete_requests()
    except OSError as exc:
        with lock:
            lines.append(f"{prefix} error={type(exc).__name__}: {exc}")
    finally:
        if pending:
            with lock:
                lines.append(f"{prefix} request-pending-bytes={len(pending)}")
        if shutdown_target:
            try:
                dst.shutdown(socket.SHUT_WR)
            except OSError:
                pass


def create_remote_stream(
    mode,
    args,
    *,
    session_route: str | None = None,
    decrypted_secure_game: bool = False,
    session_sni: str | None = None,
    retail_tls_upstream: bool = False,
    raw_retail_js5_upstream: bool = False,
):
    if mode == "tls":
        if session_route == TLS_SECURE_GAME_ROUTE:
            if retail_tls_upstream:
                retail_host = normalize_tls_server_name(session_sni) or args.tls_remote_host or args.remote_host
                retail_port = int(args.tls_remote_port or args.remote_port)
                connect_host = resolve_tls_retail_connect_host(retail_host, retail_port)
                raw_remote = socket.create_connection((connect_host, retail_port), timeout=args.connect_timeout)
                raw_remote.settimeout(args.socket_timeout)
                remote_context = ssl.create_default_context()
                remote_tls = remote_context.wrap_socket(raw_remote, server_hostname=retail_host)
                remote_tls.settimeout(args.socket_timeout)
                remote_target = f"{connect_host}:{retail_port}"
                if connect_host != retail_host:
                    remote_target += f" (sni {retail_host}:{retail_port}; "
                else:
                    remote_target += " ("
                remote_target += f"retail js5 for {session_route})"
                return remote_tls, remote_target
            target_host, target_port, target_mode = resolve_secure_game_target(
                args,
                decrypted_secure_game=decrypted_secure_game,
            )
            raw_remote = socket.create_connection((target_host, target_port), timeout=args.connect_timeout)
            raw_remote.settimeout(args.socket_timeout)
            target = f"{target_host}:{target_port} ({target_mode} for {session_route})"
            return raw_remote, target
        remote_host = args.tls_remote_host or args.remote_host
        if session_route == TLS_HTTP_CONTENT_ROUTE:
            remote_host = resolve_tls_http_upstream_host(session_sni, args)
        connect_host = args.tls_connect_host or remote_host
        remote_port = args.tls_remote_port or args.remote_port
        connect_port = args.tls_connect_port or remote_port
        if args.tls_remote_raw:
            raw_remote = socket.create_connection((connect_host, connect_port), timeout=args.connect_timeout)
            raw_remote.settimeout(args.socket_timeout)
            remote_target = f"{connect_host}:{connect_port}"
            if connect_host != remote_host or connect_port != remote_port:
                remote_target += f" (raw for {remote_host}:{remote_port})"
            return raw_remote, remote_target
        if args.tls_passthrough:
            raw_remote = socket.create_connection((connect_host, connect_port), timeout=args.connect_timeout)
            raw_remote.settimeout(args.socket_timeout)
            remote_target = f"{connect_host}:{connect_port}"
            if connect_host != remote_host or connect_port != remote_port:
                remote_target += f" (tls passthrough for {remote_host}:{remote_port})"
            return raw_remote, remote_target
        raw_remote = socket.create_connection((connect_host, connect_port), timeout=args.connect_timeout)
        raw_remote.settimeout(args.socket_timeout)
        remote_context = ssl.create_default_context()
        remote_tls = remote_context.wrap_socket(raw_remote, server_hostname=remote_host)
        remote_tls.settimeout(args.socket_timeout)
        remote_target = f"{connect_host}:{connect_port}"
        if connect_host != remote_host or connect_port != remote_port:
            remote_target += f" (sni {remote_host}:{remote_port})"
        return remote_tls, remote_target

    if raw_retail_js5_upstream:
        retail_host = normalize_tls_server_name(getattr(args, "tls_remote_host", None)) or args.remote_host
        retail_port = int(getattr(args, "tls_remote_port", 0) or 0) or int(args.remote_port)
        connect_host = resolve_tls_retail_connect_host(retail_host, retail_port)
        raw_remote = socket.create_connection((connect_host, retail_port), timeout=args.connect_timeout)
        raw_remote.settimeout(args.socket_timeout)
        remote_target = f"{connect_host}:{retail_port}"
        if connect_host != retail_host:
            remote_target += f" (raw retail js5 for {retail_host}:{retail_port})"
        else:
            remote_target += " (raw retail js5)"
        return raw_remote, remote_target

    remote_host = args.remote_host
    remote_port = args.remote_port
    raw_remote = socket.create_connection((remote_host, remote_port), timeout=args.connect_timeout)
    raw_remote.settimeout(args.socket_timeout)
    return raw_remote, f"{remote_host}:{remote_port}"


def recv_ready_data(stream) -> bytes | None:
    try:
        return stream.recv(65536)
    except (BlockingIOError, ssl.SSLWantReadError, ssl.SSLWantWriteError):
        return None
    except (ssl.SSLZeroReturnError, ssl.SSLEOFError):
        return b""


def sniff_terminated_tls_route(
    client_stream,
    timeout_seconds: float,
    *,
    allow_retail_js5_upstream: bool = False,
) -> tuple[str, str, bytes]:
    client_payload = b""
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    try:
        previous_client_timeout = client_stream.gettimeout()
    except OSError:
        previous_client_timeout = None

    client_stream.setblocking(False)

    try:
        while True:
            if looks_like_js5_handshake_prefix(client_payload):
                js5_source = "client-js5-retail" if allow_retail_js5_upstream else "client-js5"
                return TLS_SECURE_GAME_ROUTE, js5_source, client_payload
            route = classify_tls_client_prefix_route(client_payload)
            if route == TLS_HTTP_CONTENT_ROUTE:
                return route, "client-http", client_payload
            if route == TLS_SECURE_GAME_ROUTE:
                return route, "client-nonhttp", client_payload

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return TLS_SECURE_GAME_ROUTE, "timeout", client_payload

            ready, _, _ = select.select([client_stream], [], [], remaining)
            if not ready:
                return TLS_SECURE_GAME_ROUTE, "timeout", client_payload

            data = recv_ready_data(client_stream)
            if data == b"":
                if looks_like_js5_handshake_prefix(client_payload):
                    js5_source = "client-js5-retail" if allow_retail_js5_upstream else "client-js5"
                    return TLS_SECURE_GAME_ROUTE, js5_source, client_payload
                route = classify_tls_client_prefix_route(client_payload)
                if route == TLS_HTTP_CONTENT_ROUTE:
                    return route, "client-http", client_payload
                if route == TLS_SECURE_GAME_ROUTE:
                    return route, "client-nonhttp", client_payload
                return TLS_SECURE_GAME_ROUTE, "eof", client_payload
            if data:
                client_payload += data
    finally:
        try:
            client_stream.settimeout(previous_client_timeout)
        except OSError:
            pass


def classify_tls_first_appdata(client_stream, backend_stream, timeout_seconds: float) -> tuple[str, str, bytes, bytes]:
    client_payload = b""
    backend_payload = b""
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    try:
        previous_client_timeout = client_stream.gettimeout()
    except OSError:
        previous_client_timeout = None
    try:
        previous_backend_timeout = backend_stream.gettimeout()
    except OSError:
        previous_backend_timeout = None

    client_stream.setblocking(False)
    backend_stream.setblocking(False)

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                route, source = decide_tls_first_appdata_route(client_payload or None, backend_payload or None, timed_out=True)
                return route, source, client_payload, backend_payload

            ready, _, _ = select.select([client_stream, backend_stream], [], [], remaining)
            if not ready:
                route, source = decide_tls_first_appdata_route(client_payload or None, backend_payload or None, timed_out=True)
                return route, source, client_payload, backend_payload

            if client_stream in ready:
                data = recv_ready_data(client_stream)
                if data == b"":
                    route, source = decide_tls_first_appdata_route(client_payload or None, backend_payload or None, eof=True)
                    return route, source, client_payload, backend_payload
                if data:
                    client_payload += data
                    if looks_like_http_request(client_payload):
                        return TLS_HTTP_CONTENT_ROUTE, "client-http", client_payload, backend_payload

            if backend_stream in ready:
                data = recv_ready_data(backend_stream)
                if data == b"":
                    route, source = decide_tls_first_appdata_route(client_payload or None, backend_payload or None, eof=True)
                    return route, source, client_payload, backend_payload
                if data:
                    backend_payload += data
                    route, source = decide_tls_first_appdata_route(client_payload or None, backend_payload, eof=False)
                    return route, source, client_payload, backend_payload

            if client_payload:
                route, source = decide_tls_first_appdata_route(client_payload, backend_payload or None)
                return route, source, client_payload, backend_payload
    finally:
        try:
            client_stream.settimeout(previous_client_timeout)
        except OSError:
            pass
        try:
            backend_stream.settimeout(previous_backend_timeout)
        except OSError:
            pass


def handle_client(client_sock, session_id, args, output_dir: Path):
    lines = []
    lock = threading.Lock()
    started = datetime.now(timezone.utc).isoformat()
    lines.append(f"session#{session_id} start={started}")
    lines.append(f"session#{session_id} client={client_sock.getpeername()}")
    client_counter = [0]
    server_counter = [0]
    client_chunks = [0]
    server_chunks = [0]

    remote_stream = None
    mode = "unknown"
    session_route = ""
    route_source = ""
    route_mode = ""
    client_stream = client_sock
    tls_clienthello_sni = None
    tls_clienthello_sha256 = None
    deferred_tls_classification = False
    buffered_client_data = b""
    buffered_backend_data = b""

    try:
        client_sock.settimeout(args.socket_timeout)
        initial_peek = client_sock.recv(5, socket.MSG_PEEK)
        mode = "tls" if looks_like_tls_client_hello(initial_peek) else "raw"
        lines.append(f"session#{session_id} mode={mode} initial-peek={preview_hex(initial_peek[:5])}")
        raw_retail_js5_upstream = (
            mode == "raw"
            and looks_like_js5_handshake_prefix(initial_peek)
            and bool(getattr(args, "allow_retail_js5_upstream", False))
            and bool(normalize_tls_server_name(getattr(args, "tls_remote_host", None)))
        )
        if mode == "raw":
            session_route = RAW_GAME_ROUTE
            lines.append(f"session#{session_id} session-route={session_route}")
            if raw_retail_js5_upstream:
                route_source = "raw-js5-retail"
                lines.append(f"session#{session_id} raw-route-source={route_source}")
            elif looks_like_js5_handshake_prefix(initial_peek):
                route_source = "raw-js5-local"
                lines.append(f"session#{session_id} raw-route-source={route_source}")
        if mode == "tls":
            clienthello_peek = peek_tls_client_hello(client_sock)
            tls_clienthello_sni = parse_tls_client_hello_sni(clienthello_peek)
            if clienthello_peek:
                tls_clienthello_sha256 = hashlib.sha256(clienthello_peek).hexdigest()
            initial_peek = clienthello_peek
            session_route, route_mode, route_source = decide_tls_route_from_clienthello(
                tls_clienthello_sni,
                tls_clienthello_sha256,
                args,
            )
            if session_route:
                lines.append(f"session#{session_id} session-route={session_route}")
            lines.append(f"session#{session_id} tls-route-mode={route_mode}")
            lines.append(f"session#{session_id} tls-route-source={route_source}")
            if tls_clienthello_sni is not None:
                lines.append(f"session#{session_id} tls-clienthello-sni={tls_clienthello_sni}")
            if clienthello_peek:
                lines.append(f"session#{session_id} tls-clienthello-bytes={len(clienthello_peek)}")
                lines.append(f"session#{session_id} tls-clienthello-sha256={tls_clienthello_sha256}")
            if route_mode in (TLS_ROUTE_MODE_MITM, TLS_ROUTE_MODE_INSPECT, TLS_ROUTE_MODE_TERMINATE):
                if route_mode != TLS_ROUTE_MODE_TERMINATE:
                    session_route = TLS_HTTP_CONTENT_ROUTE
                lines.append(f"session#{session_id} tls-cert-subject={args.cert_subject}")
                lines.append(f"session#{session_id} tls-cert-issuer={args.cert_issuer}")
                lines.append(f"session#{session_id} tls-cert-thumbprint={args.cert_thumbprint}")
                lines.append(f"session#{session_id} tls-server-wrap=start")
                try:
                    client_stream = args.ssl_context.wrap_socket(client_sock, server_side=True)
                except (ssl.SSLZeroReturnError, ssl.SSLEOFError):
                    lines.append(f"session#{session_id} tls-server-wrap=eof")
                    raise
                except (ssl.SSLError, OSError):
                    lines.append(f"session#{session_id} tls-server-wrap=error")
                    raise
                client_stream.settimeout(args.socket_timeout)
                lines.append(f"session#{session_id} tls-server-wrap=ok")
                lines.append(
                    f"session#{session_id} tls-client-sni={getattr(client_stream, '_opennxt_sni', None)}"
                )
                lines.append(
                    f"session#{session_id} tls-server-handshake=ok cipher={client_stream.cipher()} "
                    f"version={client_stream.version()}"
                )
                if route_mode == TLS_ROUTE_MODE_INSPECT:
                    provisional_stream, provisional_target = create_remote_stream(
                        "tls",
                        args,
                        session_route=TLS_SECURE_GAME_ROUTE,
                        decrypted_secure_game=True,
                        session_sni=tls_clienthello_sni,
                    )
                    try:
                        (
                            session_route,
                            route_source,
                            buffered_client_data,
                            buffered_backend_data,
                        ) = classify_tls_first_appdata(
                            client_stream,
                            provisional_stream,
                            TLS_FIRST_APPDATA_TIMEOUT_SECONDS,
                        )
                    except Exception:
                        try:
                            provisional_stream.close()
                        except OSError:
                            pass
                        raise
                    if session_route == TLS_HTTP_CONTENT_ROUTE:
                        try:
                            provisional_stream.close()
                        except OSError:
                            pass
                    else:
                        remote_stream = provisional_stream
                        remote_target = provisional_target
                    lines.append(f"session#{session_id} session-route={session_route}")
                    lines.append(f"session#{session_id} tls-route-source={route_source}")
                    if session_route == TLS_SECURE_GAME_ROUTE:
                        lines.append(f"session#{session_id} remote-connect=start mode={mode} route={session_route}")
                    deferred_tls_classification = True
                elif route_mode == TLS_ROUTE_MODE_TERMINATE:
                    session_route, route_source, buffered_client_data = sniff_terminated_tls_route(
                        client_stream,
                        TLS_FIRST_APPDATA_TIMEOUT_SECONDS,
                        allow_retail_js5_upstream=bool(getattr(args, "allow_retail_js5_upstream", False)),
                    )
                    lines.append(f"session#{session_id} session-route={session_route}")
                    lines.append(f"session#{session_id} tls-route-source={route_source}")
                    deferred_tls_classification = True
            lines.append(f"session#{session_id} tls-first-appdata-source={route_source}")

        if mode == "tls":
            if remote_stream is None:
                lines.append(f"session#{session_id} remote-connect=start mode={mode} route={session_route}")
                remote_stream, remote_target = create_remote_stream(
                    mode,
                    args,
                    session_route=session_route,
                    decrypted_secure_game=(
                        session_route == TLS_SECURE_GAME_ROUTE
                        and (
                            deferred_tls_classification
                            or route_mode == TLS_ROUTE_MODE_TERMINATE
                        )
                    ),
                    session_sni=tls_clienthello_sni,
                    retail_tls_upstream=(
                        route_source == "client-js5-retail"
                        and bool(getattr(args, "allow_retail_js5_upstream", False))
                    ),
                )
        else:
            lines.append(f"session#{session_id} remote-connect=start mode={mode}")
            remote_stream, remote_target = create_remote_stream(
                mode,
                args,
                session_route=session_route or None,
                session_sni=tls_clienthello_sni,
                raw_retail_js5_upstream=raw_retail_js5_upstream,
            )
            lines.append(f"session#{session_id} remote={remote_target}")
        if mode == "tls" and remote_stream is not None and not any(f"session#{session_id} remote=" in line for line in lines):
            lines.append(f"session#{session_id} remote={remote_target}")
        if mode == "tls" and session_route == TLS_SECURE_GAME_ROUTE and remote_stream is not None:
            lines.append(f"session#{session_id} secure-game-target={remote_target}")

        # On Windows, the raw pre-login socket can stall after MSG_PEEK without ever
        # forwarding the already-buffered bytes. Consume and forward that first chunk
        # explicitly so the backend actually sees the initial handshake.
        if mode == "raw" and initial_peek:
            forward_initial_raw_bytes(
                client_stream,
                remote_stream,
                initial_peek,
                lines,
                f"{mode}-client->remote",
                client_counter,
                client_chunks,
                lock,
            )
        elif mode == "tls" and route_mode == TLS_ROUTE_MODE_PASSTHROUGH and initial_peek:
            forward_initial_raw_bytes(
                client_stream,
                remote_stream,
                initial_peek,
                lines,
                f"{mode}-client->remote",
                client_counter,
                client_chunks,
                lock,
            )
        elif mode == "tls" and deferred_tls_classification and session_route == TLS_SECURE_GAME_ROUTE:
            send_buffered_data(
                remote_stream,
                buffered_client_data,
                lines,
                f"{mode}-client->remote",
                client_counter,
                client_chunks,
                lock,
            )
            send_buffered_data(
                client_stream,
                buffered_backend_data,
                lines,
                f"remote->{mode}-client",
                server_counter,
                server_chunks,
                lock,
            )
        if should_disable_pump_timeouts(mode, session_route):
            disable_stream_timeouts_for_pump(client_stream, remote_stream)
            lines.append(f"session#{session_id} stream-read-timeouts=disabled")
        shutdown_target = not (
            mode == "tls" and session_route == TLS_HTTP_CONTENT_ROUTE and route_mode != TLS_ROUTE_MODE_PASSTHROUGH
        )
        client_pump_target = pump
        client_pump_args = (
            client_stream,
            remote_stream,
            lines,
            f"{mode}-client->remote",
            client_counter,
            client_chunks,
            lock,
            shutdown_target,
        )
        client_pump_kwargs = {}
        if mode == "tls" and session_route == TLS_HTTP_CONTENT_ROUTE and route_mode in (
            TLS_ROUTE_MODE_MITM,
            TLS_ROUTE_MODE_INSPECT,
            TLS_ROUTE_MODE_TERMINATE,
        ):
            http_upstream_host = resolve_tls_http_upstream_host(
                getattr(client_stream, "_opennxt_sni", None) or tls_clienthello_sni,
                args,
            )
            client_pump_target = pump_http_requests
            client_pump_args = (
                client_stream,
                remote_stream,
                lines,
                f"{mode}-client->remote",
                client_counter,
                client_chunks,
                lock,
            )
            client_pump_kwargs = {
                "upstream_host": http_upstream_host,
                "original_host": getattr(client_stream, "_opennxt_sni", None) or tls_clienthello_sni,
                "initial_buffer": buffered_client_data,
                "shutdown_target": shutdown_target,
            }
        if mode == "raw" and getattr(args, "raw_client_byte_cap", 0) > 0:
            client_pump_target = pump_with_byte_cap
            client_pump_args = (
                client_stream,
                remote_stream,
                lines,
                f"{mode}-client->remote",
                client_counter,
                client_chunks,
                lock,
            )
            client_pump_kwargs = {
                "byte_cap": int(args.raw_client_byte_cap),
                "linger_before_shutdown_seconds": float(
                    getattr(args, "raw_client_byte_cap_shutdown_delay_seconds", 0.0)
                ),
                "shutdown_target": True,
            }

        t1 = threading.Thread(
            target=client_pump_target,
            args=client_pump_args,
            kwargs=client_pump_kwargs,
            daemon=True,
        )
        t2 = threading.Thread(
            target=pump_http_response
            if mode == "tls" and session_route == TLS_HTTP_CONTENT_ROUTE and route_mode in (TLS_ROUTE_MODE_MITM, TLS_ROUTE_MODE_INSPECT, TLS_ROUTE_MODE_TERMINATE)
            else pump,
            args=(remote_stream, client_stream, lines, f"remote->{mode}-client", server_counter, server_chunks, lock),
            daemon=True,
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()
    except (ssl.SSLError, OSError) as exc:
        with lock:
            if mode == "tls":
                if not session_route:
                    session_route = TLS_SECURE_GAME_ROUTE
                    lines.append(f"session#{session_id} session-route={session_route}")
                if not route_mode:
                    route_mode = TLS_ROUTE_MODE_PASSTHROUGH
                    lines.append(f"session#{session_id} tls-route-mode={route_mode}")
                if not route_source:
                    route_source = "eof"
                    lines.append(f"session#{session_id} tls-first-appdata-source={route_source}")
                if tls_clienthello_sni is not None:
                    lines.append(f"session#{session_id} tls-clienthello-sni={tls_clienthello_sni}")
                lines.append(
                    f"session#{session_id} tls-client-sni={getattr(client_stream, '_opennxt_sni', None)}"
                )
            lines.append(f"session#{session_id} session-error={type(exc).__name__}: {exc}")
    finally:
        try:
            client_sock.close()
        except OSError:
            pass
        try:
            if remote_stream is not None:
                remote_stream.close()
        except OSError:
            pass

    lines.append(
        f"session#{session_id} bytes {mode}-client->remote={client_counter[0]} remote->{mode}-client={server_counter[0]}"
    )
    lines.append(f"session#{session_id} end={datetime.now(timezone.utc).isoformat()}")
    session_path = output_dir / f"session-{session_id:02d}-{args.timestamp}.log"
    session_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def append_summary_lines(summary_lines: list[str], summary_lock: threading.Lock, session_lines: list[str]) -> None:
    with summary_lock:
        summary_lines.extend(session_lines)
        summary_lines.append("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-host", default="127.0.0.1,::1")
    parser.add_argument("--listen-port", type=int, default=443)
    parser.add_argument("--remote-host", default="127.0.0.1")
    parser.add_argument("--remote-port", type=int, default=43595)
    parser.add_argument("--tls-remote-host", default=None)
    parser.add_argument("--tls-remote-port", type=int, default=0)
    parser.add_argument("--tls-extra-mitm-host", action="append", default=[])
    parser.add_argument("--tls-connect-host", default=None)
    parser.add_argument("--tls-connect-port", type=int, default=0)
    parser.add_argument("--tls-passthrough", action="store_true")
    parser.add_argument("--tls-remote-raw", action="store_true")
    parser.add_argument("--secure-game-passthrough-host", default=None)
    parser.add_argument("--secure-game-passthrough-port", type=int, default=0)
    parser.add_argument("--secure-game-decrypted-host", default=None)
    parser.add_argument("--secure-game-decrypted-port", type=int, default=0)
    parser.add_argument("--pfxfile", required=True)
    parser.add_argument("--pfxpassword", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--max-sessions", type=int, default=0)
    parser.add_argument("--accept-timeout", type=float, default=1.0)
    parser.add_argument("--connect-timeout", type=float, default=5.0)
    parser.add_argument("--socket-timeout", type=float, default=5.0)
    parser.add_argument("--idle-timeout-seconds", type=int, default=1800)
    parser.add_argument("--raw-client-byte-cap", type=int, default=0)
    parser.add_argument("--raw-client-byte-cap-shutdown-delay-seconds", type=float, default=0.0)
    parser.add_argument(
        "--allow-retail-js5-upstream",
        action="store_true",
        help="Opt-in split-brain mode that forwards JS5/bootstrap bytes on this listener to retail instead of the local backend.",
    )
    args = parser.parse_args()
    args.secure_game_tls_passthrough = True

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    args.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    # The old localhost classifier used full ClientHello hashes learned from
    # historical session logs. That approach is no longer used for the active
    # localhost route, so avoid the expensive startup scan that delayed or
    # prevented the :443 listener from binding on large debug directories.
    args.content_clienthello_sha256 = {item.lower() for item in DEFAULT_CONTENT_CLIENTHELLO_SHA256}

    temp_dir = TemporaryDirectory(prefix="opennxt-lobby-tls-")
    atexit.register(temp_dir.cleanup)
    temp_path = Path(temp_dir.name)

    pfx_data = Path(args.pfxfile).read_bytes()
    private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
        pfx_data,
        args.pfxpassword.encode("utf-8"),
    )
    if private_key is None or certificate is None:
        raise RuntimeError(f"Could not load certificate and private key from {args.pfxfile}")
    args.cert_subject = certificate.subject.rfc4514_string()
    args.cert_issuer = certificate.issuer.rfc4514_string()
    args.cert_thumbprint = certificate.fingerprint(hashes.SHA1()).hex().upper()

    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    presented_chain = filter_presented_chain(additional_certificates)
    if presented_chain:
        cert_pem += b"".join(cert.public_bytes(serialization.Encoding.PEM) for cert in presented_chain)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    cert_path = temp_path / "server-cert.pem"
    key_path = temp_path / "server-key.pem"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    args.ssl_context = configure_server_ssl_context(ssl_context)

    summary_lines = []
    summary_lock = threading.Lock()
    session_id = 0
    last_accept = datetime.now(timezone.utc)
    session_threads: list[threading.Thread] = []

    listeners = [create_listener(host, args.listen_port, args.accept_timeout) for host in parse_listen_hosts(args.listen_host)]
    try:
        while should_accept_more_sessions(session_id, args.max_sessions):
            if should_stop_for_idle_timeout(
                last_accept=last_accept,
                now=datetime.now(timezone.utc),
                idle_timeout_seconds=args.idle_timeout_seconds,
                session_count=session_id,
            ):
                summary_lines.append(f"idle-timeout={args.idle_timeout_seconds}s")
                break

            try:
                ready, _, _ = select.select(listeners, [], [], args.accept_timeout)
            except (OSError, ValueError):
                break
            if not ready:
                continue

            try:
                client_sock, _ = ready[0].accept()
            except TimeoutError:
                continue

            last_accept = datetime.now(timezone.utc)
            session_id += 1

            worker = threading.Thread(
                target=lambda sock=client_sock, sid=session_id: append_summary_lines(
                    summary_lines,
                    summary_lock,
                    handle_client(sock, sid, args, output_dir),
                ),
                daemon=False,
            )
            worker.start()
            session_threads.append(worker)
            session_threads = [thread for thread in session_threads if thread.is_alive()]
        if args.max_sessions > 0 and session_id >= args.max_sessions:
            summary_lines.append(f"max-sessions-reached={args.max_sessions}")
    finally:
        for listener in listeners:
            try:
                listener.close()
            except OSError:
                pass
        for worker in session_threads:
            worker.join()

    summary_path = output_dir / f"summary-{args.timestamp}.log"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
