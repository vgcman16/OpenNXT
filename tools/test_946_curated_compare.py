from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from protocol_946_debug_common import build_session, parse_world_log, session_summary
from run_946_curated_compare import (
    analyze_curated_compare,
    build_feature_fingerprint,
    build_recommended_bundle,
    classify_session_outcome,
    load_labels,
    session_window,
)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def event(
    line_number: int,
    *,
    timestamp: str,
    kind: str,
    stage: str = "",
    opcode: int | None = None,
    bytes: int | None = None,
    preview: str = "",
    player_name: str = "demon",
    data: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "lineNumber": line_number,
        "timestamp": timestamp,
        "kind": kind,
        "stage": stage,
        "opcode": opcode,
        "bytes": bytes,
        "preview": preview,
        "playerName": player_name,
        "data": data or {},
        "raw": "",
    }


def make_session(*events: dict[str, object]) -> dict[str, object]:
    return build_session(list(events))


def stable_session_lines(minute: int, *, player_info_count: int = 25, extra_lines: list[str] | None = None) -> list[str]:
    lines = [
        f"2026-03-15T20:{minute:02d}:00Z world-stage name=demon stage=appearance",
        f"2026-03-15T20:{minute:02d}:01Z world-stage name=demon stage=interfaces",
    ]
    lines.extend(extra_lines or [])
    base_second = 2 + len(extra_lines or [])
    for index in range(player_info_count):
        second = base_second + index
        lines.append(
            f"2026-03-15T20:{minute:02d}:{second:02d}Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:{minute} stage=interfaces preview=aa"
        )
    return lines


def short_loop_lines(minute: int, *, count: int = 1) -> list[str]:
    lines = [
        f"2026-03-15T20:{minute:02d}:00Z world-stage name=demon stage=appearance",
        f"2026-03-15T20:{minute:02d}:01Z world-stage name=demon stage=interfaces",
    ]
    for index in range(count):
        lines.append(
            f"2026-03-15T20:{minute:02d}:{2 + index:02d}Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:{minute} stage=interfaces preview=bb"
        )
    return lines


def rebuild_fail_lines(minute: int) -> list[str]:
    return [
        f"2026-03-15T20:{minute:02d}:00Z world-stage name=demon stage=appearance",
        f"2026-03-15T20:{minute:02d}:01Z world-stage name=demon stage=rebuild",
    ]


def append_session(log_lines: list[str], session_lines: list[str]) -> str:
    start = len(log_lines) + 1
    log_lines.extend(session_lines)
    end = len(log_lines)
    return f"{start}:{end}"


