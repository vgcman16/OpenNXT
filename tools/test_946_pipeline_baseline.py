from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_pipeline import (
    CURATED_COMPARE_PHASE,
    classify_drift_category,
    curated_compare_input_fingerprint,
    maybe_run_curated_compare,
    summarize_drift_categories,
    write_pipeline_manifest,
    write_run_report,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PipelineBaselineTest(unittest.TestCase):
    def test_classify_drift_category_groups_new_shared_artifacts(self) -> None:
        self.assertEqual(classify_drift_category("C:/x/handoff-analysis.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/sender-analysis.md"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/curated-compare.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/opcode-113-verdict.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/scene-delivery-analysis.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/js5-archive-resolution.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/plateau-diff.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/black-screen-capture.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/tool-doctor.json"), "shared-evidence")
        self.assertEqual(classify_drift_category("C:/x/verified-packets.json"), "promotion-surface")
        self.assertEqual(classify_drift_category("C:/x/runtime-verification-results.json"), "runtime-results")

    def test_summarize_drift_categories_distinguishes_informational_from_promotion(self) -> None:
        summary = summarize_drift_categories(
            [
                {"path": "C:/x/handoff-analysis.json"},
                {"path": "C:/x/sender-analysis.json"},
                {"path": "C:/x/curated-compare.md"},
                {"path": "C:/x/opcode-113-verdict.md"},
                {"path": "C:/x/scene-delivery-analysis.md"},
                {"path": "C:/x/js5-archive-resolution.md"},
                {"path": "C:/x/plateau-diff.md"},
                {"path": "C:/x/black-screen-capture.md"},
                {"path": "C:/x/tool-doctor.md"},
                {"path": "C:/x/verified-packets.json"},
            ]
        )
        self.assertFalse(summary["informationalOnly"])
        self.assertEqual(summary["categories"]["shared-evidence"], 9)
        self.assertEqual(summary["categories"]["promotion-surface"], 1)

    def test_curated_compare_input_fingerprint_changes_with_labels_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            labels_path = Path(tmpdir) / "labels.json"
            write_text(labels_path, "{\n  \"10:20\": \"stable\"\n}\n")
            first = curated_compare_input_fingerprint(labels_path)
            write_text(labels_path, "{\n  \"10:20\": \"loop\"\n}\n")
            second = curated_compare_input_fingerprint(labels_path)
            self.assertNotEqual(first, second)

    def test_cached_curated_compare_pass_returns_cached_without_running_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_json = Path(tmpdir) / "curated-compare.json"
            output_md = Path(tmpdir) / "curated-compare.md"
            write_text(output_json, "{}\n")
            write_text(output_md, "# report\n")
            cache_manifest = {
                CURATED_COMPARE_PHASE: {
                    "inputFingerprint": "fingerprint-1",
                    "outputs": [str(output_json), str(output_md)],
                }
            }
            args = SimpleNamespace(force=False)
            with patch("run_946_pipeline.CURATED_COMPARE_OUTPUTS", [output_json, output_md]), patch(
                "run_946_pipeline.curated_compare_input_fingerprint",
                return_value="fingerprint-1",
            ):
                result = maybe_run_curated_compare(args, cache_manifest)
            self.assertEqual(result["status"], "cached")
            self.assertEqual(result["phase"], CURATED_COMPARE_PHASE)

    def test_pipeline_manifest_and_run_report_include_curated_compare(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)
            curated_compare = {
                "status": "ok",
                "confidence": "high",
                "advisoryReady": True,
                "labelsPresent": True,
                "labels": {"appliedCount": 4},
                "seedSource": "labeled",
                "anchorPairSource": "labeled",
                "recommendationRationale": "Seed-compatible bundle only.",
                "bestKnownBaseline": {"recommendedFeatures": [{"feature": "minimal_varcs_sent"}]},
            }
            manifest = write_pipeline_manifest(
                shared_dir,
                phase_runs=[{"phase": CURATED_COMPARE_PHASE, "status": "cached"}],
                phase1_health={},
                evidence_index=[],
                cross_build_index={"packets": []},
                handoff_analysis={},
                sender_analysis={},
                curated_compare=curated_compare,
                opcode_113_verdict={},
                active_sub_analysis={},
                interface_diff={},
                scene_delivery={"status": "partial", "summary": {"relevantJs5SessionCount": 1, "sceneDeliveryState": "reference-tables-only"}, "verdict": {"likelyBlocker": "client-never-progressed-to-scene-archive-delivery"}},
                js5_archive_resolution={"status": "ok", "resolutions": [{"label": "archive[5,1]"}]},
                plateau_diff={"status": "ok", "hypotheses": [{"kind": "scene settle stall"}]},
                black_screen_capture={"status": "partial", "summary": {"worldWindowSelected": "10:20", "overlapAchieved": False}},
                tool_doctor={"status": "ok", "summary": {"blockedCount": 0, "partialCount": 0}},
                runtime_results={"status": "ok"},
                drift_summary={"categories": {"shared-evidence": 1}, "informationalOnly": True},
            )
            write_run_report(
                shared_dir,
                phase_runs=[{"phase": CURATED_COMPARE_PHASE, "status": "cached"}],
                baseline_drift=[],
                drift_summary={"categories": {}, "informationalOnly": False},
                runtime_results=None,
                handoff_analysis={},
                sender_analysis={},
                curated_compare=curated_compare,
                opcode_113_verdict={},
                active_sub_analysis={},
                interface_diff={},
                scene_delivery={"status": "partial", "summary": {"relevantJs5SessionCount": 1, "sceneDeliveryState": "reference-tables-only"}, "verdict": {"likelyBlocker": "client-never-progressed-to-scene-archive-delivery"}},
                js5_archive_resolution={"status": "ok", "resolutions": [{"label": "archive[5,1]"}]},
                plateau_diff={"status": "ok", "hypotheses": [{"kind": "scene settle stall"}]},
                black_screen_capture={"status": "partial", "summary": {"worldWindowSelected": "10:20", "overlapAchieved": False}},
                tool_doctor={"status": "ok", "summary": {"blockedCount": 0, "partialCount": 0}},
            )

            report_text = (shared_dir / "run-report.md").read_text(encoding="utf-8")
            self.assertTrue(manifest["counts"]["curatedComparePresent"])
            self.assertTrue(manifest["counts"]["curatedCompareAdvisoryReady"])
            self.assertEqual(manifest["curatedCompare"]["confidence"], "high")
            self.assertIn("curatedCompareJson", manifest["artifacts"])
            self.assertIn("toolDoctorJson", manifest["artifacts"])
            self.assertIn("sceneDeliveryJson", manifest["artifacts"])
            self.assertIn("js5ArchiveResolutionJson", manifest["artifacts"])
            self.assertIn("plateauDiffJson", manifest["artifacts"])
            self.assertIn("blackScreenCaptureJson", manifest["artifacts"])
            self.assertIn("toolReadiness", manifest)
            self.assertIn("## Curated Compare", report_text)
            self.assertIn("## Scene Delivery Aid", report_text)
            self.assertIn("## JS5 Archive Resolver", report_text)
            self.assertIn("## Plateau Diff", report_text)
            self.assertIn("## Black Screen Capture", report_text)
            self.assertIn("## Tool Doctor", report_text)
            self.assertIn("## Tool Readiness", report_text)
            self.assertIn("Advisory ready", report_text)


if __name__ == "__main__":
    unittest.main()
