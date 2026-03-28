from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from OpenNXT.tools.run_947_secure_content_loop_doctor import (
        STUB_CACHE_SIZE,
        build_archive_observations,
        find_repeating_suffix,
        parse_hook,
        resolve_default_hook_path,
    )
except ModuleNotFoundError:
    try:
        from tools.run_947_secure_content_loop_doctor import (
            STUB_CACHE_SIZE,
            build_archive_observations,
            find_repeating_suffix,
            parse_hook,
            resolve_default_hook_path,
        )
    except ModuleNotFoundError:
        from run_947_secure_content_loop_doctor import (  # type: ignore
            STUB_CACHE_SIZE,
            build_archive_observations,
            find_repeating_suffix,
            parse_hook,
            resolve_default_hook_path,
        )


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def write_sqlite_cache(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("create table cache_index (key integer primary key, data blob)")
        connection.execute("create table cache (key integer primary key, data blob)")
        connection.execute("insert into cache_index(key, data) values (1, zeroblob(1))")
        connection.execute("insert into cache(key, data) values (1, zeroblob(1))")
        connection.commit()
    finally:
        connection.close()
    current_size = path.stat().st_size
    if current_size < STUB_CACHE_SIZE:
        with path.open("ab") as handle:
            handle.write(b"\x00" * (STUB_CACHE_SIZE - current_size))


def write_sqlite_archive_only_cache(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("create table cache_index (key integer primary key, data blob)")
        connection.execute("create table cache (key integer primary key, data blob)")
        connection.execute("insert into cache(key, data) values (1, zeroblob(1))")
        connection.commit()
    finally:
        connection.close()
    current_size = path.stat().st_size
    if current_size < STUB_CACHE_SIZE:
        with path.open("ab") as handle:
            handle.write(b"\x00" * (STUB_CACHE_SIZE - current_size))


class SecureContentLoopDoctorTest(unittest.TestCase):
    def test_resolve_default_hook_path_prefers_latest_root_hook(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            attach_dir = root / "attach-older"
            attach_dir.mkdir()
            old_hook = attach_dir / "latest-hooks.jsonl"
            old_hook.write_text("{}", encoding="utf-8")
            latest_root_hook = root / "latest-hooks.jsonl"
            latest_root_hook.write_text("{}", encoding="utf-8")

            resolved = resolve_default_hook_path(root)

        self.assertEqual(latest_root_hook, resolved)

    def test_parse_hook_extracts_secure_requests_and_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            hook_path = root / "hook.jsonl"
            write_jsonl(
                hook_path,
                [
                    {"action": "send", "socket": "4180", "previewHex": "01ff0000000203b3000001ff0000000303b30000"},
                    {"action": "recv", "socket": "4180", "previewHex": "ff00000002010000080e00112233"},
                    {"action": "write", "path": r"C:\ProgramData\Jagex\RuneScape\js5-2.jcache"},
                ],
            )

            requests, responses, touches, socket_counts = parse_hook(hook_path)

        self.assertEqual([2, 3], [request.archive for request in requests])
        self.assertEqual([2], [response.archive for response in responses])
        self.assertEqual([2], [touch.archive for touch in touches])
        self.assertEqual(2, socket_counts["4180"])

    def test_parse_hook_extracts_first_chunk_secure_requests_and_headers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            hook_path = root / "hook.jsonl"
            write_jsonl(
                hook_path,
                [
                    {"action": "send-first-chunk", "socket": "4172", "previewHex": "01ff0000000303b30100"},
                    {"action": "recv-first-chunk", "socket": "4172", "previewHex": "ff000000030100007f7b00112233"},
                ],
            )

            requests, responses, touches, socket_counts = parse_hook(hook_path)

        self.assertEqual([3], [request.archive for request in requests])
        self.assertEqual([3], [response.archive for response in responses])
        self.assertEqual([], touches)
        self.assertEqual(1, socket_counts["4172"])

    def test_find_repeating_suffix_detects_tail_cycle(self) -> None:
        requests = []
        source_line = 1
        for _ in range(4):
            for archive in (2, 3, 12):
                requests.append(
                    type("Request", (), {"archive": archive, "source_line": source_line})()
                )
                source_line += 1

        cycle = find_repeating_suffix(requests, min_cycle_length=2, max_cycle_length=8, min_repeats=3)

        self.assertIsNotNone(cycle)
        assert cycle is not None
        self.assertEqual([2, 3, 12], cycle.archives)
        self.assertEqual(3, cycle.cycle_length)
        self.assertEqual(4, cycle.repeat_count)

    def test_build_archive_observations_flags_stubbed_source_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_cache = root / "source"
            runtime_cache = root / "runtime"
            source_cache.mkdir()
            runtime_cache.mkdir()
            (source_cache / "js5-28.jcache").write_bytes(b"\x00" * STUB_CACHE_SIZE)
            (runtime_cache / "js5-28.jcache").write_bytes(b"\x00" * STUB_CACHE_SIZE)
            (source_cache / "js5-12.jcache").write_bytes(b"\x01" * 16384)
            (runtime_cache / "js5-12.jcache").write_bytes(b"\x01" * 16384)

            requests = [
                type("Request", (), {"archive": 12})(),
                type("Request", (), {"archive": 28})(),
                type("Request", (), {"archive": 28})(),
            ]
            responses = [
                type("Response", (), {"archive": 12, "compression": 1, "length": 2062})(),
                type("Response", (), {"archive": 28, "compression": 2, "length": 4096})(),
            ]
            touches = [
                type("Touch", (), {"archive": 12, "action": "write"})(),
            ]

            observations = build_archive_observations(
                requests=requests,
                responses=responses,
                touches=touches,
                source_cache_dir=source_cache,
                runtime_cache_dir=runtime_cache,
            )

        by_archive = {observation.archive: observation for observation in observations}
        self.assertEqual("present", by_archive[12].source_cache_status)
        self.assertEqual("stub-like", by_archive[28].source_cache_status)
        self.assertEqual("stub-like", by_archive[28].runtime_cache_status)
        self.assertIn("refresh data/cache/js5-28.jcache", by_archive[28].needs)
        self.assertIn("refresh ProgramData runtime js5-28.jcache", by_archive[28].needs)

    def test_build_archive_observations_treats_sqlite_12kb_with_rows_as_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_cache = root / "source"
            runtime_cache = root / "runtime"
            source_cache.mkdir()
            runtime_cache.mkdir()
            write_sqlite_cache(source_cache / "js5-28.jcache")
            write_sqlite_cache(runtime_cache / "js5-28.jcache")

            requests = [type("Request", (), {"archive": 28})()]
            responses = [type("Response", (), {"archive": 28, "compression": 2, "length": 4096})()]
            touches = []

            observations = build_archive_observations(
                requests=requests,
                responses=responses,
                touches=touches,
                source_cache_dir=source_cache,
                runtime_cache_dir=runtime_cache,
            )

        by_archive = {observation.archive: observation for observation in observations}
        self.assertEqual("present", by_archive[28].source_cache_status)
        self.assertEqual("present", by_archive[28].runtime_cache_status)
        self.assertNotIn("refresh data/cache/js5-28.jcache", by_archive[28].needs)
        self.assertNotIn("refresh ProgramData runtime js5-28.jcache", by_archive[28].needs)

    def test_build_archive_observations_flags_archive_only_rows_as_missing_reference_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source_cache = root / "source"
            runtime_cache = root / "runtime"
            source_cache.mkdir()
            runtime_cache.mkdir()
            write_sqlite_archive_only_cache(source_cache / "js5-28.jcache")
            write_sqlite_archive_only_cache(runtime_cache / "js5-28.jcache")

            requests = [type("Request", (), {"archive": 28})()]
            responses = [type("Response", (), {"archive": 28, "compression": 2, "length": 4096})()]
            touches = []

            observations = build_archive_observations(
                requests=requests,
                responses=responses,
                touches=touches,
                source_cache_dir=source_cache,
                runtime_cache_dir=runtime_cache,
            )

        by_archive = {observation.archive: observation for observation in observations}
        self.assertEqual("missing-reference-table", by_archive[28].source_cache_status)
        self.assertEqual("missing-reference-table", by_archive[28].runtime_cache_status)
        self.assertIn("refresh data/cache/js5-28.jcache reference table", by_archive[28].needs)
        self.assertIn("refresh ProgramData runtime js5-28.jcache reference table", by_archive[28].needs)


if __name__ == "__main__":
    unittest.main()
