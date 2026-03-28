from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_loading_var_gate_doctor import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, text: str) -> None:
    write_text(path, text)


class LoadingVarGateDoctorTest(unittest.TestCase):
    def test_build_artifact_aggregates_loading_scripts_and_candidate_vars(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            var_root = root / "var-meaning"
            shared = root / "shared"
            map_gate_dir = root / "map-gate"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-22T10:00:00.000000Z world-stage name=demon stage=appearance",
                        "2026-03-22T10:00:00.100000Z world-send-reset-client-varcache name=demon",
                        "2026-03-22T10:00:01.000000Z world-send-deferred-completion-announcement-scripts name=demon scripts=1264,3529",
                        "2026-03-22T10:00:02.000000Z world-send-deferred-light-tail-scripts-after-scene-start name=demon scripts=11145,8420,8310 count=7 control50=125",
                    ]
                ),
            )
            write_json(
                shared / "scene-start-doctor.json",
                """{
                  "summary": {
                    "latestLikelyBlocker": "accepted-ready-no-scene-archives"
                  }
                }""",
            )
            write_json(
                shared / "post-scene-opcode-doctor.json",
                """{
                  "summary": {
                    "latestLikelyBlocker": "accepted-ready-no-scene-archives"
                  }
                }""",
            )
            write_json(
                map_gate_dir / "summary-live.json",
                """{
                  "idxLookupCount": 0,
                  "httpMsRequestCount": 0,
                  "httpNonReferenceRequestCount": 0
                }""",
            )
            write_json(
                var_root / "scripts" / "3529.json",
                """{
                  "scriptId": 3529,
                  "decodeMode": "unsupported",
                  "exactParse": false,
                  "directVarps": [],
                  "directVarbits": [],
                  "heuristicVarps": [
                    {"id": 6, "access": "get", "extraction": "heuristic", "offset": 10},
                    {"id": 3920, "access": "set", "extraction": "heuristic", "offset": 20}
                  ],
                  "heuristicVarbits": []
                }""",
            )
            write_json(
                var_root / "scripts" / "8420.json",
                """{
                  "scriptId": 8420,
                  "decodeMode": "unsupported",
                  "exactParse": false,
                  "directVarps": [
                    {"id": 11, "access": "set", "extraction": "exact", "offset": 12}
                  ],
                  "directVarbits": [],
                  "heuristicVarps": [],
                  "heuristicVarbits": [
                    {"id": 44, "access": "get", "extraction": "heuristic", "offset": 9}
                  ]
                }""",
            )
            write_json(
                var_root / "varps" / "6.json",
                """{
                  "varpId": 6,
                  "domain": "PLAYER",
                  "type": "INT",
                  "forceDefault": false,
                  "backingVarbits": [1, 2]
                }""",
            )
            write_json(
                var_root / "varps" / "11.json",
                """{
                  "varpId": 11,
                  "domain": "PLAYER",
                  "type": "INT",
                  "forceDefault": true,
                  "backingVarbits": []
                }""",
            )
            write_json(
                var_root / "varbits" / "44.json",
                """{
                  "varbitId": 44,
                  "baseVar": 11,
                  "lsb": 1,
                  "msb": 3
                }""",
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    var_meaning_root=var_root,
                    map_gate_dir=map_gate_dir,
                    scene_start_artifact=shared / "scene-start-doctor.json",
                    post_scene_artifact=shared / "post-scene-opcode-doctor.json",
                    tail_bytes=1024 * 1024,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["latestLikelyBlocker"], "accepted-ready-no-scene-archives")
        self.assertTrue(artifact["summary"]["resetClientVarcacheObserved"])
        self.assertFalse(artifact["summary"]["deferredDefaultVarpsObserved"])
        self.assertEqual(artifact["summary"]["candidateDirectVarpCount"], 1)
        self.assertEqual(artifact["summary"]["candidateHeuristicVarpCount"], 2)
        self.assertIn(1264, artifact["summary"]["scriptsMissingEvidence"])
        self.assertEqual(artifact["candidateVarps"]["direct"][0]["id"], 11)
        heuristic_ids = [entry["id"] for entry in artifact["candidateVarps"]["heuristic"]]
        self.assertEqual(heuristic_ids, [6, 3920])
        rendered = render_markdown(artifact)
        self.assertIn("accepted-ready-no-scene-archives", rendered)
        self.assertIn("client-side var gate before archive resolution", rendered)
        self.assertIn("script 3529", rendered)
        self.assertIn("varp 11", rendered)


if __name__ == "__main__":
    unittest.main()
