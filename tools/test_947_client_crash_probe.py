from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest

try:
    from tools.trace_947_client_crash_probe import (
        DEFAULT_CALLER_SITE_RVAS,
        archive_probe_output_path,
        build_hook_script,
        validate_probe_configuration,
    )
except ModuleNotFoundError:
    from trace_947_client_crash_probe import (
        DEFAULT_CALLER_SITE_RVAS,
        archive_probe_output_path,
        build_hook_script,
        validate_probe_configuration,
    )


class ClientCrashProbeTest(unittest.TestCase):
    def test_archive_probe_output_path_is_timestamped(self) -> None:
        path = archive_probe_output_path(Path("root"), datetime(2026, 3, 29, 10, 41, 30))

        self.assertEqual(Path("root/947-client-only-crash-probe-20260329-104130.jsonl"), path)

    def test_build_hook_script_contains_fault_family_details(self) -> None:
        script = build_hook_script(
            module_name="rs2client.exe",
            function_start_rva=0x590BC0,
            fault_rva=0x590DE8,
            state_capture_rva=0x590DCB,
            tracked_offsets=(0x7710, 0x7734, 0x77E0),
            repair_r15_at_state_capture=True,
            repair_epilogue_frame=True,
            enable_missing_indexed_table_guard=True,
            guard_caller_site_rva=0x58FF0F,
            guard_resume_rva=0x58FF14,
        )

        self.assertIn("0x590bc0", script.lower())
        self.assertIn("0x590de8", script.lower())
        self.assertIn("0x590dcb", script.lower())
        self.assertIn("0x7734", script.lower())
        self.assertIn("fault-family-match", script)
        self.assertIn("state-checkpoint", script)
        self.assertIn("state-repair-applied", script)
        self.assertIn("branch-checkpoint", script)
        self.assertIn("caller-site-hit", script)
        self.assertIn("callerCallSite", script)
        self.assertIn("callerCallSiteRva", script)
        self.assertIn("latestCallerSite", script)
        self.assertIn("param2U32", script)
        self.assertIn("0x590db5", script.lower())
        self.assertIn("bad-path-edge", script)
        self.assertIn("release-prep", script)
        self.assertIn("release-call-8", script)
        self.assertIn("release-call-10", script)
        self.assertIn("epilogue-prep", script)
        self.assertIn("registerU32", script)
        self.assertIn("address.readu8()", script.lower())
        self.assertIn("address.readpointer()", script.lower())
        self.assertIn("stackObjectDetails", script)
        self.assertIn("repairepilogueframe", script.lower())
        self.assertIn("repairEpilogueFrameCallerSiteRvas", script)
        self.assertIn("repairreleaseframe", script.lower())
        self.assertIn("repairReleaseFrameCallerSiteRvas", script)
        self.assertIn("savedR15", script)
        self.assertIn("savedR14", script)
        self.assertIn("returnAddress", script)
        self.assertIn("epilogue-frame-repair-applied", script)
        self.assertIn("epilogueFrameRepair", script)
        self.assertIn("savedRbx", script)
        self.assertIn("savedRbp", script)
        self.assertIn("release-frame-repair-applied", script)
        self.assertIn("releaseFrameRepair", script)
        self.assertIn("slot8Read", script)
        self.assertIn("slot10Read", script)
        self.assertIn("checkpointEpiloguePrep", script)
        self.assertIn("caller-guard-skip", script)
        self.assertIn("decidemissingindexedtableguard", script.lower())
        self.assertIn("0x58ff0f", script.lower())
        self.assertIn("0x58ff14", script.lower())
        self.assertIn("forcesuccesscallersitervas", script.lower())
        self.assertIn("forceSuccessEligible", script)
        self.assertIn("function-leave", script)
        self.assertIn("inflight-function-fault", script)
        self.assertIn("forced-success-return", script)
        self.assertIn("instruction.parse", script.lower())
        self.assertIn("hook-skipped", script)
        self.assertIn("direct-call-opcode", script)
        self.assertIn("instructionbytes", script.lower())

    def test_build_hook_script_can_force_success_for_specific_callers(self) -> None:
        script = build_hook_script(
            module_name="rs2client.exe",
            function_start_rva=0x590BC0,
            fault_rva=0x590DE8,
            state_capture_rva=0x590DCB,
            tracked_offsets=(0x7710, 0x7734, 0x77E0),
            force_success_caller_site_rvas=(0x58FF0F, 0x5903D7),
        )

        self.assertIn("0x58ff0f", script.lower())
        self.assertIn("0x5903d7", script.lower())
        self.assertIn("returnValueBeforeU32", script)
        self.assertIn("retval.replace(ptr('0x1'))", script)

    def test_default_profile_excludes_known_unsafe_caller_sites(self) -> None:
        self.assertNotIn(0x58FF0F, DEFAULT_CALLER_SITE_RVAS)
        self.assertNotIn(0x4488D7, DEFAULT_CALLER_SITE_RVAS)

    def test_validate_probe_configuration_rejects_known_unsafe_guard_site(self) -> None:
        args = SimpleNamespace(
            enable_missing_indexed_table_guard=True,
            guard_caller_site_rva=0x58FF0F,
        )

        with self.assertRaisesRegex(ValueError, "known-unsafe"):
            validate_probe_configuration(args)


if __name__ == "__main__":
    unittest.main()
