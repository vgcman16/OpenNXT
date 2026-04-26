from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

try:
    from tools import run_947_logged_out_js5_session_doctor as module
    from tools.run_947_logged_out_js5_session_doctor import (
        DEFAULT_SERVER_LOG_CANDIDATES,
        IllegalStateException,
        Js5Request,
        ReplayRequestState,
        ReplaySummary,
        ResponseHeader,
        ResponseRecord,
        assemble_streamed_responses,
        build_handshake,
        compare_responses,
        iter_log_tail_lines,
        parse_jav_config_token,
        parse_response_header,
        parse_sessions,
        replay_sequence,
        resolve_default_log_path,
        select_latest_logged_out_session,
        select_latest_logged_out_session_with_state,
    )
except ImportError:
    import run_947_logged_out_js5_session_doctor as module
    from run_947_logged_out_js5_session_doctor import (
        DEFAULT_SERVER_LOG_CANDIDATES,
        IllegalStateException,
        Js5Request,
        ReplayRequestState,
        ReplaySummary,
        ResponseHeader,
        ResponseRecord,
        assemble_streamed_responses,
        build_handshake,
        compare_responses,
        iter_log_tail_lines,
        parse_jav_config_token,
        parse_response_header,
        parse_sessions,
        replay_sequence,
        resolve_default_log_path,
        select_latest_logged_out_session,
        select_latest_logged_out_session_with_state,
    )


