from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
SCRIPT = TOOLS_DIR / "resolve_runescape_graphics_device.ps1"
POWERSHELL = Path(os.environ["WINDIR"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"


class ResolveRuneScapeGraphicsDeviceTest(unittest.TestCase):
    def run_script(self, preference: str, controllers: list[dict[str, str]]) -> dict:
        with tempfile.TemporaryDirectory() as temp_dir:
            controllers_path = Path(temp_dir) / "controllers.json"
            controllers_path.write_text(json.dumps(controllers), encoding="utf-8")
            completed = subprocess.run(
                [
                    str(POWERSHELL),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(SCRIPT),
                    "-Preference",
                    preference,
                    "-ControllersJsonPath",
                    str(controllers_path),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            return json.loads(completed.stdout)

    def test_power_saving_prefers_intel_integrated_adapter(self) -> None:
        payload = self.run_script(
            "power-saving",
            [
                {
                    "Name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "AdapterCompatibility": "NVIDIA",
                    "PNPDeviceID": r"PCI\VEN_10DE&DEV_28E0&SUBSYS_17311025&REV_A1\4&1B0D88EE&0&0008",
                    "DriverVersion": "32.0.15.9597",
                    "VideoProcessor": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "AdapterDACType": "Integrated RAMDAC",
                },
                {
                    "Name": "Intel(R) UHD Graphics",
                    "AdapterCompatibility": "Intel Corporation",
                    "PNPDeviceID": r"PCI\VEN_8086&DEV_A788&SUBSYS_17311025&REV_04\3&11583659&0&10",
                    "DriverVersion": "32.0.101.5972",
                    "VideoProcessor": "Intel(R) RaptorLake-S Mobile Graphics Controller",
                    "AdapterDACType": "Internal",
                },
            ],
        )

        self.assertEqual("a788", payload["SelectedGraphicsDevice"])
        self.assertEqual("Intel(R) UHD Graphics", payload["SelectedController"]["Name"])

    def test_high_performance_prefers_discrete_adapter(self) -> None:
        payload = self.run_script(
            "high-performance",
            [
                {
                    "Name": "Intel(R) UHD Graphics",
                    "AdapterCompatibility": "Intel Corporation",
                    "PNPDeviceID": r"PCI\VEN_8086&DEV_A788&SUBSYS_17311025&REV_04\3&11583659&0&10",
                    "DriverVersion": "32.0.101.5972",
                    "VideoProcessor": "Intel(R) RaptorLake-S Mobile Graphics Controller",
                    "AdapterDACType": "Internal",
                },
                {
                    "Name": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "AdapterCompatibility": "NVIDIA",
                    "PNPDeviceID": r"PCI\VEN_10DE&DEV_28E0&SUBSYS_17311025&REV_A1\4&1B0D88EE&0&0008",
                    "DriverVersion": "32.0.15.9597",
                    "VideoProcessor": "NVIDIA GeForce RTX 4060 Laptop GPU",
                    "AdapterDACType": "Integrated RAMDAC",
                },
            ],
        )

        self.assertEqual("28e0", payload["SelectedGraphicsDevice"])
        self.assertEqual("NVIDIA GeForce RTX 4060 Laptop GPU", payload["SelectedController"]["Name"])

    def test_default_returns_no_selected_device(self) -> None:
        payload = self.run_script(
            "default",
            [
                {
                    "Name": "Intel(R) UHD Graphics",
                    "AdapterCompatibility": "Intel Corporation",
                    "PNPDeviceID": r"PCI\VEN_8086&DEV_A788&SUBSYS_17311025&REV_04\3&11583659&0&10",
                    "DriverVersion": "32.0.101.5972",
                    "VideoProcessor": "Intel(R) RaptorLake-S Mobile Graphics Controller",
                    "AdapterDACType": "Internal",
                }
            ],
        )

        self.assertIsNone(payload["SelectedGraphicsDevice"])
        self.assertIsNone(payload["SelectedController"])


if __name__ == "__main__":
    unittest.main()
