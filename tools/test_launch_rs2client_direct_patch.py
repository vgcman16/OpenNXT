from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_rs2client_direct_patch import parse_resolve_redirect_specs, write_summary_output


class LaunchRs2ClientDirectPatchTest(unittest.TestCase):
    def test_parse_resolve_redirect_specs_normalizes_hosts(self) -> None:
        redirects = parse_resolve_redirect_specs(
            [
                "RS.CONFIG.RUNESCAPE.COM=localhost",
                "content.runescape.com=127.0.0.1",
            ]
        )
        self.assertEqual(
            redirects,
            {
                "rs.config.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
            },
        )

    def test_parse_resolve_redirect_specs_rejects_bad_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_resolve_redirect_specs(["missing-separator"])

    def test_write_summary_output_replaces_file_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "summary.json"
            summary_path.write_text('{"summaryStage":"old"}', encoding="utf-8")

            write_summary_output(summary_path, {"summaryStage": "ready", "pid": 1234})

            self.assertEqual(
                json.loads(summary_path.read_text(encoding="utf-8")),
                {"summaryStage": "ready", "pid": 1234},
            )
            self.assertFalse((Path(temp_dir) / "summary.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
