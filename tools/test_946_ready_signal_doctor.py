from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_ready_signal_doctor import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ReadySignalDoctorTest(unittest.TestCase):
    def test_build_artifact_reports_skipped_ready_wait_then_ignored_ready_packets(self) -> None:
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
                        "session#1 end=2026-03-21T01:10:32.900000+00:00",
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
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Ignoring unidentified client opcode 48 for demon (payloadBytes=10, preview=0a01e55f014b0227082f, awaitingMapBuildComplete=false, awaitingWorldReadySignal=false)",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Ignoring unidentified client opcode 17 for demon (payloadBytes=12, preview=0501ffff014b022700082f00, awaitingMapBuildComplete=false, awaitingWorldReadySignal=false)",
                        "[nioEventLoopGroup-3-9] INFO com.opennxt.net.game.pipeline.DynamicPacketHandler - Channel /127.0.0.1:64022 closed after bootstrap stage interfaces (current=none, completed=appearance, login-response, pipeline-switch, rebuild, stats, default-state, interfaces)",
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

        self.assertEqual(artifact["summary"]["likelyBlocker"], "ready-signal-cleared-too-early")
        self.assertEqual(artifact["summary"]["ignoredReadyOpcodeCount"], 2)
        self.assertEqual(artifact["attempts"][0]["serverAttempt"]["ignoredReadyOpcodes"], [48, 17])
        rendered = render_markdown(artifact)
        self.assertIn("ready-signal-cleared-too-early", rendered)
        self.assertIn("Ignored ready opcodes", rendered)

    def test_build_artifact_reports_when_ready_signal_is_latched_and_consumed(self) -> None:
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
                        "2026-03-21T01:10:32.002000Z world-stage name=demon stage=interfaces",
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
                        "session#1 end=2026-03-21T01:10:32.900000+00:00",
                    ]
                ),
            )
            write_text(
                server_log,
                "\n".join(
                    [
                        "[nioEventLoopGroup-3-6] INFO com.opennxt.net.login.LoginServerDecoder - Attempted game login: demon, ***** (type=GAME)",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Latching unidentified client opcode 48 for demon as an early post-bootstrap world-ready candidate (payloadBytes=206, preview=0b06ffff, awaitingMapBuildComplete=true, awaitingWorldReadySignal=false)",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Waiting for post-bootstrap world-ready signal before sending initial world sync for demon",
                        "[tick-engine] INFO com.opennxt.model.world.WorldPlayer - Treating unidentified opcode 48 as post-bootstrap world-ready signal for demon (payloadBytes=206, preview=0b06ffff, source=latched)",
                        "[nioEventLoopGroup-3-9] INFO com.opennxt.net.game.pipeline.DynamicPacketHandler - Channel /127.0.0.1:64022 closed after bootstrap stage interfaces (current=none, completed=appearance, interfaces)",
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

        self.assertEqual(artifact["summary"]["likelyBlocker"], "ready-signal-accepted-but-loop-persisted")
        self.assertEqual(artifact["summary"]["acceptedReadyOpcodeCount"], 1)
        self.assertEqual(artifact["attempts"][0]["serverAttempt"]["acceptedReadyOpcodes"], [48])


if __name__ == "__main__":
    unittest.main()
