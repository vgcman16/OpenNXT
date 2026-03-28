from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


WORKSPACE = Path(r"C:\Users\Demon\Documents\New project\OpenNXT")
PHASE4_DIR = WORKSPACE / "data" / "prot" / "946" / "generated" / "phase4"


def load_json(path: Path) -> dict | list:
    return json.loads(path.read_text(encoding="utf-8"))


class Phase4FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        command = [
            sys.executable,
            str(WORKSPACE / "tools" / "run_946_phase4.py"),
            "--extract-packet",
            "IF_SETRETEX",
            "--extract-packet",
            "IF_SETEVENTS",
            "--extract-packet",
            "OBJ_ADD",
        ]
        completed = subprocess.run(
            command,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                "Phase 4 fixture extraction failed.\n"
                f"STDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
            )

    def test_if_setretex_exact_candidate_types(self) -> None:
        payload = load_json(PHASE4_DIR / "parserFields" / "IF_SETRETEX.json")
        self.assertEqual(
            [field["candidateType"] for field in payload["fields"]],
            ["ubytec", "intv1", "ushort128", "ushortle"],
        )

    def test_if_setevents_exact_candidate_types(self) -> None:
        payload = load_json(PHASE4_DIR / "parserFields" / "IF_SETEVENTS.json")
        self.assertEqual(
            [field["candidateType"] for field in payload["fields"]],
            ["intle", "ushortle", "intv2", "ushortle128"],
        )

    def test_obj_add_exact_candidate_types(self) -> None:
        payload = load_json(PHASE4_DIR / "parserFields" / "OBJ_ADD.json")
        self.assertEqual(
            [field["candidateType"] for field in payload["fields"]],
            ["ushortle128", "ubytec", "ushort128"],
        )


if __name__ == "__main__":
    unittest.main()
