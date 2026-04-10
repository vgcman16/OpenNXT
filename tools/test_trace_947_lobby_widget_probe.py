from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path

import tools.trace_947_lobby_widget_probe as probe


class Trace947LobbyWidgetProbeTest(unittest.TestCase):
    def test_archive_probe_output_path_uses_timestamp(self) -> None:
        path = probe.archive_probe_output_path(Path("root"), datetime(2026, 4, 4, 8, 15, 0))
        self.assertEqual(Path("root/947-lobby-widget-probe-20260404-081500.jsonl"), path)

    def test_resolve_hooks_adds_custom_entries(self) -> None:
        hooks = probe.resolve_hooks(["custom=0x1234"])
        self.assertIn(("custom", 0x1234), hooks)
        self.assertIn(("if_button_router", 0x1A3600), hooks)


if __name__ == "__main__":
    unittest.main()
