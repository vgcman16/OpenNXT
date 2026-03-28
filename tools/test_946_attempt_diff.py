from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_attempt_diff import build_artifact, common_suffix, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class AttemptDiffDoctorTest(unittest.TestCase):
    def test_common_suffix_keeps_only_shared_tail(self) -> None:
        self.assertEqual(common_suffix([["a", "b", "c"], ["x", "b", "c"], ["b", "c"]]), ["b", "c"])

    def test_build_artifact_reports_deterministic_interfaces_tail(self) -> None:
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
                        "2026-03-21T01:10:32.002000Z world-stage name=demon stage=login-response",
                        "2026-03-21T01:10:32.003000Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-21T01:10:32.004000Z world-stage name=demon stage=rebuild",
                        "2026-03-21T01:10:32.005000Z world-stage name=demon stage=stats",
                        "2026-03-21T01:10:32.006000Z world-stage name=demon stage=default-state",
                        "2026-03-21T01:10:32.007000Z world-stage name=demon stage=interfaces",
                        "2026-03-21T01:10:32.008000Z world-open-minimal-child name=demon id=1482 parent=1477 component=27",
                        "2026-03-21T01:10:32.009000Z send-raw stage=interfaces opcode=59 bytes=12 preview=deadbeef",
                        "2026-03-21T01:10:32.010000Z world-send-deferred-completion-tail name=demon",
                        "2026-03-21T01:10:32.011000Z send-raw stage=interfaces opcode=42 bytes=64 preview=beadfeed",
                        "2026-03-21T01:10:35.000000Z world-stage name=demon stage=appearance",
                        "2026-03-21T01:10:35.002000Z world-stage name=demon stage=login-response",
                        "2026-03-21T01:10:35.003000Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-21T01:10:35.004000Z world-stage name=demon stage=rebuild",
                        "2026-03-21T01:10:35.005000Z world-stage name=demon stage=stats",
                        "2026-03-21T01:10:35.006000Z world-stage name=demon stage=default-state",
                        "2026-03-21T01:10:35.007000Z world-stage name=demon stage=interfaces",
                        "2026-03-21T01:10:35.008000Z world-open-minimal-child name=demon id=1482 parent=1477 component=27",
                        "2026-03-21T01:10:35.009000Z send-raw stage=interfaces opcode=59 bytes=12 preview=deadbeef",
                        "2026-03-21T01:10:35.010000Z world-send-deferred-completion-tail name=demon",
                        "2026-03-21T01:10:35.011000Z send-raw stage=interfaces opcode=42 bytes=64 preview=beadfeed",
                    ]
                ),
            )
            write_text(
                content_dir / "session-20-20260321-011007.log",
                "\n".join(
                    [
                        "session#20 start=2026-03-21T01:10:31.500000+00:00",
                        "session#20 mode=tls initial-peek=16 03 03 00 a9",
                        "session#20 session-route=tls-http-content",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 32 35 35 26 6b 3d 39 34 36 26 67 3d 32 35 35 26 63 3d 30 26 76 3d 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "remote->tls-client first-chunk-1 bytes=40 hex=48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d 0a 43 6f 6e 74 65 6e 74 2d 6c 65 6e 67 74 68 3a 20 34 31 39 31 0d 0a 0d 0a",
                        "session#20 bytes tls-client->remote=80 remote->tls-client=4191",
                        "session#20 end=2026-03-21T01:10:32.900000+00:00",
                    ]
                ),
            )
            write_text(
                content_dir / "session-21-20260321-011007.log",
                "\n".join(
                    [
                        "session#21 start=2026-03-21T01:10:34.500000+00:00",
                        "session#21 mode=tls initial-peek=16 03 03 00 a9",
                        "session#21 session-route=tls-http-content",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 32 35 35 26 6b 3d 39 34 36 26 67 3d 32 35 35 26 63 3d 30 26 76 3d 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "remote->tls-client first-chunk-1 bytes=40 hex=48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d 0a 43 6f 6e 74 65 6e 74 2d 6c 65 6e 67 74 68 3a 20 34 31 39 31 0d 0a 0d 0a",
                        "session#21 bytes tls-client->remote=80 remote->tls-client=4191",
                        "session#21 end=2026-03-21T01:10:35.900000+00:00",
                    ]
                ),
            )
            write_text(
                content_dir / "session-22-20260321-011007.log",
                "\n".join(
                    [
                        "session#22 start=2026-03-21T01:10:31.300000+00:00",
                        "session#22 mode=raw initial-peek=0e",
                        "session#22 session-route=raw-game",
                        "session#22 bytes raw-client->remote=2108 remote->raw-client=10174",
                        "session#22 end=2026-03-21T01:10:32.800000+00:00",
                    ]
                ),
            )
            write_text(
                content_dir / "session-23-20260321-011007.log",
                "\n".join(
                    [
                        "session#23 start=2026-03-21T01:10:34.300000+00:00",
                        "session#23 mode=raw initial-peek=0e",
                        "session#23 session-route=raw-game",
                        "session#23 bytes raw-client->remote=2108 remote->raw-client=10174",
                        "session#23 end=2026-03-21T01:10:35.800000+00:00",
                    ]
                ),
            )
            write_text(
                server_log,
                "\n".join(
                    [
                        "[nioEventLoopGroup-3-6] INFO com.opennxt.net.login.LoginServerDecoder - Attempted game login: demon, ***** (type=GAME)",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Finished world bootstrap for demon after stages appearance, login-response, pipeline-switch, rebuild, stats, default-state, interfaces",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Skipping post-bootstrap world-ready wait for demon because forced MAP_BUILD fallback completed without a latched ready signal; sending initial world sync immediately",
                        "[nioEventLoopGroup-3-9] INFO com.opennxt.net.game.pipeline.DynamicPacketHandler - Channel /127.0.0.1:64022 closed after bootstrap stage interfaces (current=none, completed=appearance, login-response, pipeline-switch, rebuild, stats, default-state, interfaces)",
                        "[nioEventLoopGroup-3-6] INFO com.opennxt.net.login.LoginServerDecoder - Attempted game login: demon, ***** (type=GAME)",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Finished world bootstrap for demon after stages appearance, login-response, pipeline-switch, rebuild, stats, default-state, interfaces",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Skipping post-bootstrap world-ready wait for demon because forced MAP_BUILD fallback completed without a latched ready signal; sending initial world sync immediately",
                        "[nioEventLoopGroup-3-9] INFO com.opennxt.net.game.pipeline.DynamicPacketHandler - Channel /127.0.0.1:64023 closed after bootstrap stage interfaces (current=none, completed=appearance, login-response, pipeline-switch, rebuild, stats, default-state, interfaces)",
                    ]
                ),
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

        self.assertEqual(artifact["summary"]["uniqueTailSignatureCount"], 1)
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "deterministic-interfaces-tail-loopback")
        self.assertIn("world-send-deferred-completion-tail", artifact["summary"]["commonWorldTailSuffix"])
        self.assertEqual(artifact["attempts"][0]["pairedContentSession"]["firstRequestLabel"], "reference-table[0]")
        rendered = render_markdown(artifact)
        self.assertIn("Signature 1", rendered)
        self.assertIn("world-send-deferred-completion-tail", rendered)


if __name__ == "__main__":
    unittest.main()
