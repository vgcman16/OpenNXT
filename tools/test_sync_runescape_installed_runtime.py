from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

try:
    from tools.sync_runescape_installed_runtime import resolve_config_url_for_fetch
except ImportError:
    from sync_runescape_installed_runtime import resolve_config_url_for_fetch  # type: ignore


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT = TOOLS_DIR / "sync_runescape_installed_runtime.py"
PYTHON = "python"


class SyncRuneScapeInstalledRuntimeTest(unittest.TestCase):
    def test_public_config_url_resolves_to_local_server_fetch(self) -> None:
        resolved = resolve_config_url_for_fetch(
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&downloadMetadataSource=patched"
        )

        self.assertEqual(
            "http://127.0.0.1:8080/jav_config.ws?binaryType=6&downloadMetadataSource=patched",
            resolved,
        )

    def run_script(
        self,
        config_file: Path,
        local_dir: Path,
        installed_dir: Path,
        *extra_args: str,
    ) -> dict:
        args = [
            PYTHON,
            str(SCRIPT),
            "--config-file",
            str(config_file),
            "--local-dir",
            str(local_dir),
            "--installed-dir",
            str(installed_dir),
        ]
        args.extend(extra_args)
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_copies_mismatched_installed_runtime_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_file = temp_path / "jav_config.ws"
            local_dir = temp_path / "local"
            installed_dir = temp_path / "installed"
            local_dir.mkdir()
            installed_dir.mkdir()

            local_bytes = b"correct-947-child"
            installed_bytes = b"wrong-runtime-child"
            (local_dir / "rs2client.exe").write_bytes(local_bytes)
            (installed_dir / "rs2client.exe").write_bytes(installed_bytes)
            crc = subprocess.run(
                [
                    PYTHON,
                    "-c",
                    (
                        "import sys,zlib;"
                        "data=open(sys.argv[1],'rb').read();"
                        "print(zlib.crc32(data)&0xffffffff)"
                    ),
                    str(local_dir / "rs2client.exe"),
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            config_file.write_text(
                "\n".join(
                    [
                        "download_name_3=rs2client.exe",
                        f"download_crc_3={crc}",
                    ]
                ),
                encoding="utf-8",
            )

            summary = self.run_script(config_file, local_dir, installed_dir)

            self.assertTrue(summary["localReady"])
            self.assertFalse(summary["installedReadyBefore"])
            self.assertTrue(summary["installedReadyAfter"])
            self.assertEqual(1, summary["plannedCopyCount"])
            self.assertEqual(1, summary["copiedCount"])
            self.assertEqual(0, summary["failedCount"])
            self.assertEqual(["rs2client.exe"], summary["copiedFiles"])
            self.assertEqual(local_bytes, (installed_dir / "rs2client.exe").read_bytes())

    def test_check_only_does_not_modify_installed_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_file = temp_path / "jav_config.ws"
            local_dir = temp_path / "local"
            installed_dir = temp_path / "installed"
            local_dir.mkdir()
            installed_dir.mkdir()

            local_bytes = b"correct-libegl"
            installed_bytes = b"wrong-libegl"
            (local_dir / "libEGL.dll").write_bytes(local_bytes)
            (installed_dir / "libEGL.dll").write_bytes(installed_bytes)
            crc = subprocess.run(
                [
                    PYTHON,
                    "-c",
                    (
                        "import sys,zlib;"
                        "data=open(sys.argv[1],'rb').read();"
                        "print(zlib.crc32(data)&0xffffffff)"
                    ),
                    str(local_dir / "libEGL.dll"),
                ],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            config_file.write_text(
                "\n".join(
                    [
                        "download_name_0=libEGL.dll",
                        f"download_crc_0={crc}",
                    ]
                ),
                encoding="utf-8",
            )

            summary = self.run_script(config_file, local_dir, installed_dir, "--check-only")

            self.assertTrue(summary["checkOnly"])
            self.assertEqual(1, summary["plannedCopyCount"])
            self.assertEqual(0, summary["copiedCount"])
            self.assertFalse(summary["installedReadyAfter"])
            self.assertEqual(b"wrong-libegl", (installed_dir / "libEGL.dll").read_bytes())


if __name__ == "__main__":
    unittest.main()
