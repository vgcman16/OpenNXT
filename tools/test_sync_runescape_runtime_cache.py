from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT = TOOLS_DIR / "sync_runescape_runtime_cache.ps1"
POWERSHELL = Path(os.environ["WINDIR"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


def write_sqlite_reference_table(path: Path) -> None:
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
    if current_size < 12288:
        path.write_bytes(path.read_bytes() + (b"\x00" * (12288 - current_size)))


def write_sqlite_archive_only(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("create table cache_index (key integer primary key, data blob)")
        connection.execute("create table cache (key integer primary key, data blob)")
        connection.execute("insert into cache(key, data) values (1, zeroblob(1))")
        connection.commit()
    finally:
        connection.close()
    current_size = path.stat().st_size
    if current_size < 12288:
        path.write_bytes(path.read_bytes() + (b"\x00" * (12288 - current_size)))


class SyncRuneScapeRuntimeCacheTest(unittest.TestCase):
    def run_script(self, source_dir: Path, runtime_dir: Path, *extra_args: str) -> dict:
        args = [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-SourceCacheDir",
            str(source_dir),
            "-RuntimeCacheDir",
            str(runtime_dir),
        ]
        args.extend(extra_args)
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_copies_missing_and_mismatched_runtime_archives(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            source_two = source_dir / "js5-2.jcache"
            source_three = source_dir / "js5-3.jcache"
            runtime_two = runtime_dir / "js5-2.jcache"
            runtime_three = runtime_dir / "js5-3.jcache"

            source_two.write_bytes(b"source-archive-two-v2")
            source_three.write_bytes(b"source-archive-three-v1")
            runtime_three.write_bytes(b"source-archive-three-v1")
            runtime_two.write_bytes(b"x" * len(b"source-archive-two-v2"))
            os.utime(source_two, (source_two.stat().st_atime, source_two.stat().st_mtime + 5))

            summary = self.run_script(source_dir, runtime_dir)

            self.assertEqual(2, summary["SourceFileCount"])
            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual(1, summary["UnchangedCount"])
            self.assertEqual([2], summary["CopiedArchives"])
            self.assertEqual(b"source-archive-two-v2", runtime_two.read_bytes())
            self.assertEqual(b"source-archive-three-v1", runtime_three.read_bytes())

    def test_check_only_reports_planned_copies_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            (source_dir / "js5-12.jcache").write_bytes(b"source-archive-twelve")
            (runtime_dir / "js5-12.jcache").write_bytes(b"runtime-archive-twelve")

            before_bytes = (runtime_dir / "js5-12.jcache").read_bytes()
            summary = self.run_script(source_dir, runtime_dir, "-CheckOnly")

            self.assertTrue(summary["CheckOnly"])
            self.assertEqual(1, summary["PlannedCopyCount"])
            self.assertEqual(0, summary["CopiedCount"])
            self.assertEqual(["would-copy"], [entry["Action"] for entry in summary["Entries"]])
            self.assertEqual(before_bytes, (runtime_dir / "js5-12.jcache").read_bytes())

    def test_rescues_skipped_bootstrap_stub_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            (source_dir / "js5-2.jcache").write_bytes(b"source-archive-two")
            (runtime_dir / "js5-2.jcache").write_bytes(b"stub")

            summary = self.run_script(
                source_dir,
                runtime_dir,
                "-SeedMissingOnly",
                "-SkipJs5Archives",
                "2",
                "-RescueSkippedBootstrapStubs",
                "-BootstrapStubMaxLength",
                "4",
            )

            self.assertTrue(summary["RescueSkippedBootstrapStubs"])
            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual(1, summary["RescuedCount"])
            self.assertEqual([2], summary["CopiedArchives"])
            self.assertEqual([2], summary["RescuedArchives"])
            self.assertEqual([], summary["SkippedArchives"])
            self.assertEqual(
                ["rescued-hot-stub"],
                [entry["Action"] for entry in summary["Entries"]],
            )
            self.assertEqual(
                b"source-archive-two",
                (runtime_dir / "js5-2.jcache").read_bytes(),
            )

    def test_rescues_skipped_tiny_runtime_copy_by_hash_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            source_payload = b"A" * 128
            runtime_payload = b"B" * 128
            (source_dir / "js5-28.jcache").write_bytes(source_payload)
            (runtime_dir / "js5-28.jcache").write_bytes(runtime_payload)

            summary = self.run_script(
                source_dir,
                runtime_dir,
                "-SeedMissingOnly",
                "-SkipJs5Archives",
                "28",
                "-RescueSkippedBootstrapStubs",
                "-BootstrapStubMaxLength",
                "1024",
            )

            self.assertTrue(summary["RescueSkippedBootstrapStubs"])
            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual(1, summary["RescuedCount"])
            self.assertEqual([28], summary["CopiedArchives"])
            self.assertEqual([28], summary["RescuedArchives"])
            self.assertEqual([], summary["SkippedArchives"])
            self.assertEqual(
                "rescue-skipped-bootstrap-hash-mismatch",
                summary["Entries"][0]["Reason"],
            )
            self.assertEqual(source_payload, (runtime_dir / "js5-28.jcache").read_bytes())

    def test_skipped_archives_preserve_runtime_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            (source_dir / "js5-62.jcache").write_bytes(b"C" * 64)
            (runtime_dir / "js5-62.jcache").write_bytes(b"D" * 64)

            summary = self.run_script(
                source_dir,
                runtime_dir,
                "-SeedMissingOnly",
                "-SkipJs5Archives",
                "62",
            )

            self.assertFalse(summary["ValidateSkippedArchives"])
            self.assertEqual(0, summary["CopiedCount"])
            self.assertEqual(0, summary["ValidatedSkippedCount"])
            self.assertEqual([], summary["CopiedArchives"])
            self.assertEqual([62], summary["SkippedArchives"])
            self.assertEqual(
                ["skipped"],
                [entry["Action"] for entry in summary["Entries"]],
            )
            self.assertEqual(
                b"D" * 64,
                (runtime_dir / "js5-62.jcache").read_bytes(),
            )

    def test_validates_skipped_archives_by_hash_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            (source_dir / "js5-8.jcache").write_bytes(b"A" * 32)
            (runtime_dir / "js5-8.jcache").write_bytes(b"B" * 32)

            summary = self.run_script(
                source_dir,
                runtime_dir,
                "-SeedMissingOnly",
                "-SkipJs5Archives",
                "8",
                "-ValidateSkippedArchives",
            )

            self.assertTrue(summary["ValidateSkippedArchives"])
            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual(1, summary["ValidatedSkippedCount"])
            self.assertEqual([8], summary["ValidatedSkippedArchives"])
            self.assertEqual([8], summary["CopiedArchives"])
            self.assertEqual([], summary["SkippedArchives"])
            self.assertEqual(
                ["validated-skipped-copy"],
                [entry["Action"] for entry in summary["Entries"]],
            )
            self.assertEqual(
                "validate-skipped-hash-mismatch",
                summary["Entries"][0]["Reason"],
            )
            self.assertEqual(
                b"A" * 32,
                (runtime_dir / "js5-8.jcache").read_bytes(),
            )

    def test_copies_large_runtime_archive_missing_reference_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            source_path = source_dir / "js5-12.jcache"
            runtime_path = runtime_dir / "js5-12.jcache"
            write_sqlite_reference_table(source_path)
            write_sqlite_archive_only(runtime_path)

            summary = self.run_script(source_dir, runtime_dir)

            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual([12], summary["CopiedArchives"])
            self.assertEqual(
                ["copied"],
                [entry["Action"] for entry in summary["Entries"]],
            )
            self.assertIn(
                summary["Entries"][0]["Reason"],
                {"missing-reference-table", "hash-mismatch"},
            )

            connection = sqlite3.connect(runtime_path)
            try:
                cache_index_rows = connection.execute("select count(*) from cache_index").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(1, cache_index_rows)

    def test_validates_large_skipped_archive_missing_reference_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            source_path = source_dir / "js5-57.jcache"
            runtime_path = runtime_dir / "js5-57.jcache"
            write_sqlite_reference_table(source_path)
            write_sqlite_archive_only(runtime_path)

            summary = self.run_script(
                source_dir,
                runtime_dir,
                "-SeedMissingOnly",
                "-SkipJs5Archives",
                "57",
                "-ValidateSkippedArchives",
            )

            self.assertTrue(summary["ValidateSkippedArchives"])
            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual([57], summary["ValidatedSkippedArchives"])
            self.assertIn(
                summary["Entries"][0]["Reason"],
                {"validate-skipped-missing-reference-table", "validate-skipped-hash-mismatch"},
            )

            connection = sqlite3.connect(runtime_path)
            try:
                cache_index_rows = connection.execute("select count(*) from cache_index").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(1, cache_index_rows)

    def test_copies_small_runtime_cache_when_reference_table_row_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "source"
            runtime_dir = temp_path / "runtime"
            source_dir.mkdir()
            runtime_dir.mkdir()

            source_path = source_dir / "js5-28.jcache"
            runtime_path = runtime_dir / "js5-28.jcache"
            write_sqlite_reference_table(source_path)
            write_sqlite_archive_only(runtime_path)

            summary = self.run_script(source_dir, runtime_dir)

            self.assertEqual(1, summary["CopiedCount"])
            self.assertEqual([28], summary["CopiedArchives"])
            self.assertIn(summary["Entries"][0]["Reason"], {"missing-reference-table", "hash-mismatch"})

            connection = sqlite3.connect(runtime_path)
            try:
                cache_index_rows = connection.execute("select count(*) from cache_index").fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(1, cache_index_rows)


if __name__ == "__main__":
    unittest.main()
