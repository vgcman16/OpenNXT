from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_946_interface_diff import analyze_interface_diff


def write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class InterfaceDiffTest(unittest.TestCase):
    def test_interface_diff_ranks_missing_active_sub_and_head_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good_session = {
                "events": [
                    {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {"lineNumber": 2, "timestamp": "t2", "kind": "send-raw", "stage": "interfaces", "opcode": 126, "bytes": 5, "preview": "aa", "playerName": "", "raw": ""},
                    {"lineNumber": 3, "timestamp": "t3", "kind": "send-raw", "stage": "interfaces", "opcode": 116, "bytes": 25, "preview": "bb", "playerName": "", "raw": ""},
                    {"lineNumber": 4, "timestamp": "t4", "kind": "send-raw", "stage": "interfaces", "opcode": 106, "bytes": 6, "preview": "cc", "playerName": "", "raw": ""},
                ]
            }
            bad_session = {
                "events": [
                    {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {"lineNumber": 2, "timestamp": "t2", "kind": "send-raw", "stage": "interfaces", "opcode": 126, "bytes": 5, "preview": "aa", "playerName": "", "raw": ""},
                ]
            }
            good_path = root / "good.json"
            bad_path = root / "bad.json"
            write_json_file(good_path, good_session)
            write_json_file(bad_path, bad_session)

            class Args:
                good_session = good_path
                bad_session = bad_path
                good_window = None
                bad_window = None
                output_dir = root

            artifact = analyze_interface_diff(Args())

            self.assertEqual(artifact["status"], "ok")
            top_labels = [finding["label"] for finding in artifact["topFindings"]]
            self.assertTrue(any("IF_OPENSUB_ACTIVE" in label or "IF_SETPLAYERMODEL_SELF" in label for label in top_labels))

    def test_interface_diff_emits_compare_verdict_for_116_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            off_session = {
                "events": [
                    {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {
                        "lineNumber": 2,
                        "timestamp": "t2",
                        "kind": "world-skip-active-player",
                        "stage": "interfaces",
                        "opcode": None,
                        "bytes": None,
                        "preview": "",
                        "playerName": "demon",
                        "data": {"packetRegistered": "true", "configEnabled": "false", "reason": "experimental-opensub-disabled"},
                        "raw": "",
                    },
                    {"lineNumber": 3, "timestamp": "t3", "kind": "send-raw", "stage": "interfaces", "opcode": 106, "bytes": 6, "preview": "cc", "playerName": "", "raw": ""},
                ]
            }
            on_session = {
                "events": [
                    {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {
                        "lineNumber": 2,
                        "timestamp": "t2",
                        "kind": "world-open-active-player",
                        "stage": "interfaces",
                        "opcode": None,
                        "bytes": None,
                        "preview": "",
                        "playerName": "demon",
                        "data": {
                            "packetRegistered": "true",
                            "configEnabled": "true",
                            "subInterfaceId": "1482",
                            "childComponentId": "1",
                            "targetComponentId": "97124353",
                        },
                        "raw": "",
                    },
                    {"lineNumber": 3, "timestamp": "t3", "kind": "send-raw", "stage": "interfaces", "opcode": 116, "bytes": 25, "preview": "aa", "playerName": "", "raw": ""},
                    {"lineNumber": 4, "timestamp": "t4", "kind": "send-raw", "stage": "interfaces", "opcode": 106, "bytes": 6, "preview": "bb", "playerName": "", "raw": ""},
                ]
            }
            off_path = root / "off.json"
            on_path = root / "on.json"
            write_json_file(off_path, off_session)
            write_json_file(on_path, on_session)

            class Args:
                good_session = off_path
                bad_session = on_path
                good_window = None
                bad_window = None
                output_dir = root

            artifact = analyze_interface_diff(Args())

            self.assertEqual(artifact["verdict"]["activePlayer116Sent"], "yes")
            self.assertEqual(artifact["verdict"]["bootstrapMarkerPresent"], "yes")
            self.assertEqual(artifact["verdict"]["interfaceStageDelta"], "none")
            self.assertEqual(artifact["verdict"]["handoffOutcomeChanged"], "no")
            self.assertEqual(artifact["activePlayerComparison"]["detectedEnabledSession"], "badSession")
            self.assertEqual(artifact["activePlayerComparison"]["detectedDisabledSession"], "goodSession")

    def test_bootstrap_only_ignores_late_teardown_packets(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            good_session = {
                "events": [
                    {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "appearance", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {"lineNumber": 2, "timestamp": "t2", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {"lineNumber": 3, "timestamp": "t3", "kind": "send-raw", "stage": "interfaces", "opcode": 126, "bytes": 5, "preview": "aa", "playerName": "", "raw": ""},
                    {"lineNumber": 4, "timestamp": "t4", "kind": "send-raw", "stage": "none", "opcode": 129, "bytes": 6, "preview": "bb", "playerName": "", "raw": ""},
                    {"lineNumber": 5, "timestamp": "t5", "kind": "send-raw", "stage": "reset", "opcode": 134, "bytes": 0, "preview": "<empty>", "playerName": "", "raw": ""},
                ]
            }
            bad_session = {
                "events": [
                    {"lineNumber": 1, "timestamp": "t1", "kind": "world-stage", "stage": "appearance", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {"lineNumber": 2, "timestamp": "t2", "kind": "world-stage", "stage": "interfaces", "opcode": None, "bytes": None, "preview": "", "playerName": "demon", "raw": ""},
                    {"lineNumber": 3, "timestamp": "t3", "kind": "send-raw", "stage": "interfaces", "opcode": 126, "bytes": 5, "preview": "aa", "playerName": "", "raw": ""},
                ]
            }
            good_path = root / "good.json"
            bad_path = root / "bad.json"
            write_json_file(good_path, good_session)
            write_json_file(bad_path, bad_session)

            class Args:
                good_session = good_path
                bad_session = bad_path
                good_window = None
                bad_window = None
                bootstrap_only = True
                output_dir = root

            artifact = analyze_interface_diff(Args())

            labels = [finding["label"] for finding in artifact["topFindings"]]
            self.assertNotIn("UPDATE_STAT", labels)
            self.assertNotIn("RESET_CLIENT_VARCACHE", labels)


if __name__ == "__main__":
    unittest.main()
