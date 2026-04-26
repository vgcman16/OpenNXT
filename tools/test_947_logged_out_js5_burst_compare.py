from __future__ import annotations

import sys
import unittest
from pathlib import Path

try:
    from tools.run_947_logged_out_js5_burst_compare import (
        BytesSocket,
        attempt_parse_payload,
        compare_raw_bytes,
        select_session_with_minimum_requests,
    )
    from tools.run_947_logged_out_js5_session_doctor import Js5Request, build_request_packet
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_947_logged_out_js5_burst_compare import (
        BytesSocket,
        attempt_parse_payload,
        compare_raw_bytes,
        select_session_with_minimum_requests,
    )
    from run_947_logged_out_js5_session_doctor import Js5Request, build_request_packet


class LoggedOutJs5BurstCompareTests(unittest.TestCase):
    def test_compare_raw_bytes_reports_first_difference_window(self) -> None:
        summary = compare_raw_bytes(bytes.fromhex("0001020304"), bytes.fromhex("0001090304"), window_bytes=1)

        self.assertEqual("mismatch", summary.state)
        self.assertEqual(2, summary.common_prefix_bytes)
        self.assertEqual(2, summary.first_diff_offset)
        self.assertIsNotNone(summary.window)
        assert summary.window is not None
        self.assertEqual("0102", summary.window.local_hex)
        self.assertEqual("0109", summary.window.live_hex)

    def test_compare_raw_bytes_detects_prefix_case(self) -> None:
        summary = compare_raw_bytes(bytes.fromhex("000102"), bytes.fromhex("00010203"))

        self.assertEqual("local-prefix-of-live", summary.state)
        self.assertEqual(3, summary.common_prefix_bytes)
        self.assertEqual(3, summary.first_diff_offset)

    def test_attempt_parse_payload_reports_failure_for_request_bytes(self) -> None:
        request = Js5Request(
            line_number=1,
            request_id=1,
            remote="/127.0.0.1:1",
            opcode=1,
            priority=True,
            nxt=False,
            build=947,
            occurrence=1,
            kind="reference-table",
            index=255,
            archive=26,
            available=True,
        )

        parse = attempt_parse_payload(build_request_packet(request), [request])

        self.assertEqual("parse-failed", parse.state)
        self.assertTrue(parse.error)

    def test_bytes_socket_returns_empty_after_payload_end(self) -> None:
        sock = BytesSocket(b"\x01\x02")

        self.assertEqual(b"\x01", sock.recv(1))
        self.assertEqual(b"\x02", sock.recv(8))
        self.assertEqual(b"", sock.recv(8))

    def test_select_session_with_minimum_requests_prefers_latest_qualified_session(self) -> None:
        small = type("Session", (), {})()
        small.build = 947
        small.logged_out_line = 10
        small.total_request_count = 1
        small.requests = [type("Request", (), {"index": 255})()]

        large = type("Session", (), {})()
        large.build = 947
        large.logged_out_line = 20
        large.total_request_count = 64
        large.requests = [type("Request", (), {"index": 255})()]

        selected = select_session_with_minimum_requests(
            [small, large],
            build=947,
            require_non_255=False,
            min_request_count=32,
        )

        self.assertIs(large, selected)


if __name__ == "__main__":
    unittest.main()
