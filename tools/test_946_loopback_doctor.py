from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_loopback_doctor import build_artifact, parse_cluster_stamp, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class LoopbackDoctorTest(unittest.TestCase):
    def test_parse_cluster_stamp_reads_timestamp_suffix(self) -> None:
        stamp = parse_cluster_stamp(Path("session-47-20260321-011007.log"))
        self.assertEqual(stamp, "20260321-011007")

    def test_build_artifact_reports_reference_table_loopback_with_exact_needs(self) -> None:
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
                        "2026-03-21T01:10:32.005000Z world-send-rebuild-tail name=demon chunkX=402 chunkY=402 npcBits=7 mapSize=5 areaType=474 hash1=-2147483648 hash2=2147483647",
                        "2026-03-21T01:10:32.008000Z world-waiting-map-build-complete name=demon",
                        "2026-03-21T01:10:32.629000Z world-map-build-complete-compat name=demon opcode=0 bytes=1291",
                        "2026-03-21T01:10:32.630000Z world-stage name=demon stage=stats",
                        "2026-03-21T01:10:32.654000Z world-stage name=demon stage=default-state",
                        "2026-03-21T01:10:32.658000Z world-stage name=demon stage=interfaces",
                        "2026-03-21T01:10:32.670000Z world-open-minimal-child name=demon id=1482 parent=1477 component=27",
                    ]
                ),
            )
            write_text(
                content_dir / "session-47-20260321-011007.log",
                "\n".join(
                    [
                        "session#47 start=2026-03-21T01:10:31.500000+00:00",
                        "session#47 mode=tls initial-peek=16 03 03 00 a9",
                        "session#47 session-route=tls-http-content",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 32 35 35 26 6b 3d 39 34 36 26 67 3d 32 35 35 26 63 3d 30 26 76 3d 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "remote->tls-client first-chunk-1 bytes=40 hex=48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d 0a 43 6f 6e 74 65 6e 74 2d 6c 65 6e 67 74 68 3a 20 33 37 39 38 0d 0a 0d 0a",
                        "session#47 bytes tls-client->remote=80 remote->tls-client=4191",
                        "session#47 end=2026-03-21T01:10:32.900000+00:00",
                    ]
                ),
            )
            write_text(
                content_dir / "session-75-20260321-011007.log",
                "\n".join(
                    [
                        "session#75 start=2026-03-21T01:10:31.900000+00:00",
                        "session#75 mode=raw initial-peek=0e",
                        "session#75 session-route=raw-game",
                        "session#75 bytes raw-client->remote=2107 remote->raw-client=6887",
                        "session#75 end=2026-03-21T01:10:32.800000+00:00",
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
                    ]
                ),
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    content_capture_dir=content_dir,
                    server_log=server_log,
                    attempt_limit=12,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["likelyBlocker"], "reference-table-loopback")
        self.assertEqual(artifact["summary"]["latestDisconnectStage"], "interfaces")
        self.assertEqual(artifact["summary"]["archiveRequestCount"], 0)
        self.assertIn("first real scene archive request after interfaces", artifact["summary"]["latestNeeds"])
        rendered = render_markdown(artifact)
        self.assertIn("reference-table-loopback", rendered)
        self.assertIn("first non-reference /ms request", rendered)

    def test_build_artifact_reports_prelogin_when_cluster_has_no_world_attempts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            content_dir = root / "content"
            server_log = root / "server.log"

            write_text(world_log, "")
            write_text(
                content_dir / "session-01-20260321-011007.log",
                "\n".join(
                    [
                        "session#1 start=2026-03-21T01:10:23.410272+00:00",
                        "session#1 mode=raw initial-peek=0f 2a 00 00 03",
                        "session#1 session-route=raw-game",
                        "session#1 bytes raw-client->remote=74 remote->raw-client=5884",
                        "session#1 end=2026-03-21T01:10:53.480514+00:00",
                    ]
                ),
            )
            write_text(server_log, "")

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    content_capture_dir=content_dir,
                    server_log=server_log,
                    attempt_limit=12,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["likelyBlocker"], "prelogin-stall")

    def test_build_artifact_prefers_latest_cluster_with_world_attempts(self) -> None:
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
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 32 35 35 26 6b 3d 39 34 36 26 67 3d 32 35 35 26 63 3d 30 26 76 3d 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "session#1 bytes tls-client->remote=80 remote->tls-client=4191",
                        "session#1 end=2026-03-21T01:10:32.900000+00:00",
                    ]
                ),
            )
            write_text(
                content_dir / "session-01-20260321-011515.log",
                "\n".join(
                    [
                        "session#1 start=2026-03-21T01:15:15.500000+00:00",
                        "session#1 mode=raw initial-peek=0f 2a 00 00 03",
                        "session#1 session-route=raw-game",
                        "session#1 bytes raw-client->remote=74 remote->raw-client=5884",
                        "session#1 end=2026-03-21T01:15:16.000000+00:00",
                    ]
                ),
            )
            write_text(
                server_log,
                "[nioEventLoopGroup-3-9] INFO com.opennxt.net.login.LoginServerDecoder - Attempted game login: demon, ***** (type=GAME)\n"
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    content_capture_dir=content_dir,
                    server_log=server_log,
                    cluster_id=None,
                    attempt_limit=12,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["clusterId"], "20260321-011007")


if __name__ == "__main__":
    unittest.main()
