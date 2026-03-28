from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_plateau_diff import build_artifact, render_markdown, scene_snapshot


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_world_log() -> str:
    return "\n".join(
        [
            "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
            "2026-03-16T18:00:01.000000Z world-stage stage=interfaces",
            "2026-03-16T18:00:02.000000Z recv-raw stage=interfaces opcode=48 bytes=1 preview=aa",
            "2026-03-16T18:00:03.000000Z send-raw stage=interfaces opcode=42 bytes=66 preview=bb",
            "2026-03-16T18:01:00.000000Z world-stage stage=appearance",
            "2026-03-16T18:01:01.000000Z world-stage stage=interfaces",
            "2026-03-16T18:01:02.000000Z recv-raw stage=interfaces opcode=48 bytes=1 preview=aa",
            "2026-03-16T18:01:03.000000Z send-raw stage=interfaces opcode=42 bytes=66 preview=bb",
        ]
    ) + "\n"


class PlateauDiffTest(unittest.TestCase):
    def test_scene_snapshot_supplies_default_content_capture_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            args = SimpleNamespace(
                world_log=root / "world.log",
                js5_session_dir=root / "js5",
                runtime_trace_dir=root / "runtime",
                clienterror_dir=root / "clienterror",
                output_dir=root,
            )
            with patch("run_946_plateau_diff.build_scene_delivery_artifact", return_value={"status": "ok"}) as mock_build:
                scene_snapshot(args, "1:4")

            namespace = mock_build.call_args.args[0]
            self.assertTrue(hasattr(namespace, "content_capture_dir"))
            self.assertTrue(str(namespace.content_capture_dir).endswith("data\\debug\\lobby-tls-terminator"))

    @patch("run_946_plateau_diff.input_fingerprint", return_value="fingerprint")
    def test_identical_plateaus_produce_empty_opcode_delta(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            write_text(world_log, build_world_log())
            scene = {
                "status": "ok",
                "summary": {"sceneDeliveryState": "archive-delivery-observed", "archiveRequestsObserved": 2},
                "runtimeTrace": {"summary": {"timeoutCount": 0}},
            }
            with patch("run_946_plateau_diff.scene_snapshot", side_effect=[scene, scene]):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        left_window="1:4",
                        right_window="5:8",
                        labels=root / "labels.json",
                        js5_session_dir=root / "js5",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["deltas"]["clientOpcodes"]["missingInRight"], {})
        self.assertIn("# 946 Plateau Diff", render_markdown(artifact))

    @patch("run_946_plateau_diff.input_fingerprint", return_value="fingerprint")
    def test_asset_delivery_divergence_is_ranked_first(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            write_text(world_log, build_world_log())
            left_scene = {
                "status": "ok",
                "summary": {"sceneDeliveryState": "archive-delivery-observed", "archiveRequestsObserved": 3},
                "runtimeTrace": {"summary": {"timeoutCount": 0}},
            }
            right_scene = {
                "status": "partial",
                "summary": {"sceneDeliveryState": "reference-tables-only", "archiveRequestsObserved": 0},
                "runtimeTrace": {"summary": {"timeoutCount": 0}},
            }
            with patch("run_946_plateau_diff.scene_snapshot", side_effect=[left_scene, right_scene]):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        left_window="1:4",
                        right_window="5:8",
                        labels=root / "labels.json",
                        js5_session_dir=root / "js5",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["summary"]["topHypothesis"], "asset-delivery stall")

    @patch("run_946_plateau_diff.input_fingerprint", return_value="fingerprint")
    def test_runtime_only_divergence_surfaces_scene_settle_stall(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            write_text(world_log, build_world_log())
            left_scene = {
                "status": "ok",
                "summary": {"sceneDeliveryState": "archive-delivery-observed", "archiveRequestsObserved": 2},
                "runtimeTrace": {"summary": {"timeoutCount": 0}},
            }
            right_scene = {
                "status": "partial",
                "summary": {"sceneDeliveryState": "archive-delivery-observed-but-runtime-stalled", "archiveRequestsObserved": 2},
                "runtimeTrace": {"summary": {"timeoutCount": 3}},
            }
            with patch("run_946_plateau_diff.scene_snapshot", side_effect=[left_scene, right_scene]):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        left_window="1:4",
                        right_window="5:8",
                        labels=root / "labels.json",
                        js5_session_dir=root / "js5",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["summary"]["topHypothesis"], "scene settle stall")


if __name__ == "__main__":
    unittest.main()
