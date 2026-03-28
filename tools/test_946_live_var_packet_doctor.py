from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_live_var_packet_doctor import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class LiveVarPacketDoctorTest(unittest.TestCase):
    def test_build_artifact_classifies_candidate_varps_against_reset_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            golden_log = root / "golden.log"
            loading_artifact = root / "loading-var-gate-doctor.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-22T10:00:00.000000Z world-stage name=demon stage=appearance",
                        "2026-03-22T10:00:00.100000Z world-send-reset-client-varcache name=demon reason=forced-map-build-fallback-minimal-bootstrap",
                        "2026-03-22T10:00:00.200000Z world-send-minimal-varcs name=demon ids=181,1027,1034,3497",
                        "2026-03-22T10:00:01.000000Z world-accept-late-scene-ready-signal name=demon opcode=48 bytes=8 control50=175 acceptedCount=1",
                        "2026-03-22T10:00:02.000000Z world-send-deferred-completion-announcement-scripts name=demon scripts=1264,3529",
                    ]
                ),
            )
            write_text(
                golden_log,
                "\n".join(
                    [
                        "timestamp=2026-03-22T09:59:59.900000Z direction=send localSide=SERVER packet=VARP_SMALL opcode=72 size=3 unread=0 remote=embedded fields={id=6, value=1} packetValue=VarpSmall(id=6, value=1) hex=000000",
                        "timestamp=2026-03-22T10:00:00.500000Z direction=send localSide=SERVER packet=VARP_LARGE opcode=51 size=6 unread=0 remote=/127.0.0.1:43594 fields={value=42, id=0} packetValue=VarpLarge(id=0, value=42) hex=000000",
                        "timestamp=2026-03-22T10:00:01.500000Z direction=send localSide=SERVER packet=VARP_SMALL opcode=72 size=3 unread=0 remote=/127.0.0.1:43594 fields={id=1, value=7} packetValue=VarpSmall(id=1, value=7) hex=000000",
                    ]
                ),
            )
            write_text(
                loading_artifact,
                """{
                  "summary": {
                    "latestLikelyBlocker": "accepted-ready-no-scene-archives"
                  },
                  "candidateVarps": {
                    "direct": [],
                    "heuristic": [
                      {
                        "id": 0,
                        "scriptIds": [3529],
                        "accesses": {"get": 1},
                        "meaning": {"present": true, "domain": "PLAYER", "type": "QUESTHELP", "forceDefault": true, "backingVarbitCount": 3}
                      },
                      {
                        "id": 6,
                        "scriptIds": [3529],
                        "accesses": {"get": 1},
                        "meaning": {"present": true, "domain": "PLAYER", "type": "INT", "forceDefault": false, "backingVarbitCount": 0}
                      },
                      {
                        "id": 11,
                        "scriptIds": [8420],
                        "accesses": {"set": 1},
                        "meaning": {"present": true, "domain": "PLAYER", "type": "INT", "forceDefault": true, "backingVarbitCount": 0}
                      }
                    ]
                  },
                  "candidateVarbits": {
                    "direct": [],
                    "heuristic": [
                      {
                        "id": 44,
                        "scriptIds": [8420],
                        "accesses": {"get": 1},
                        "meaning": {"present": true, "baseVar": 6}
                      }
                    ]
                  }
                }""",
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    golden_log=golden_log,
                    loading_var_gate_artifact=loading_artifact,
                    world_tail_bytes=1024 * 1024,
                    golden_tail_bytes=1024 * 1024,
                    golden_pad_seconds=2.0,
                    include_embedded=False,
                    output_dir=root,
                )
            )

        summary = artifact["summary"]
        self.assertEqual(summary["latestLikelyBlocker"], "post-reset-candidate-varp-gap")
        self.assertEqual(summary["candidateVarpCount"], 3)
        self.assertEqual(summary["candidateVarpsObserved"], 1)
        self.assertEqual(summary["candidateVarpsSentAfterReset"], 0)
        self.assertEqual(summary["ignoredEmbeddedGoldenVarpEventCount"], 1)
        self.assertTrue(summary["resetClientVarcacheObserved"])
        self.assertFalse(summary["deferredDefaultVarpsObserved"])

        rows = {row["id"]: row for row in artifact["candidateVarps"]}
        self.assertEqual(rows[0]["status"], "not-sent-after-ready")
        self.assertEqual(rows[6]["status"], "never-sent")
        self.assertEqual(rows[11]["status"], "never-sent")
        rendered = render_markdown(artifact)
        self.assertIn("Ignored embedded golden VARP events: `1`", rendered)
        self.assertIn("candidate varps 0,6,11 are still missing post-reset/send-after-ready evidence", rendered)
        self.assertIn("varp 6", rendered)
        self.assertIn("Minimal varcs", rendered)


if __name__ == "__main__":
    unittest.main()
