from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_opcode_113_verdict import build_artifact, render_markdown


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
SCRIPT_PATH = WORKSPACE / "tools" / "run_946_opcode_113_verdict.py"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Opcode113VerdictTest(unittest.TestCase):
    def test_build_artifact_classifies_state_report_and_promotes_116(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sender_json = root / "sender-analysis.json"
            handoff_json = root / "handoff-analysis.json"
            active_sub_json = root / "active-sub-analysis.json"
            world_log = root / "world.log"
            write_text(
                sender_json,
                json.dumps(
                    {
                        "senders": [
                            {
                                "opcode": 113,
                                "status": "clean",
                                "senderFunction": "FUN_1400ced60",
                                "senderAddress": "1400ced60",
                                "requestedSenderFunction": "FUN_1400ced60",
                                "requestedSenderAddress": "1400ced60",
                                "resolvedFunctionName": "FUN_1400cec80",
                                "resolvedFunctionEntry": "1400cec80",
                                "callerLookupFunction": "FUN_1400cec80",
                                "callerLookupAddress": "1400cec80",
                                "callerLookupSource": "resolved-containing-function",
                                "callerRefs": [],
                                "packetSizeEvidence": {
                                    "observedCount": 3,
                                    "observedStageCounts": {"interfaces": 3},
                                    "samplePreviews": [
                                        {"preview": "000000e5", "stage": "interfaces", "bytes": 4, "lineNumber": 10},
                                        {"preview": "000000db", "stage": "interfaces", "bytes": 4, "lineNumber": 11},
                                    ],
                                },
                                "decompiledBody": "\n".join(
                                    [
                                        "void FUN_1400cec80(longlong param_1) {",
                                        "  if (*(ulonglong *)(param_1 + 0x77b8) < DAT_140e55a90) {",
                                        "    lVar7 = DAT_140e55a90 + 10000;",
                                        "    *(undefined1 *)(param_1 + 0x77c0) = 1;",
                                        "  }",
                                        "  iVar6 = FUN_1400bbb90();",
                                        "  uVar2 = *(uint *)(*(longlong *)(param_1 + 8) + 0x55c);",
                                        "  *(undefined1 *)(*(longlong *)(local_20 + 0x18) + *(longlong *)(local_20 + 0x20)) = 0;",
                                        "  *(char *)(lVar3 + 1 + *(longlong *)(local_20 + 0x18)) = (char)iVar6;",
                                        "  *(char *)(lVar3 + *(longlong *)(local_20 + 0x18)) = -0x80 - cVar5;",
                                        "}",
                                    ]
                                ),
                                "descriptorEvidence": {"namedTokens": [], "symbols": {}},
                                "callerChain": [],
                            }
                        ]
                    },
                    indent=2,
                ),
            )
            write_text(
                handoff_json,
                json.dumps(
                    {
                        "suspects": [
                            {
                                "opcode": 113,
                                "suspectClass": "likely-blocker",
                                "coverageStatus": "unresolved",
                                "observedStageCounts": {"interfaces": 24, "rebuild": 1},
                                "firstSeenStage": "rebuild",
                                "lastSeenStage": "interfaces",
                            }
                        ]
                    },
                    indent=2,
                ),
            )
            write_text(
                active_sub_json,
                json.dumps(
                    {
                        "targets": [
                            {
                                "opcode": 116,
                                "status": "ok",
                                "confidence": "medium",
                                "exportedFieldTypes": ["ushort", "ushort128", "intv1", "ubytec"],
                            }
                        ]
                    },
                    indent=2,
                ),
            )
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:34:32Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:34:33Z world-stage name=demon stage=login-response",
                        "2026-03-15T20:34:34Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-15T20:34:35Z world-stage name=demon stage=rebuild",
                        "2026-03-15T20:34:36Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:34:37Z recv-raw opcode=113 bytes=4 remote=/127.0.0.1:62816 stage=rebuild preview=000000e5",
                        "2026-03-15T20:34:38Z recv-raw opcode=113 bytes=4 remote=/127.0.0.1:62816 stage=interfaces preview=000000db",
                        "2026-03-15T20:34:39Z recv-raw opcode=113 bytes=4 remote=/127.0.0.1:62816 stage=interfaces preview=000000db",
                    ]
                )
                + "\n",
            )

            args = type(
                "Args",
                (),
                {
                    "opcode": 113,
                    "sender_analysis_json": sender_json,
                    "handoff_json": handoff_json,
                    "active_sub_json": active_sub_json,
                    "world_log": world_log,
                    "output_dir": root,
                },
            )()

            artifact = build_artifact(args)

            self.assertEqual(artifact["verdict"], "state-report")
            self.assertEqual(artifact["addressValidation"]["resolvedFunctionEntry"], "1400cec80")
            self.assertEqual(artifact["nextLead"]["opcode"], 116)
            self.assertTrue(artifact["liveValueCorrelation"]["matchesPayloadHypothesis"])
            self.assertIn("10000", " ".join(artifact["rationale"]))

    def test_script_output_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            sender_json = root / "sender-analysis.json"
            handoff_json = root / "handoff-analysis.json"
            active_sub_json = root / "active-sub-analysis.json"
            world_log = root / "world.log"
            out_a = root / "out-a"
            out_b = root / "out-b"
            write_text(
                sender_json,
                json.dumps(
                    {
                        "senders": [
                            {
                                "opcode": 113,
                                "status": "clean",
                                "senderFunction": "FUN_1400ced60",
                                "senderAddress": "1400ced60",
                                "requestedSenderFunction": "FUN_1400ced60",
                                "requestedSenderAddress": "1400ced60",
                                "resolvedFunctionName": "FUN_1400cec80",
                                "resolvedFunctionEntry": "1400cec80",
                                "callerLookupFunction": "FUN_1400cec80",
                                "callerLookupAddress": "1400cec80",
                                "callerLookupSource": "resolved-containing-function",
                                "callerRefs": [],
                                "packetSizeEvidence": {"observedCount": 1, "observedStageCounts": {"interfaces": 1}, "samplePreviews": []},
                                "decompiledBody": "lVar7 = DAT_140e55a90 + 10000; iVar6 = FUN_1400bbb90(); uVar2 = *(uint *)(*(longlong *)(param_1 + 8) + 0x55c);",
                                "descriptorEvidence": {"namedTokens": [], "symbols": {}},
                                "callerChain": [],
                            }
                        ]
                    },
                    indent=2,
                ),
            )
            write_text(handoff_json, json.dumps({"suspects": [{"opcode": 113, "observedStageCounts": {"interfaces": 1}}]}, indent=2))
            write_text(active_sub_json, json.dumps({"targets": []}, indent=2))
            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-15T20:34:32Z world-stage name=demon stage=appearance",
                        "2026-03-15T20:34:33Z world-stage name=demon stage=interfaces",
                        "2026-03-15T20:34:34Z recv-raw opcode=113 bytes=4 remote=/127.0.0.1:62816 stage=interfaces preview=000000db",
                    ]
                )
                + "\n",
            )

            for output_dir in (out_a, out_b):
                completed = subprocess.run(
                    [
                        "python",
                        str(SCRIPT_PATH),
                        "--sender-analysis-json",
                        str(sender_json),
                        "--handoff-json",
                        str(handoff_json),
                        "--active-sub-json",
                        str(active_sub_json),
                        "--world-log",
                        str(world_log),
                        "--output-dir",
                        str(output_dir),
                    ],
                    cwd=str(WORKSPACE),
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)

            json_a = json.loads((out_a / "opcode-113-verdict.json").read_text(encoding="utf-8"))
            json_b = json.loads((out_b / "opcode-113-verdict.json").read_text(encoding="utf-8"))
            self.assertEqual(json_a, json_b)
            self.assertEqual(
                (out_a / "opcode-113-verdict.md").read_text(encoding="utf-8"),
                (out_b / "opcode-113-verdict.md").read_text(encoding="utf-8"),
            )
            self.assertEqual(render_markdown(json_a), render_markdown(json_b))


if __name__ == "__main__":
    unittest.main()
