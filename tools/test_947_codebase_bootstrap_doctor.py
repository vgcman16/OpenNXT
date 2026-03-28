from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_947_codebase_bootstrap_doctor import (  # type: ignore
    build_socket_exchanges,
    choose_codebase_exchange,
    infer_likely_blocker,
    resolve_default_hook_path,
)


class CodebaseBootstrapDoctorTest(unittest.TestCase):
    def test_selects_http_exchange_on_port_80(self) -> None:
        events = [
            {
                "category": "client.net",
                "action": "connect",
                "socket": "5376",
                "remoteHost": "127.0.0.1",
                "remotePort": 80,
                "status": 0,
                "timestamp": 10.0,
            },
            {
                "category": "client.net",
                "action": "send-first-chunk",
                "socket": "5376",
                "remoteHost": "127.0.0.1",
                "remotePort": 80,
                "bytes": 80,
                "previewHex": "474554202f6b3d352f20485454502f312e310d0a",
                "previewText": "GET /k=5/ HTTP/1.1\r\nHost: localhost\r\n\r\n",
                "firstLine": "GET /k=5/ HTTP/1.1",
                "looksHttp": True,
                "timestamp": 10.1,
            },
            {
                "category": "client.net",
                "action": "recv-first-chunk",
                "socket": "5376",
                "remoteHost": "127.0.0.1",
                "remotePort": 80,
                "bytes": 96,
                "previewHex": "485454502f312e3120343034204e6f7420466f756e64",
                "previewText": "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n",
                "firstLine": "HTTP/1.1 404 Not Found",
                "looksHttp": True,
                "timestamp": 10.2,
            },
            {
                "category": "client.net",
                "action": "close",
                "socket": "5376",
                "remoteHost": "127.0.0.1",
                "remotePort": 80,
                "bytesSent": 80,
                "bytesReceived": 96,
                "status": 0,
                "timestamp": 10.3,
            },
        ]

        exchanges = build_socket_exchanges(events)
        selected = choose_codebase_exchange(exchanges)
        self.assertIsNotNone(selected)
        self.assertEqual(selected.remote_port, 80)
        self.assertEqual(selected.first_send.first_line, "GET /k=5/ HTTP/1.1")
        self.assertEqual(infer_likely_blocker(selected), "codebase-bootstrap-http-404")

    def test_flags_missing_exchange(self) -> None:
        self.assertEqual(infer_likely_blocker(None), "no-codebase-bootstrap-exchange-captured")

    def test_selects_exchange_when_only_byte_totals_are_captured(self) -> None:
        events = [
            {
                "category": "client.net",
                "action": "connect",
                "socket": "6200",
                "remoteHost": "127.0.0.1",
                "remotePort": 8080,
                "status": 0,
                "timestamp": 11.0,
            },
            {
                "category": "client.net",
                "action": "close",
                "socket": "6200",
                "remoteHost": "127.0.0.1",
                "remotePort": 8080,
                "bytesSent": 289,
                "bytesReceived": 7872,
                "status": 0,
                "timestamp": 11.5,
            },
        ]

        exchanges = build_socket_exchanges(events)
        selected = choose_codebase_exchange(exchanges)
        self.assertIsNotNone(selected)
        self.assertEqual(8080, selected.remote_port)
        self.assertEqual("codebase-bootstrap-send-missing", infer_likely_blocker(selected))

    def test_prefers_newest_direct_patched_summary_with_startup_hook(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            direct_dir = root / "direct"
            direct_dir.mkdir()
            fallback = root / "fallback.jsonl"
            fallback.write_text("", encoding="utf-8")
            target_hook = root / "hook.jsonl"
            target_hook.write_text("", encoding="utf-8")
            (direct_dir / "older.json").write_text("{}", encoding="utf-8")
            (direct_dir / "newer.json").write_text(
                (
                    '{"startupHookOutput": "%s", "liveProcessPath": '
                    '"C:\\\\Users\\\\Demon\\\\Documents\\\\New project\\\\OpenNXT\\\\data\\\\clients\\\\947\\\\win64c\\\\patched\\\\rs2client.exe"}'
                )
                % str(target_hook).replace("\\", "\\\\"),
                encoding="utf-8",
            )

            resolved = resolve_default_hook_path(direct_debug_dir=direct_dir, fallback_hook_path=fallback)

        self.assertEqual(target_hook, resolved)


if __name__ == "__main__":
    unittest.main()
