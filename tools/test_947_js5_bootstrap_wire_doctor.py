from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    from tools.run_947_js5_bootstrap_wire_doctor import (
        compare_bytes,
        latest_session_log,
        parse_args,
        parse_send_chunks,
        replay_capture,
        SendChunk,
    )
except ImportError:
    from run_947_js5_bootstrap_wire_doctor import (
        compare_bytes,
        latest_session_log,
        parse_args,
        parse_send_chunks,
        replay_capture,
        SendChunk,
    )


class Js5BootstrapWireDoctorTest(unittest.TestCase):
    def test_parse_send_chunks_extracts_raw_client_chunks(self) -> None:
        text = "\n".join(
            [
                "raw-client->remote first-chunk-1 bytes=5 hex=0f 2a 00 00 03",
                "remote->raw-client first-chunk-1 bytes=1 hex=00",
                "raw-client->remote first-chunk-2 bytes=3 hex=01 ff 00",
            ]
        )

        chunks = parse_send_chunks(text)

        self.assertEqual(["first-chunk-1", "first-chunk-2"], [chunk.label for chunk in chunks])
        self.assertEqual([b"\x0f\x2a\x00\x00\x03", b"\x01\xff\x00"], [chunk.payload for chunk in chunks])

    def test_compare_bytes_reports_exact_match(self) -> None:
        diff = compare_bytes(b"abc", b"abc")

        self.assertEqual("match", diff.state)
        self.assertEqual(3, diff.common_prefix_bytes)
        self.assertIsNone(diff.first_diff_offset)

    def test_compare_bytes_reports_prefix_mismatch(self) -> None:
        diff = compare_bytes(b"abcd", b"ab")

        self.assertEqual("live-prefix-of-local", diff.state)
        self.assertEqual(2, diff.common_prefix_bytes)
        self.assertEqual(2, diff.first_diff_offset)

    def test_parse_args_defaults_local_port_to_backend_js5_listener(self) -> None:
        with mock.patch("sys.argv", ["wire-doctor"]):
            args = parse_args()

        self.assertEqual(43596, args.local_port)

    def test_latest_session_log_prefers_newest_raw_bootstrap_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            newest = log_dir / "session-02.log"
            older_raw = log_dir / "session-01.log"
            newer_non_raw = log_dir / "session-03.log"
            newest.write_text("remote->tls-client first-chunk-1 bytes=1 hex=00\n", encoding="utf-8")
            older_raw.write_text("raw-client->remote first-chunk-1 bytes=1 hex=00\n", encoding="utf-8")
            newer_non_raw.write_text("session without raw bootstrap\n", encoding="utf-8")
            older_raw.touch()
            newest.touch()
            newer_non_raw.touch()

            selected = latest_session_log(log_dir)

        self.assertEqual(older_raw, selected)

    def test_replay_capture_tolerates_windows_connection_abort(self) -> None:
        class FakeSocket:
            def __init__(self) -> None:
                self.sent = bytearray()

            def __enter__(self) -> "FakeSocket":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def settimeout(self, _timeout: float) -> None:
                return None

            def sendall(self, payload: bytes) -> None:
                self.sent.extend(payload)

            def recv(self, _size: int) -> bytes:
                error = OSError("connection aborted")
                error.winerror = 10053
                raise error

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "capture.bin"
            chunks = [SendChunk(label="c1", byte_count=3, payload=b"abc")]
            with mock.patch("socket.create_connection", return_value=FakeSocket()):
                capture = replay_capture(
                    host="127.0.0.1",
                    port=43596,
                    chunks=chunks,
                    recv_timeout_seconds=0.1,
                    inter_chunk_delay_seconds=0.0,
                    output_path=output_path,
                )
            written = output_path.read_bytes()

        self.assertEqual(3, capture.sent_bytes)
        self.assertEqual(0, capture.received_bytes)
        self.assertEqual(b"", written)


if __name__ == "__main__":
    unittest.main()
