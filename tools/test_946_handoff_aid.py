from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_handoff_aid import (
    PLAYER_INFO_OPCODE,
    analyze_handoff,
    build_handoff_diff,
    decomp_status_for_path,
    find_latest_session,
    parse_world_log,
    render_markdown,
)


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
SCRIPT_PATH = WORKSPACE / "tools" / "run_946_handoff_aid.py"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class HandoffAidTest(unittest.TestCase):
    def test_find_latest_session_uses_newest_appearance_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:00:00Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:00:01Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:10:00Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:10:01Z world-stage name=demon stage=login-response",
                        "2026-03-15T20:10:02Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-15T20:10:03Z world-stage name=demon stage=rebuild",
                        "2026-03-15T20:10:04Z world-stage name=demon stage=default-state",
                        "2026-03-15T20:10:05Z world-stage name=demon stage=interfaces",
                    ]
                )
                + "\n",
            )
            events = parse_world_log(world_log)
            session = find_latest_session(events)

            self.assertIsNotNone(session)
            self.assertEqual(session["startLine"], 3)
            self.assertEqual(session["stageSequence"], ["appearance", "login-response", "pipeline-switch", "rebuild", "default-state", "interfaces"])

    def test_analyze_handoff_surfaces_burst_and_player_info_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            world_log = temp_root / "world.log"
            decomp_dir = temp_root / "ghidra"
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:34:32Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:34:33Z world-stage name=demon stage=login-response",
                        "2026-03-15T20:34:34Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-15T20:34:35Z world-stage name=demon stage=rebuild",
                        "2026-03-15T20:34:36Z send-raw opcode=42 bytes=66 remote=/127.0.0.1:62816 stage=rebuild preview=010203",
                        "2026-03-15T20:34:37Z world-stage name=demon stage=default-state",
                        "2026-03-15T20:34:38Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:34:39Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:62816 stage=interfaces preview=007ff4",
                        "2026-03-15T20:34:40Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:62816 stage=interfaces preview=007ff4",
                        "2026-03-15T20:34:41Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:62816 stage=interfaces preview=007ff4",
                        "2026-03-15T20:34:42Z recv-raw opcode=83 bytes=1 remote=/127.0.0.1:62816 stage=interfaces preview=01",
                        "2026-03-15T20:34:43Z world-ignore-client-compat name=demon opcode=83 bytes=1 awaitingMapBuildComplete=false awaitingWorldReadySignal=false preview=01",
                        "2026-03-15T20:34:44Z recv-raw opcode=48 bytes=8 remote=/127.0.0.1:62816 stage=interfaces preview=1000f61d001904fa",
                        "2026-03-15T20:34:45Z recv-raw opcode=17 bytes=15 remote=/127.0.0.1:62816 stage=interfaces preview=0301f61d001c050000069d00071d00",
                        "2026-03-15T20:34:46Z recv-raw opcode=113 bytes=4 remote=/127.0.0.1:62816 stage=interfaces preview=00000001",
                    ]
                )
                + "\n",
            )
            write_text(
                decomp_dir / "decomp-1400cfcb0.log",
                "void FUN_1400cfcb0(void) {\n  return;\n}\n\n (GhidraScript)\n",
            )
            write_text(
                decomp_dir / "decomp-1400ced60.log",
                "void FUN_1400ced60(void) {\n  return;\n}\n\n (GhidraScript)\n",
            )

            artifact, used_logs = analyze_handoff(
                world_log_path=world_log,
                decomp_log_dir=decomp_dir,
                manual_opcodes=[],
            )

            suspect_opcodes = [entry["opcode"] for entry in artifact["suspects"]]
            self.assertEqual(suspect_opcodes, [17, 48, 83, 113])
            self.assertEqual(artifact["playerInfo"]["opcode"], PLAYER_INFO_OPCODE)
            self.assertEqual(artifact["playerInfo"]["firstLargeSendSize"], 66)
            self.assertEqual(artifact["playerInfo"]["repeatedTinyFrameCount"], 3)
            self.assertTrue(artifact["playerInfo"]["needsReview"])
            self.assertEqual(
                artifact["suspects"][2]["decompLog"]["status"],
                "clean",
            )
            self.assertEqual(
                artifact["suspects"][3]["decompLog"]["status"],
                "clean",
            )
            self.assertEqual(len(used_logs), 2)

    def test_runtime_markers_promote_unhandled_and_demote_handled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            world_log = temp_root / "world.log"
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:34:32Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:34:33Z world-stage name=demon stage=login-response",
                        "2026-03-15T20:34:34Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-15T20:34:35Z world-stage name=demon stage=rebuild",
                        "2026-03-15T20:34:36Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:34:37Z recv-raw opcode=28 bytes=8 remote=/127.0.0.1:62816 stage=interfaces preview=2601000101020501",
                        "2026-03-15T20:34:38Z world-client-bootstrap-blob name=demon opcode=28 bytes=8 entryCount=38 count=1 preview=2601000101020501 awaitingMapBuildComplete=false awaitingWorldReadySignal=false",
                        "2026-03-15T20:34:39Z recv-raw opcode=17 bytes=12 remote=/127.0.0.1:62816 stage=interfaces preview=0300ffff00bf028900081600",
                        "2026-03-15T20:34:40Z world-unhandled-client-compat name=demon opcode=17 bytes=12 preview=0300ffff00bf028900081600",
                    ]
                )
                + "\n",
            )

            artifact, _ = analyze_handoff(
                world_log_path=world_log,
                decomp_log_dir=temp_root / "ghidra",
                manual_opcodes=[],
            )

            suspect_by_opcode = {entry["opcode"]: entry for entry in artifact["suspects"]}
            self.assertEqual(suspect_by_opcode[28]["suspectClass"], "handled-report")
            self.assertEqual(suspect_by_opcode[28]["runtimeMarkers"]["handled"], 1)
            self.assertEqual(suspect_by_opcode[17]["suspectClass"], "likely-blocker")
            self.assertEqual(suspect_by_opcode[17]["runtimeMarkers"]["unhandled"], 1)

    def test_missing_world_log_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact, used_logs = analyze_handoff(
                world_log_path=Path(tmpdir) / "missing.log",
                decomp_log_dir=Path(tmpdir),
                manual_opcodes=[83],
            )

            self.assertEqual(artifact["status"], "partial")
            self.assertFalse(artifact["session"]["exists"])
            self.assertEqual(used_logs, [])

    def test_warning_only_decomp_log_is_classified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "decomp-140012340.log"
            write_text(path, "WARN  Decompiling 140012340: Unable to read bytes at ram:20ccccccc (DecompileCallback)\n")
            summary = decomp_status_for_path(path)
            self.assertEqual(summary["status"], "warning-only")

    def test_sender_aid_can_demote_state_report_suspect(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            world_log = temp_root / "world.log"
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:34:32Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:34:33Z world-stage name=demon stage=login-response",
                        "2026-03-15T20:34:34Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-15T20:34:35Z world-stage name=demon stage=rebuild",
                        "2026-03-15T20:34:36Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:34:42Z recv-raw opcode=83 bytes=1 remote=/127.0.0.1:62816 stage=interfaces preview=01",
                        "2026-03-15T20:34:46Z recv-raw opcode=113 bytes=4 remote=/127.0.0.1:62816 stage=interfaces preview=00000001",
                    ]
                )
                + "\n",
            )

            artifact, _ = analyze_handoff(
                world_log_path=world_log,
                decomp_log_dir=temp_root / "ghidra",
                manual_opcodes=[],
                sender_analysis={
                    "senders": [
                        {
                            "opcode": 113,
                            "status": "clean",
                            "senderFunction": "FUN_1400ced60",
                            "senderAddress": "1400ced60",
                            "decompiledBody": "void FUN_1400ced60(void) { GetFocus(); return; }",
                            "descriptorEvidence": {"namedTokens": ["GetFocus"]},
                            "callerChain": [],
                            "decompSnippet": ["GetFocus();"],
                        }
                    ]
                },
            )

            suspect_by_opcode = {entry["opcode"]: entry for entry in artifact["suspects"]}
            self.assertEqual(suspect_by_opcode[113]["suspectClass"], "state-report")

    def test_build_handoff_diff_reports_only_left_and_right_opcodes(self) -> None:
        left = {
            "events": [
                {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "appearance", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                {"lineNumber": 2, "timestamp": "t2", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "", "raw": ""},
                {"lineNumber": 3, "timestamp": "t3", "kind": "recv-raw", "stage": "interfaces", "opcode": 83, "bytes": 1, "preview": "01", "playerName": "", "raw": ""},
            ]
        }
        right = {
            "events": [
                {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "appearance", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                {"lineNumber": 2, "timestamp": "t2", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "", "raw": ""},
                {"lineNumber": 3, "timestamp": "t3", "kind": "recv-raw", "stage": "interfaces", "opcode": 48, "bytes": 8, "preview": "aa", "playerName": "", "raw": ""},
            ]
        }
        diff = build_handoff_diff(find_latest_session(left["events"]), find_latest_session(right["events"]))
        self.assertEqual(diff["onlyInLeft"], [83])
        self.assertEqual(diff["onlyInRight"], [48])

    def test_markdown_and_script_output_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_root = Path(tmpdir)
            world_log = temp_root / "world.log"
            decomp_dir = temp_root / "ghidra"
            out_a = temp_root / "out-a"
            out_b = temp_root / "out-b"
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:34:32Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:34:33Z world-stage name=demon stage=login-response",
                        "2026-03-15T20:34:34Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-15T20:34:35Z world-stage name=demon stage=rebuild",
                        "2026-03-15T20:34:36Z world-stage name=demon stage=default-state",
                        "2026-03-15T20:34:37Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:34:38Z send-raw opcode=42 bytes=66 remote=/127.0.0.1:62816 stage=rebuild preview=010203",
                        "2026-03-15T20:34:39Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:62816 stage=interfaces preview=007ff4",
                        "2026-03-15T20:34:40Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:62816 stage=interfaces preview=007ff4",
                        "2026-03-15T20:34:41Z send-raw opcode=42 bytes=3 remote=/127.0.0.1:62816 stage=interfaces preview=007ff4",
                        "2026-03-15T20:34:42Z recv-raw opcode=83 bytes=1 remote=/127.0.0.1:62816 stage=interfaces preview=01",
                    ]
                )
                + "\n",
            )
            artifact, _ = analyze_handoff(world_log_path=world_log, decomp_log_dir=decomp_dir, manual_opcodes=[])
            markdown_a = render_markdown(artifact)
            markdown_b = render_markdown(artifact)
            self.assertEqual(markdown_a, markdown_b)

            for output_dir in (out_a, out_b):
                completed = subprocess.run(
                    [
                        "python",
                        str(SCRIPT_PATH),
                        "--world-log",
                        str(world_log),
                        "--decomp-log-dir",
                        str(decomp_dir),
                        "--output-dir",
                        str(output_dir),
                    ],
                    cwd=str(WORKSPACE),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

            json_a = json.loads((out_a / "handoff-analysis.json").read_text(encoding="utf-8"))
            json_b = json.loads((out_b / "handoff-analysis.json").read_text(encoding="utf-8"))
            self.assertEqual(json_a, json_b)
            self.assertEqual(
                (out_a / "handoff-analysis.md").read_text(encoding="utf-8"),
                (out_b / "handoff-analysis.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
