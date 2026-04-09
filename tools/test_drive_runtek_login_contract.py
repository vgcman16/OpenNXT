from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "drive_runtek_login.ps1"


class DriveRuneTekLoginContractTests(unittest.TestCase):
    def test_drive_script_has_legacy_fallback_guard(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("function Test-ShouldUseLegacyLoginFallback", text)
        self.assertIn("falling back to legacy no-OCR submitter", text)
        self.assertIn("Get-LatestDirectPatchPid", text)

    def test_drive_script_legacy_submit_uses_keyboard_navigation(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("Send-Tab", text)
        self.assertIn("Invoke-WindowClick -Handle $handlePtr -XPercent 0.60 -YPercent 0.69", text)
        self.assertGreaterEqual(text.count("Send-Enter"), 4)


if __name__ == "__main__":
    unittest.main()
