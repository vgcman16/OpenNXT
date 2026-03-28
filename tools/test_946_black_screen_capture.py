from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_black_screen_capture import build_capture_artifact


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class BlackScreenCaptureTest(unittest.TestCase):
    @patch("run_946_black_screen_capture.required_paths", return_value={"missing": Path("C:/does-not-exist")})
    def test_missing_helper_script_blocks_capture(self, _required_paths: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            artifact = build_capture_artifact(
                SimpleNamespace(
                    capture_seconds=1,
                    runtime_trace_seconds=1,
                    js5_idle_timeout_seconds=1,
                    reset_cache=False,
                client_variant="patched",
                world_log=root / "world.log",
                js5_session_dir=root / "js5",
                content_capture_dir=root / "content",
                runtime_trace_dir=root / "runtime",
                output_dir=root,
            )
            )

        self.assertEqual(artifact["status"], "blocked")
        self.assertEqual(artifact["summary"]["statusReason"], "missing-helper-paths")

    @patch("run_946_black_screen_capture.required_paths", return_value={"ok": Path(__file__)})
    @patch("run_946_black_screen_capture.run_downstream_tools")
    @patch("run_946_black_screen_capture.latest_path")
    @patch("run_946_black_screen_capture.select_new_world_window", return_value="11:20")
    @patch("run_946_black_screen_capture.finalize_process", return_value={"returnCode": 0, "stdout": "", "stderr": ""})
    @patch("run_946_black_screen_capture.kill_pid")
    @patch("run_946_black_screen_capture.summarize_recent_content_sessions")
    @patch("run_946_black_screen_capture.summarize_live_watch")
    @patch("run_946_black_screen_capture.collect_client_network_snapshot")
    @patch("run_946_black_screen_capture.time.sleep")
    @patch("run_946_black_screen_capture.start_runtime_trace")
    @patch("run_946_black_screen_capture.launch_live_stack")
    @patch("run_946_black_screen_capture.list_world_windows", return_value=["1:10"])
    def test_successful_capture_emits_ok_metadata(
        self,
        _before_windows: patch,
        launch_live_stack: patch,
        start_runtime_trace: patch,
        _sleep: patch,
        collect_client_network_snapshot: patch,
        summarize_live_watch: patch,
        summarize_recent_content_sessions: patch,
        _kill_pid: patch,
        _finalize: patch,
        _select_window: patch,
        latest_path: patch,
        run_downstream_tools: patch,
        _required_paths: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            latest_path.return_value = root / "content-session.log"
            launch_live_stack.return_value = {
                "command": ["launch"],
                "returnCode": 0,
                "stdout": "{}",
                "stderr": "",
                "state": {
                    "ClientPid": 200,
                    "ServerPid": 201,
                    "LobbyProxyPid": 202,
                    "GameProxyPid": 203,
                    "WatchdogPid": 204,
                    "WrapperPid": 205,
                    "ForceLobbyTlsMitm": True,
                    "UseContentTlsRoute": True,
                    "ContentRouteMode": "content-only-local-mitm",
                    "ClientArgs": [
                        "http://lobby45a.runescape.com:8081/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&gameHostOverride=lobby45a.runescape.com"
                    ],
                },
            }
            start_runtime_trace.return_value = (SimpleNamespace(pid=300), ["trace"], root / "trace.jsonl")
            collect_client_network_snapshot.return_value = {
                "localMitm443ConnectionCount": 1,
                "directExternal443ConnectionCount": 0,
            }
            summarize_recent_content_sessions.return_value = {
                "freshSessionCount": 1,
                "freshTlsSessionCount": 1,
                "localMsRequestsObserved": True,
                "latestSessionLog": str(root / "content-session.log"),
                "sessions": [],
            }
            summarize_live_watch.return_value = {"present": True, "terminalState": "black-screen-plateau", "path": str(root / "live-watch.json")}
            run_downstream_tools.return_value = {
                "sceneDeliveryCommand": ["scene"],
                "toolDoctorCommand": ["doctor"],
                "sceneDeliveryArtifact": {
                    "status": "ok",
                    "summary": {"overlapConfidence": "exact"},
                    "verdict": {"likelyBlocker": "archive-delivery-observed"},
                },
                "toolDoctorArtifact": {"status": "ok"},
            }

            artifact = build_capture_artifact(
                SimpleNamespace(
                    capture_seconds=1,
                    runtime_trace_seconds=1,
                    js5_idle_timeout_seconds=1,
                    reset_cache=False,
                    client_variant="patched",
                    world_log=root / "world.log",
                    js5_session_dir=root / "js5",
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "ok")
        self.assertTrue(artifact["summary"]["overlapAchieved"])
        self.assertTrue(artifact["summary"]["liveWatcherPresent"])
        run_downstream_tools.assert_called_once_with("11:20")

    @patch("run_946_black_screen_capture.required_paths", return_value={"ok": Path(__file__)})
    @patch("run_946_black_screen_capture.run_downstream_tools")
    @patch("run_946_black_screen_capture.latest_path")
    @patch("run_946_black_screen_capture.select_new_world_window", return_value="11:20")
    @patch("run_946_black_screen_capture.finalize_process", return_value={"returnCode": 0, "stdout": "", "stderr": ""})
    @patch("run_946_black_screen_capture.kill_pid")
    @patch("run_946_black_screen_capture.summarize_recent_content_sessions")
    @patch("run_946_black_screen_capture.collect_client_network_snapshot")
    @patch("run_946_black_screen_capture.time.sleep")
    @patch("run_946_black_screen_capture.start_runtime_trace")
    @patch("run_946_black_screen_capture.launch_live_stack")
    @patch("run_946_black_screen_capture.list_world_windows", return_value=["1:10"])
    def test_missing_overlap_returns_partial(
        self,
        _before_windows: patch,
        launch_live_stack: patch,
        start_runtime_trace: patch,
        _sleep: patch,
        collect_client_network_snapshot: patch,
        summarize_recent_content_sessions: patch,
        _kill_pid: patch,
        _finalize: patch,
        _select_window: patch,
        latest_path: patch,
        run_downstream_tools: patch,
        _required_paths: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            latest_path.return_value = root / "content-session.log"
            launch_live_stack.return_value = {
                "command": ["launch"],
                "returnCode": 0,
                "stdout": "{}",
                "stderr": "",
                "state": {
                    "ClientPid": 200,
                    "ForceLobbyTlsMitm": True,
                    "UseContentTlsRoute": True,
                    "ContentRouteMode": "content-only-local-mitm",
                    "ClientArgs": [
                        "http://lobby45a.runescape.com:8081/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&gameHostOverride=lobby45a.runescape.com"
                    ],
                },
            }
            start_runtime_trace.return_value = (SimpleNamespace(pid=300), ["trace"], root / "trace.jsonl")
            collect_client_network_snapshot.return_value = {
                "localMitm443ConnectionCount": 1,
                "directExternal443ConnectionCount": 0,
            }
            summarize_recent_content_sessions.return_value = {
                "freshSessionCount": 1,
                "freshTlsSessionCount": 1,
                "localMsRequestsObserved": True,
                "latestSessionLog": str(root / "content-session.log"),
                "sessions": [],
            }
            run_downstream_tools.return_value = {
                "sceneDeliveryCommand": ["scene"],
                "toolDoctorCommand": ["doctor"],
                "sceneDeliveryArtifact": {
                    "status": "partial",
                    "summary": {"overlapConfidence": "missing"},
                    "verdict": {"likelyBlocker": "capture-missing"},
                },
                "toolDoctorArtifact": {"status": "ok"},
            }

            artifact = build_capture_artifact(
                SimpleNamespace(
                    capture_seconds=1,
                    runtime_trace_seconds=1,
                    js5_idle_timeout_seconds=1,
                    reset_cache=False,
                    client_variant="patched",
                    world_log=root / "world.log",
                    js5_session_dir=root / "js5",
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["summary"]["statusReason"], "overlap-missing")

    @patch("run_946_black_screen_capture.required_paths", return_value={"ok": Path(__file__)})
    @patch("run_946_black_screen_capture.run_downstream_tools")
    @patch("run_946_black_screen_capture.latest_path")
    @patch("run_946_black_screen_capture.select_new_world_window", return_value=None)
    @patch("run_946_black_screen_capture.finalize_process", return_value={"returnCode": 0, "stdout": "", "stderr": ""})
    @patch("run_946_black_screen_capture.kill_pid")
    @patch("run_946_black_screen_capture.summarize_recent_content_sessions")
    @patch("run_946_black_screen_capture.collect_client_network_snapshot")
    @patch("run_946_black_screen_capture.time.sleep")
    @patch("run_946_black_screen_capture.start_runtime_trace")
    @patch("run_946_black_screen_capture.launch_live_stack")
    @patch("run_946_black_screen_capture.list_world_windows", return_value=["1:10"])
    def test_missing_world_window_reports_prelogin_route_regression(
        self,
        _before_windows: patch,
        launch_live_stack: patch,
        start_runtime_trace: patch,
        _sleep: patch,
        collect_client_network_snapshot: patch,
        summarize_recent_content_sessions: patch,
        _kill_pid: patch,
        _finalize: patch,
        _select_window: patch,
        latest_path: patch,
        run_downstream_tools: patch,
        _required_paths: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            latest_path.return_value = root / "content-session.log"
            launch_live_stack.return_value = {
                "command": ["launch"],
                "returnCode": 0,
                "stdout": "{}",
                "stderr": "",
                "state": {
                    "ClientPid": 200,
                    "ForceLobbyTlsMitm": True,
                    "UseContentTlsRoute": True,
                    "ContentRouteMode": "content-only-local-mitm",
                    "ClientArgs": [
                        "http://lobby45a.runescape.com:8081/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&gameHostOverride=lobby45a.runescape.com"
                    ],
                },
            }
            start_runtime_trace.return_value = (SimpleNamespace(pid=300), ["trace"], root / "trace.jsonl")
            collect_client_network_snapshot.return_value = {
                "localMitm443ConnectionCount": 0,
                "directExternal443ConnectionCount": 0,
            }
            summarize_recent_content_sessions.return_value = {
                "freshSessionCount": 0,
                "freshTlsSessionCount": 0,
                "localMsRequestsObserved": False,
                "latestSessionLog": "",
                "sessions": [],
            }
            run_downstream_tools.return_value = {
                "sceneDeliveryCommand": ["scene"],
                "toolDoctorCommand": ["doctor"],
                "sceneDeliveryArtifact": {"status": "partial", "summary": {"overlapConfidence": "missing"}, "verdict": {}},
                "toolDoctorArtifact": {"status": "ok"},
            }

            artifact = build_capture_artifact(
                SimpleNamespace(
                    capture_seconds=1,
                    runtime_trace_seconds=1,
                    js5_idle_timeout_seconds=1,
                    reset_cache=False,
                    client_variant="patched",
                    world_log=root / "world.log",
                    js5_session_dir=root / "js5",
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["summary"]["statusReason"], "prelogin-route-regression")
        self.assertTrue(artifact["summary"]["canonicalMitmLaunch"])

    @patch("run_946_black_screen_capture.required_paths", return_value={"ok": Path(__file__)})
    @patch("run_946_black_screen_capture.run_downstream_tools")
    @patch("run_946_black_screen_capture.latest_path")
    @patch("run_946_black_screen_capture.select_new_world_window", return_value="11:20")
    @patch("run_946_black_screen_capture.finalize_process", return_value={"returnCode": 0, "stdout": "", "stderr": ""})
    @patch("run_946_black_screen_capture.kill_pid")
    @patch("run_946_black_screen_capture.summarize_recent_content_sessions")
    @patch("run_946_black_screen_capture.collect_client_network_snapshot")
    @patch("run_946_black_screen_capture.time.sleep")
    @patch("run_946_black_screen_capture.start_runtime_trace")
    @patch("run_946_black_screen_capture.launch_live_stack")
    @patch("run_946_black_screen_capture.list_world_windows", return_value=["1:10"])
    def test_host_rewrite_one_is_flagged_non_canonical(
        self,
        _before_windows: patch,
        launch_live_stack: patch,
        start_runtime_trace: patch,
        _sleep: patch,
        collect_client_network_snapshot: patch,
        summarize_recent_content_sessions: patch,
        _kill_pid: patch,
        _finalize: patch,
        _select_window: patch,
        latest_path: patch,
        run_downstream_tools: patch,
        _required_paths: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            latest_path.return_value = root / "content-session.log"
            launch_live_stack.return_value = {
                "command": ["launch"],
                "returnCode": 0,
                "stdout": "{}",
                "stderr": "",
                "state": {
                    "ClientPid": 200,
                    "ForceLobbyTlsMitm": True,
                    "UseContentTlsRoute": True,
                    "ContentRouteMode": "content-only-local-mitm",
                    "ClientArgs": [
                        "http://lobby45a.runescape.com:8081/jav_config.ws?binaryType=6&hostRewrite=1&lobbyHostRewrite=1&contentRouteRewrite=1&gameHostOverride=lobby45a.runescape.com"
                    ],
                },
            }
            start_runtime_trace.return_value = (SimpleNamespace(pid=300), ["trace"], root / "trace.jsonl")
            collect_client_network_snapshot.return_value = {
                "localMitm443ConnectionCount": 0,
                "directExternal443ConnectionCount": 0,
            }
            summarize_recent_content_sessions.return_value = {
                "freshSessionCount": 0,
                "freshTlsSessionCount": 0,
                "localMsRequestsObserved": False,
                "latestSessionLog": "",
                "sessions": [],
            }
            run_downstream_tools.return_value = {
                "sceneDeliveryCommand": ["scene"],
                "toolDoctorCommand": ["doctor"],
                "sceneDeliveryArtifact": {"status": "partial", "summary": {"overlapConfidence": "missing"}, "verdict": {}},
                "toolDoctorArtifact": {"status": "ok"},
            }

            artifact = build_capture_artifact(
                SimpleNamespace(
                    capture_seconds=1,
                    runtime_trace_seconds=1,
                    js5_idle_timeout_seconds=1,
                    reset_cache=False,
                    client_variant="patched",
                    world_log=root / "world.log",
                    js5_session_dir=root / "js5",
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["summary"]["statusReason"], "non-canonical-host-rewrite")
        self.assertEqual(artifact["summary"]["hostRewrite"], "1")

    @patch("run_946_black_screen_capture.required_paths", return_value={"ok": Path(__file__)})
    @patch("run_946_black_screen_capture.run_downstream_tools")
    @patch("run_946_black_screen_capture.latest_path")
    @patch("run_946_black_screen_capture.select_new_world_window", return_value="11:20")
    @patch("run_946_black_screen_capture.finalize_process", return_value={"returnCode": 0, "stdout": "", "stderr": ""})
    @patch("run_946_black_screen_capture.kill_pid")
    @patch("run_946_black_screen_capture.summarize_recent_content_sessions")
    @patch("run_946_black_screen_capture.collect_client_network_snapshot")
    @patch("run_946_black_screen_capture.time.sleep")
    @patch("run_946_black_screen_capture.start_runtime_trace")
    @patch("run_946_black_screen_capture.launch_live_stack")
    @patch("run_946_black_screen_capture.list_world_windows", return_value=["1:10"])
    def test_direct_external_443_without_local_ms_is_flagged_as_content_route_bypass(
        self,
        _before_windows: patch,
        launch_live_stack: patch,
        start_runtime_trace: patch,
        _sleep: patch,
        collect_client_network_snapshot: patch,
        summarize_recent_content_sessions: patch,
        _kill_pid: patch,
        _finalize: patch,
        _select_window: patch,
        latest_path: patch,
        run_downstream_tools: patch,
        _required_paths: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            latest_path.return_value = None
            launch_live_stack.return_value = {
                "command": ["launch"],
                "returnCode": 0,
                "stdout": "{}",
                "stderr": "",
                "state": {
                    "ClientPid": 200,
                    "ForceLobbyTlsMitm": True,
                    "UseContentTlsRoute": True,
                    "ContentRouteMode": "content-only-local-mitm",
                    "ClientArgs": [
                        "http://lobby45a.runescape.com:8081/jav_config.ws?binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1&gameHostOverride=lobby45a.runescape.com"
                    ],
                },
            }
            start_runtime_trace.return_value = (SimpleNamespace(pid=300), ["trace"], root / "trace.jsonl")
            collect_client_network_snapshot.return_value = {
                "localMitm443ConnectionCount": 0,
                "directExternal443ConnectionCount": 2,
            }
            summarize_recent_content_sessions.return_value = {
                "freshSessionCount": 1,
                "freshTlsSessionCount": 0,
                "localMsRequestsObserved": False,
                "latestSessionLog": str(root / "session-01.log"),
                "sessions": [],
            }
            run_downstream_tools.return_value = {
                "sceneDeliveryCommand": ["scene"],
                "toolDoctorCommand": ["doctor"],
                "sceneDeliveryArtifact": {
                    "status": "partial",
                    "summary": {"overlapConfidence": "missing"},
                    "verdict": {"likelyBlocker": "capture-missing"},
                },
                "toolDoctorArtifact": {"status": "ok"},
            }

            artifact = build_capture_artifact(
                SimpleNamespace(
                    capture_seconds=1,
                    runtime_trace_seconds=1,
                    js5_idle_timeout_seconds=1,
                    reset_cache=False,
                    client_variant="patched",
                    world_log=root / "world.log",
                    js5_session_dir=root / "js5",
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["summary"]["statusReason"], "content-route-bypassed-local-mitm")
        self.assertEqual(artifact["summary"]["directExternal443ConnectionCount"], 2)
        self.assertFalse(artifact["summary"]["localMsRequestsObserved"])


if __name__ == "__main__":
    unittest.main()
