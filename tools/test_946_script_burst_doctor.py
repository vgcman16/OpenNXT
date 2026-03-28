from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_script_burst_doctor import summarize_attempt, verdict


class ScriptBurstDoctorTest(unittest.TestCase):
    def test_runclientscript_burst_is_flagged_with_script_families(self) -> None:
        world_session = {
            "startLine": 200,
            "endLine": 280,
            "startTimestamp": "2026-03-21T12:57:40.000000Z",
            "endTimestamp": "2026-03-21T12:57:42.000000Z",
            "playerName": "demon",
            "durationSeconds": 2.0,
            "eventCount": 70,
            "stageCounts": {"appearance": 1, "interfaces": 1},
            "clientOpcodeCounts": {},
            "serverOpcodeCounts": {141: 32},
            "markerCounts": {},
            "stageSequence": ["appearance", "interfaces"],
            "events": [
                {
                    "kind": "world-send-deferred-completion-tail-after-sync",
                    "lineNumber": 220,
                    "timestamp": "2026-03-21T12:57:41.000000Z",
                },
                {
                    "kind": "world-send-light-interface-tail",
                    "lineNumber": 221,
                    "timestamp": "2026-03-21T12:57:41.010000Z",
                },
                {
                    "kind": "world-send-deferred-completion-scripts",
                    "lineNumber": 222,
                    "timestamp": "2026-03-21T12:57:41.020000Z",
                },
                {
                    "kind": "world-send-deferred-completion-announcement-scripts",
                    "lineNumber": 223,
                    "timestamp": "2026-03-21T12:57:41.030000Z",
                },
            ]
            + [
                {
                    "kind": "send-raw",
                    "opcode": 141,
                    "bytes": 15 if i < 28 else 168,
                    "lineNumber": 224 + i,
                    "timestamp": "2026-03-21T12:57:41.040000Z",
                }
                for i in range(32)
            ]
            + [
                {
                    "kind": "world-channel-inactive",
                    "lineNumber": 260,
                    "timestamp": "2026-03-21T12:57:41.900000Z",
                }
            ],
        }
        content_session = {
            "firstRequestLabel": "reference-table[0]",
            "referenceTableRequests": 1,
            "archiveRequests": 0,
        }

        attempt = summarize_attempt(world_session, content_session, 1)

        self.assertEqual(attempt["likelyPivot"], "runclientscript-burst-before-disconnect")
        self.assertEqual(attempt["dominantServerOpcode"], 141)
        self.assertEqual(attempt["dominantServerOpcodeCount"], 32)
        family_names = {family["family"] for family in attempt["scriptFamilies"]}
        self.assertIn("light-interface-tail", family_names)
        self.assertIn("deferred-completion-scripts", family_names)
        self.assertIn("announcement-scripts", family_names)
        self.assertIn(
            "trim or defer the deferred completion RUNCLIENTSCRIPT batch",
            "\n".join(attempt["needs"]),
        )

    def test_verdict_reports_script_burst_blocker(self) -> None:
        artifact_verdict = verdict(
            [
                {
                    "likelyPivot": "runclientscript-burst-before-disconnect",
                    "dominantServerOpcode": 141,
                    "dominantServerOpcodeCount": 32,
                    "needs": ["trim or defer the announcement RUNCLIENTSCRIPT pair (1264,3529)"],
                }
            ]
        )

        self.assertEqual(artifact_verdict["likelyBlocker"], "post-ready-runclientscript-burst")
        self.assertIn("RUNCLIENTSCRIPT", artifact_verdict["recommendation"])

    def test_skipped_light_tail_is_not_recommended_again(self) -> None:
        world_session = {
            "startLine": 300,
            "endLine": 380,
            "startTimestamp": "2026-03-21T15:17:41.000000Z",
            "endTimestamp": "2026-03-21T15:17:43.000000Z",
            "playerName": "demon",
            "durationSeconds": 2.0,
            "eventCount": 60,
            "stageCounts": {"interfaces": 1},
            "clientOpcodeCounts": {},
            "serverOpcodeCounts": {141: 25},
            "markerCounts": {},
            "stageSequence": ["interfaces"],
            "events": [
                {
                    "kind": "world-send-deferred-completion-tail-after-sync",
                    "lineNumber": 320,
                    "timestamp": "2026-03-21T15:17:42.000000Z",
                },
                {
                    "kind": "world-send-light-interface-tail",
                    "lineNumber": 321,
                    "timestamp": "2026-03-21T15:17:42.010000Z",
                },
                {
                    "kind": "world-skip-forced-fallback-light-tail-scripts",
                    "lineNumber": 322,
                    "timestamp": "2026-03-21T15:17:42.015000Z",
                },
                {
                    "kind": "world-send-deferred-completion-scripts",
                    "lineNumber": 323,
                    "timestamp": "2026-03-21T15:17:42.020000Z",
                },
            ]
            + [
                {
                    "kind": "send-raw",
                    "opcode": 141,
                    "bytes": 15 if i < 24 else 168,
                    "lineNumber": 324 + i,
                    "timestamp": "2026-03-21T15:17:42.040000Z",
                }
                for i in range(25)
            ]
            + [
                {
                    "kind": "world-channel-inactive",
                    "lineNumber": 360,
                    "timestamp": "2026-03-21T15:17:42.900000Z",
                }
            ],
        }

        attempt = summarize_attempt(world_session, None, 1)

        self.assertIn("light-interface-tail", attempt["skippedScriptFamilies"])
        self.assertNotIn(
            "trim or defer the forced-fallback light-tail RUNCLIENTSCRIPT set (11145,8420,8310)",
            attempt["needs"],
        )
        self.assertIn(
            "trim or defer the deferred completion RUNCLIENTSCRIPT batch (8862,2651,7486,10903,8778,4704,4308,10623)",
            attempt["needs"],
        )

    def test_skipped_announcement_scripts_are_not_recommended_again(self) -> None:
        world_session = {
            "startLine": 400,
            "endLine": 470,
            "startTimestamp": "2026-03-21T17:05:41.000000Z",
            "endTimestamp": "2026-03-21T17:05:43.000000Z",
            "playerName": "demon",
            "durationSeconds": 2.0,
            "eventCount": 40,
            "stageCounts": {"interfaces": 1},
            "clientOpcodeCounts": {},
            "serverOpcodeCounts": {141: 6},
            "markerCounts": {},
            "stageSequence": ["interfaces"],
            "events": [
                {
                    "kind": "world-send-deferred-completion-tail-after-sync",
                    "lineNumber": 420,
                    "timestamp": "2026-03-21T17:05:42.000000Z",
                },
                {
                    "kind": "world-send-deferred-completion-announcement-scripts",
                    "lineNumber": 421,
                    "timestamp": "2026-03-21T17:05:42.010000Z",
                },
                {
                    "kind": "world-skip-forced-fallback-announcement-scripts",
                    "lineNumber": 422,
                    "timestamp": "2026-03-21T17:05:42.015000Z",
                },
            ]
            + [
                {
                    "kind": "send-raw",
                    "opcode": 141,
                    "bytes": 10 if i < 2 else (168 if i == 2 else 5),
                    "lineNumber": 423 + i,
                    "timestamp": "2026-03-21T17:05:42.040000Z",
                }
                for i in range(4)
            ]
            + [
                {
                    "kind": "world-channel-inactive",
                    "lineNumber": 450,
                    "timestamp": "2026-03-21T17:05:42.900000Z",
                }
            ],
        }

        attempt = summarize_attempt(world_session, None, 1)

        self.assertIn("announcement-scripts", attempt["skippedScriptFamilies"])
        self.assertNotIn(
            "trim or defer the announcement RUNCLIENTSCRIPT pair (1264,3529)",
            attempt["needs"],
        )

    def test_skipped_forced_fallback_completion_companions_are_not_recommended_again(self) -> None:
        world_session = {
            "startLine": 500,
            "endLine": 560,
            "startTimestamp": "2026-03-21T17:46:41.000000Z",
            "endTimestamp": "2026-03-21T17:46:43.000000Z",
            "playerName": "demon",
            "durationSeconds": 2.0,
            "eventCount": 24,
            "stageCounts": {"interfaces": 1},
            "clientOpcodeCounts": {},
            "serverOpcodeCounts": {141: 3},
            "markerCounts": {},
            "stageSequence": ["interfaces"],
            "events": [
                {
                    "kind": "world-send-forced-fallback-completion-companions",
                    "lineNumber": 520,
                    "timestamp": "2026-03-21T17:46:42.000000Z",
                },
                {
                    "kind": "world-skip-forced-fallback-completion-companions",
                    "lineNumber": 521,
                    "timestamp": "2026-03-21T17:46:42.005000Z",
                },
            ]
            + [
                {
                    "kind": "send-raw",
                    "opcode": 141,
                    "bytes": 10,
                    "lineNumber": 522 + i,
                    "timestamp": "2026-03-21T17:46:42.040000Z",
                }
                for i in range(3)
            ]
            + [
                {
                    "kind": "world-channel-inactive",
                    "lineNumber": 550,
                    "timestamp": "2026-03-21T17:46:42.900000Z",
                }
            ],
        }

        attempt = summarize_attempt(world_session, None, 1)

        self.assertIn("forced-fallback-completion-companions", attempt["skippedScriptFamilies"])
        self.assertNotIn(
            "trim or defer the forced-fallback completion companion block "
            "(ids 1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639; scripts 139,14150)",
            attempt["needs"],
        )


if __name__ == "__main__":
    unittest.main()
