from __future__ import annotations

import json
import unittest
from pathlib import Path

from protocol_automation_common import DO_NOT_TOUCH_PACKET_NAMES
from run_946_pipeline import build_promotion_status, evaluate_verification


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
PHASE4_DIR = WORKSPACE / "data" / "prot" / "946" / "generated" / "phase4"


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


class PromotionFixtureTest(unittest.TestCase):
    def test_unknown_field_types_block_verification(self) -> None:
        verification, conflicts, prelim_verified = evaluate_verification(
            size=2,
            packet_name="SYNTHETIC_UNKNOWN",
            field_declaration=[{"name": "value", "type": "ushort_unknown"}],
            draft_types=["ushort_unknown"],
            legacy_shape=[],
        )
        self.assertFalse(prelim_verified)
        self.assertIn("unknown-field-types", conflicts)
        self.assertFalse(verification["noUnknownFields"])

    def test_blacklist_packets_do_not_promote_even_with_runtime_success(self) -> None:
        packet_name = "PLAYER_INFO"
        self.assertIn(packet_name, DO_NOT_TOUCH_PACKET_NAMES)
        statuses = build_promotion_status(
            [
                {
                    "side": "server",
                    "opcode": 255,
                    "packetName": packet_name,
                    "status": "blacklisted",
                    "phase5Eligible": False,
                    "runtimePriority": False,
                    "reviewSource": "manual",
                    "conflicts": [],
                }
            ],
            {
                "packets": [
                    {
                        "packetName": packet_name,
                        "runtimeVerified": True,
                        "proxyStructured": True,
                    }
                ]
            },
        )
        self.assertEqual(statuses[0]["status"], "blacklisted")

    def test_reviewed_override_wins_over_heuristic_obj_add_draft(self) -> None:
        parser_index = load_json(PHASE4_DIR / "parserFieldIndex.json")
        obj_add = next(item for item in parser_index if item["packetName"] == "OBJ_ADD")
        self.assertTrue(obj_add["manualOverride"])
        self.assertEqual(obj_add["reviewSource"], "reviewed-override")
        self.assertEqual(obj_add["status"], "reviewed-override")
        self.assertEqual(obj_add["candidateTypes"], ["ushortle128", "ubytec", "ushort128"])


if __name__ == "__main__":
    unittest.main()
