from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_runtime_verifier import build_artifact, render_markdown


class RuntimeVerifierTest(unittest.TestCase):
    @patch("run_946_runtime_verifier.input_fingerprint", return_value="fingerprint")
    @patch("run_946_runtime_verifier.load_json")
    @patch("run_946_runtime_verifier.run_gradle_runtime_suite")
    @patch("run_946_runtime_verifier.run_python_fixture_tests")
    def test_build_artifact_emits_standard_contract(
        self,
        python_tests: patch,
        gradle_suite: patch,
        load_json: patch,
        _: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            shared_dir = Path(tmpdir)
            args = SimpleNamespace(shared_dir=shared_dir, run_tests=True)
            python_tests.return_value = (True, [{"command": ["python"], "returnCode": 0, "stdout": "", "stderr": ""}])
            gradle_suite.return_value = {
                "command": ["gradle"],
                "returnCode": 0,
                "stdout": "",
                "stderr": "",
                "passed": True,
            }
            load_json.side_effect = [
                [
                    {
                        "packetName": "IF_SETEVENTS",
                        "side": "server",
                        "opcode": 59,
                        "proofGates": {
                            "fieldDeclarationExists": True,
                            "widthMatches": True,
                            "draftMatchesDeclaration": True,
                            "legacyCompatible": True,
                            "noUnknownFields": True,
                        },
                        "hasManualRegistration": True,
                    }
                ],
                [{"packetName": "IF_SETEVENTS"}],
                {"status": "partial", "summary": {"sceneDeliveryState": "capture-missing", "overlapConfidence": "missing"}},
                {"status": "ok", "summary": {"resolvedArchiveCount": 2}},
                {"status": "ok", "summary": {"topHypothesis": "scene settle stall"}},
                {"status": "partial", "summary": {"overlapAchieved": False}},
            ]

            artifact = build_artifact(args)

        self.assertEqual(artifact["tool"], "run_946_runtime_verifier")
        self.assertEqual(artifact["schemaVersion"], 1)
        self.assertEqual(artifact["status"], "partial")
        self.assertIn("inputs", artifact)
        self.assertIn("artifacts", artifact)
        self.assertIn("summary", artifact)
        self.assertEqual(artifact["summary"]["sceneDeliveryState"], "capture-missing")
        self.assertEqual(artifact["summary"]["js5ResolutionStatus"], "ok")
        self.assertEqual(len(artifact["packets"]), 1)
        self.assertIn("## Scene/JS5", render_markdown(artifact))
        self.assertIn("# 946 Runtime Verification", render_markdown(artifact))


if __name__ == "__main__":
    unittest.main()