class CuratedCompareTest(unittest.TestCase):
    def test_parse_world_log_captures_generic_world_markers_and_session_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:00:00Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:00:01Z world-send-minimal-varcs name=demon ids=181,1027,1034,3497",
                        "2026-03-15T20:00:02Z world-ready-signal name=demon opcode=113 bytes=4 preview=00000072 source=compat",
                        "2026-03-15T20:00:03Z send-raw opcode=42 bytes=66 remote=/127.0.0.1:1 stage=interfaces preview=aa",
                    ]
                )
                + "\n",
            )

            events = parse_world_log(world_log)
            session = build_session(events)
            summary = session_summary(session)

            self.assertEqual([entry["kind"] for entry in events][1:3], ["world-send-minimal-varcs", "world-ready-signal"])
            self.assertEqual(summary["markerCounts"]["world-send-minimal-varcs"], 1)
            self.assertEqual(summary["markerCounts"]["world-ready-signal"], 1)
            self.assertEqual(summary["serverOpcodeCounts"][42], 1)
            self.assertEqual(summary["durationSeconds"], 3.0)

    def test_load_labels_supports_simple_and_rich_map(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            simple_path = Path(tmpdir) / "simple.json"
            rich_path = Path(tmpdir) / "rich.json"
            write_json_file(simple_path, {"10:20": "loop"})
            write_json_file(
                rich_path,
                {
                    "sessions": {
                        "30:40": {
                            "label": "stable",
                            "note": "seed session",
                            "role": "seed",
                        }
                    }
                },
            )

            simple = load_labels(simple_path)
            rich = load_labels(rich_path)

            self.assertEqual(simple["format"], "simple-map")
            self.assertEqual(simple["entries"]["10:20"]["normalizedOutcome"], "short_loop")
            self.assertEqual(rich["format"], "rich-map")
            self.assertEqual(rich["entries"]["30:40"]["role"], "seed")
            self.assertEqual(rich["entries"]["30:40"]["note"], "seed session")

    def test_classify_session_outcomes_and_manual_override(self) -> None:
        stable_events = [
            event(1, timestamp="2026-03-15T20:00:00Z", kind="world-stage", stage="appearance"),
            event(2, timestamp="2026-03-15T20:00:01Z", kind="world-stage", stage="interfaces"),
        ]
        stable_events.extend(
            event(
                3 + index,
                timestamp=f"2026-03-15T20:00:{2 + index:02d}Z",
                kind="send-raw",
                stage="interfaces",
                opcode=42,
                bytes=3,
            )
            for index in range(25)
        )
        stable_session = make_session(*stable_events)

        short_loop_session = make_session(
            event(1, timestamp="2026-03-15T20:01:00Z", kind="world-stage", stage="appearance"),
            event(2, timestamp="2026-03-15T20:01:01Z", kind="world-stage", stage="interfaces"),
            event(3, timestamp="2026-03-15T20:01:02Z", kind="send-raw", stage="interfaces", opcode=42, bytes=3),
        )
        rebuild_fail_session = make_session(
            event(1, timestamp="2026-03-15T20:02:00Z", kind="world-stage", stage="appearance"),
            event(2, timestamp="2026-03-15T20:02:01Z", kind="world-stage", stage="rebuild"),
        )

        labels = {session_window(stable_session): "crash"}

        self.assertEqual(classify_session_outcome(stable_session, {})[0], "stable_interfaces")
        self.assertEqual(classify_session_outcome(short_loop_session, {})[0], "short_loop")
        self.assertEqual(classify_session_outcome(rebuild_fail_session, {})[0], "rebuild_fail")
        self.assertEqual(classify_session_outcome(stable_session, labels), ("short_loop", "manual", "crash"))

    def test_default_checked_in_labels_path_is_used_when_labels_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            labels_path = Path(tmpdir) / "labels.json"
            lines: list[str] = []
            stable_window = append_session(lines, stable_session_lines(0))
            bad_window = append_session(lines, short_loop_lines(1))
            write_text(world_log, "\n".join(lines) + "\n")
            write_json_file(
                labels_path,
                {
                    stable_window: {"label": "stable", "role": "seed"},
                    bad_window: {"label": "loop", "role": "bad"},
                },
            )

            fake_diff = {"status": "ok", "verdict": {"activePlayer116Sent": "no", "bootstrapMarkerPresent": "no", "interfaceStageDelta": "none", "handoffOutcomeChanged": "no"}, "topFindings": [], "diff": {}}
            args = SimpleNamespace(world_log=world_log, labels=None, good_count=5, bad_count=5, output_dir=Path(tmpdir))
            with patch("run_946_curated_compare.DEFAULT_LABELS_PATH", labels_path), patch("run_946_curated_compare.analyze_interface_diff", return_value=fake_diff):
                artifact = analyze_curated_compare(args)

            self.assertTrue(artifact["labelsPresent"])
            self.assertEqual(artifact["labels"]["path"], str(labels_path))
            self.assertEqual(artifact["seedSource"], "labeled")

    def test_labeled_stable_seed_beats_unlabeled_outlier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            labels_path = Path(tmpdir) / "labels.json"
            lines: list[str] = []
            unlabeled_outlier = append_session(lines, stable_session_lines(0, player_info_count=40))
            labeled_seed = append_session(lines, stable_session_lines(1, player_info_count=25))
            labeled_bad = append_session(lines, short_loop_lines(2))
            write_text(world_log, "\n".join(lines) + "\n")
            write_json_file(
                labels_path,
                {
                    labeled_seed: {"label": "stable", "role": "seed"},
                    labeled_bad: {"label": "loop", "role": "bad"},
                },
            )

            fake_diff = {"status": "ok", "verdict": {"activePlayer116Sent": "no", "bootstrapMarkerPresent": "no", "interfaceStageDelta": "material", "handoffOutcomeChanged": "yes"}, "topFindings": [], "diff": {}}
            args = SimpleNamespace(world_log=world_log, labels=labels_path, good_count=5, bad_count=5, output_dir=Path(tmpdir))
            with patch("run_946_curated_compare.analyze_interface_diff", return_value=fake_diff):
                artifact = analyze_curated_compare(args)

            self.assertEqual(artifact["seedSource"], "labeled")
            self.assertEqual(artifact["bestKnownBaseline"]["seedSession"]["window"], labeled_seed)
            self.assertNotEqual(artifact["bestKnownBaseline"]["seedSession"]["window"], unlabeled_outlier)

    def test_labeled_bad_session_beats_heuristic_bad_choice_for_anchor_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            labels_path = Path(tmpdir) / "labels.json"
            lines: list[str] = []
            stable_seed = append_session(lines, stable_session_lines(0))
            worse_unlabeled_bad = append_session(lines, short_loop_lines(1, count=1))
            labeled_bad = append_session(lines, short_loop_lines(2, count=3))
            write_text(world_log, "\n".join(lines) + "\n")
            write_json_file(
                labels_path,
                {
                    stable_seed: {"label": "stable", "role": "seed"},
                    labeled_bad: {"label": "loop", "role": "bad"},
                },
            )

            fake_diff = {"status": "ok", "verdict": {"activePlayer116Sent": "no", "bootstrapMarkerPresent": "no", "interfaceStageDelta": "material", "handoffOutcomeChanged": "yes"}, "topFindings": [{"category": "childInterfaces", "label": "IF_OPENSUB", "score": 1}], "diff": {}}
            args = SimpleNamespace(world_log=world_log, labels=labels_path, good_count=5, bad_count=5, output_dir=Path(tmpdir))
            with patch("run_946_curated_compare.analyze_interface_diff", return_value=fake_diff):
                artifact = analyze_curated_compare(args)

            self.assertEqual(artifact["anchorPairSource"], "labeled")
            self.assertEqual(artifact["anchorPair"]["badSession"]["window"], labeled_bad)
            self.assertNotEqual(artifact["anchorPair"]["badSession"]["window"], worse_unlabeled_bad)

    def test_confidence_and_advisory_ready_use_labeled_cohorts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            labels_path = Path(tmpdir) / "labels.json"
            lines: list[str] = []
            stable_seed = append_session(lines, stable_session_lines(0))
            stable_two = append_session(lines, stable_session_lines(1))
            bad_one = append_session(lines, short_loop_lines(2))
            bad_two = append_session(lines, rebuild_fail_lines(3))
            write_text(world_log, "\n".join(lines) + "\n")
            write_json_file(
                labels_path,
                {
                    stable_seed: {"label": "stable", "role": "seed"},
                    stable_two: {"label": "stable", "role": "stable"},
                    bad_one: {"label": "loop", "role": "bad"},
                    bad_two: {"label": "rebuild-fail", "role": "bad"},
                },
            )

            fake_diff = {"status": "ok", "verdict": {"activePlayer116Sent": "no", "bootstrapMarkerPresent": "no", "interfaceStageDelta": "material", "handoffOutcomeChanged": "yes"}, "topFindings": [], "diff": {}}
            args = SimpleNamespace(world_log=world_log, labels=labels_path, good_count=5, bad_count=5, output_dir=Path(tmpdir))
            with patch("run_946_curated_compare.analyze_interface_diff", return_value=fake_diff):
                artifact = analyze_curated_compare(args)

            self.assertEqual(artifact["confidence"], "high")
            self.assertTrue(artifact["advisoryReady"])
            self.assertEqual(artifact["labeledStableCount"], 2)
            self.assertEqual(artifact["labeledBadCount"], 2)

    def test_build_recommended_bundle_reports_no_synthetic_union_rationale(self) -> None:
        seed = {
            "window": "10:20",
            "outcome": "stable_interfaces",
            "outcomeSource": "manual",
            "manualLabel": "stable",
            "manualRole": "seed",
            "manualNote": None,
            "stabilityScore": 999,
            "summary": {"eventCount": 250, "durationSeconds": 40.0, "stageSequence": ["appearance", "interfaces"], "markerCounts": {}},
            "features": {
                "presence": {
                    "skip_deferred_completion_scripts": True,
                    "deferred_completion_scripts": False,
                },
                "playerInfo": {"count": 100, "firstLargeSendSize": 66},
            },
        }
        rankings = [
            {"feature": "deferred_completion_scripts", "stablePrevalence": 0.8, "shortLoopPrevalence": 0.1, "delta": 0.7, "verdict": "helped", "bundleEligible": True},
        ]

        bundle = build_recommended_bundle(seed, rankings)

        self.assertEqual(bundle["recommendedFeatures"], [])
        self.assertIn("did not coexist", bundle["rationale"])
        self.assertEqual(bundle["rejectedFeatures"][0]["reason"], "mutually-exclusive-with-seed:skip_deferred_completion_scripts")

    def test_anchor_pair_integration_embeds_pairwise_structural_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            labels_path = Path(tmpdir) / "labels.json"
            lines: list[str] = []
            stable_seed = append_session(lines, stable_session_lines(0))
            bad_session = append_session(lines, short_loop_lines(1))
            write_text(world_log, "\n".join(lines) + "\n")
            write_json_file(
                labels_path,
                {
                    stable_seed: {"label": "stable", "role": "seed"},
                    bad_session: {"label": "loop", "role": "bad"},
                },
            )

            fake_diff = {
                "status": "ok",
                "verdict": {
                    "activePlayer116Sent": "no",
                    "bootstrapMarkerPresent": "no",
                    "interfaceStageDelta": "material",
                    "handoffOutcomeChanged": "yes",
                },
                "topFindings": [{"category": "childInterfaces", "label": "IF_OPENSUB", "score": 42}],
                "diff": {},
            }

            args = SimpleNamespace(world_log=world_log, labels=labels_path, good_count=5, bad_count=5, output_dir=Path(tmpdir))
            with patch("run_946_curated_compare.analyze_interface_diff", return_value=fake_diff):
                artifact = analyze_curated_compare(args)

            self.assertEqual(artifact["status"], "ok")
            self.assertIsNotNone(artifact["anchorPair"])
            self.assertEqual(artifact["anchorPair"]["interfaceDiff"]["verdict"]["interfaceStageDelta"], "material")
            self.assertEqual(artifact["anchorPair"]["interfaceDiff"]["topFindings"][0]["label"], "IF_OPENSUB")

    def test_build_feature_fingerprint_tracks_requested_minimum_markers(self) -> None:
        session = make_session(
            event(1, timestamp="2026-03-15T20:00:00Z", kind="world-stage", stage="appearance"),
            event(2, timestamp="2026-03-15T20:00:01Z", kind="world-stage", stage="interfaces"),
            event(3, timestamp="2026-03-15T20:00:02Z", kind="world-send-minimal-varcs", stage="interfaces"),
            event(4, timestamp="2026-03-15T20:00:03Z", kind="world-post-initial-sync-hold", stage="interfaces"),
            event(5, timestamp="2026-03-15T20:00:04Z", kind="world-trimmed-interface-tail", stage="interfaces"),
            event(6, timestamp="2026-03-15T20:00:05Z", kind="world-map-build-complete-compat", stage="interfaces", opcode=113, bytes=4),
            event(7, timestamp="2026-03-15T20:00:06Z", kind="send-raw", stage="interfaces", opcode=116, bytes=25),
            event(8, timestamp="2026-03-15T20:00:07Z", kind="send-raw", stage="interfaces", opcode=42, bytes=66),
            event(9, timestamp="2026-03-15T20:00:08Z", kind="send-raw", stage="interfaces", opcode=42, bytes=3),
            event(10, timestamp="2026-03-15T20:00:09Z", kind="recv-raw", stage="interfaces", opcode=106, bytes=6),
        )

        fingerprint = build_feature_fingerprint(session)

        self.assertTrue(fingerprint["presence"]["compat_map_build_113"])
        self.assertTrue(fingerprint["presence"]["active_player_116_sent"])
        self.assertTrue(fingerprint["presence"]["minimal_varcs_sent"])
        self.assertTrue(fingerprint["presence"]["post_initial_hold"])
        self.assertTrue(fingerprint["presence"]["trimmed_interface_tail"])
        self.assertTrue(fingerprint["presence"]["full_initial_player_info"])
        self.assertEqual(fingerprint["serverOpcodeCounts"][116], 1)
        self.assertEqual(fingerprint["clientOpcodeCounts"][106], 1)


if __name__ == "__main__":
    unittest.main()
