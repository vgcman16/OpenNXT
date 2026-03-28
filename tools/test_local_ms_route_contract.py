from __future__ import annotations

import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent


class LocalMsRouteContractTest(unittest.TestCase):
    def test_live_launcher_defaults_content_mitm_to_local_http(self) -> None:
        text = (TOOLS_DIR / "launch-win64c-live.ps1").read_text(encoding="utf-8")
        self.assertIn('$effectiveContentTlsConnectHost = "127.0.0.1"', text)
        self.assertIn('$effectiveContentTlsConnectPort = $configuredHttpPort', text)
        self.assertIn('$effectiveContentTlsRemoteRaw = $true', text)

    def test_watchdog_restarts_lobby_proxy_against_local_http_content_route(self) -> None:
        text = (TOOLS_DIR / "keep_local_live_stack.ps1").read_text(encoding="utf-8")
        self.assertIn('"-TlsRemoteHost"', text)
        self.assertIn('"content.runescape.com"', text)
        self.assertIn('"-TlsConnectHost"', text)
        self.assertIn('"127.0.0.1"', text)
        self.assertIn('"-TlsConnectPort"', text)
        self.assertIn('$configuredHttpPort.ToString()', text)
        self.assertIn('"-TlsRemoteRaw"', text)

    def test_js5_ms_endpoint_serves_general_cache_payloads(self) -> None:
        text = (
            ROOT_DIR
            / "src"
            / "main"
            / "kotlin"
            / "com"
            / "opennxt"
            / "net"
            / "http"
            / "endpoints"
            / "Js5MsEndpoint.kt"
        ).read_text(encoding="utf-8")
        self.assertIn("readReferenceTable(archive)", text)
        self.assertIn("OpenNXT.filesystem.read(index, archive)", text)
        self.assertIn('ResolvedPayload(data, "reference-table")', text)
        self.assertIn('ResolvedPayload(data, "archive")', text)


if __name__ == "__main__":
    unittest.main()
