from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT = TOOLS_DIR / "set_windows_gpu_preference.ps1"
POWERSHELL = Path(os.environ["WINDIR"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class SetWindowsGpuPreferenceTest(unittest.TestCase):
    def run_script(self, registry_path: str, preference: str, executable_path: str) -> dict:
        completed = subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-RegistryPath",
                registry_path,
                "-Preference",
                preference,
                "-ExecutablePath",
                executable_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(completed.stdout)

    def remove_registry_path(self, registry_path: str) -> None:
        subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"Remove-Item -Path '{registry_path}' -Recurse -Force -ErrorAction SilentlyContinue",
            ],
            check=False,
        )

    def test_power_saving_writes_gpu_preference_value(self) -> None:
        registry_path = "HKCU:\\Software\\OpenNXTTest\\GpuPreferencesPowerSaving"
        fake_exe = str(Path(tempfile.gettempdir()) / "OpenNXT-RuneScape.exe")
        self.remove_registry_path(registry_path)
        try:
            summary = self.run_script(registry_path, "power-saving", fake_exe)
            entry = summary["Entries"][0]
            self.assertEqual("GpuPreference=1;", entry["After"])
            self.assertTrue(entry["Changed"])
        finally:
            self.remove_registry_path(registry_path)

    def test_high_performance_writes_gpu_preference_value(self) -> None:
        registry_path = "HKCU:\\Software\\OpenNXTTest\\GpuPreferencesHighPerformance"
        fake_exe = str(Path(tempfile.gettempdir()) / "OpenNXT-RuneScape-high.exe")
        self.remove_registry_path(registry_path)
        try:
            summary = self.run_script(registry_path, "high-performance", fake_exe)
            entry = summary["Entries"][0]
            self.assertEqual("GpuPreference=2;", entry["After"])
            self.assertTrue(entry["Changed"])
        finally:
            self.remove_registry_path(registry_path)

    def test_default_removes_existing_gpu_preference_value(self) -> None:
        registry_path = "HKCU:\\Software\\OpenNXTTest\\GpuPreferencesDefault"
        fake_exe = str(Path(tempfile.gettempdir()) / "OpenNXT-RuneScape-default.exe")
        self.remove_registry_path(registry_path)
        try:
            self.run_script(registry_path, "power-saving", fake_exe)
            summary = self.run_script(registry_path, "default", fake_exe)
            entry = summary["Entries"][0]
            self.assertIsNone(entry["After"])
            self.assertTrue(entry["Changed"])
        finally:
            self.remove_registry_path(registry_path)


if __name__ == "__main__":
    unittest.main()
