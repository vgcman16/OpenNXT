from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT = TOOLS_DIR / "set_runescape_launcher_preferences.ps1"
POWERSHELL = Path(os.environ["WINDIR"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class SetRuneScapeLauncherPreferencesTest(unittest.TestCase):
    def run_script(
        self,
        preferences_path: Path,
        *extra_args: str,
        include_default_dont_ask: bool = True,
    ) -> dict:
        args = [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-PreferencesPath",
            str(preferences_path),
            "-Compatibility",
            "true",
        ]
        if include_default_dont_ask:
            args.append("-DontAskAgain")
        args.extend(extra_args)
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def test_updates_existing_compatibility_value(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preferences_path = Path(temp_dir) / "preferences.cfg"
            preferences_path.write_text(
                "\n".join(
                    [
                        "graphics_device=28e0",
                        "compatibility=default",
                        "graphics_version=32.0.15.9579",
                    ]
                ),
                encoding="ascii",
            )

            summary = self.run_script(preferences_path)

            self.assertEqual("true", summary["After"]["Compatibility"])
            self.assertEqual("1", summary["After"]["DontAskGraphics"])
            self.assertIn("compatibility", summary["ChangedKeys"])
            self.assertIn("dont_ask_graphics", summary["ChangedKeys"])
            self.assertIn("compatibility=true", preferences_path.read_text(encoding="ascii"))

    def test_adds_missing_keys_without_dropping_existing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preferences_path = Path(temp_dir) / "preferences.cfg"
            preferences_path.write_text(
                "\n".join(
                    [
                        "graphics_device=28e0",
                        "graphics_version=32.0.15.9579",
                        r"cache_folder=C:\ProgramData\Jagex",
                    ]
                ),
                encoding="ascii",
            )

            summary = self.run_script(preferences_path)
            updated_text = preferences_path.read_text(encoding="ascii")

            self.assertEqual("true", summary["After"]["Compatibility"])
            self.assertEqual("1", summary["After"]["DontAskGraphics"])
            self.assertIn("graphics_device=28e0", updated_text)
            self.assertIn(r"cache_folder=C:\ProgramData\Jagex", updated_text)
            self.assertIn("compatibility=true", updated_text)
            self.assertIn("dont_ask_graphics=1", updated_text)

    def test_default_graphics_device_clears_adapter_pin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preferences_path = Path(temp_dir) / "preferences.cfg"
            preferences_path.write_text(
                "\n".join(
                    [
                        "graphics_device=28e0",
                        "compatibility=default",
                        "graphics_version=32.0.15.9579",
                    ]
                ),
                encoding="ascii",
            )

            summary = self.run_script(preferences_path, "-GraphicsDevice", "default")
            updated_text = preferences_path.read_text(encoding="ascii")

            self.assertIsNone(summary["After"]["GraphicsDevice"])
            self.assertIn("graphics_device", summary["ChangedKeys"])
            self.assertNotIn("graphics_device=", updated_text)
            self.assertIn("compatibility=true", updated_text)

    def test_clear_dont_ask_again_removes_existing_flag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            preferences_path = Path(temp_dir) / "preferences.cfg"
            preferences_path.write_text(
                "\n".join(
                    [
                        "graphics_device=a788",
                        "compatibility=default",
                        "dont_ask_graphics=1",
                        "graphics_version=32.0.101.7085",
                    ]
                ),
                encoding="ascii",
            )

            summary = self.run_script(
                preferences_path,
                "-GraphicsDevice",
                "default",
                "-ClearDontAskAgain",
                include_default_dont_ask=False,
            )
            updated_text = preferences_path.read_text(encoding="ascii")

            self.assertEqual("true", summary["After"]["Compatibility"])
            self.assertIsNone(summary["After"]["DontAskGraphics"])
            self.assertNotIn("dont_ask_graphics=", updated_text)
            self.assertNotIn("graphics_device=", updated_text)
            self.assertIn("dont_ask_graphics", summary["ChangedKeys"])
            self.assertIn("graphics_device", summary["ChangedKeys"])


if __name__ == "__main__":
    unittest.main()
