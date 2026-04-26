from __future__ import annotations

import sys
import threading
import unittest
import socket
import ssl
from tempfile import TemporaryDirectory
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tls_terminate_proxy import (
    classify_tls_client_prefix_route,
    TLS_HTTP_CONTENT_ROUTE,
    RAW_GAME_ROUTE,
    TLS_ROUTE_MODE_INSPECT,
    TLS_ROUTE_MODE_MITM,
    TLS_ROUTE_MODE_PASSTHROUGH,
    TLS_ROUTE_MODE_TERMINATE,
    TLS_SECURE_GAME_ROUTE,
    classify_tls_application_data,
    decide_tls_route_from_clienthello,
    decide_tls_first_appdata_route,
    HttpResponseProgress,
    HttpResponseSequenceTracker,
    is_http_tls_sni,
    looks_like_js5_handshake_prefix,
    is_world_tls_sni,
    create_remote_stream,
    load_known_content_clienthello_sha256,
    parse_tls_client_hello_sni,
    pump_http_response,
    pump_with_byte_cap,
    resolve_secure_game_target,
    should_accept_more_sessions,
    should_mitm_tls_clienthello,
    configure_server_ssl_context,
    filter_presented_chain,
    forward_initial_raw_bytes,
    looks_like_tls_client_hello,
    parse_listen_hosts,
    parse_http_request_header,
    pump_http_requests,
    rewrite_http_request,
    reset_localhost_requested_world_host_for_tests,
    seed_localhost_requested_world_host,
    resolve_tls_http_upstream_host,
    should_disable_pump_timeouts,
    sniff_terminated_tls_route,
    should_stop_for_idle_timeout,
    socket_family_for_host,
    disable_stream_timeouts_for_pump,
)


class FakeSocket:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.sent = bytearray()
        self.shutdown_calls: list[int] = []
        self.timeout = None
        self.blocking = True

    def recv(self, size: int, *_args) -> bytes:
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        return chunk[:size]

    def sendall(self, data: bytes) -> None:
        self.sent.extend(data)

    def shutdown(self, how: int) -> None:
        self.shutdown_calls.append(how)

    def settimeout(self, value) -> None:
        self.timeout = value

    def gettimeout(self):
        return self.timeout

    def setblocking(self, flag: bool) -> None:
        self.blocking = flag


class FakeCert:
    def __init__(self, subject: str, issuer: str) -> None:
        self.subject = subject
        self.issuer = issuer


def build_client_hello(*, server_name: str | None) -> bytes:
    body = bytearray()
    body.extend(b"\x03\x03")
    body.extend(b"\x00" * 32)
    body.append(0)
    body.extend((2).to_bytes(2, "big"))
    body.extend(b"\x13\x01")
    body.append(1)
    body.append(0)
    extensions = bytearray()
    if server_name is not None:
        encoded_name = server_name.encode("ascii")
        name_entry = b"\x00" + len(encoded_name).to_bytes(2, "big") + encoded_name
        name_list = len(name_entry).to_bytes(2, "big") + name_entry
        extensions.extend(b"\x00\x00")
        extensions.extend(len(name_list).to_bytes(2, "big"))
        extensions.extend(name_list)
    body.extend(len(extensions).to_bytes(2, "big"))
    body.extend(extensions)

    handshake = bytearray()
    handshake.append(0x01)
    handshake.extend(len(body).to_bytes(3, "big"))
    handshake.extend(body)

    record = bytearray()
    record.extend(b"\x16\x03\x03")
    record.extend(len(handshake).to_bytes(2, "big"))
    record.extend(handshake)
    return bytes(record)


class TlsTerminateProxyTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_localhost_requested_world_host_for_tests()

    def test_rewrite_http_request_retargets_host_without_forcing_close(self) -> None:
        original = (
            b"GET /ms?m=0&a=40 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: */*\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(original, "content.runescape.com")

        self.assertTrue(changed)
        self.assertIn(b"Host: content.runescape.com\r\n", rewritten)
        self.assertIn(b"Connection: keep-alive\r\n", rewritten)
        self.assertTrue(rewritten.endswith(b"\r\n\r\n"))

    def test_rewrite_http_request_preserves_existing_connection_header(self) -> None:
        original = (
            b"GET /ms?m=0&a=40 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Connection: keep-alive\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(original, "content.runescape.com")

        self.assertTrue(changed)
        self.assertIn(b"Connection: keep-alive\r\n", rewritten)
        self.assertNotIn(b"Connection: close\r\n", rewritten)

    def test_rewrite_http_request_preserves_original_world_host_when_retargeted(self) -> None:
        original = (
            b"GET /k=5/jav_config.ws HTTP/1.1\r\n"
            b"Host: world31.runescape.com\r\n"
            b"Accept: */*\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(
            original,
            "content.runescape.com",
            original_host="world31.runescape.com",
        )

        self.assertTrue(changed)
        self.assertIn(b"Host: content.runescape.com\r\n", rewritten)
        self.assertIn(b"X-OpenNXT-Original-Host: world31.runescape.com\r\n", rewritten)

    def test_rewrite_http_request_omits_original_host_header_when_not_retargeted(self) -> None:
        original = (
            b"GET /ms?m=0&a=40 HTTP/1.1\r\n"
            b"Host: content.runescape.com\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(
            original,
            "content.runescape.com",
            original_host="content.runescape.com",
        )

        self.assertTrue(changed)
        self.assertNotIn(b"X-OpenNXT-Original-Host:", rewritten)

    def test_rewrite_http_request_uses_requested_world_host_for_localhost_jav_config(self) -> None:
        original = (
            b"GET /k=5/jav_config.ws?requestedWorldHost=world97a.runescape.com&binaryType=6 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: */*\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(
            original,
            "content.runescape.com",
            original_host="localhost",
        )

        self.assertTrue(changed)
        self.assertIn(b"Host: content.runescape.com\r\n", rewritten)
        self.assertIn(b"X-OpenNXT-Original-Host: world97a.runescape.com\r\n", rewritten)
        self.assertNotIn(b"X-OpenNXT-Original-Host: localhost\r\n", rewritten)

    def test_rewrite_http_request_reuses_sticky_world_host_for_followup_localhost_jav_config(self) -> None:
        bootstrap = (
            b"GET /k=5/jav_config.ws?requestedWorldHost=world97a.runescape.com&binaryType=6 HTTP/1.1\r\n"
            b"Host: localhost\r\n\r\n"
        )
        followup = (
            b"GET /k=5/jav_config.ws?userFlow=123&binaryType=6 HTTP/1.1\r\n"
            b"Host: localhost\r\n\r\n"
        )

        rewrite_http_request(
            bootstrap,
            "content.runescape.com",
            original_host="localhost",
        )
        rewritten, changed = rewrite_http_request(
            followup,
            "content.runescape.com",
            original_host="localhost",
        )

        self.assertTrue(changed)
        self.assertIn(b"X-OpenNXT-Original-Host: world97a.runescape.com\r\n", rewritten)

    def test_rewrite_http_request_uses_seeded_world_host_for_first_localhost_jav_config(self) -> None:
        seed_localhost_requested_world_host("world22.runescape.com")
        original = (
            b"GET /k=5/jav_config.ws?userFlow=3039958176800131556&binaryType=6 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: */*\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(
            original,
            "content.runescape.com",
            original_host="localhost",
        )

        self.assertTrue(changed)
        self.assertIn(b"Host: content.runescape.com\r\n", rewritten)
        self.assertIn(b"X-OpenNXT-Original-Host: world22.runescape.com\r\n", rewritten)

    def test_rewrite_http_request_omits_localhost_original_host_for_ms_requests(self) -> None:
        original = (
            b"GET /ms?m=0&a=255&k=947&g=255&c=0&v=0 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: */*\r\n"
            b"\r\n"
        )

        rewritten, changed = rewrite_http_request(
            original,
            "content.runescape.com",
            original_host="localhost",
        )

        self.assertTrue(changed)
        self.assertIn(b"Host: content.runescape.com\r\n", rewritten)
        self.assertNotIn(b"X-OpenNXT-Original-Host:", rewritten)

    def test_rewrite_http_request_leaves_non_http_payload_unchanged(self) -> None:
        payload = bytes.fromhex("170303401800000000")
        rewritten, changed = rewrite_http_request(payload, "content.runescape.com")
        self.assertFalse(changed)
        self.assertEqual(rewritten, payload)

    def test_parse_http_request_header_parses_get_request(self) -> None:
        payload = (
            b"GET /ms?m=0&a=40 HTTP/1.1\r\n"
            b"Host: localhost\r\n"
            b"Accept: */*\r\n"
            b"\r\n"
        )

        parsed = parse_http_request_header(payload)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["method"], "GET")
        self.assertEqual(parsed["path"], "/ms?m=0&a=40")
        self.assertEqual(parsed["contentLength"], 0)
        self.assertEqual(parsed["expectedTotalBytes"], len(payload))

    def test_classify_tls_application_data_routes_http_content(self) -> None:
        payload = b"GET /ms?m=0&a=40 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        self.assertEqual(classify_tls_application_data(payload), TLS_HTTP_CONTENT_ROUTE)

    def test_classify_tls_application_data_routes_non_http_to_secure_game(self) -> None:
        payload = bytes.fromhex("0f000001020304")
        self.assertEqual(classify_tls_application_data(payload), TLS_SECURE_GAME_ROUTE)

    def test_classify_tls_client_prefix_route_keeps_partial_http_prefix_undecided(self) -> None:
        self.assertIsNone(classify_tls_client_prefix_route(b"GE"))
        self.assertIsNone(classify_tls_client_prefix_route(b"POST"))

    def test_classify_tls_client_prefix_route_resolves_http_and_binary(self) -> None:
        self.assertEqual(
            classify_tls_client_prefix_route(b"GET /k=5/jav_config.ws HTTP/1.1\r\n\r\n"),
            TLS_HTTP_CONTENT_ROUTE,
        )
        self.assertEqual(classify_tls_client_prefix_route(bytes.fromhex("0f000001020304")), TLS_SECURE_GAME_ROUTE)

    def test_looks_like_js5_handshake_prefix_matches_first_byte(self) -> None:
        self.assertTrue(looks_like_js5_handshake_prefix(bytes.fromhex("0f000001020304")))
        self.assertFalse(looks_like_js5_handshake_prefix(bytes.fromhex("06000001020304")))
        self.assertFalse(looks_like_js5_handshake_prefix(b""))

    def test_decide_tls_first_appdata_route_prefers_client_http(self) -> None:
        route, source = decide_tls_first_appdata_route(
            b"GET /ms?m=0&a=40 HTTP/1.1\r\n\r\n",
            None,
        )
        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(source, "client-http")

    def test_decide_tls_first_appdata_route_uses_client_nonhttp_for_secure_game(self) -> None:
        route, source = decide_tls_first_appdata_route(bytes.fromhex("0f000001020304"), None)
        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "client-nonhttp")

    def test_decide_tls_first_appdata_route_uses_backend_first_bytes(self) -> None:
        route, source = decide_tls_first_appdata_route(None, bytes.fromhex("01020304"))
        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "backend")

    def test_decide_tls_first_appdata_route_defaults_timeout_to_secure_game(self) -> None:
        route, source = decide_tls_first_appdata_route(None, None, timed_out=True)
        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "timeout")

    def test_sniff_terminated_tls_route_routes_http_request(self) -> None:
        client = FakeSocket([b"GET /k=5/jav_config.ws HTTP/1.1\r\n\r\n"])

        with patch("tls_terminate_proxy.select.select", return_value=([client], [], [])):
            route, source, payload = sniff_terminated_tls_route(client, 0.1)

        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(source, "client-http")
        self.assertTrue(payload.startswith(b"GET /k=5/jav_config.ws"))

    def test_sniff_terminated_tls_route_routes_binary_payload(self) -> None:
        client = FakeSocket([bytes.fromhex("0f000001020304")])

        with patch("tls_terminate_proxy.select.select", return_value=([client], [], [])):
            route, source, payload = sniff_terminated_tls_route(client, 0.1)

        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "client-js5")
        self.assertEqual(payload, bytes.fromhex("0f000001020304"))

    def test_sniff_terminated_tls_route_can_opt_into_retail_js5_source(self) -> None:
        client = FakeSocket([bytes.fromhex("0f000001020304")])

        with patch("tls_terminate_proxy.select.select", return_value=([client], [], [])):
            route, source, payload = sniff_terminated_tls_route(
                client,
                0.1,
                allow_retail_js5_upstream=True,
            )

        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "client-js5-retail")
        self.assertEqual(payload, bytes.fromhex("0f000001020304"))

    def test_sniff_terminated_tls_route_routes_non_js5_binary_payload_locally(self) -> None:
        client = FakeSocket([bytes.fromhex("06000001020304")])

        with patch("tls_terminate_proxy.select.select", return_value=([client], [], [])):
            route, source, payload = sniff_terminated_tls_route(client, 0.1)

        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "client-nonhttp")
        self.assertEqual(payload, bytes.fromhex("06000001020304"))

    def test_sniff_terminated_tls_route_waits_for_partial_http_prefix(self) -> None:
        client = FakeSocket([b"GE", b"T /k=5/jav_config.ws HTTP/1.1\r\n\r\n"])

        with patch(
            "tls_terminate_proxy.select.select",
            side_effect=[([client], [], []), ([client], [], [])],
        ):
            route, source, payload = sniff_terminated_tls_route(client, 0.1)

        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(source, "client-http")
        self.assertEqual(payload, b"GET /k=5/jav_config.ws HTTP/1.1\r\n\r\n")

    def test_sniff_terminated_tls_route_defaults_timeout_to_secure_game(self) -> None:
        client = FakeSocket([])

        with patch("tls_terminate_proxy.select.select", return_value=([], [], [])):
            route, source, payload = sniff_terminated_tls_route(client, 0.1)

        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(source, "timeout")
        self.assertEqual(payload, b"")

    def test_should_disable_pump_timeouts_for_raw_and_secure_game(self) -> None:
        self.assertTrue(should_disable_pump_timeouts("raw", RAW_GAME_ROUTE))
        self.assertTrue(should_disable_pump_timeouts("tls", TLS_SECURE_GAME_ROUTE))
        self.assertFalse(should_disable_pump_timeouts("tls", TLS_HTTP_CONTENT_ROUTE))

    def test_disable_stream_timeouts_for_pump_clears_socket_timeouts(self) -> None:
        client = FakeSocket([])
        remote = FakeSocket([])
        client.settimeout(30.0)
        remote.settimeout(30.0)

        disable_stream_timeouts_for_pump(client, remote)

        self.assertIsNone(client.gettimeout())
        self.assertIsNone(remote.gettimeout())

    def test_tls_detector_distinguishes_tls_from_raw(self) -> None:
        self.assertTrue(looks_like_tls_client_hello(bytes.fromhex("16030300a9")))
        self.assertFalse(looks_like_tls_client_hello(bytes.fromhex("0f00000102")))

    def test_parse_tls_client_hello_sni_extracts_server_name(self) -> None:
        self.assertEqual(parse_tls_client_hello_sni(build_client_hello(server_name="localhost")), "localhost")

    def test_parse_tls_client_hello_sni_returns_none_without_extension(self) -> None:
        self.assertIsNone(parse_tls_client_hello_sni(build_client_hello(server_name=None)))

    def test_should_mitm_tls_clienthello_matches_content_hosts(self) -> None:
        args = SimpleNamespace(tls_remote_host="content.runescape.com", tls_extra_mitm_host=[])
        self.assertTrue(should_mitm_tls_clienthello("content.runescape.com", args))
        self.assertTrue(should_mitm_tls_clienthello("content1.runescape.com", args))
        self.assertTrue(should_mitm_tls_clienthello("rs.config.runescape.com", args))
        self.assertFalse(should_mitm_tls_clienthello(None, args))
        self.assertFalse(should_mitm_tls_clienthello("localhost", args))
        self.assertFalse(should_mitm_tls_clienthello("world5.runescape.com", args))

    def test_should_mitm_tls_clienthello_excludes_world_hosts_even_when_extra_mitm_hosts_include_them(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_extra_mitm_host=["world59.runescape.com", "lobby3.runescape.com"],
        )
        self.assertFalse(should_mitm_tls_clienthello("world59.runescape.com", args))
        self.assertTrue(should_mitm_tls_clienthello("lobby3.runescape.com", args))

    def test_tls_sni_helpers_distinguish_world_and_http_hosts(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_extra_mitm_host=["world59.runescape.com", "lobby3.runescape.com"],
        )
        self.assertTrue(is_world_tls_sni("world59.runescape.com"))
        self.assertFalse(is_world_tls_sni("content.runescape.com"))
        self.assertTrue(is_http_tls_sni("content.runescape.com", args))
        self.assertTrue(is_http_tls_sni("content1.runescape.com", args))
        self.assertTrue(is_http_tls_sni("lobby3.runescape.com", args))
        self.assertFalse(is_http_tls_sni("world59.runescape.com", args))

    def test_resolve_tls_http_upstream_host_prefers_session_sni_for_config_host(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            remote_host="127.0.0.1",
            tls_extra_mitm_host=[],
        )
        self.assertEqual(
            resolve_tls_http_upstream_host("rs.config.runescape.com", args),
            "rs.config.runescape.com",
        )

    def test_resolve_tls_http_upstream_host_prefers_session_sni_for_numbered_content_host(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            remote_host="127.0.0.1",
            tls_extra_mitm_host=[],
        )
        self.assertEqual(
            resolve_tls_http_upstream_host("content1.runescape.com", args),
            "content1.runescape.com",
        )

    def test_resolve_tls_http_upstream_host_falls_back_to_configured_content_host(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            remote_host="127.0.0.1",
            tls_extra_mitm_host=[],
        )
        self.assertEqual(
            resolve_tls_http_upstream_host("world79.runescape.com", args),
            "content.runescape.com",
        )

    def test_decide_tls_route_from_clienthello_routes_localhost_to_inspect(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_passthrough=False,
            content_clienthello_sha256={"abc123"},
        )
        route, mode, source = decide_tls_route_from_clienthello("localhost", "abc123", args)
        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(mode, TLS_ROUTE_MODE_INSPECT)
        self.assertEqual(source, "clienthello-localhost-inspect")

    def test_decide_tls_route_from_clienthello_routes_remote_content_sni_to_mitm(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_passthrough=False,
            content_clienthello_sha256=set(),
        )
        route, mode, source = decide_tls_route_from_clienthello("content.runescape.com", None, args)
        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(mode, TLS_ROUTE_MODE_MITM)
        self.assertEqual(source, "clienthello-content-sni")

    def test_decide_tls_route_from_clienthello_routes_numbered_content_sni_to_mitm(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_passthrough=False,
            content_clienthello_sha256=set(),
        )
        route, mode, source = decide_tls_route_from_clienthello("content1.runescape.com", None, args)
        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(mode, TLS_ROUTE_MODE_MITM)
        self.assertEqual(source, "clienthello-content-sni")

    def test_decide_tls_route_from_clienthello_routes_world_sni_to_secure_game_even_if_extra_host_is_present(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_passthrough=False,
            tls_extra_mitm_host=["world59.runescape.com"],
            content_clienthello_sha256=set(),
        )
        route, mode, source = decide_tls_route_from_clienthello("world59.runescape.com", None, args)
        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(mode, TLS_ROUTE_MODE_TERMINATE)
        self.assertEqual(source, "clienthello-world-sni")

    def test_decide_tls_route_from_clienthello_routes_lobby_sni_to_http_content(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_passthrough=False,
            tls_extra_mitm_host=[],
            content_clienthello_sha256=set(),
        )
        route, mode, source = decide_tls_route_from_clienthello("lobby42.runescape.com", None, args)
        self.assertEqual(route, TLS_HTTP_CONTENT_ROUTE)
        self.assertEqual(mode, TLS_ROUTE_MODE_MITM)
        self.assertEqual(source, "clienthello-content-sni")

    def test_decide_tls_route_from_clienthello_routes_missing_sni_to_secure_game(self) -> None:
        args = SimpleNamespace(
            tls_remote_host="content.runescape.com",
            tls_passthrough=False,
            content_clienthello_sha256=set(),
        )
        route, mode, source = decide_tls_route_from_clienthello(None, None, args)
        self.assertEqual(route, TLS_SECURE_GAME_ROUTE)
        self.assertEqual(mode, TLS_ROUTE_MODE_PASSTHROUGH)
        self.assertEqual(source, "clienthello-no-sni")

    def test_load_known_content_clienthello_sha256_learns_from_successful_get_logs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "session-01-test.log"
            log_path.write_text(
                "\n".join(
                    [
                        "session#1 tls-clienthello-sha256=deadbeef",
                        "session#1 tls-server-wrap=ok",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fingerprints = load_known_content_clienthello_sha256(Path(temp_dir))

        self.assertIn("deadbeef", fingerprints)

    def test_load_known_content_clienthello_sha256_ignores_non_session_logs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            Path(temp_dir, "summary-test.log").write_text(
                "\n".join(
                    [
                        "session#1 tls-clienthello-sha256=badbad",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            fingerprints = load_known_content_clienthello_sha256(Path(temp_dir))

        self.assertNotIn("badbad", fingerprints)

    def test_resolve_secure_game_target_uses_public_tls_port_for_passthrough(self) -> None:
        args = SimpleNamespace(
            remote_host="127.0.0.1",
            remote_port=43596,
            secure_game_tls_passthrough=True,
            secure_game_passthrough_host="127.0.0.1",
            secure_game_passthrough_port=43594,
        )
        host, port, mode = resolve_secure_game_target(args, decrypted_secure_game=False)
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 43594)
        self.assertEqual(mode, "tls passthrough")

    def test_resolve_secure_game_target_keeps_backend_for_decrypted_stream(self) -> None:
        args = SimpleNamespace(
            remote_host="127.0.0.1",
            remote_port=43594,
            secure_game_tls_passthrough=True,
            secure_game_passthrough_host="127.0.0.1",
            secure_game_passthrough_port=43594,
            secure_game_decrypted_host="127.0.0.1",
            secure_game_decrypted_port=43596,
        )
        host, port, mode = resolve_secure_game_target(args, decrypted_secure_game=True)
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 43596)
        self.assertEqual(mode, "plain")

    def test_create_remote_stream_uses_decrypted_secure_game_backend_when_requested(self) -> None:
        args = SimpleNamespace(
            remote_host="127.0.0.1",
            remote_port=43596,
            tls_remote_host="content.runescape.com",
            tls_remote_port=443,
            tls_connect_host="127.0.0.1",
            tls_connect_port=8080,
            tls_remote_raw=True,
            tls_passthrough=False,
            secure_game_tls_passthrough=True,
            secure_game_passthrough_host="127.0.0.1",
            secure_game_passthrough_port=43594,
            secure_game_decrypted_host="127.0.0.1",
            secure_game_decrypted_port=43596,
            connect_timeout=1.0,
            socket_timeout=30.0,
        )
        fake_remote = FakeSocket([])

        with patch("tls_terminate_proxy.socket.create_connection", return_value=fake_remote) as create_connection:
            remote_stream, remote_target = create_remote_stream(
                "tls",
                args,
                session_route=TLS_SECURE_GAME_ROUTE,
                decrypted_secure_game=True,
                session_sni="world79.runescape.com",
            )

        create_connection.assert_called_once_with(("127.0.0.1", 43596), timeout=1.0)
        self.assertIs(remote_stream, fake_remote)
        self.assertEqual(remote_target, "127.0.0.1:43596 (plain for tls-secure-game)")

    def test_create_remote_stream_uses_retail_tls_for_js5_world_session(self) -> None:
        args = SimpleNamespace(
            remote_host="127.0.0.1",
            remote_port=43596,
            tls_remote_host="content.runescape.com",
            tls_remote_port=443,
            tls_connect_host="127.0.0.1",
            tls_connect_port=8080,
            tls_remote_raw=True,
            tls_passthrough=False,
            secure_game_tls_passthrough=True,
            secure_game_passthrough_host="127.0.0.1",
            secure_game_passthrough_port=43594,
            secure_game_decrypted_host="127.0.0.1",
            secure_game_decrypted_port=43596,
            connect_timeout=1.0,
            socket_timeout=30.0,
        )
        fake_raw_remote = FakeSocket([])
        fake_tls_remote = FakeSocket([])
        fake_context = SimpleNamespace(wrap_socket=lambda sock, server_hostname: fake_tls_remote)

        with (
            patch("tls_terminate_proxy.resolve_tls_retail_connect_host", return_value="8.8.8.8") as resolve_connect_host,
            patch("tls_terminate_proxy.socket.create_connection", return_value=fake_raw_remote) as create_connection,
            patch("tls_terminate_proxy.ssl.create_default_context", return_value=fake_context) as create_default_context,
        ):
            remote_stream, remote_target = create_remote_stream(
                "tls",
                args,
                session_route=TLS_SECURE_GAME_ROUTE,
                decrypted_secure_game=True,
                session_sni="world79.runescape.com",
                retail_tls_upstream=True,
            )

        resolve_connect_host.assert_called_once_with("world79.runescape.com", 443)
        create_connection.assert_called_once_with(("8.8.8.8", 443), timeout=1.0)
        create_default_context.assert_called_once()
        self.assertIs(remote_stream, fake_tls_remote)
        self.assertEqual(
            remote_target,
            "8.8.8.8:443 (sni world79.runescape.com:443; retail js5 for tls-secure-game)",
        )

    def test_create_remote_stream_uses_http_backend_for_world_http_route(self) -> None:
        args = SimpleNamespace(
            remote_host="127.0.0.1",
            remote_port=43596,
            tls_remote_host="content.runescape.com",
            tls_remote_port=443,
            tls_connect_host="127.0.0.1",
            tls_connect_port=8080,
            tls_remote_raw=True,
            tls_passthrough=False,
            secure_game_tls_passthrough=True,
            secure_game_passthrough_host="127.0.0.1",
            secure_game_passthrough_port=43594,
            secure_game_decrypted_host="127.0.0.1",
            secure_game_decrypted_port=43596,
            connect_timeout=1.0,
            socket_timeout=30.0,
            tls_extra_mitm_host=[],
        )
        fake_remote = FakeSocket([])

        with patch("tls_terminate_proxy.socket.create_connection", return_value=fake_remote) as create_connection:
            remote_stream, remote_target = create_remote_stream(
                "tls",
                args,
                session_route=TLS_HTTP_CONTENT_ROUTE,
                decrypted_secure_game=False,
                session_sni="world79.runescape.com",
            )

        create_connection.assert_called_once_with(("127.0.0.1", 8080), timeout=1.0)
        self.assertIs(remote_stream, fake_remote)
        self.assertEqual(remote_target, "127.0.0.1:8080 (raw for content.runescape.com:443)")

    def test_create_remote_stream_uses_raw_retail_js5_upstream_when_requested(self) -> None:
        args = SimpleNamespace(
            remote_host="127.0.0.1",
            remote_port=43596,
            tls_remote_host="content.runescape.com",
            tls_remote_port=443,
            tls_connect_host="127.0.0.1",
            tls_connect_port=8080,
            tls_remote_raw=True,
            tls_passthrough=False,
            secure_game_tls_passthrough=True,
            secure_game_passthrough_host="127.0.0.1",
            secure_game_passthrough_port=43594,
            secure_game_decrypted_host="127.0.0.1",
            secure_game_decrypted_port=43596,
            connect_timeout=1.0,
            socket_timeout=30.0,
        )
        fake_remote = FakeSocket([])

        with (
            patch("tls_terminate_proxy.resolve_tls_retail_connect_host", return_value="1.1.1.1") as resolve_connect_host,
            patch("tls_terminate_proxy.socket.create_connection", return_value=fake_remote) as create_connection,
        ):
            remote_stream, remote_target = create_remote_stream(
                "raw",
                args,
                session_route=RAW_GAME_ROUTE,
                raw_retail_js5_upstream=True,
            )

        resolve_connect_host.assert_called_once_with("content.runescape.com", 443)
        create_connection.assert_called_once_with(("1.1.1.1", 443), timeout=1.0)
        self.assertIs(remote_stream, fake_remote)
        self.assertEqual(remote_target, "1.1.1.1:443 (raw retail js5 for content.runescape.com:443)")

    def test_configure_server_ssl_context_returns_same_context(self) -> None:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        configured = configure_server_ssl_context(context)
        self.assertIs(configured, context)

    def test_filter_presented_chain_drops_self_signed_root(self) -> None:
        leaf_intermediate = FakeCert("CN=Leaf Intermediate", "CN=Root")
        root = FakeCert("CN=Root", "CN=Root")
        filtered = filter_presented_chain([leaf_intermediate, root])
        self.assertEqual(filtered, [leaf_intermediate])

    def test_http_response_progress_marks_complete_large_body(self) -> None:
        tracker = HttpResponseProgress()
        tracker.observe(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n1234")
        tracker.observe(b"5678")

        summary = tracker.finish(stream_closed=False)

        self.assertTrue(summary["complete"])
        self.assertFalse(summary["truncated"])
        self.assertEqual(summary["expectedTotalBytes"], summary["totalBytes"])

    def test_http_response_progress_marks_truncated_response(self) -> None:
        tracker = HttpResponseProgress()
        tracker.observe(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n1234")

        summary = tracker.finish(stream_closed=True)

        self.assertFalse(summary["complete"])
        self.assertTrue(summary["truncated"])
        self.assertGreater(summary["expectedTotalBytes"], summary["totalBytes"])

    def test_http_response_sequence_tracker_handles_multiple_keep_alive_responses(self) -> None:
        tracker = HttpResponseSequenceTracker()

        events = tracker.observe(
            b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: keep-alive\r\n\r\nABCD"
            b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: keep-alive\r\n\r\nX"
        )
        events.extend(tracker.observe(b"YZ"))

        self.assertEqual(
            [(event["type"], event["responseIndex"]) for event in events],
            [("header", 1), ("complete", 1), ("header", 2), ("complete", 2)],
        )
        self.assertIsNone(tracker.finish(stream_closed=False))

    def test_pump_http_response_keeps_forwarding_across_multiple_http_responses(self) -> None:
        src = FakeSocket(
            [
                b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: keep-alive\r\n\r\nABCD",
                b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: keep-alive\r\n\r\nXYZ",
            ]
        )
        dst = FakeSocket([])
        lines: list[str] = []
        byte_counter = [0]
        first_chunks = [0]

        pump_http_response(
            src,
            dst,
            lines,
            "remote->tls-client",
            byte_counter,
            first_chunks,
            threading.Lock(),
        )

        self.assertEqual(
            bytes(dst.sent),
            b"HTTP/1.1 200 OK\r\nContent-Length: 4\r\nConnection: keep-alive\r\n\r\nABCD"
            b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\nConnection: keep-alive\r\n\r\nXYZ",
        )
        self.assertIn("remote->tls-client response-complete[1]=True bytes=66 expected=66", lines)
        self.assertIn("remote->tls-client response-complete[2]=True bytes=65 expected=65", lines)

    def test_pump_http_requests_rewrites_initial_buffer_and_keep_alive_followup(self) -> None:
        src = FakeSocket(
            [
                b"Host: localhost\r\n\r\nGET /ms?m=0&a=41 HTTP/1.1\r\nHost: localhost\r\n\r\n",
            ]
        )
        dst = FakeSocket([])
        lines: list[str] = []
        byte_counter = [0]
        first_chunks = [0]

        pump_http_requests(
            src,
            dst,
            lines,
            "tls-client->remote",
            byte_counter,
            first_chunks,
            threading.Lock(),
            upstream_host="content.runescape.com",
            initial_buffer=b"GET /ms?m=0&a=40 HTTP/1.1\r\n",
        )

        sent = bytes(dst.sent)
        self.assertEqual(sent.count(b"Host: content.runescape.com\r\n"), 2)
        self.assertNotIn(b"Host: localhost\r\n", sent)
        self.assertIn("tls-client->remote request-rewritten[1]=True host=content.runescape.com", lines)
        self.assertIn("tls-client->remote request-rewritten[2]=True host=content.runescape.com", lines)
        self.assertTrue(
            any(line.startswith("tls-client->remote request-complete[2]=True") for line in lines)
        )

    def test_forward_initial_raw_bytes_relays_peeked_handshake(self) -> None:
        client = FakeSocket([b"\x0f\x00\x00\x01\x02"])
        remote = FakeSocket([])
        lines: list[str] = []
        byte_counter = [0]
        first_chunks = [0]

        forwarded = forward_initial_raw_bytes(
            client,
            remote,
            b"\x0f\x00\x00\x01\x02",
            lines,
            "raw-client->remote",
            byte_counter,
            first_chunks,
            threading.Lock(),
        )

        self.assertEqual(forwarded, 5)
        self.assertEqual(bytes(remote.sent), b"\x0f\x00\x00\x01\x02")
        self.assertEqual(byte_counter[0], 5)
        self.assertEqual(first_chunks[0], 1)

    def test_pump_with_byte_cap_stops_before_extra_raw_request(self) -> None:
        client = FakeSocket(
            [
                bytes.fromhex("06 00 00 05 00 00 03 b2 d0 ed 03 00 00 05 00 00 03 b2 d0 ed"),
                bytes.fromhex("21 ff 00 00 00 ff 03 b2 d0 ed"),
            ]
        )
        remote = FakeSocket([])
        lines: list[str] = []
        byte_counter = [44]
        first_chunks = [2]

        pump_with_byte_cap(
            client,
            remote,
            lines,
            "raw-client->remote",
            byte_counter,
            first_chunks,
            threading.Lock(),
            byte_cap=64,
        )

        self.assertEqual(bytes(remote.sent), bytes.fromhex("06 00 00 05 00 00 03 b2 d0 ed 03 00 00 05 00 00 03 b2 d0 ed"))
        self.assertEqual(byte_counter[0], 64)
        self.assertIn("raw-client->remote byte-cap-reached=64", lines)

    def test_parse_listen_hosts_supports_dual_loopback(self) -> None:
        self.assertEqual(parse_listen_hosts("127.0.0.1,::1"), ["127.0.0.1", "::1"])

    def test_socket_family_for_host_detects_ipv6(self) -> None:
        self.assertEqual(socket_family_for_host("127.0.0.1"), socket.AF_INET)
        self.assertEqual(socket_family_for_host("::1"), socket.AF_INET6)

    def test_should_accept_more_sessions_supports_unlimited_mode(self) -> None:
        self.assertTrue(should_accept_more_sessions(0, 0))
        self.assertTrue(should_accept_more_sessions(9999, 0))
        self.assertTrue(should_accept_more_sessions(15, -1))
        self.assertTrue(should_accept_more_sessions(15, 16))
        self.assertFalse(should_accept_more_sessions(16, 16))

    def test_should_stop_for_idle_timeout_disables_non_positive_timeout(self) -> None:
        now = datetime.now(timezone.utc)
        last_accept = now - timedelta(hours=12)
        self.assertFalse(
            should_stop_for_idle_timeout(
                last_accept=last_accept,
                now=now,
                idle_timeout_seconds=0,
                session_count=1,
            )
        )
        self.assertFalse(
            should_stop_for_idle_timeout(
                last_accept=last_accept,
                now=now,
                idle_timeout_seconds=-1,
                session_count=1,
            )
        )

    def test_should_stop_for_idle_timeout_requires_elapsed_time_and_sessions(self) -> None:
        now = datetime.now(timezone.utc)
        last_accept = now - timedelta(seconds=5)
        self.assertFalse(
            should_stop_for_idle_timeout(
                last_accept=last_accept,
                now=now,
                idle_timeout_seconds=10,
                session_count=1,
            )
        )
        self.assertFalse(
            should_stop_for_idle_timeout(
                last_accept=last_accept,
                now=now,
                idle_timeout_seconds=1,
                session_count=0,
            )
        )
        self.assertTrue(
            should_stop_for_idle_timeout(
                last_accept=last_accept,
                now=now,
                idle_timeout_seconds=1,
                session_count=1,
            )
        )


if __name__ == "__main__":
    unittest.main()
