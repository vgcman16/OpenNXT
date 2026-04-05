from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from tools.run_947_bootstrap_packet_doctor import (
        TARGET_PACKET_NAMES,
        analyze_packets,
        infer_likely_blocker,
        load_bootstrap_captures,
        mismatch_flags_for_payload,
        parse_contained_ms_session_log,
        select_captures,
    )
except ImportError:
    from run_947_bootstrap_packet_doctor import (
        TARGET_PACKET_NAMES,
        analyze_packets,
        infer_likely_blocker,
        load_bootstrap_captures,
        mismatch_flags_for_payload,
        parse_contained_ms_session_log,
        select_captures,
    )


class BootstrapPacketDoctorTests(unittest.TestCase):
    def test_parse_contained_ms_session_log_extracts_request_and_body_preview(self) -> None:
        session_text = "\n".join(
            [
                "tls-client->remote request-header[1] line=GET /ms?m=0&a=255&k=947&g=255&c=0&v=0 HTTP/1.1 contentLength=0 headerBytes=92",
                "remote->tls-client first-chunk-1 bytes=57 hex=48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d 0a 43 6f 6e 74 65 6e 74 2d 6c 65 6e 67 74 68 3a 20 34 0d 0a 0d 0a 01 02 03 04",
                "remote->tls-client response-header[1] status=HTTP/1.1 200 OK contentLength=4 headerBytes=38",
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            session_path = Path(tmpdir) / "session-02.log"
            session_path.write_text(session_text, encoding="utf-8")

            evidence = parse_contained_ms_session_log(session_path)

        self.assertEqual("GET /ms?m=0&a=255&k=947&g=255&c=0&v=0 HTTP/1.1", evidence.request_line)
        self.assertEqual("HTTP/1.1 200 OK", evidence.response_status)
        self.assertEqual(4, evidence.response_content_length)
        self.assertEqual("01020304", evidence.response_body_preview_hex)

    def test_load_bootstrap_captures_keeps_target_packet_fields(self) -> None:
        records = [
            {
                "timestamp": "2026-03-28T20:20:00Z",
                "timestampEpochMillis": 123,
                "packet": "CLIENT_BOOTSTRAP_BLOB_28",
                "opcode": 28,
                "payloadSize": 3,
                "payloadHex": "02aabb",
                "previewHex": "02aabb",
                "bootstrapStage": "live-bootstrap",
                "username": "tester",
                "playerIndex": 42,
                "decodeSummary": {"entryCount": 2},
                "expectation": {"shape": "variable"},
                "mismatchFlags": [],
            },
            {
                "timestamp": "2026-03-28T20:20:01Z",
                "timestampEpochMillis": 124,
                "packet": "CLIENT_BOOTSTRAP_CONTROL_50",
                "opcode": 50,
                "payloadSize": 4,
                "payloadHex": "12345678",
                "previewHex": "12345678",
                "bootstrapStage": "live-bootstrap",
                "username": "tester",
                "playerIndex": 42,
                "decodeSummary": {"value": 305419896},
                "expectation": {"expectedSize": 4},
                "mismatchFlags": [],
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "world-bootstrap-packets.jsonl"
            path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

            captures = load_bootstrap_captures(path)

        self.assertEqual([28, 50], [capture.opcode for capture in captures])
        self.assertEqual("tester", captures[0].username)
        self.assertEqual("12345678", captures[1].payload_hex)
        self.assertEqual(TARGET_PACKET_NAMES[50], captures[1].packet)

    def test_missing_packet_reporting_flags_empty_capture_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bootstrap_jsonl = Path(tmpdir) / "world-bootstrap-packets.jsonl"
            bootstrap_jsonl.write_text("", encoding="utf-8")

            source, captures = select_captures(bootstrap_jsonl, None)
            analyses = analyze_packets(captures)

        self.assertEqual("bootstrap-jsonl", source)
        self.assertTrue(all(analysis.missing for analysis in analyses))
        self.assertEqual("missing-bootstrap-packet-captures", infer_likely_blocker(analyses))

    def test_mismatch_detection_flags_wrong_fixed_sizes(self) -> None:
        self.assertEqual(["expected-size-4-got-3"], mismatch_flags_for_payload(50, bytes.fromhex("123456")))
        self.assertEqual(["expected-size-3-got-2"], mismatch_flags_for_payload(82, bytes.fromhex("beef")))
        self.assertEqual([], mismatch_flags_for_payload(28, bytes.fromhex("01ff")))


if __name__ == "__main__":
    unittest.main()
