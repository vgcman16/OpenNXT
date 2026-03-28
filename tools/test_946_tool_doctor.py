from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_tool_doctor import analyze_doctor, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ToolDoctorTest(unittest.TestCase):
    @patch("run_946_tool_doctor.PHASE3_CANDIDATES")
    @patch("run_946_tool_doctor.PHASE5_PACKETS")
    @patch("run_946_tool_doctor.VERIFIED_PACKETS")
    @patch("run_946_tool_doctor.EVIDENCE_INDEX")
    @patch("run_946_tool_doctor.CURATED_COMPARE_JSON")
    @patch("run_946_tool_doctor.SENDER_ANALYSIS_JSON")
    @patch("run_946_tool_doctor.ACTIVE_SUB_JSON")
    @patch("run_946_tool_doctor.INTERFACE_DIFF_JSON")
    @patch("run_946_tool_doctor.SCENE_DELIVERY_JSON")
    @patch("run_946_tool_doctor.JS5_ARCHIVE_RESOLUTION_JSON")
    @patch("run_946_tool_doctor.PLATEAU_DIFF_JSON")
    @patch("run_946_tool_doctor.BLACK_SCREEN_CAPTURE_JSON")
    @patch("run_946_tool_doctor.LOOPBACK_DOCTOR_JSON")
    @patch("run_946_tool_doctor.ATTEMPT_DIFF_JSON")
    @patch("run_946_tool_doctor.READY_SIGNAL_DOCTOR_JSON")
    @patch("run_946_tool_doctor.POST_READY_CADENCE_DOCTOR_JSON")
    @patch("run_946_tool_doctor.DISCONNECT_PIVOT_DOCTOR_JSON")
    @patch("run_946_tool_doctor.SCRIPT_BURST_DOCTOR_JSON")
    @patch("run_946_tool_doctor.SCENE_START_DOCTOR_JSON")
    @patch("run_946_tool_doctor.POST_SCENE_OPCODE_DOCTOR_JSON")
    @patch("run_946_tool_doctor.CLIENT_LIVE_WATCH_JSON")
    @patch("run_946_tool_doctor.RUNTIME_VERIFIER_JSON")
    def test_doctor_reports_ok_when_required_inputs_exist(
        self,
        runtime_json: patch,
        live_watch_json: patch,
        post_scene_opcode_doctor_json: patch,
        scene_start_doctor_json: patch,
        script_burst_doctor_json: patch,
        disconnect_pivot_doctor_json: patch,
        post_ready_cadence_doctor_json: patch,
        ready_signal_doctor_json: patch,
        attempt_diff_json: patch,
        loopback_doctor_json: patch,
        black_screen_capture_json: patch,
        plateau_diff_json: patch,
        js5_archive_resolution_json: patch,
        scene_delivery_json: patch,
        interface_json: patch,
        active_sub_json: patch,
        sender_json: patch,
        curated_json: patch,
        evidence_index: patch,
        verified_packets: patch,
        phase5_packets: patch,
        phase3_candidates: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            labels = root / "labels.json"
            decomp_dir = root / "ghidra-projects"
            ghidra_dir = root / "ghidra"
            write_text(world_log, "20:00:00 world-stage stage=appearance\n")
            write_text(labels, "{\n  \"10:20\": \"stable\"\n}\n")
            write_text(phase3_candidates := root / "phase3.json", "{}\n")
            write_text(phase5_packets := root / "phase5.json", "{}\n")
            write_text(verified_packets := root / "verified.json", "{}\n")
            write_text(evidence_index := root / "evidence.json", "{}\n")
            write_text(curated_json := root / "curated.json", "{}\n")
            write_text(sender_json := root / "sender.json", "{}\n")
            write_text(active_sub_json := root / "active.json", "{}\n")
            write_text(interface_json := root / "diff.json", "{}\n")
            write_text(scene_delivery_json := root / "scene.json", "{}\n")
            write_text(js5_archive_resolution_json := root / "resolver.json", "{}\n")
            write_text(plateau_diff_json := root / "plateau.json", "{}\n")
            write_text(black_screen_capture_json := root / "capture.json", "{}\n")
            write_text(loopback_doctor_json := root / "loopback.json", "{}\n")
            write_text(attempt_diff_json := root / "attempt-diff.json", "{}\n")
            write_text(ready_signal_doctor_json := root / "ready-signal-doctor.json", "{}\n")
            write_text(post_ready_cadence_doctor_json := root / "post-ready-cadence-doctor.json", "{}\n")
            write_text(disconnect_pivot_doctor_json := root / "disconnect-pivot-doctor.json", "{}\n")
            write_text(script_burst_doctor_json := root / "script-burst-doctor.json", "{}\n")
            write_text(scene_start_doctor_json := root / "scene-start-doctor.json", "{}\n")
            write_text(post_scene_opcode_doctor_json := root / "post-scene-opcode-doctor.json", "{}\n")
            write_text(live_var_packet_doctor_json := root / "live-var-packet-doctor.json", "{}\n")
            write_text(forced_fallback_parity_doctor_json := root / "forced-fallback-parity-doctor.json", "{}\n")
            write_text(live_watch_json := root / "live-watch.json", "{}\n")
            write_text(runtime_json := root / "runtime.json", "{}\n")
            write_text(ghidra_dir / "support" / "analyzeHeadless.bat", "echo headless")
            decomp_dir.mkdir(parents=True, exist_ok=True)

            with ExitStack() as stack:
                stack.enter_context(patch("run_946_tool_doctor.PHASE3_CANDIDATES", phase3_candidates))
                stack.enter_context(patch("run_946_tool_doctor.PHASE5_PACKETS", phase5_packets))
                stack.enter_context(patch("run_946_tool_doctor.VERIFIED_PACKETS", verified_packets))
                stack.enter_context(patch("run_946_tool_doctor.EVIDENCE_INDEX", evidence_index))
                stack.enter_context(patch("run_946_tool_doctor.CURATED_COMPARE_JSON", curated_json))
                stack.enter_context(patch("run_946_tool_doctor.SENDER_ANALYSIS_JSON", sender_json))
                stack.enter_context(patch("run_946_tool_doctor.ACTIVE_SUB_JSON", active_sub_json))
                stack.enter_context(patch("run_946_tool_doctor.INTERFACE_DIFF_JSON", interface_json))
                stack.enter_context(patch("run_946_tool_doctor.SCENE_DELIVERY_JSON", scene_delivery_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.JS5_ARCHIVE_RESOLUTION_JSON", js5_archive_resolution_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.PLATEAU_DIFF_JSON", plateau_diff_json))
                stack.enter_context(patch("run_946_tool_doctor.BLACK_SCREEN_CAPTURE_JSON", black_screen_capture_json))
                stack.enter_context(patch("run_946_tool_doctor.LOOPBACK_DOCTOR_JSON", loopback_doctor_json))
                stack.enter_context(patch("run_946_tool_doctor.ATTEMPT_DIFF_JSON", attempt_diff_json))
                stack.enter_context(patch("run_946_tool_doctor.READY_SIGNAL_DOCTOR_JSON", ready_signal_doctor_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.POST_READY_CADENCE_DOCTOR_JSON", post_ready_cadence_doctor_json)
                )
                stack.enter_context(
                    patch("run_946_tool_doctor.DISCONNECT_PIVOT_DOCTOR_JSON", disconnect_pivot_doctor_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.SCRIPT_BURST_DOCTOR_JSON", script_burst_doctor_json))
                stack.enter_context(patch("run_946_tool_doctor.SCENE_START_DOCTOR_JSON", scene_start_doctor_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.POST_SCENE_OPCODE_DOCTOR_JSON", post_scene_opcode_doctor_json)
                )
                stack.enter_context(
                    patch("run_946_tool_doctor.LIVE_VAR_PACKET_DOCTOR_JSON", live_var_packet_doctor_json)
                )
                stack.enter_context(
                    patch("run_946_tool_doctor.FORCED_FALLBACK_PARITY_DOCTOR_JSON", forced_fallback_parity_doctor_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.CLIENT_LIVE_WATCH_JSON", live_watch_json))
                stack.enter_context(patch("run_946_tool_doctor.RUNTIME_VERIFIER_JSON", runtime_json))
                artifact = analyze_doctor(
                    SimpleNamespace(
                        world_log=world_log,
                        labels=labels,
                        decomp_log_dir=decomp_dir,
                        ghidra_dir=ghidra_dir,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["status"], "ok")
        self.assertIn("toolReadiness", artifact)
        self.assertTrue(any(row["tool"] == "run_946_attempt_diff" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_ready_signal_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_post_ready_cadence_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_disconnect_pivot_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_script_burst_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_scene_start_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_post_scene_opcode_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_live_var_packet_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "run_946_forced_fallback_parity_doctor" for row in artifact["toolReadiness"]))
        self.assertTrue(any(row["tool"] == "watch_rs2client_live" for row in artifact["toolReadiness"]))
        self.assertIn("# 946 Tool Doctor", render_markdown(artifact))

    @patch("run_946_tool_doctor.PHASE3_CANDIDATES")
    @patch("run_946_tool_doctor.PHASE5_PACKETS")
    @patch("run_946_tool_doctor.VERIFIED_PACKETS")
    @patch("run_946_tool_doctor.EVIDENCE_INDEX")
    @patch("run_946_tool_doctor.CURATED_COMPARE_JSON")
    @patch("run_946_tool_doctor.SENDER_ANALYSIS_JSON")
    @patch("run_946_tool_doctor.ACTIVE_SUB_JSON")
    @patch("run_946_tool_doctor.INTERFACE_DIFF_JSON")
    @patch("run_946_tool_doctor.SCENE_DELIVERY_JSON")
    @patch("run_946_tool_doctor.JS5_ARCHIVE_RESOLUTION_JSON")
    @patch("run_946_tool_doctor.PLATEAU_DIFF_JSON")
    @patch("run_946_tool_doctor.BLACK_SCREEN_CAPTURE_JSON")
    @patch("run_946_tool_doctor.LOOPBACK_DOCTOR_JSON")
    @patch("run_946_tool_doctor.ATTEMPT_DIFF_JSON")
    @patch("run_946_tool_doctor.READY_SIGNAL_DOCTOR_JSON")
    @patch("run_946_tool_doctor.SCENE_START_DOCTOR_JSON")
    @patch("run_946_tool_doctor.RUNTIME_VERIFIER_JSON")
    def test_doctor_surfaces_prelogin_route_regression_reasoning(
        self,
        runtime_json: patch,
        scene_start_doctor_json: patch,
        ready_signal_doctor_json: patch,
        attempt_diff_json: patch,
        loopback_doctor_json: patch,
        black_screen_capture_json: patch,
        plateau_diff_json: patch,
        js5_archive_resolution_json: patch,
        scene_delivery_json: patch,
        interface_json: patch,
        active_sub_json: patch,
        sender_json: patch,
        curated_json: patch,
        evidence_index: patch,
        verified_packets: patch,
        phase5_packets: patch,
        phase3_candidates: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            labels = root / "labels.json"
            decomp_dir = root / "ghidra-projects"
            ghidra_dir = root / "ghidra"
            write_text(world_log, "20:00:00 world-stage stage=appearance\n")
            write_text(labels, "{\n  \"10:20\": \"stable\"\n}\n")
            write_text(phase3_candidates := root / "phase3.json", "{}\n")
            write_text(phase5_packets := root / "phase5.json", "{}\n")
            write_text(verified_packets := root / "verified.json", "{}\n")
            write_text(evidence_index := root / "evidence.json", "{}\n")
            write_text(curated_json := root / "curated.json", "{}\n")
            write_text(sender_json := root / "sender.json", "{}\n")
            write_text(active_sub_json := root / "active.json", "{}\n")
            write_text(interface_json := root / "diff.json", "{}\n")
            write_text(
                scene_delivery_json := root / "scene.json",
                "{\n  \"verdict\": {\"likelyBlocker\": \"prelogin-route-regression\"}\n}\n",
            )
            write_text(js5_archive_resolution_json := root / "resolver.json", "{}\n")
            write_text(plateau_diff_json := root / "plateau.json", "{}\n")
            write_text(
                black_screen_capture_json := root / "capture.json",
                "{\n  \"summary\": {\"statusReason\": \"prelogin-route-regression\"}\n}\n",
            )
            write_text(loopback_doctor_json := root / "loopback.json", "{}\n")
            write_text(attempt_diff_json := root / "attempt-diff.json", "{}\n")
            write_text(ready_signal_doctor_json := root / "ready-signal-doctor.json", "{}\n")
            write_text(scene_start_doctor_json := root / "scene-start-doctor.json", "{}\n")
            write_text(forced_fallback_parity_doctor_json := root / "forced-fallback-parity-doctor.json", "{}\n")
            write_text(runtime_json := root / "runtime.json", "{}\n")
            write_text(ghidra_dir / "support" / "analyzeHeadless.bat", "echo headless")
            decomp_dir.mkdir(parents=True, exist_ok=True)

            with ExitStack() as stack:
                stack.enter_context(patch("run_946_tool_doctor.PHASE3_CANDIDATES", phase3_candidates))
                stack.enter_context(patch("run_946_tool_doctor.PHASE5_PACKETS", phase5_packets))
                stack.enter_context(patch("run_946_tool_doctor.VERIFIED_PACKETS", verified_packets))
                stack.enter_context(patch("run_946_tool_doctor.EVIDENCE_INDEX", evidence_index))
                stack.enter_context(patch("run_946_tool_doctor.CURATED_COMPARE_JSON", curated_json))
                stack.enter_context(patch("run_946_tool_doctor.SENDER_ANALYSIS_JSON", sender_json))
                stack.enter_context(patch("run_946_tool_doctor.ACTIVE_SUB_JSON", active_sub_json))
                stack.enter_context(patch("run_946_tool_doctor.INTERFACE_DIFF_JSON", interface_json))
                stack.enter_context(patch("run_946_tool_doctor.SCENE_DELIVERY_JSON", scene_delivery_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.JS5_ARCHIVE_RESOLUTION_JSON", js5_archive_resolution_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.PLATEAU_DIFF_JSON", plateau_diff_json))
                stack.enter_context(patch("run_946_tool_doctor.BLACK_SCREEN_CAPTURE_JSON", black_screen_capture_json))
                stack.enter_context(patch("run_946_tool_doctor.LOOPBACK_DOCTOR_JSON", loopback_doctor_json))
                stack.enter_context(patch("run_946_tool_doctor.ATTEMPT_DIFF_JSON", attempt_diff_json))
                stack.enter_context(patch("run_946_tool_doctor.READY_SIGNAL_DOCTOR_JSON", ready_signal_doctor_json))
                stack.enter_context(patch("run_946_tool_doctor.SCENE_START_DOCTOR_JSON", scene_start_doctor_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.FORCED_FALLBACK_PARITY_DOCTOR_JSON", forced_fallback_parity_doctor_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.RUNTIME_VERIFIER_JSON", runtime_json))
                artifact = analyze_doctor(
                    SimpleNamespace(
                        world_log=world_log,
                        labels=labels,
                        decomp_log_dir=decomp_dir,
                        ghidra_dir=ghidra_dir,
                        output_dir=root,
                    )
                )

        scene_row = next(row for row in artifact["toolReadiness"] if row["tool"] == "run_946_scene_delivery_aid")
        capture_row = next(row for row in artifact["toolReadiness"] if row["tool"] == "run_946_black_screen_capture")
        self.assertIn("pre-login MITM route regression", scene_row["reason"])
        self.assertIn("regressed before login", capture_row["reason"])

    @patch("run_946_tool_doctor.PHASE3_CANDIDATES")
    @patch("run_946_tool_doctor.PHASE5_PACKETS")
    @patch("run_946_tool_doctor.VERIFIED_PACKETS")
    @patch("run_946_tool_doctor.EVIDENCE_INDEX")
    @patch("run_946_tool_doctor.CURATED_COMPARE_JSON")
    @patch("run_946_tool_doctor.SENDER_ANALYSIS_JSON")
    @patch("run_946_tool_doctor.ACTIVE_SUB_JSON")
    @patch("run_946_tool_doctor.INTERFACE_DIFF_JSON")
    @patch("run_946_tool_doctor.SCENE_DELIVERY_JSON")
    @patch("run_946_tool_doctor.JS5_ARCHIVE_RESOLUTION_JSON")
    @patch("run_946_tool_doctor.PLATEAU_DIFF_JSON")
    @patch("run_946_tool_doctor.BLACK_SCREEN_CAPTURE_JSON")
    @patch("run_946_tool_doctor.LOOPBACK_DOCTOR_JSON")
    @patch("run_946_tool_doctor.ATTEMPT_DIFF_JSON")
    @patch("run_946_tool_doctor.READY_SIGNAL_DOCTOR_JSON")
    @patch("run_946_tool_doctor.SCENE_START_DOCTOR_JSON")
    @patch("run_946_tool_doctor.RUNTIME_VERIFIER_JSON")
    def test_doctor_surfaces_content_route_bypass_reasoning(
        self,
        runtime_json: patch,
        scene_start_doctor_json: patch,
        ready_signal_doctor_json: patch,
        attempt_diff_json: patch,
        loopback_doctor_json: patch,
        black_screen_capture_json: patch,
        plateau_diff_json: patch,
        js5_archive_resolution_json: patch,
        scene_delivery_json: patch,
        interface_json: patch,
        active_sub_json: patch,
        sender_json: patch,
        curated_json: patch,
        evidence_index: patch,
        verified_packets: patch,
        phase5_packets: patch,
        phase3_candidates: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            labels = root / "labels.json"
            decomp_dir = root / "ghidra-projects"
            ghidra_dir = root / "ghidra"
            write_text(world_log, "20:00:00 world-stage stage=appearance\n")
            write_text(labels, "{\n  \"10:20\": \"stable\"\n}\n")
            write_text(phase3_candidates := root / "phase3.json", "{}\n")
            write_text(phase5_packets := root / "phase5.json", "{}\n")
            write_text(verified_packets := root / "verified.json", "{}\n")
            write_text(evidence_index := root / "evidence.json", "{}\n")
            write_text(curated_json := root / "curated.json", "{}\n")
            write_text(sender_json := root / "sender.json", "{}\n")
            write_text(active_sub_json := root / "active.json", "{}\n")
            write_text(interface_json := root / "diff.json", "{}\n")
            write_text(
                scene_delivery_json := root / "scene.json",
                "{\n  \"verdict\": {\"likelyBlocker\": \"content-route-bypassed-local-mitm\"}\n}\n",
            )
            write_text(js5_archive_resolution_json := root / "resolver.json", "{}\n")
            write_text(plateau_diff_json := root / "plateau.json", "{}\n")
            write_text(
                black_screen_capture_json := root / "capture.json",
                "{\n  \"summary\": {\"statusReason\": \"content-route-bypassed-local-mitm\"}\n}\n",
            )
            write_text(loopback_doctor_json := root / "loopback.json", "{}\n")
            write_text(attempt_diff_json := root / "attempt-diff.json", "{}\n")
            write_text(ready_signal_doctor_json := root / "ready-signal-doctor.json", "{}\n")
            write_text(scene_start_doctor_json := root / "scene-start-doctor.json", "{}\n")
            write_text(forced_fallback_parity_doctor_json := root / "forced-fallback-parity-doctor.json", "{}\n")
            write_text(runtime_json := root / "runtime.json", "{}\n")
            write_text(ghidra_dir / "support" / "analyzeHeadless.bat", "echo headless")
            decomp_dir.mkdir(parents=True, exist_ok=True)

            with ExitStack() as stack:
                stack.enter_context(patch("run_946_tool_doctor.PHASE3_CANDIDATES", phase3_candidates))
                stack.enter_context(patch("run_946_tool_doctor.PHASE5_PACKETS", phase5_packets))
                stack.enter_context(patch("run_946_tool_doctor.VERIFIED_PACKETS", verified_packets))
                stack.enter_context(patch("run_946_tool_doctor.EVIDENCE_INDEX", evidence_index))
                stack.enter_context(patch("run_946_tool_doctor.CURATED_COMPARE_JSON", curated_json))
                stack.enter_context(patch("run_946_tool_doctor.SENDER_ANALYSIS_JSON", sender_json))
                stack.enter_context(patch("run_946_tool_doctor.ACTIVE_SUB_JSON", active_sub_json))
                stack.enter_context(patch("run_946_tool_doctor.INTERFACE_DIFF_JSON", interface_json))
                stack.enter_context(patch("run_946_tool_doctor.SCENE_DELIVERY_JSON", scene_delivery_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.JS5_ARCHIVE_RESOLUTION_JSON", js5_archive_resolution_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.PLATEAU_DIFF_JSON", plateau_diff_json))
                stack.enter_context(patch("run_946_tool_doctor.BLACK_SCREEN_CAPTURE_JSON", black_screen_capture_json))
                stack.enter_context(patch("run_946_tool_doctor.LOOPBACK_DOCTOR_JSON", loopback_doctor_json))
                stack.enter_context(patch("run_946_tool_doctor.ATTEMPT_DIFF_JSON", attempt_diff_json))
                stack.enter_context(patch("run_946_tool_doctor.READY_SIGNAL_DOCTOR_JSON", ready_signal_doctor_json))
                stack.enter_context(patch("run_946_tool_doctor.SCENE_START_DOCTOR_JSON", scene_start_doctor_json))
                stack.enter_context(
                    patch("run_946_tool_doctor.FORCED_FALLBACK_PARITY_DOCTOR_JSON", forced_fallback_parity_doctor_json)
                )
                stack.enter_context(patch("run_946_tool_doctor.RUNTIME_VERIFIER_JSON", runtime_json))
                artifact = analyze_doctor(
                    SimpleNamespace(
                        world_log=world_log,
                        labels=labels,
                        decomp_log_dir=decomp_dir,
                        ghidra_dir=ghidra_dir,
                        output_dir=root,
                    )
                )

        scene_row = next(row for row in artifact["toolReadiness"] if row["tool"] == "run_946_scene_delivery_aid")
        capture_row = next(row for row in artifact["toolReadiness"] if row["tool"] == "run_946_black_screen_capture")
        self.assertIn("bypassed the local content MITM route", scene_row["reason"])
        self.assertIn("bypassed the local content MITM route", capture_row["reason"])


if __name__ == "__main__":
    unittest.main()
