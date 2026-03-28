from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_disconnect_pivot_doctor import summarize_attempt, verdict


class DisconnectPivotDoctorTest(unittest.TestCase):
    def test_if_setevents_burst_is_flagged(self) -> None:
        world_session = {
            "startLine": 100,
            "endLine": 150,
            "startTimestamp": "2026-03-21T10:47:41.000000Z",
            "endTimestamp": "2026-03-21T10:47:43.000000Z",
            "playerName": "demon",
            "durationSeconds": 2.0,
            "eventCount": 68,
            "stageCounts": {"appearance": 1, "interfaces": 1},
            "clientOpcodeCounts": {},
            "serverOpcodeCounts": {42: 1, 59: 64},
            "markerCounts": {},
            "stageSequence": ["appearance", "interfaces"],
            "events": [
                {"kind": "world-ready-signal", "lineNumber": 110, "timestamp": "2026-03-21T10:47:41.100000Z"},
                {
                    "kind": "world-send-deferred-completion-tail-after-sync",
                    "lineNumber": 120,
                    "timestamp": "2026-03-21T10:47:41.200000Z",
                },
                {
                    "kind": "world-send-deferred-completion-event-delta",
                    "lineNumber": 121,
                    "timestamp": "2026-03-21T10:47:41.210000Z",
                },
            ]
            + [
                {"kind": "send-raw", "opcode": 59, "lineNumber": 122 + i, "timestamp": "2026-03-21T10:47:41.220000Z"}
                for i in range(64)
            ]
            + [
                {"kind": "send-raw", "opcode": 42, "lineNumber": 190, "timestamp": "2026-03-21T10:47:41.900000Z"},
                {"kind": "world-channel-inactive", "lineNumber": 191, "timestamp": "2026-03-21T10:47:42.000000Z"},
            ],
        }
        content_session = {
            "firstRequestLabel": "reference-table[0]",
            "referenceTableRequests": 1,
            "archiveRequests": 0,
        }

        attempt = summarize_attempt(world_session, content_session, 1)

        self.assertEqual(attempt["likelyPivot"], "if-setevents-burst-before-disconnect")
        self.assertEqual(attempt["dominantServerOpcode"], 59)
        self.assertGreaterEqual(attempt["dominantServerOpcodeCount"], 64)
        self.assertIn("trim or defer the post-ready IF_SETEVENTS burst", "\n".join(attempt["needs"]))

    def test_verdict_reports_post_ready_if_setevents_burst(self) -> None:
        artifact_verdict = verdict(
            [
                {
                    "likelyPivot": "if-setevents-burst-before-disconnect",
                    "dominantServerOpcode": 59,
                    "dominantServerOpcodeCount": 88,
                    "needs": ["trim or defer the post-ready IF_SETEVENTS burst"],
                }
            ]
        )

        self.assertEqual(artifact_verdict["likelyBlocker"], "post-ready-if-setevents-burst")
        self.assertIn("IF_SETEVENTS", artifact_verdict["recommendation"])


if __name__ == "__main__":
    unittest.main()
