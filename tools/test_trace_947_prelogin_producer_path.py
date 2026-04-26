from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

try:
    from tools.trace_947_prelogin_producer_path import (
        DEFAULT_BUILDER_MASTER_LOOKUP_RVA,
        DEFAULT_BUILDER_POST_GATE_RVA,
        DEFAULT_BUILDER_RVA,
        DEFAULT_FALLBACK_RVA,
        DEFAULT_INDEXED_TABLE_SLOT_OFFSET,
        DEFAULT_PRODUCER_RVA,
        DEFAULT_RECORD_STRIDE,
        archive_output_path,
        archive_summary_path,
        build_script,
    )
except ModuleNotFoundError:
    from trace_947_prelogin_producer_path import (
        DEFAULT_BUILDER_MASTER_LOOKUP_RVA,
        DEFAULT_BUILDER_POST_GATE_RVA,
        DEFAULT_BUILDER_RVA,
        DEFAULT_FALLBACK_RVA,
        DEFAULT_INDEXED_TABLE_SLOT_OFFSET,
        DEFAULT_PRODUCER_RVA,
        DEFAULT_RECORD_STRIDE,
        archive_output_path,
        archive_summary_path,
        build_script,
    )


class Trace947PreloginProducerPathTest(unittest.TestCase):
    def test_archive_paths_are_timestamped(self) -> None:
        timestamp = datetime(2026, 3, 30, 23, 15, 0)

        self.assertEqual(
            Path("root/947-prelogin-producer-20260330-231500.jsonl"),
            archive_output_path(Path("root"), timestamp),
        )
        self.assertEqual(
            Path("root/947-prelogin-producer-20260330-231500.json"),
            archive_summary_path(Path("root"), timestamp),
        )

    def test_build_script_contains_key_rvas_and_events(self) -> None:
        script = build_script(
            producer_rva=DEFAULT_PRODUCER_RVA,
            builder_rva=DEFAULT_BUILDER_RVA,
            builder_master_lookup_rva=DEFAULT_BUILDER_MASTER_LOOKUP_RVA,
            builder_post_gate_rva=DEFAULT_BUILDER_POST_GATE_RVA,
            fallback_rva=DEFAULT_FALLBACK_RVA,
            indexed_table_slot_offset=DEFAULT_INDEXED_TABLE_SLOT_OFFSET,
            record_stride=DEFAULT_RECORD_STRIDE,
        )

        script_lower = script.lower()
        self.assertIn("0x590220", script_lower)
        self.assertIn("0x590bc0", script_lower)
        self.assertIn("0x590c58", script_lower)
        self.assertIn("0x590de8", script_lower)
        self.assertIn("0x591a00", script_lower)
        self.assertIn("0x30d0", script_lower)
        self.assertIn("0x108", script_lower)
        self.assertIn("Process.enumerateModules()[0].base", script)
        self.assertIn("producer-script-loaded", script)
        self.assertIn("rpc.exports = {", script)
        self.assertIn("snapshot()", script)
        self.assertIn("producer-call-unique", script)
        self.assertIn("producer-builder-leave-unique", script)
        self.assertIn("producer-builder-master-lookup-unique", script)
        self.assertIn("producer-builder-post-gate-unique", script)
        self.assertIn("producer-fallback-leave-unique", script)
        self.assertIn("function summarizeOwner(owner)", script)
        self.assertIn("function summarizeRecord(owner, resourceIndex)", script)
        self.assertIn("function summarizePathBase(pathBase, recordBase)", script)
        self.assertIn("callsiteRvaText", script)
        self.assertIn("table30d0", script)
        self.assertIn("flag7734", script)
        self.assertIn("field7710", script)
        self.assertIn("field7730", script)
        self.assertIn("field327c", script)
        self.assertIn("count32c0", script)
        self.assertIn("count77d8", script)
        self.assertIn("pathBase", script)
        self.assertIn("outFlagValue", script)


if __name__ == "__main__":
    unittest.main()
