from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_installed_server_smoke import CANONICAL_QUERY_PARAMS, build_canonical_query, contains_no_class_def, load_server_ports


class InstalledServerSmokeTest(unittest.TestCase):
    def test_canonical_query_uses_content_route_rewrite(self) -> None:
        query = build_canonical_query(8080)
        self.assertIn("localhost:8080", query)
        self.assertIn("hostRewrite=0", query)
        self.assertIn("lobbyHostRewrite=0", query)
        self.assertIn("contentRouteRewrite=1", query)
        self.assertIn("worldUrlRewrite=0", query)
        self.assertIn("codebaseRewrite=0", query)
        self.assertIn("baseConfigSource=live", query)
        self.assertIn("liveCache=1", query)
        self.assertIn("downloadMetadataSource=patched", query)
        self.assertEqual(CANONICAL_QUERY_PARAMS["gameHostOverride"], "lobby45a.runescape.com")

    def test_contains_no_class_def_detects_runtime_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stderr_path = Path(tmpdir) / "stderr.log"
            stderr_path.write_text("java.lang.NoClassDefFoundError: com/opennxt/util/TextUtils\n", encoding="utf-8")
            self.assertTrue(contains_no_class_def(stderr_path))

    def test_contains_no_class_def_ignores_clean_log(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            stderr_path = Path(tmpdir) / "stderr.log"
            stderr_path.write_text("all good\n", encoding="utf-8")
            self.assertFalse(contains_no_class_def(stderr_path))

    def test_load_server_ports_uses_configured_http_and_game_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "server.toml"
            config_path.write_text(
                "\n".join(
                    [
                        "[networking.ports]",
                        "http = 8080",
                        "game = 43594",
                        "gameBackend = 43596",
                    ]
                ),
                encoding="utf-8",
            )
            ports = load_server_ports(config_path)
        self.assertEqual(ports["http"], 8080)
        self.assertEqual(ports["game"], 43596)


if __name__ == "__main__":
    unittest.main()
