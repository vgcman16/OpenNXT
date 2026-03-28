from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_forced_fallback_parity_doctor import build_artifact, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ForcedFallbackParityDoctorTest(unittest.TestCase):
    def test_reports_full_only_families_missing_on_forced_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            world_player_source = root / "WorldPlayer.kt"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-22T07:44:11.198367600Z world-stage name=demon stage=appearance",
                        "2026-03-22T07:44:11.208592800Z world-bind-local-player-model name=demon id=1482 component=1",
                        "2026-03-22T07:44:11.247706600Z world-open-loading-notes name=demon id=1417 parent=1477 component=508 reason=forced-map-build-fallback-minimal-bootstrap",
                        "2026-03-22T07:44:11.252898900Z world-force-minimal-interface-bootstrap name=demon reason=forced-map-build-fallback",
                        "2026-03-22T07:44:13.732170500Z world-open-forced-fallback-scene-bridge name=demon ids=1431,568,1465,1919",
                        "2026-03-22T07:44:13.732170500Z world-send-deferred-forced-fallback-completion-companions name=demon ids=1484,1483,745,284,1213,1448,291,1488,1680,1847,635,1639 scripts=139,14150 reason=forced-map-build-fallback-post-ready",
                        "2026-03-22T07:44:13.732170500Z world-send-forced-fallback-deferred-completion-scripts name=demon scripts=8862,2651,7486,10903,8778,4704,4308,10623,5559,3957 reason=forced-map-build-fallback",
                        "2026-03-22T07:44:20.778881100Z world-send-deferred-light-tail-scripts-after-scene-start name=demon scripts=11145,8420,8310 count=7 control50=141",
                        "2026-03-22T07:45:57.788288300Z world-send-deferred-completion-announcement-scripts-after-late-ready name=demon count=2 scripts=1264,3529 control50=236 acceptedCount=4",
                        "2026-03-22T07:46:01.000000000Z world-stage name=demon stage=appearance",
                        "2026-03-22T07:46:01.100000000Z world-bind-local-player-model name=demon id=1482 component=1",
                        "2026-03-22T07:46:01.200000000Z world-open-restored-interface name=demon id=1887 parent=1477 component=219",
                        "2026-03-22T07:46:01.300000000Z world-open-loading-notes name=demon id=1417 parent=1477 component=508 reason=full-bootstrap",
                    ]
                ),
            )

            write_text(
                world_player_source,
                "\n".join(
                    [
                        "private fun sendDeferredSceneStartLightTailScripts() {",
                        "}",
                        "private fun sendDeferredSceneStartFinalEventDelta() {",
                        "}",
                        "private fun sendDeferredCompletionAnnouncementScripts() {",
                        "}",
                        "private fun sendDeferredLateWorldCompletionEventDelta() {",
                        "}",
                        "private fun sendDeferredCompletionFullScripts() {",
                        "}",
                        "private fun sendLateRootInterfaceEventsIfConfigured(): Boolean {",
                        "}",
                        "private fun openForcedFallbackSceneStartBridge(includeEvents: Boolean = true) {",
                        "}",
                        "private fun sendForcedFallbackCompletionCompanions() {",
                        "}",
                        "player.interfaces.open(id = 1464, parent = 1477, component = 109, walkable = true)",
                        "sendInterfaceBootstrapScript(script = 8862, args = arrayOf(5, 1))",
                        "player.interfaces.open(id = 550, parent = 1477, component = 475, walkable = true)",
                        "player.interfaces.events(id = 1894, component = 16, from = 0, to = 2, mask = 2)",
                    ]
                ),
            )

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    world_player_source=world_player_source,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["summary"]["latestLikelyBlocker"], "forced-fallback-family-gap-before-scene-archives")
        families = {family["name"]: family for family in artifact["families"]}
        self.assertEqual(families["restored-world-panels"]["status"], "missing-on-forced-fallback")
        self.assertEqual(families["utility-panel-deck"]["status"], "missing-on-forced-fallback")
        self.assertTrue(families["scene-bridge-family"]["runtimeObserved"])
        self.assertTrue(families["completion-script-batch"]["runtimeObserved"])
        rendered = render_markdown(artifact)
        self.assertIn("restored-world-panels", rendered)
        self.assertIn("utility-panel-deck", rendered)
        self.assertIn("forced-fallback-family-gap-before-scene-archives", rendered)


if __name__ == "__main__":
    unittest.main()
