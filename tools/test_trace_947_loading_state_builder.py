from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

try:
    from tools.trace_947_loading_state_builder import (
        DEFAULT_LOADING_CALLSITE_RVA,
        DEFAULT_LOADING_GATE_RVA,
        DEFAULT_RECORD_STRIDE,
        DEFAULT_STATE_COPY_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )
except ModuleNotFoundError:
    from trace_947_loading_state_builder import (
        DEFAULT_LOADING_CALLSITE_RVA,
        DEFAULT_LOADING_GATE_RVA,
        DEFAULT_RECORD_STRIDE,
        DEFAULT_STATE_COPY_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )


class Trace947LoadingStateBuilderTest(unittest.TestCase):
    def test_archive_output_paths_are_timestamped(self) -> None:
        timestamp = datetime(2026, 4, 2, 22, 59, 0)

        self.assertEqual(
            Path("root/947-loading-state-builder-20260402-225900.jsonl"),
            archive_output_path(Path("root"), timestamp),
        )
        self.assertEqual(
            Path("root/947-loading-state-builder-20260402-225900.json"),
            archive_summary_path(Path("root"), timestamp),
        )

    def test_build_script_contains_copy_and_gate_offsets(self) -> None:
        script = build_script(
            state_copy_rva=DEFAULT_STATE_COPY_RVA,
            loading_gate_rva=DEFAULT_LOADING_GATE_RVA,
            loading_callsite_rva=DEFAULT_LOADING_CALLSITE_RVA,
            record_stride=DEFAULT_RECORD_STRIDE,
        )

        script_lower = script.lower()
        self.assertIn("0x593010", script_lower)
        self.assertIn("0x594a10", script_lower)
        self.assertIn("0x59109c", script_lower)
        self.assertIn("0x108", script_lower)
        self.assertIn("loading-state-copy-leave-unique", script)
        self.assertIn("loading-state-callsite-unique", script)
        self.assertIn("loading-state-gate-unique", script)
        self.assertIn("summarizeState", script)
        self.assertIn("summarizeOwnerSlot", script)
        self.assertIn("beforeTarget", script)
        self.assertIn("afterTarget", script)
        self.assertIn("block98Count", script)
        self.assertIn("vectorA0", script)
        self.assertIn("blockC8Count", script)
        self.assertIn("vectorD0", script)
        self.assertIn("chosenMatches31f8", script)
        self.assertIn("slotBc28", script)
        self.assertIn("snapshot()", script)


if __name__ == "__main__":
    unittest.main()
