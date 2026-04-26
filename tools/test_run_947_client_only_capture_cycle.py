from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

from tools import run_947_client_only_capture_cycle as capture_cycle


class Run947ClientOnlyCaptureCycleTest(unittest.TestCase):
    def test_parse_args_accepts_loading_gate_and_table_lifecycle_flags(self) -> None:
        argv = [
            "run_947_client_only_capture_cycle.py",
            "--gate-force-record-open-on-field1c",
            "--gate-force-recordd-ready-on-ptr178",
            "--gate-force-recordd-ready-on-latch-clear",
            "--gate-force-recordd-ready-on-close-suppression",
            "--gate-force-selector-ready-on-ptr178",
            "--gate-force-dispatch-provider-accept",
            "--gate-force-dispatch-result-metadata-fallback",
            "--gate-force-post-dispatch-release-callback-fallback",
            "--gate-force-finalize-on-dispatch-return",
            "--gate-demote-hot-donezero-queued-record",
            "--gate-force-post-select-status-retval",
            "22",
            "--gate-force-post-select-publication-success",
            "--gate-suppress-post-select-latch-clear",
            "--gate-suppress-record-close-bulk-pass",
            "--gate-suppress-record-close-call-rva",
            "0x595be3",
            "--gate-force-type0-prepare-branch",
            "--gate-force-type0-requested-length-from-source-header",
            "--gate-force-type0-source-object-from-side-slots",
            "--gate-force-type0-inner-source-from-side-wrapper",
            "--gate-force-type0-parser-single-byte-payload-to-1",
            "--gate-force-queue-helper-resolver-synthetic-success",
            "--gate-force-queue-helper-post-parser-cleanup-suppression",
            "--gate-force-type0-handler-return-slot-restore",
            "--bridge-force-seed-dispatch-on-state1",
            "--bridge-force-finalize-on-state1",
            "--loading-gate-trace",
            "--loading-state-builder-trace",
            "--table-lifecycle-trace",
            "--table-force-length-gate-0x41",
            "--table-mirror-compare-left-into-right",
            "--table-inject-null-master-table",
            "--table-inject-null-master-table-count",
            "99",
            "--probe-repair-release-frame",
        ]
        with patch.object(sys, "argv", argv):
            args = capture_cycle.parse_args()

        self.assertTrue(args.gate_force_record_open_on_field1c)
        self.assertTrue(args.gate_force_recordd_ready_on_ptr178)
        self.assertTrue(args.gate_force_recordd_ready_on_latch_clear)
        self.assertTrue(args.gate_force_recordd_ready_on_close_suppression)
        self.assertTrue(args.gate_force_selector_ready_on_ptr178)
        self.assertTrue(args.gate_force_dispatch_provider_accept)
        self.assertTrue(args.gate_force_dispatch_result_metadata_fallback)
        self.assertTrue(args.gate_force_post_dispatch_release_callback_fallback)
        self.assertTrue(args.gate_force_finalize_on_dispatch_return)
        self.assertTrue(args.gate_demote_hot_donezero_queued_record)
        self.assertEqual("22", args.gate_force_post_select_status_retval)
        self.assertTrue(args.gate_force_post_select_publication_success)
        self.assertTrue(args.gate_suppress_post_select_latch_clear)
        self.assertTrue(args.gate_suppress_record_close_bulk_pass)
        self.assertEqual(["0x595be3"], args.gate_suppress_record_close_call_rva)
        self.assertTrue(args.gate_force_type0_prepare_branch)
        self.assertTrue(args.gate_force_type0_requested_length_from_source_header)
        self.assertTrue(args.gate_force_type0_source_object_from_side_slots)
        self.assertTrue(args.gate_force_type0_inner_source_from_side_wrapper)
        self.assertTrue(args.gate_force_type0_parser_single_byte_payload_to_1)
        self.assertTrue(args.gate_force_queue_helper_resolver_synthetic_success)
        self.assertTrue(args.gate_force_queue_helper_post_parser_cleanup_suppression)
        self.assertTrue(args.gate_force_type0_handler_return_slot_restore)
        self.assertTrue(args.bridge_force_seed_dispatch_on_state1)
        self.assertTrue(args.bridge_force_finalize_on_state1)
        self.assertTrue(args.loading_gate_trace)
        self.assertTrue(args.loading_state_builder_trace)
        self.assertTrue(args.table_lifecycle_trace)
        self.assertTrue(args.table_force_length_gate_0x41)
        self.assertTrue(args.table_mirror_compare_left_into_right)
        self.assertTrue(args.table_inject_null_master_table)
        self.assertEqual(99, args.table_inject_null_master_table_count)
        self.assertTrue(args.probe_repair_release_frame)

    def test_wait_for_main_pid_falls_back_to_direct_patch_summary(self) -> None:
        with (
            patch.object(capture_cycle, "read_hook_events", return_value=[]),
            patch.object(
                capture_cycle,
                "read_direct_patch_summary",
                return_value={"pid": 22984, "processAlive": True},
            ),
            patch.object(capture_cycle, "read_launcher_summary", return_value={}),
            patch.object(capture_cycle, "process_exists", return_value=True),
        ):
            pid = capture_cycle.wait_for_main_pid(deadline=capture_cycle.time.time() + 1.0)

        self.assertEqual(22984, pid)

    def test_wait_for_main_pid_prefers_hook_event_when_available(self) -> None:
        with (
            patch.object(
                capture_cycle,
                "read_hook_events",
                return_value=[{"action": "exception-handler-installed", "pid": 20700}],
            ),
            patch.object(capture_cycle, "read_direct_patch_summary", return_value={}),
            patch.object(capture_cycle, "read_launcher_summary", return_value={}),
        ):
            pid = capture_cycle.wait_for_main_pid(deadline=capture_cycle.time.time() + 1.0)

        self.assertEqual(20700, pid)

    def test_wait_for_main_pid_falls_back_to_launcher_stdout_summary(self) -> None:
        with (
            patch.object(capture_cycle, "read_hook_events", return_value=[]),
            patch.object(capture_cycle, "read_direct_patch_summary", return_value={}),
            patch.object(
                capture_cycle,
                "read_launcher_summary",
                return_value={"ClientPid": 21232, "BootstrapClientPid": 21232},
            ),
            patch.object(capture_cycle, "process_exists", return_value=True),
        ):
            pid = capture_cycle.wait_for_main_pid(
                deadline=capture_cycle.time.time() + 1.0,
                launcher_stdout_log=capture_cycle.ROOT / "dummy-launcher.json",
            )

        self.assertEqual(21232, pid)

    def test_build_gate_trace_extra_args_includes_reset_close_caller(self) -> None:
        argv = [
            "run_947_client_only_capture_cycle.py",
            "--gate-force-selector-ready-on-ptr178",
            "--gate-force-recordd-ready-on-latch-clear",
            "--gate-force-recordd-ready-on-close-suppression",
            "--gate-force-finalize-on-dispatch-return",
            "--gate-force-dispatch-provider-accept",
            "--gate-force-dispatch-result-metadata-fallback",
            "--gate-force-post-dispatch-release-callback-fallback",
            "--gate-demote-hot-donezero-queued-record",
            "--gate-force-post-select-publication-success",
            "--gate-suppress-record-close-bulk-pass",
            "--gate-suppress-record-close-call-rva",
            "0x595be3",
            "--gate-force-type3-followon-on-post-state1",
            "--gate-force-type0-prepare-branch",
            "--gate-force-type0-requested-length-from-source-header",
            "--gate-force-type0-source-object-from-side-slots",
            "--gate-force-type0-inner-source-from-side-wrapper",
            "--gate-force-type0-parser-single-byte-payload-to-1",
            "--gate-force-queue-helper-resolver-synthetic-success",
            "--gate-force-queue-helper-post-parser-cleanup-suppression",
            "--gate-force-type0-handler-return-slot-restore",
        ]
        with patch.object(sys, "argv", argv):
            args = capture_cycle.parse_args()

        extra_args = capture_cycle.build_gate_trace_extra_args(args)

        self.assertIn("--force-selector-ready-on-ptr178", extra_args)
        self.assertIn("--force-recordd-ready-on-latch-clear", extra_args)
        self.assertIn("--force-recordd-ready-on-close-suppression", extra_args)
        self.assertIn("--force-finalize-on-dispatch-return", extra_args)
        self.assertIn("--force-dispatch-provider-accept", extra_args)
        self.assertIn("--force-dispatch-result-metadata-fallback", extra_args)
        self.assertIn("--force-post-dispatch-release-callback-fallback", extra_args)
        self.assertIn("--demote-hot-donezero-queued-record", extra_args)
        self.assertIn("--force-post-select-publication-success", extra_args)
        self.assertIn("--force-type3-followon-on-post-state1", extra_args)
        self.assertIn("--force-type0-prepare-branch", extra_args)
        self.assertIn("--force-type0-requested-length-from-source-header", extra_args)
        self.assertIn("--force-type0-source-object-from-side-slots", extra_args)
        self.assertIn("--force-type0-inner-source-from-side-wrapper", extra_args)
        self.assertIn("--force-type0-parser-single-byte-payload-to-1", extra_args)
        self.assertIn("--force-queue-helper-resolver-synthetic-success", extra_args)
        self.assertIn("--force-queue-helper-post-parser-cleanup-suppression", extra_args)
        self.assertIn("--force-type0-handler-return-slot-restore", extra_args)
        self.assertEqual(4, extra_args.count("--suppress-record-close-call-rva"))
        self.assertIn("0x5946cf", extra_args)
        self.assertIn("0x594700", extra_args)
        self.assertIn("0x595433", extra_args)
        self.assertIn("0x595be3", extra_args)


if __name__ == "__main__":
    unittest.main()
