from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_rs2client_direct_patch import parse_resolve_redirect_specs


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


if __name__ == "__main__":
    unittest.main()
