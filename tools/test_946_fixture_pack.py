from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_fixture_pack import analyze_fixture_pack


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FixturePackTest(unittest.TestCase):
    def test_fixture_pack_writes_labeled_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            labels = root / "labels.json"
            output_dir = root / "fixtures"
            write_text(
                world_log,
                "\n".join(
                    [
                        "20:00:00 world-stage stage=appearance",
                        "20:00:01 world-stage stage=interfaces",
                        "20:00:02 send-raw stage=interfaces opcode=42 bytes=66 preview=aa",
                        "20:01:00 world-stage stage=appearance",
                        "20:01:01 world-stage stage=interfaces",
                        "20:01:02 send-raw stage=interfaces opcode=42 bytes=3 preview=bb",
                    ]
                )
                + "\n",
            )
            write_text(
                labels,
                json.dumps(
                    {
                        "1:3": {"label": "stable", "role": "seed"},
                        "4:6": {"label": "loop", "role": "bad"},
                    },
                    indent=2,
                )
                + "\n",
            )

            artifact = analyze_fixture_pack(
                SimpleNamespace(
                    world_log=world_log,
                    labels=labels,
                    window=[],
                    output_dir=output_dir,
                )
            )

            stable_fixture = output_dir / "stable_interfaces" / "session_1_3.json"
            bad_fixture = output_dir / "short_loop" / "session_4_6.json"
            stable_exists = stable_fixture.exists()
            bad_exists = bad_fixture.exists()

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["summary"]["fixtureCount"], 2)
        self.assertTrue(stable_exists)
        self.assertTrue(bad_exists)


if __name__ == "__main__":
    unittest.main()
