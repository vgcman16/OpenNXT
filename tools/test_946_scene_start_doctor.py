from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_scene_start_doctor import render_markdown, summarize_attempt, verdict


class SceneStartDoctorTest(unittest.TestCase):
    def test_summarize_attempt_flags_accepted_ready_plateau_without_scene_archives(self) -> None:
        world_session = {
            "startLine": 100,
            "endLine": 220,
            "startTimestamp": "2026-03-21T19:16:57.000000Z",
            "endTimestamp": "2026-03-21T19:17:26.000000Z",
            "playerName": "demon",
            "durationSeconds": 29.0,
            "eventCount": 20,
            "stageCounts": {"appearance": 1, "interfaces": 1},
            "clientOpcodeCounts": {17: 2, 83: 1},
            "serverOpcodeCounts": {42: 5},
            "markerCounts": {"world-ready-signal": 1},
            "stageSequence": ["appearance", "interfaces"],
            "events": [
                {
                    "kind": "world-send-rebuild-tail",
                    "lineNumber": 110,
                    "timestamp": "2026-03-21T19:16:57.600000Z",
                    "data": {"chunkX": "402", "chunkY": "402"},
                },
                {
                    "kind": "world-ready-signal-latched",
                    "lineNumber": 120,
                    "timestamp": "2026-03-21T19:16:57.850000Z",
                    "data": {"opcode": "48"},
                },
                {
                    "kind": "world-ready-signal",
                    "lineNumber": 130,
                    "timestamp": "2026-03-21T19:16:57.990000Z",
                    "data": {"opcode": "48"},
                },
                {
                    "kind": "world-send-player-info",
                    "lineNumber": 135,
                    "timestamp": "2026-03-21T19:16:58.030000Z",
                    "data": {"reason": "initial"},
                },
                {
                    "kind": "world-send-player-info",
                    "lineNumber": 136,
                    "timestamp": "2026-03-21T19:16:58.040000Z",
                    "data": {"reason": "initial-followup"},
                },
                {
                    "kind": "world-client-bootstrap-control",
                    "lineNumber": 140,
                    "timestamp": "2026-03-21T19:16:58.460000Z",
                    "opcode": 50,
                    "data": {"value": "1"},
                },
                {
                    "kind": "world-client-bootstrap-control",
                    "lineNumber": 141,
                    "timestamp": "2026-03-21T19:16:58.470000Z",
                    "opcode": 82,
                    "data": {"value": "0"},
                },
                {
                    "kind": "world-client-bootstrap-control",
                    "lineNumber": 142,
                    "timestamp": "2026-03-21T19:16:58.480000Z",
                    "opcode": 50,
                    "data": {"value": "3"},
                },
                {
                    "kind": "recv-raw",
                    "lineNumber": 150,
                    "timestamp": "2026-03-21T19:17:15.640000Z",
                    "opcode": 17,
                    "bytes": 12,
                    "preview": "0300ffff013d021c0007ec00",
                },
                {
                    "kind": "world-ignore-client-compat",
                    "lineNumber": 160,
                    "timestamp": "2026-03-21T19:17:18.240000Z",
                    "opcode": 83,
                    "bytes": 1,
                    "preview": "00",
                },
            ],
        }
        content_session = {
            "firstRequestLabel": "reference-table[0]",
            "requestCount": 1,
            "referenceTableRequests": 1,
            "archiveRequests": 0,
            "responseHeaderCount": 1,
            "responseBytes": 4191,
        }

        attempt = summarize_attempt(world_session, content_session, 1)

        self.assertEqual(attempt["likelyBlocker"], "accepted-ready-no-scene-archives")
        self.assertTrue(attempt["rebuildBeforeReadyAccepted"])
        self.assertTrue(attempt["rebuildBeforeBootstrapControls"])
        self.assertFalse(attempt["closeLoadingOverlay"]["present"])
        self.assertIn("first non-reference /ms archive request after reference-table[0]", attempt["needs"])
        self.assertIn("explicit loading-overlay close on the accepted-ready minimal branch", attempt["needs"])

    def test_verdict_and_markdown_surface_exact_branch(self) -> None:
        artifact_verdict = verdict(
            [
                {
                    "likelyBlocker": "accepted-ready-no-scene-archives",
                    "rebuildBeforeBootstrapControls": True,
                    "closeLoadingOverlay": {"present": False},
                    "contentSession": {"firstRequestLabel": "reference-table[0]", "archiveRequests": 0},
                    "needs": [
                        "explicit loading-overlay close on the accepted-ready minimal branch",
                        "first non-reference /ms archive request after reference-table[0]",
                    ],
                }
            ]
        )

        self.assertEqual(artifact_verdict["likelyBlocker"], "accepted-ready-no-scene-archives")
        self.assertIn("reference-table[0]", artifact_verdict["recommendation"])

        rendered = render_markdown(
            {
                "status": "ok",
                "summary": {
                    "clusterId": "20260321-191008",
                    "attemptCount": 1,
                    "latestRebuildBeforeBootstrapControls": True,
                    "latestHasCloseLoadingOverlay": False,
                    "latestContentFirstRequestLabel": "reference-table[0]",
                    "latestArchiveRequests": 0,
                },
                "verdict": artifact_verdict,
                "attempts": [
                    {
                        "attemptIndex": 1,
                        "likelyBlocker": "accepted-ready-no-scene-archives",
                        "worldSession": {"startLine": 100, "endLine": 220},
                        "rebuild": {"lineNumber": 110},
                        "readyAccepted": {"lineNumber": 130},
                        "closeLoadingOverlay": {"lineNumber": None},
                        "rebuildBeforeReadyAccepted": True,
                        "rebuildBeforeBootstrapControls": True,
                        "controlBursts": [{"lineNumber": 140, "opcode": 50, "value": "1", "timestamp": ""}],
                        "postReadyClientSignals": [{"lineNumber": 150, "opcode": 17, "bytes": 12, "preview": "03"}],
                        "contentSession": {
                            "firstRequestLabel": "reference-table[0]",
                            "referenceTableRequests": 1,
                            "archiveRequests": 0,
                            "responseBytes": 4191,
                        },
                        "needs": artifact_verdict["needs"],
                    }
                ],
            }
        )
        self.assertIn("rebuild before first 50/82/50 burst", rendered)
        self.assertIn("reference-table[0]", rendered)


if __name__ == "__main__":
    unittest.main()
