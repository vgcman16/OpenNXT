import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = ROOT / "tools" / "sync_runescape_runtime_cache.ps1"
REPAIR_SCRIPT = ROOT / "tools" / "repair_runescape_runtime_hot_cache.ps1"
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")


class RuntimeCacheRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = Path(tempfile.mkdtemp(prefix="runtime-cache-repair-"))
        self.source_dir = self.tempdir / "source"
        self.runtime_dir = self.tempdir / "runtime"
        self.summary_dir = self.tempdir / "summaries"
        self.source_dir.mkdir()
        self.runtime_dir.mkdir()
        self.summary_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tempdir, ignore_errors=True)

    def _run_ps1(self, script: Path, *args: str) -> None:
        result = subprocess.run(
            [
                str(POWERSHELL),
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                *args,
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(
                f"{script.name} failed with exit code {result.returncode}\n"
                f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
            )

    def test_sync_validates_hot_archives_and_repair_moves_them(self) -> None:
        (self.source_dir / "js5-2.jcache").write_bytes(b"source-two")
        (self.source_dir / "js5-3.jcache").write_bytes(b"source-three")
        (self.source_dir / "js5-99.jcache").write_bytes(b"source-ninety-nine")

        sync_summary = self.summary_dir / "sync.json"
        self._run_ps1(
            SYNC_SCRIPT,
            "-SourceCacheDir",
            str(self.source_dir),
            "-RuntimeCacheDir",
            str(self.runtime_dir),
            "-SeedMissingOnly",
            "-SkipJs5Archives",
            "2",
            "-ValidateSkippedArchives",
            "-SummaryOutput",
            str(sync_summary),
            "-NoOutput",
        )

        sync_data = json.loads(sync_summary.read_text(encoding="utf-8-sig"))
        self.assertTrue(sync_data["ValidateSkippedArchives"])
        self.assertEqual(sync_data["CopiedArchives"], [2, 3, 99])
        self.assertEqual(sync_data["ValidatedSkippedArchives"], [2])
        self.assertEqual(sync_data["SkippedArchives"], [])
        self.assertEqual((self.runtime_dir / "js5-2.jcache").read_bytes(), b"source-two")
        self.assertEqual((self.runtime_dir / "js5-3.jcache").read_bytes(), b"source-three")
        self.assertEqual((self.runtime_dir / "js5-99.jcache").read_bytes(), b"source-ninety-nine")

        runtime_hot = self.runtime_dir / "js5-3.jcache"
        runtime_hot.write_bytes(b"runtime-three")
        repair_summary = self.summary_dir / "repair.json"
        self._run_ps1(
            REPAIR_SCRIPT,
            "-RuntimeCacheDir",
            str(self.runtime_dir),
            "-ArchiveIds",
            "3",
            "-SummaryOutput",
            str(repair_summary),
            "-NoOutput",
        )

        repair_data = json.loads(repair_summary.read_text(encoding="utf-8-sig"))
        self.assertEqual(repair_data["MovedCount"], 1)
        self.assertFalse(runtime_hot.exists())
        backup_path = Path(repair_data["MovedFiles"][0]["BackupPath"])
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.read_bytes(), b"runtime-three")


if __name__ == "__main__":
    unittest.main()
