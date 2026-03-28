from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trace_rs2client_live import build_hook_script  # type: ignore


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


if __name__ == "__main__":
    unittest.main()
