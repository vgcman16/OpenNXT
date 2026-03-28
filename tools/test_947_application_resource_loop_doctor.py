from __future__ import annotations

import unittest

try:
    from tools.run_947_application_resource_loop_doctor import (
        find_repeating_suffix,
        parse_recent_reference_requests,
        select_latest_loop_session,
    )
    from tools.run_947_logged_out_js5_session_doctor import Js5Request
except ImportError:
    from run_947_application_resource_loop_doctor import (  # type: ignore
        find_repeating_suffix,
        parse_recent_reference_requests,
        select_latest_loop_session,
    )
    from run_947_logged_out_js5_session_doctor import Js5Request  # type: ignore


class ApplicationResourceLoopDoctorTest(unittest.TestCase):
    def make_request(self, archive: int, line_number: int, occurrence: int) -> Js5Request:
        return Js5Request(
            line_number=line_number,
            request_id=line_number,
            remote="/127.0.0.1:10001",
            opcode=1,
            priority=True,
            nxt=False,
            build=947,
            occurrence=occurrence,
            kind="reference-table",
            index=255,
            archive=archive,
            available=True,
        )

    def test_find_repeating_suffix_detects_minimal_cycle(self) -> None:
        requests = []
        line = 1
        for repeat in range(4):
            for archive in (2, 3, 12):
                requests.append(self.make_request(archive, line, repeat + 1))
                line += 1

        cycle = find_repeating_suffix(requests, min_cycle_length=2, max_cycle_length=8, min_repeats=3)

        self.assertIsNotNone(cycle)
        assert cycle is not None
        self.assertEqual(3, cycle.cycle_length)
        self.assertEqual(4, cycle.repeat_count)
        self.assertEqual([2, 3, 12], [request.archive for request in cycle.requests])
        self.assertEqual(0, cycle.tail_skew)

    def test_find_repeating_suffix_detects_cycle_with_partial_tail_boundary(self) -> None:
        requests = []
        line = 1
        for archive in (17, 18):
            requests.append(self.make_request(archive, line, 1))
            line += 1
        for repeat in range(3):
            for archive in (2, 3, 12, 16):
                requests.append(self.make_request(archive, line, repeat + 1))
                line += 1
        for archive in (2, 3):
            requests.append(self.make_request(archive, line, 4))
            line += 1

        cycle = find_repeating_suffix(requests, min_cycle_length=2, max_cycle_length=8, min_repeats=3)

        self.assertIsNotNone(cycle)
        assert cycle is not None
        self.assertEqual(4, cycle.cycle_length)
        self.assertEqual(3, cycle.repeat_count)
        self.assertEqual([2, 3, 12, 16], [request.archive for request in cycle.requests])
        self.assertLessEqual(cycle.tail_skew, 2)

    def test_parse_recent_reference_requests_groups_by_remote(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        log_lines = [
            "[x] INFO Queued js5 request #1 from /127.0.0.1:10001: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=2), available=true",
            "[x] INFO Queued js5 request #2 from /127.0.0.1:10002: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=3), available=true",
            "[x] INFO Queued js5 request #3 from /127.0.0.1:10001: opcode=1, priority=true, nxt=false, build=947, occurrence=2, reference-table(index=255, archive=12), available=true",
        ]

        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "server.log"
            log_path.write_text("\n".join(log_lines), encoding="utf-8")
            sessions = parse_recent_reference_requests(log_path, build=947, max_requests_per_remote=8)

        by_remote = {session.remote: session for session in sessions}
        self.assertEqual([2, 12], [request.archive for request in by_remote["/127.0.0.1:10001"].requests])
        self.assertEqual([3], [request.archive for request in by_remote["/127.0.0.1:10002"].requests])

    def test_select_latest_loop_session_prefers_latest_line(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        lines = []
        request_id = 1
        for offset, remote in enumerate(("/127.0.0.1:10001", "/127.0.0.1:10002"), start=0):
            for repeat in range(3):
                for archive in (2, 3, 12):
                    lines.append(
                        f"[x] INFO Queued js5 request #{request_id} from {remote}: opcode=1, priority=true, nxt=false, build=947, occurrence={repeat + 1}, reference-table(index=255, archive={archive}), available=true"
                    )
                    request_id += 1
            if offset == 0:
                lines.append(
                    f"[x] INFO Queued js5 request #{request_id} from {remote}: opcode=1, priority=true, nxt=false, build=947, occurrence=4, reference-table(index=255, archive=99), available=true"
                )
                request_id += 1

        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "server.log"
            log_path.write_text("\n".join(lines), encoding="utf-8")
            sessions = parse_recent_reference_requests(log_path, build=947, max_requests_per_remote=32)

        session, cycle = select_latest_loop_session(sessions, min_cycle_length=2, max_cycle_length=8, min_repeats=3)

        self.assertEqual("/127.0.0.1:10002", session.remote)
        self.assertEqual([2, 3, 12], [request.archive for request in cycle.requests])

    def test_select_latest_loop_session_prefers_recent_skewed_cycle_over_older_aligned_cycle(self) -> None:
        from pathlib import Path
        from tempfile import TemporaryDirectory

        lines = []
        request_id = 1
        older_remote = "/127.0.0.1:10001"
        for repeat in range(3):
            for archive in (2, 3, 12):
                lines.append(
                    f"[x] INFO Queued js5 request #{request_id} from {older_remote}: opcode=1, priority=true, nxt=false, build=947, occurrence={repeat + 1}, reference-table(index=255, archive={archive}), available=true"
                )
                request_id += 1

        newer_remote = "/127.0.0.1:10002"
        for archive in (17, 18):
            lines.append(
                f"[x] INFO Queued js5 request #{request_id} from {newer_remote}: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive={archive}), available=true"
            )
            request_id += 1
        for repeat in range(3):
            for archive in (2, 3, 12, 16):
                lines.append(
                    f"[x] INFO Queued js5 request #{request_id} from {newer_remote}: opcode=1, priority=true, nxt=false, build=947, occurrence={repeat + 1}, reference-table(index=255, archive={archive}), available=true"
                )
                request_id += 1
        for archive in (2, 3):
            lines.append(
                f"[x] INFO Queued js5 request #{request_id} from {newer_remote}: opcode=1, priority=true, nxt=false, build=947, occurrence=4, reference-table(index=255, archive={archive}), available=true"
            )
            request_id += 1

        with TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "server.log"
            log_path.write_text("\n".join(lines), encoding="utf-8")
            sessions = parse_recent_reference_requests(log_path, build=947, max_requests_per_remote=64)

        session, cycle = select_latest_loop_session(sessions, min_cycle_length=2, max_cycle_length=8, min_repeats=3)

        self.assertEqual(newer_remote, session.remote)
        self.assertEqual([2, 3, 12, 16], [request.archive for request in cycle.requests])
        self.assertLessEqual(cycle.tail_skew, 2)


if __name__ == "__main__":
    unittest.main()
