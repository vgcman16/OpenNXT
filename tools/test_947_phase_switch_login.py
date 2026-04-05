from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_947_phase_switch_login import (
    build_phase_switch_trace_args,
    default_phase_switch_redirects,
    load_summary_pid,
)


class PhaseSwitchLoginTests(unittest.TestCase):
    def test_default_phase_switch_redirects_cover_world_lobby_and_content(self) -> None:
        self.assertEqual(
            default_phase_switch_redirects(),
            [
                "world*.runescape.com=localhost",
                "lobby*.runescape.com=localhost",
                "content.runescape.com=localhost",
            ],
        )

    def test_load_summary_pid_returns_integer_pid(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "latest-live.json"
            summary_path.write_text(json.dumps({"pid": 12345}), encoding="utf-8")
            self.assertEqual(load_summary_pid(summary_path), 12345)

    def test_load_summary_pid_handles_missing_or_invalid_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.json"
            self.assertEqual(load_summary_pid(missing_path), 0)

            invalid_path = Path(temp_dir) / "invalid.json"
            invalid_path.write_text("{not-json", encoding="utf-8")
            self.assertEqual(load_summary_pid(invalid_path), 0)

    def test_build_phase_switch_trace_args_include_resolve_and_connect_redirects(self) -> None:
        root = Path(r"C:\Users\skull\Documents\RuneScape\OpenNXT-mitm")
        args = build_phase_switch_trace_args(
            python_exe="python",
            root=root,
            pid=123,
            output_path=root / "data" / "debug" / "direct-rs2client-patch" / "latest-phase-switch-hook.jsonl",
            duration_seconds=45,
            resolve_redirects=[
                "world*.runescape.com=localhost",
                "content.runescape.com=localhost",
            ],
            connect_redirects=[
                "world*.runescape.com=localhost",
                "world*.runescape.com=localhost",
                "content.runescape.com=localhost",
            ],
        )

        self.assertIn("--resolve-redirect", args)
        self.assertIn("--connect-redirect", args)
        self.assertEqual(args.count("--resolve-redirect"), 2)
        self.assertEqual(args.count("--connect-redirect"), 2)
        self.assertIn("world*.runescape.com=localhost", args)
        self.assertIn("content.runescape.com=localhost", args)


if __name__ == "__main__":
    unittest.main()
