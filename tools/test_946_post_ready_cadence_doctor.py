from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_post_ready_cadence_doctor import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PostReadyCadenceDoctorTest(unittest.TestCase):
    def test_build_artifact_reports_short_post_ready_cadence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            content_dir = root / "content"
            server_log = root / "server.log"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-21T01:10:32.000000Z world-stage name=demon stage=appearance",
                        "2026-03-21T01:10:32.001000Z world-stage name=demon stage=interfaces",
                        "2026-03-21T01:10:32.002000Z world-ready-signal name=demon opcode=48 bytes=8 preview=1100 source=live",
                        "2026-03-21T01:10:32.003000Z world-sync-frame name=demon reason=initial frame=1 npcInfoOpcode=28 playerInfoOpcode=42",
                        "2026-03-21T01:10:32.004000Z world-send-player-info name=demon reason=initial frame=1 opcode=42 bytes=64",
                        "2026-03-21T01:10:32.005000Z send-raw opcode=42 bytes=64 remote=/127.0.0.1:64022 stage=interfaces preview=00",
                        "2026-03-21T01:10:32.006000Z world-hold-keepalive name=demon ticksRemaining=1 packet=NO_TIMEOUT reason=forced-map-build-fallback",
                        "2026-03-21T01:10:32.007000Z send-raw opcode=131 bytes=0 remote=/127.0.0.1:64022 stage=interfaces preview=<empty>",
                        "2026-03-21T01:10:32.008000Z world-send-deferred-completion-tail-after-sync name=demon reason=post-sync-hold-cleared",
                        "2026-03-21T01:10:32.009000Z world-sync-frame name=demon reason=tick frame=2 npcInfoOpcode=28 playerInfoOpcode=42",
                        "2026-03-21T01:10:32.010000Z world-send-player-info name=demon reason=tick frame=2 opcode=42 bytes=64",
                        "2026-03-21T01:10:32.011000Z send-raw opcode=42 bytes=64 remote=/127.0.0.1:64022 stage=interfaces preview=00",
                        "2026-03-21T01:10:32.012000Z send-raw opcode=131 bytes=0 remote=/127.0.0.1:64022 stage=interfaces preview=<empty>",
                    ]
                ),
            )
            write_text(
                content_dir / "session-01-20260321-011007.log",
                "\n".join(
                    [
                        "session#1 start=2026-03-21T01:10:31.500000+00:00",
                        "session#1 mode=tls initial-peek=16 03 03 00 a9",
                        "session#1 session-route=tls-http-content",
                        "session#1 request[1]=GET /ms?m=0&a=255 label=reference-table[0]",
                        "session#1 end=2026-03-21T01:10:32.900000+00:00",
                    ]
                ),
            )
            write_text(
                server_log,
                "[nioEventLoopGroup-3-9] INFO com.opennxt.net.game.pipeline.DynamicPacketHandler - Channel /127.0.0.1:64022 closed after bootstrap stage interfaces (current=none, completed=appearance, interfaces)\n",
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    content_capture_dir=content_dir,
                    server_log=server_log,
                    attempt_limit=12,
                    cluster_id="20260321-011007",
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["likelyBlocker"], "post-ready-cadence-too-short")
        self.assertEqual(artifact["summary"]["acceptedReadyAttemptCount"], 1)
        self.assertEqual(artifact["summary"]["maxTickPlayerInfoFramesAfterReady"], 1)
        self.assertEqual(artifact["attempts"][0]["sendRaw131CountAfterReady"], 2)
        rendered = render_markdown(artifact)
        self.assertIn("post-ready-cadence-too-short", rendered)
        self.assertIn("Tick PLAYER_INFO frames after ready", rendered)


if __name__ == "__main__":
    unittest.main()
