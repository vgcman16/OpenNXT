from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trace_rs2client_live import build_hook_script, partition_redirect_rules  # type: ignore


class TraceRs2ClientLiveTest(unittest.TestCase):
    def test_build_hook_script_captures_first_socket_chunks(self) -> None:
        script = build_hook_script(verbose=False, resolve_redirects={}, connect_redirects={})
        self.assertIn("send-first-chunk", script)
        self.assertIn("recv-first-chunk", script)
        self.assertIn("summarizeSocketChunk", script)
        self.assertIn("WSAConnectByNameW", script)
        self.assertIn("WSAConnectByNameA", script)
        self.assertIn("WSASend", script)
        self.assertIn("WSARecv", script)
        self.assertIn("status: retval.toInt32()", script)

    def test_build_hook_script_verbose_includes_tls_payload_preview(self) -> None:
        script = build_hook_script(verbose=True, resolve_redirects={}, connect_redirects={})
        self.assertIn("summarizeSecBufferPayload", script)
        self.assertIn("payloadPreview = summarizeSecBufferPayload", script)
        self.assertIn("if (VERBOSE)", script)
        self.assertIn("summarizeSocketChunk(this.bufferPointer, actual, 64)", script)
        self.assertIn("summarizeSocketChunk(this.wsabuf.pointer, actual, 64)", script)

    def test_build_hook_script_keeps_resolve_redirect_pointer_alive(self) -> None:
        script = build_hook_script(
            verbose=False,
            resolve_redirects={"content.runescape.com": "localhost"},
            connect_redirects={"185.225.9.8": "localhost"},
        )
        self.assertIn("redirectPointer: redirectPointer", script)
        self.assertIn("const CONNECT_REDIRECTS =", script)
        self.assertIn("lookupConnectRedirect", script)

    def test_partition_redirect_rules_separates_exact_and_wildcard_hosts(self) -> None:
        exact, patterns = partition_redirect_rules(
            {
                "content.runescape.com": "localhost",
                "world*.runescape.com": "localhost",
            }
        )

        self.assertEqual({"content.runescape.com": "localhost"}, exact)
        self.assertEqual([{"pattern": "world*.runescape.com", "target": "localhost"}], patterns)

    def test_build_hook_script_supports_wildcard_redirect_patterns(self) -> None:
        script = build_hook_script(
            verbose=False,
            resolve_redirects={"world*.runescape.com": "localhost"},
            connect_redirects={"*.runescape.com": "127.0.0.1"},
        )

        self.assertIn("const RESOLVE_REDIRECT_PATTERNS =", script)
        self.assertIn("const CONNECT_REDIRECT_PATTERNS =", script)
        self.assertIn("matchesRedirectPattern", script)
        self.assertIn("lookupRedirectFromTables", script)
        self.assertIn('"pattern": "world*.runescape.com"', script)
        self.assertIn('"pattern": "*.runescape.com"', script)


if __name__ == "__main__":
    unittest.main()