class LoggedOutJs5SessionDoctorTest(unittest.TestCase):
    def test_parse_jav_config_token_extracts_build_and_token(self) -> None:
        build, token = parse_jav_config_token("server_version=947\nparam=10=abc123\n")

        self.assertEqual(947, build)
        self.assertEqual("abc123", token)

    def test_parse_jav_config_token_prefers_dynamic_session_token(self) -> None:
        build, token = parse_jav_config_token("server_version=947\nparam=10=static123\nparam=29=dynamic456\n")

        self.assertEqual(947, build)
        self.assertEqual("dynamic456", token)

    def test_parse_sessions_and_select_latest_non_255(self) -> None:
        log_text = "\n".join(
            [
                "[x] INFO Decoded js5 handshake for session#7 from /127.0.0.1:10001 with build=947.1",
                "[x] INFO JS5 logged out state from /127.0.0.1:10001 for build=947",
                "[x] INFO Queued js5 request #1 from /127.0.0.1:10001: opcode=33, priority=true, nxt=true, build=947, occurrence=1, reference-table(index=255, archive=12), available=true",
                "[x] INFO Decoded js5 handshake for session#8 from /127.0.0.1:10002 with build=947.1",
                "[x] INFO JS5 logged out state from /127.0.0.1:10002 for build=947",
                "[x] INFO Queued js5 request #2 from /127.0.0.1:10002: opcode=33, priority=true, nxt=true, build=947, occurrence=1, reference-table(index=255, archive=16), available=true",
                "[x] INFO Queued js5 request #3 from /127.0.0.1:10002: opcode=32, priority=false, nxt=true, build=947, occurrence=1, archive(index=48, archive=0), available=true",
            ]
        )

        sessions = parse_sessions(log_text)
        session = select_latest_logged_out_session(sessions, build=947, require_non_255=True)

        self.assertEqual("/127.0.0.1:10002", session.remote)
        self.assertEqual(2, len(session.requests))
        self.assertEqual(48, session.requests[-1].index)

    def test_select_latest_logged_out_session_falls_back_to_handshake_only_sessions(self) -> None:
        log_text = "\n".join(
            [
                "[x] INFO Decoded js5 handshake for session#9 from /127.0.0.1:10003 with build=947.1",
                "[x] INFO Queued js5 request #4 from /127.0.0.1:10003: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=2), available=true",
                "[x] INFO Queued js5 request #5 from /127.0.0.1:10003: opcode=32, priority=false, nxt=true, build=947, occurrence=1, archive(index=48, archive=0), available=true",
            ]
        )

        sessions = parse_sessions(log_text)
        session = select_latest_logged_out_session(sessions, build=947, require_non_255=True)

        self.assertEqual("/127.0.0.1:10003", session.remote)
        self.assertIsNone(session.logged_out_line)
        self.assertEqual(2, len(session.requests))

    def test_select_latest_logged_out_session_falls_back_to_request_only_sessions(self) -> None:
        log_text = "\n".join(
            [
                "[x] INFO Queued js5 request #6 from /127.0.0.1:10004: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=2), available=true",
                "[x] INFO Queued js5 request #7 from /127.0.0.1:10004: opcode=32, priority=false, nxt=true, build=947, occurrence=1, archive(index=48, archive=1), available=true",
            ]
        )

        sessions = parse_sessions(log_text)
        session = select_latest_logged_out_session(sessions, build=947, require_non_255=True)

        self.assertEqual("/127.0.0.1:10004", session.remote)
        self.assertIsNone(session.handshake_line)
        self.assertIsNone(session.logged_out_line)
        self.assertEqual(2, len(session.requests))

    def test_select_latest_logged_out_session_with_state_falls_back_to_255_only(self) -> None:
        log_text = "\n".join(
            [
                "[x] INFO Decoded js5 handshake for session#10 from /127.0.0.1:10005 with build=947.1",
                "[x] INFO JS5 logged out state from /127.0.0.1:10005 for build=947",
                "[x] INFO Queued js5 request #8 from /127.0.0.1:10005: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=2), available=true",
                "[x] INFO Queued js5 request #9 from /127.0.0.1:10005: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=3), available=true",
            ]
        )

        sessions = parse_sessions(log_text)
        selection = select_latest_logged_out_session_with_state(
            sessions,
            build=947,
            require_non_255=True,
        )

        self.assertEqual("255-only-fallback", selection.state)
        self.assertEqual("/127.0.0.1:10005", selection.session.remote)

    def test_parse_sessions_accepts_master_reference_table_request(self) -> None:
        log_text = "\n".join(
            [
                "[x] INFO Decoded js5 handshake for session#11 from /127.0.0.1:10006 with build=947.1",
                "[x] INFO JS5 logged out state from /127.0.0.1:10006 for build=947",
                "[x] INFO Queued js5 request #10 from /127.0.0.1:10006: opcode=33, priority=true, nxt=true, build=947, occurrence=1, master-reference-table(index=255, archive=255), available=checksum-table",
            ]
        )

        sessions = parse_sessions(log_text)

        self.assertEqual(1, len(sessions))
        self.assertEqual(1, len(sessions[0].requests))
        self.assertEqual("master-reference-table", sessions[0].requests[0].kind)
        self.assertEqual(255, sessions[0].requests[0].archive)

    def test_parse_response_header_computes_body_length(self) -> None:
        header = parse_response_header(bytes.fromhex("30000000090200000c4e"))

        self.assertEqual(48, header.index)
        self.assertEqual(9, header.archive)
        self.assertEqual(2, header.compression)
        self.assertEqual(3150, header.file_size)
        self.assertEqual(3154, header.body_length)

    def test_uncompressed_response_header_has_no_extra_length_word(self) -> None:
        header = ResponseHeader(index=48, archive=1, priority=False, compression=0, file_size=123)

        self.assertEqual(123, header.body_length)
        self.assertEqual(128, header.container_bytes)

    def test_build_handshake_matches_live_prefix(self) -> None:
        handshake = build_handshake(947, "abcd")

        self.assertEqual(bytes.fromhex("0f0e000003b300000001616263640000"), handshake)

    def test_compare_responses_reports_first_mismatch(self) -> None:
        request = Js5Request(
            line_number=1,
            request_id=1,
            remote="/127.0.0.1:10002",
            opcode=32,
            priority=False,
            nxt=True,
            build=947,
            occurrence=1,
            kind="archive",
            index=48,
            archive=0,
            available=True,
        )
        other_request = Js5Request(
            line_number=2,
            request_id=2,
            remote="/127.0.0.1:10002",
            opcode=32,
            priority=False,
            nxt=True,
            build=947,
            occurrence=1,
            kind="archive",
            index=48,
            archive=1,
            available=True,
        )
        local = [
            ResponseRecord(1, request, ResponseHeader(48, 0, False, 2, 10), 20, "aaa", "00"),
            ResponseRecord(2, other_request, ResponseHeader(48, 1, False, 2, 10), 20, "bbb", "00"),
        ]
        live = [
            ResponseRecord(1, request, ResponseHeader(48, 0, False, 2, 10), 20, "aaa", "00"),
            ResponseRecord(2, other_request, ResponseHeader(48, 1, False, 2, 10), 20, "ccc", "00"),
        ]

        compare = compare_responses(local, live)

        self.assertEqual("response-mismatch", compare.state)
        self.assertEqual(2, compare.first_mismatch_ordinal)
        self.assertEqual({"index": 48, "archive": 1}, compare.first_mismatch_request)

    def test_replay_sequence_falls_back_to_per_request_mode(self) -> None:
        request = Js5Request(
            line_number=1,
            request_id=1,
            remote="/127.0.0.1:10002",
            opcode=1,
            priority=True,
            nxt=False,
            build=947,
            occurrence=1,
            kind="reference-table",
            index=255,
            archive=2,
            available=True,
        )
        fallback_summary = ReplaySummary(
            host="127.0.0.1",
            port=43596,
            handshake_response=0,
            response_count=1,
            total_response_bytes=42,
            combined_sha256="abc",
            first_64_hex="00",
            replay_mode="per-request",
        )
        fallback_response = ResponseRecord(
            ordinal=1,
            request=request,
            header=ResponseHeader(255, 2, True, 0, 3),
            response_size=8,
            sha256="def",
            raw_hex_prefix="00",
        )

        class FakeSocket:
            def __init__(self) -> None:
                self.recv_calls = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def settimeout(self, timeout: float) -> None:
                return None

            def sendall(self, payload: bytes) -> None:
                return None

            def recv(self, size: int) -> bytes:
                self.recv_calls += 1
                return b"\x00" if self.recv_calls == 1 else b""

        with (
            patch.object(module.socket, "create_connection", return_value=FakeSocket()),
            patch.object(module, "assemble_streamed_responses", side_effect=IllegalStateException("boom")),
            patch.object(
                module,
                "replay_requests_individually",
                return_value=(fallback_summary, [fallback_response]),
            ) as replay_individually,
        ):
            summary, responses = replay_sequence(
                host="127.0.0.1",
                port=43596,
                build=947,
                token="abcd",
                requests=[request],
                timeout_seconds=1.0,
            )

        replay_individually.assert_called_once()
        self.assertEqual("per-request", summary.replay_mode)
        self.assertEqual([fallback_response], responses)

    def test_assemble_streamed_responses_handles_interleaved_large_blocks(self) -> None:
        request_small = Js5Request(
            line_number=1,
            request_id=1,
            remote="/127.0.0.1:10002",
            opcode=1,
            priority=True,
            nxt=False,
            build=947,
            occurrence=1,
            kind="reference-table",
            index=255,
            archive=2,
            available=True,
        )
        request_large = Js5Request(
            line_number=2,
            request_id=2,
            remote="/127.0.0.1:10002",
            opcode=1,
            priority=True,
            nxt=False,
            build=947,
            occurrence=1,
            kind="reference-table",
            index=255,
            archive=12,
            available=True,
        )

        small_prefix = bytes([0]) + (3).to_bytes(4, "big")
        small_body = b"abc"
        small_block = bytes([255]) + (2).to_bytes(4, "big") + small_prefix + small_body

        large_file_size = 102400
        large_prefix = bytes([0]) + large_file_size.to_bytes(4, "big")
        large_body_a = b"x" * 102390
        large_body_b = b"y" * 10
        large_first_block = bytes([255]) + (12).to_bytes(4, "big") + large_prefix + large_body_a
        large_second_block = bytes([255]) + (12).to_bytes(4, "big") + large_body_b

        stream = small_block + large_first_block + large_second_block

        class FakeSocket:
            def __init__(self, payload: bytes) -> None:
                self.payload = payload
                self.offset = 0

            def recv(self, size: int) -> bytes:
                if self.offset >= len(self.payload):
                    return b""
                end = min(len(self.payload), self.offset + size)
                chunk = self.payload[self.offset:end]
                self.offset = end
                return chunk

        responses, combined_stream = assemble_streamed_responses(FakeSocket(stream), [request_small, request_large])

        self.assertEqual(2, len(responses))
        self.assertEqual((255, 2), (responses[0].header.index, responses[0].header.archive))
        self.assertEqual((255, 12), (responses[1].header.index, responses[1].header.archive))
        self.assertEqual(len(small_block), responses[0].response_size)
        self.assertEqual(len(large_first_block) + len(large_second_block), responses[1].response_size)
        self.assertEqual(stream, combined_stream)

    def test_iter_log_tail_lines_discards_partial_first_line(self) -> None:
        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "doctor.log"
            log_path.write_text("old-line\nkeep-one\nkeep-two\n", encoding="utf-8", newline="\n")

            tail = "".join(iter_log_tail_lines(log_path, tail_bytes=len("e\nkeep-one\nkeep-two\n")))

        self.assertEqual("keep-one\nkeep-two\n", tail)

    def test_resolve_default_log_path_prefers_newer_existing_manual_log(self) -> None:
        from tools import run_947_logged_out_js5_session_doctor as module

        with TemporaryDirectory() as temp_dir:
            manual = Path(temp_dir) / "tmp-manual-js5.err.log"
            runserver = Path(temp_dir) / "tmp-runserver.err.log"
            runserver.write_text("older\n", encoding="utf-8")
            manual.write_text("newer\n", encoding="utf-8")
            manual.touch()

            original_candidates = module.DEFAULT_SERVER_LOG_CANDIDATES
            try:
                module.DEFAULT_SERVER_LOG_CANDIDATES = (manual, runserver)
                self.assertEqual(manual, module.resolve_default_log_path())
            finally:
                module.DEFAULT_SERVER_LOG_CANDIDATES = original_candidates


if __name__ == "__main__":
    unittest.main()
