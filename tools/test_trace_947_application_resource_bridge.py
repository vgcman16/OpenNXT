from __future__ import annotations

from datetime import datetime
from pathlib import Path
import unittest

try:
    from tools.trace_947_application_resource_bridge import (
        DEFAULT_BRIDGE_SCAN_RVA,
        DEFAULT_DISPATCH_RVA,
        DEFAULT_RECORD_FINALIZE_RVA,
        DEFAULT_RECORD_STATE_RVA,
        DEFAULT_SCHEDULER_GLOBAL_RVA,
        DEFAULT_SEED_DISPATCH_RVA,
        DEFAULT_STATE1_WRITE_RVA,
        DEFAULT_STATE2_WRITE_RVA,
        DEFAULT_STATE34_WRITE_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )
except ModuleNotFoundError:
    from trace_947_application_resource_bridge import (
        DEFAULT_BRIDGE_SCAN_RVA,
        DEFAULT_DISPATCH_RVA,
        DEFAULT_RECORD_STATE_RVA,
        DEFAULT_SCHEDULER_GLOBAL_RVA,
        DEFAULT_SEED_DISPATCH_RVA,
        DEFAULT_STATE1_WRITE_RVA,
        DEFAULT_STATE2_WRITE_RVA,
        DEFAULT_STATE34_WRITE_RVA,
        archive_output_path,
        archive_summary_path,
        build_script,
    )


class Trace947ApplicationResourceBridgeTest(unittest.TestCase):
    def test_archive_paths_are_timestamped(self) -> None:
        timestamp = datetime(2026, 3, 30, 2, 45, 0)

        self.assertEqual(
            Path("root/947-application-resource-bridge-20260330-024500.jsonl"),
            archive_output_path(Path("root"), timestamp),
        )
        self.assertEqual(
            Path("root/947-application-resource-bridge-20260330-024500.json"),
            archive_summary_path(Path("root"), timestamp),
        )

    def test_build_script_contains_bridge_and_state_events(self) -> None:
        script = build_script(
            bridge_scan_rva=DEFAULT_BRIDGE_SCAN_RVA,
            dispatch_rva=DEFAULT_DISPATCH_RVA,
            seed_dispatch_rva=DEFAULT_SEED_DISPATCH_RVA,
            record_state_rva=DEFAULT_RECORD_STATE_RVA,
            record_finalize_rva=DEFAULT_RECORD_FINALIZE_RVA,
            state1_write_rva=DEFAULT_STATE1_WRITE_RVA,
            state2_write_rva=DEFAULT_STATE2_WRITE_RVA,
            state34_write_rva=DEFAULT_STATE34_WRITE_RVA,
            scheduler_global_rva=DEFAULT_SCHEDULER_GLOBAL_RVA,
            force_state1_on_ptr178=True,
            force_selector_ready_on_ptr178=True,
            force_owner_11d4a_open_on_special20=True,
            force_seed_dispatch_on_state1=True,
            force_recordstate_on_state1=True,
            force_direct_dispatch_on_state1=True,
            force_finalize_on_state1=True,
        )

        script_lower = script.lower()
        self.assertIn("0x5963cf", script_lower)
        self.assertIn("0x595530", script_lower)
        self.assertIn("0x597230", script_lower)
        self.assertIn("0x597d10", script_lower)
        self.assertIn("0x597fd0", script_lower)
        self.assertIn("0x590b96", script_lower)
        self.assertIn("0x5954c1", script_lower)
        self.assertIn("0x597c73", script_lower)
        self.assertIn("bridge-scan", script)
        self.assertIn("seed-dispatch-call", script)
        self.assertIn("loop-state-write", script)
        self.assertIn("state1-write", script)
        self.assertIn("state2-write", script)
        self.assertIn("state34-write", script)
        self.assertIn("force-state1-on-ptr178", script)
        self.assertIn("force-selector-ready-on-ptr178", script)
        self.assertIn("force-owner-11d4a-open-on-special20", script)
        self.assertIn("force-seed-dispatch-on-state1", script)
        self.assertIn("force-recordstate-on-state1", script)
        self.assertIn("force-direct-dispatch-on-state1", script)
        self.assertIn("force-finalize-on-state1", script)
        self.assertIn("forcedState1OnPtr178", script)
        self.assertIn("forcedSelectorReadyOnPtr178", script)
        self.assertIn("forcedOwner11d4aOpenOnSpecial20", script)
        self.assertIn("forcedSeedDispatchOnState1", script)
        self.assertIn("forcedRecordStateOnState1", script)
        self.assertIn("forcedDirectDispatchOnState1", script)
        self.assertIn("forcedFinalizeOnState1", script)
        self.assertIn("totalForcedState1Promotions", script)
        self.assertIn("totalForcedSelectorReadyPromotions", script)
        self.assertIn("totalForcedOwner11d4aOpen", script)
        self.assertIn("totalForcedSeedDispatches", script)
        self.assertIn("totalForcedRecordStateDispatches", script)
        self.assertIn("totalForcedDirectDispatches", script)
        self.assertIn("totalForcedFinalizeDispatches", script)
        self.assertIn("const seedDispatch = new NativeFunction(seedDispatchAddress, 'void', ['pointer', 'int']);", script)
        self.assertIn("const recordFinalize = new NativeFunction(recordFinalizeAddress, 'void', ['pointer', 'pointer']);", script)
        self.assertIn("seedDispatch(ptr(owner), index);", script)
        self.assertIn("recordState(ptr(owner), item);", script)
        self.assertIn("directDispatch(ptr(owner), index);", script)
        self.assertIn("recordFinalize(ptr(owner), recordBase);", script)
        self.assertIn("allocateSyntheticRecordStateItem", script)
        self.assertIn("queuedCount", script)
        self.assertIn("stateCount", script)
        self.assertIn("ptr178SetCount", script)
        self.assertIn("selectorEligibleCount", script)
        self.assertIn("selectorPtr178Details", script)
        self.assertIn("flag11508", script)
        self.assertIn("field170", script)
        self.assertIn("ptr180", script)
        self.assertIn("ptr188", script)
        self.assertIn("ptr1c8", script)
        self.assertIn("const effectiveTotal = (total164 === null || total164 === 0) ? 100 : total164;", script)
        self.assertIn("const requiredDone = Math.max(1, Math.ceil((effectiveTotal * 5) / 100));", script)


if __name__ == "__main__":
    unittest.main()
