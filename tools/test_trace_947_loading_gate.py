from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

try:
    from tools.trace_947_loading_gate import (
        DEFAULT_FUNCTION_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )
except ModuleNotFoundError:
    from trace_947_loading_gate import (
        DEFAULT_FUNCTION_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )


class Trace947LoadingGateTest(unittest.TestCase):
    def test_archive_output_paths_are_timestamped(self) -> None:
        timestamp = datetime(2026, 3, 29, 18, 31, 0)

        self.assertEqual(
            Path("root/947-loading-gate-20260329-183100.jsonl"),
            archive_output_path(Path("root"), timestamp),
        )
        self.assertEqual(
            Path("root/947-loading-gate-20260329-183100.json"),
            archive_summary_path(Path("root"), timestamp),
        )

    def test_build_script_contains_gate_offsets_and_snapshot_export(self) -> None:
        script = build_script(function_rva=DEFAULT_FUNCTION_RVA)

        self.assertIn("0x594a10", script.lower())
        self.assertIn("0xa0", script.lower())
        self.assertIn("0xd0", script.lower())
        self.assertIn("loading-gate-unique", script)
        self.assertIn("snapshot()", script)
        self.assertIn("selectedPrimary", script)
        self.assertIn("selectedSecondary", script)


if __name__ == "__main__":
    unittest.main()
