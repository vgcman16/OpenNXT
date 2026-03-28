from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

try:
    from tools.run_947_startup_hook_diff_doctor import compare_markers, parse_hook_markers
except ModuleNotFoundError:
    from run_947_startup_hook_diff_doctor import compare_markers, parse_hook_markers


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


class StartupHookDiffDoctorTest(unittest.TestCase):
    def test_compare_markers_flags_local_http_master_table_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            official = root / "official.jsonl"
            local = root / "local.jsonl"

            write_jsonl(
                official,
                [
                    {"action": "resolve", "host": "world2a.runescape.com", "service": "443"},
                    {"action": "initialize-security-context", "targetName": "world2a.runescape.com", "status": 0},
                    {"action": "resolve", "host": "content.runescape.com", "service": "443"},
                    {"action": "open", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-12.jcache"},
                    {"action": "initialize-security-context", "targetName": "content.runescape.com", "status": 0},
                ],
            )
            write_jsonl(
                local,
                [
                    {"action": "resolve", "host": "localhost", "service": "443"},
                    {"action": "send-first-chunk", "remotePort": 443, "looksHttp": False, "firstLine": ".*"},
                    {"action": "open", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-12.jcache"},
                    {"action": "write", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-12.jcache"},
                    {"action": "resolve", "host": "localhost", "service": "80"},
                    {
                        "action": "send-first-chunk",
                        "remotePort": 80,
                        "looksHttp": True,
                        "firstLine": "GET /ms?m=0&a=255&k=947&g=255&c=0&v=0 HTTP/1.1",
                    },
                    {
                        "action": "recv-first-chunk",
                        "remotePort": 80,
                        "looksHttp": True,
                        "firstLine": "HTTP/1.1 200 OK",
                    },
                ],
            )

            official_summary = parse_hook_markers(official)
            local_summary = parse_hook_markers(local)
            diff = compare_markers(official_summary, local_summary)

        self.assertEqual(
            [
                "resolve:world-secure",
                "tls-ready:world-secure",
                "resolve:content-secure",
                "cache:hot-js5-touch",
                "tls-ready:content-secure",
            ],
            [marker.label for marker in official_summary.markers],
        )
        self.assertEqual(
            [
                "resolve:local-secure-bootstrap",
                "send:raw-bootstrap",
                "cache:hot-js5-touch",
                "cache:hot-js5-write",
                "resolve:local-http-content",
                "send:http-master-table",
                "recv:http-master-table-200",
            ],
            [marker.label for marker in local_summary.markers],
        )
        self.assertEqual("content-bootstrap-transport-diverged", diff.likely_blocker)

    def test_parse_hook_markers_tracks_hot_cache_touch_and_write_sets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "hook.jsonl"
            write_jsonl(
                hook_path,
                [
                    {"action": "open", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-2.jcache"},
                    {"action": "write", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-2.jcache"},
                    {"action": "open", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-99.jcache"},
                    {"action": "write", "fileCategory": "cache", "path": r"C:\ProgramData\Jagex\RuneScape\js5-57.jcache"},
                ],
            )

            summary = parse_hook_markers(hook_path)

        self.assertEqual([2, 57], summary.hot_cache_slots_touched)
        self.assertEqual([2, 57], summary.hot_cache_slots_written)
        self.assertEqual(
            ["cache:hot-js5-touch", "cache:hot-js5-write"],
            [marker.label for marker in summary.markers],
        )

    def test_parse_hook_markers_tolerates_missing_remote_port(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "hook.jsonl"
            write_jsonl(
                hook_path,
                [
                    {"action": "send-first-chunk", "remotePort": None, "looksHttp": False, "firstLine": ".."},
                    {"action": "recv-first-chunk", "remotePort": None, "looksHttp": False, "firstLine": "."},
                ],
            )

            summary = parse_hook_markers(hook_path)

        self.assertEqual([], summary.markers)
        self.assertEqual(0, summary.raw_bootstrap_count)
        self.assertEqual(0, summary.http_master_table_success_count)

    def test_parse_hook_markers_treats_tls_client_hello_separately_from_raw_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            hook_path = Path(temp_dir) / "hook.jsonl"
            write_jsonl(
                hook_path,
                [
                    {
                        "action": "send-first-chunk",
                        "remotePort": 443,
                        "looksHttp": False,
                        "firstLine": "...",
                        "previewHex": "16030300b5010000b10303abcdef",
                    },
                    {
                        "action": "send-first-chunk",
                        "remotePort": 443,
                        "looksHttp": False,
                        "firstLine": ".*",
                        "previewHex": "0f2a000003b30000000153776a49",
                    },
                ],
            )

            summary = parse_hook_markers(hook_path)

        self.assertEqual(
            ["send:tls-client-hello", "send:raw-bootstrap"],
            [marker.label for marker in summary.markers],
        )
        self.assertEqual(1, summary.raw_bootstrap_count)


if __name__ == "__main__":
    unittest.main()
