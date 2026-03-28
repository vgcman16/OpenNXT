from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_post_scene_opcode_doctor import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PostSceneOpcodeDoctorTest(unittest.TestCase):
    def test_build_artifact_classifies_late_unresolved_pointer_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            content_dir = root / "content"
            decomp_dir = root / "ghidra-projects"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-22T02:56:01.000000Z world-stage name=demon stage=appearance",
                        "2026-03-22T02:56:01.010000Z world-stage name=demon stage=login-response",
                        "2026-03-22T02:56:01.020000Z world-stage name=demon stage=pipeline-switch",
                        "2026-03-22T02:56:01.030000Z world-stage name=demon stage=rebuild",
                        "2026-03-22T02:56:01.040000Z world-stage name=demon stage=interfaces",
                        "2026-03-22T02:56:10.000000Z world-accept-late-scene-ready-signal name=demon opcode=48 bytes=8 preview=01020304 source=live-post-scene-start control50=175 acceptedCount=1 keepAwaiting=true",
                        "2026-03-22T02:56:10.100000Z recv-raw name=demon opcode=17 bytes=12 preview=0300ffff014202cf0007ab00",
                        "2026-03-22T02:56:10.200000Z world-ignore-client-compat name=demon opcode=17 bytes=12 awaitingMapBuildComplete=false awaitingWorldReadySignal=false preview=0300ffff014202cf0007ab00",
                        "2026-03-22T02:56:10.300000Z recv-raw name=demon opcode=2 bytes=6 preview=0432009d7f7f",
                        "2026-03-22T02:56:10.400000Z world-unhandled-client-compat name=demon opcode=2 bytes=6 preview=0432009d7f7f",
                        "2026-03-22T02:56:10.500000Z recv-raw name=demon opcode=85 bytes=7 preview=fffffe9d003204",
                        "2026-03-22T02:56:10.600000Z world-unhandled-client-compat name=demon opcode=85 bytes=7 preview=fffffe9d003204",
                    ]
                ),
            )

            write_text(
                content_dir / "session-04-20260322-025545.log",
                "\n".join(
                    [
                        "session#4 start=2026-03-22T02:55:46+00:00",
                        "session#4 mode=tls initial-peek=16 03 03 00 a9",
                        "session#4 session-route=tls-http-content",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 32 35 35 26 6b 3d 39 34 36 26 67 3d 32 35 35 26 63 3d 30 26 76 3d 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "remote->tls-client first-chunk-1 bytes=40 hex=48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d 0a 43 6f 6e 74 65 6e 74 2d 6c 65 6e 67 74 68 3a 20 34 31 39 31 0d 0a 0d 0a",
                        "session#4 bytes tls-client->remote=80 remote->tls-client=4191",
                        "session#4 end=2026-03-22T02:56:15+00:00",
                    ]
                ),
            )

            write_text(
                decomp_dir / "decomp-1400d08e0.log",
                "\n".join(
                    [
                        "void FUN_1400d08e0(longlong param_1)",
                        "uVar14 = 0x7fff;",
                        "uVar6 = *(longlong *)(piVar1 + 6) - *(longlong *)(param_1 + 0x20);",
                        "if ((int)(float)piVar1[2] < 0xffff) { }",
                        "if ((int)(float)piVar1[1] < 0xffff) { }",
                        "*(byte *)(lVar4 + *(longlong *)(local_30 + 0x18)) = (byte)(-(uint)(iVar2 != 0) >> 8);",
                    ]
                ),
            )
            write_text(
                decomp_dir / "decomp-140144a60.log",
                "\n".join(
                    [
                        "void FUN_140144a60(longlong param_1)",
                        "uVar9 = 0xffff;",
                        "uVar9 = *(longlong *)(lVar12 + 0x18) - *(longlong *)(param_1 + 0x20);",
                        "if ((int)*(float *)(lVar12 + 8) < 0xffff) { }",
                        "if ((int)*(float *)(lVar12 + 4) < 0xffff) { }",
                        "uVar2 = *(undefined4 *)(lVar12 + 0x2c);",
                        "uVar3 = *(undefined4 *)(lVar12 + 0x28);",
                    ]
                ),
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    content_capture_dir=content_dir,
                    cluster_id="20260322-025545",
                    attempt_limit=12,
                    decomp_log_dir=decomp_dir,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["latestLikelyBlocker"], "post-scene-server-stall-after-ready")
        unresolved = artifact["attempts"][0]["unresolvedClientOpcodes"]
        self.assertEqual([entry["opcode"] for entry in unresolved], [2, 85])
        self.assertEqual(unresolved[0]["classification"], "pointer-input-press-delta")
        self.assertEqual(unresolved[1]["classification"], "pointer-input-state")
        self.assertEqual(unresolved[0]["responseExpectation"], "no-direct-server-response-expected")
        self.assertEqual(artifact["attempts"][0]["pairedContentSummary"]["archiveRequests"], 0)
        rendered = render_markdown(artifact)
        self.assertIn("post-scene-server-stall-after-ready", rendered)
        self.assertIn("first non-reference /ms archive request after late-scene-ready acceptance", rendered)


if __name__ == "__main__":
    unittest.main()
