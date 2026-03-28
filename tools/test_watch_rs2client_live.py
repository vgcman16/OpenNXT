from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from watch_rs2client_live import (
    build_summary_artifact,
    content_session_overlaps_watch,
    derive_terminal_state,
    discover_process_family,
    infer_build_from_client_path,
    is_compile_shader_cmdline,
    is_nonfatal_graphics_exception,
    launch_state_matches_client,
    latest_rs2client_pid,
    normalize_content_line,
    normalize_js5_live_line,
    normalize_world_line,
    parse_http_payload,
    prepare_world_window_baseline,
    recent_directory_paths,
    resolve_watch_target,
    resolve_runtime_build,
    should_retry_hook_target,
    update_summary,
)


class WatchRs2ClientLiveTest(unittest.TestCase):
    def test_is_compile_shader_cmdline_detects_shader_worker(self) -> None:
        self.assertTrue(is_compile_shader_cmdline([r"C:\game\rs2client.exe", "--compileshader", "1"]))
        self.assertFalse(is_compile_shader_cmdline([r"C:\game\rs2client.exe", "http://localhost:8080/jav_config.ws"]))

    def test_infer_build_from_client_path_reads_open_nxt_client_directory(self) -> None:
        self.assertEqual(
            infer_build_from_client_path(r"C:\Users\Demon\Documents\New project\OpenNXT\data\clients\947\win64c\original\rs2client.exe"),
            947,
        )

    def test_resolve_runtime_build_prefers_launch_state(self) -> None:
        self.assertEqual(resolve_runtime_build(client_pid=None, launch_state={"ClientBuild": 947}), 947)

    def test_launch_state_matches_client_requires_matching_runtime_pid(self) -> None:
        self.assertTrue(launch_state_matches_client({"ClientPid": 123, "WrapperPid": 456}, 123))
        self.assertFalse(launch_state_matches_client({"ClientPid": 999, "WrapperPid": 456}, 123))

    def test_resolve_runtime_build_ignores_stale_launch_state_for_attach(self) -> None:
        with (
            patch("watch_rs2client_live.psutil.pid_exists", return_value=True),
            patch("watch_rs2client_live.psutil.Process") as process_ctor,
            patch("watch_rs2client_live.read_configured_build", return_value=947),
        ):
            process_ctor.return_value.exe.return_value = r"C:\ProgramData\Jagex\launcher\rs2client.exe"
            self.assertEqual(resolve_runtime_build(client_pid=123, launch_state={"ClientBuild": 946, "ClientPid": 999}), 947)

    def test_latest_rs2client_pid_prefers_main_process_over_compile_shader_child(self) -> None:
        main = Mock()
        main.info = {
            "pid": 100,
            "name": "rs2client.exe",
            "create_time": 10.0,
            "cmdline": [r"C:\game\rs2client.exe", "http://localhost:8080/jav_config.ws"],
        }
        shader = Mock()
        shader.info = {
            "pid": 200,
            "name": "rs2client.exe",
            "create_time": 20.0,
            "cmdline": [r"C:\game\rs2client.exe", "--compileshader", "100", "0", "1", "2", "3"],
        }
        with patch("watch_rs2client_live.psutil.process_iter", return_value=[main, shader]):
            self.assertEqual(latest_rs2client_pid(), 100)

    def test_discover_process_family_excludes_same_name_peer_started_nearby(self) -> None:
        root = Mock()
        root.pid = 100
        root.children.return_value = []
        with (
            patch("watch_rs2client_live.psutil.Process", return_value=root),
            patch("watch_rs2client_live.safe_process_name", side_effect=lambda proc: "rs2client.exe"),
            patch("watch_rs2client_live.safe_process_exe", side_effect=lambda proc: r"C:\game\rs2client.exe"),
            patch(
                "watch_rs2client_live.psutil.process_iter",
                return_value=[
                    SimpleNamespace(
                        info={
                            "pid": 100,
                            "name": "rs2client.exe",
                            "exe": r"C:\game\rs2client.exe",
                            "create_time": 10.0,
                            "ppid": 0,
                            "cmdline": [r"C:\game\rs2client.exe"],
                        }
                    ),
                    SimpleNamespace(
                        info={
                            "pid": 200,
                            "name": "rs2client.exe",
                            "exe": r"C:\game\rs2client.exe",
                            "create_time": 20.0,
                            "ppid": 999,
                            "cmdline": [r"C:\game\rs2client.exe"],
                        }
                    ),
                ],
            ),
        ):
            family = discover_process_family(100)
        self.assertEqual(sorted(family), [100])

    def test_resolve_watch_target_auto_attaches_existing_main_client(self) -> None:
        args = SimpleNamespace(pid=None, force_launch=False)
        with patch("watch_rs2client_live.latest_rs2client_pid", return_value=4321):
            self.assertEqual(resolve_watch_target(args), ("attach", 4321, True))

    def test_resolve_watch_target_force_launch_skips_existing_client(self) -> None:
        args = SimpleNamespace(pid=None, force_launch=True)
        with patch("watch_rs2client_live.latest_rs2client_pid", return_value=4321):
            self.assertEqual(resolve_watch_target(args), ("launch", None, False))

    def test_parse_http_payload_decodes_archive_request(self) -> None:
        payload = b"GET /ms?m=0&a=40&k=946 HTTP/1.1\r\nHost: localhost\r\n\r\n"
        parsed = parse_http_payload(payload)
        self.assertEqual(parsed["kind"], "request")
        self.assertEqual(parsed["index"], 0)
        self.assertEqual(parsed["archive"], 40)

    def test_normalize_content_line_decodes_first_chunk_http_request(self) -> None:
        line = (
            "tls-client->remote first-chunk-1 bytes=50 hex="
            "47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 34 30 20 48 54 54 50 2f 31 2e 31 0d 0a 0d 0a"
        )
        category, action, details = normalize_content_line(line)
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "request")
        self.assertEqual(details["archive"], 40)

    def test_normalize_content_line_decodes_session_route(self) -> None:
        category, action, details = normalize_content_line("session#1 session-route=tls-secure-game")
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "route")
        self.assertEqual(details["sessionRoute"], "tls-secure-game")

    def test_normalize_content_line_decodes_route_source(self) -> None:
        category, action, details = normalize_content_line("session#1 tls-first-appdata-source=backend")
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "route-source")
        self.assertEqual(details["routeSource"], "backend")

    def test_normalize_content_line_decodes_route_mode(self) -> None:
        category, action, details = normalize_content_line("session#1 tls-route-mode=passthrough")
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "route-mode")
        self.assertEqual(details["routeMode"], "passthrough")

    def test_normalize_content_line_decodes_clienthello_sni(self) -> None:
        category, action, details = normalize_content_line("session#1 tls-clienthello-sni=localhost")
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "clienthello-sni")
        self.assertEqual(details["tlsClienthelloSni"], "localhost")

    def test_normalize_content_line_decodes_wrap_status(self) -> None:
        category, action, details = normalize_content_line("session#1 tls-server-wrap=eof")
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "wrap-status")
        self.assertEqual(details["tlsServerWrapStatus"], "eof")

    def test_normalize_content_line_decodes_cert_subject(self) -> None:
        category, action, details = normalize_content_line("session#1 tls-cert-subject=CN=lobby45a.runescape.com")
        self.assertEqual(category, "proxy.content")
        self.assertEqual(action, "cert-subject")
        self.assertEqual(details["tlsCertSubject"], "CN=lobby45a.runescape.com")

    def test_normalize_world_line_maps_stage(self) -> None:
        category, action, details = normalize_world_line(
            "2026-03-16T18:00:00.000000Z world-stage stage=interfaces name=demon"
        )
        self.assertEqual(category, "world.stage")
        self.assertEqual(action, "stage")
        self.assertEqual(details["stage"], "interfaces")

    def test_normalize_js5_live_line_decodes_reference_table_request(self) -> None:
        category, action, details = normalize_js5_live_line(
            "[nioEventLoopGroup-3-6] INFO com.opennxt.net.js5.Js5Session - "
            "Queued js5 request #7104 from /127.0.0.1:65351: opcode=1, priority=true, nxt=false, "
            "build=947, occurrence=337, reference-table(index=255, archive=2), available=true"
        )
        self.assertEqual(category, "proxy.js5")
        self.assertEqual(action, "request")
        self.assertEqual(details["build"], 947)
        self.assertEqual(details["index"], 255)
        self.assertEqual(details["archive"], 2)

    def test_terminal_state_prefers_black_screen_plateau_after_interfaces(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": ["appearance", "interfaces"],
            "localContentMitmObserved": True,
            "archiveRequestCount": 1,
            "responseHeaderCount": 1,
            "worldBootstrapObserved": True,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": False,
            "proxySecureGameTlsObserved": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "black-screen-plateau")

    def test_terminal_state_distinguishes_loading_application_resources_loop(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "worldBootstrapObserved": False,
            "js5ReferenceTable255RequestCount": 10,
            "archiveRequestCount": 0,
            "proxyMitmHandshakeFailedObserved": False,
            "proxyMitmHandshakeOkObserved": False,
            "proxyHttpContentTlsObserved": False,
            "proxySecureGamePassthroughObserved": False,
            "proxySecureGameTlsObserved": False,
            "contentErrors": [],
            "tlsContextEstablished": False,
            "tlsAppDataObserved": False,
            "proxyRawGameObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "loading-application-resources-loop")

    def test_terminal_state_distinguishes_prelogin_secure_game(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "localContentMitmObserved": False,
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "worldBootstrapObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": False,
            "proxySecureGameTlsObserved": True,
            "proxySecureGamePassthroughObserved": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "prelogin-secure-game")

    def test_terminal_state_distinguishes_prelogin_secure_game_passthrough(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "localContentMitmObserved": False,
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "worldBootstrapObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": False,
            "proxySecureGameTlsObserved": True,
            "proxySecureGamePassthroughObserved": True,
        }
        self.assertEqual(derive_terminal_state(summary, True), "prelogin-secure-game-passthrough")

    def test_terminal_state_distinguishes_prelogin_http_content(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "localContentMitmObserved": True,
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "worldBootstrapObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": True,
            "proxyMitmHandshakeOkObserved": True,
            "proxyMitmHandshakeFailedObserved": False,
            "proxySecureGameTlsObserved": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "prelogin-http-content")

    def test_terminal_state_distinguishes_mitm_handshake_failure(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "localContentMitmObserved": False,
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "worldBootstrapObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": True,
            "proxyMitmHandshakeOkObserved": False,
            "proxyMitmHandshakeFailedObserved": True,
            "proxySecureGameTlsObserved": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "prelogin-mitm-handshake-failed")

    def test_terminal_state_does_not_treat_raw_game_only_as_login_screen(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "localContentMitmObserved": False,
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "worldBootstrapObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": False,
            "proxySecureGameTlsObserved": False,
            "proxyRawGameObserved": True,
            "contentErrors": [],
            "tlsContextEstablished": False,
            "tlsAppDataObserved": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "prelogin-raw-game-only")

    def test_terminal_state_marks_tls_failure_before_app_data(self) -> None:
        summary = {
            "crashDetected": False,
            "worldStages": [],
            "localContentMitmObserved": False,
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "worldBootstrapObserved": False,
            "windowObserved": True,
            "localMitm443Seen": True,
            "directExternal443Seen": False,
            "proxyHttpContentTlsObserved": False,
            "proxySecureGameTlsObserved": False,
            "proxyRawGameObserved": False,
            "contentErrors": ["SSLZeroReturnError"],
            "tlsContextEstablished": True,
            "tlsAppDataObserved": False,
        }
        self.assertEqual(derive_terminal_state(summary, True), "prelogin-tls-failed")

    def test_nonfatal_graphics_exception_is_not_treated_as_crash_signal(self) -> None:
        details = {
            "backtrace": [
                {"symbol": "0x1 rs2client.exe!OpenAdapter10_2"},
                {"symbol": "0x2 rs2client.exe!OpenAdapter_D3D11On12"},
            ],
            "context": {"rdi": "0xe06d7363"},
        }
        self.assertTrue(is_nonfatal_graphics_exception(details))

    def test_old_content_session_is_ignored_for_new_watch(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session-01.log"
            path.write_text(
                "\n".join(
                    [
                        "session#1 start=2026-03-17T02:27:17.000000+00:00",
                        "session#1 mode=tls initial-peek=16 03 03 00 a9",
                        "session#1 end=2026-03-17T02:27:17.500000+00:00",
                    ]
                ),
                encoding="utf-8",
            )
            session_started_at = datetime(2026, 3, 17, 2, 31, 31, tzinfo=timezone.utc)
            self.assertFalse(content_session_overlaps_watch(path, session_started_at=session_started_at))

    def test_recent_directory_paths_limits_to_recent_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            old_path = root / "session-old.log"
            new_a = root / "session-a.log"
            new_b = root / "session-b.log"
            old_path.write_text("old", encoding="utf-8")
            new_a.write_text("a", encoding="utf-8")
            new_b.write_text("b", encoding="utf-8")
            old_mtime = datetime(2026, 3, 17, 2, 0, tzinfo=timezone.utc).timestamp()
            new_a_mtime = datetime(2026, 3, 17, 3, 0, tzinfo=timezone.utc).timestamp()
            new_b_mtime = datetime(2026, 3, 17, 4, 0, tzinfo=timezone.utc).timestamp()
            old_path.touch()
            new_a.touch()
            new_b.touch()
            import os

            os.utime(old_path, (old_mtime, old_mtime))
            os.utime(new_a, (new_a_mtime, new_a_mtime))
            os.utime(new_b, (new_b_mtime, new_b_mtime))

            paths = recent_directory_paths(
                root,
                "session-*.log",
                since_epoch=datetime(2026, 3, 17, 2, 30, tzinfo=timezone.utc).timestamp(),
                max_files=1,
            )
            self.assertEqual(paths, [new_b])

    def test_build_summary_artifact_includes_latest_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            args = SimpleNamespace(
                client_variant="patched",
                pid=0,
                duration_seconds=30,
                verbose=False,
                no_frida=False,
                world_log=root / "world.log",
                content_capture_dir=root / "content",
                js5_session_dir=root / "js5",
                clienterror_dir=root / "clienterror",
                output_dir=root,
            )
            paths = {
                "sessionJsonl": root / "session.jsonl",
                "summaryJson": root / "summary.json",
                "summaryMarkdown": root / "summary.md",
                "hooksJsonl": root / "hooks.jsonl",
            }
            summary = {
                "sessionStartedAt": None,
                "sessionEndedAt": None,
                "worldBootstrapObserved": True,
                "localContentMitmObserved": True,
                "localMsRequestsObserved": True,
                "proxyRawGameObserved": False,
                "proxySecureGameTlsObserved": False,
                "proxySecureGamePassthroughObserved": False,
                "proxyHttpContentTlsObserved": True,
                "proxyMitmHandshakeOkObserved": True,
                "proxyMitmHandshakeFailedObserved": False,
                "contentSessionRoutes": Counter({"tls-http-content": 1}),
                "proxyMitmWrapStatuses": Counter({"ok": 1}),
                "proxyRouteModes": Counter({"mitm": 1}),
                "contentRouteSources": Counter({"client-http": 1}),
                "proxySecureGameBackendFirstObserved": False,
                "tlsClienthelloSnis": Counter({"localhost": 1}),
                "tlsCertSubjects": Counter({"CN=lobby45a.runescape.com": 1}),
                "tlsCertIssuers": Counter({"CN=lobby45a.runescape.com": 1}),
                "tlsCertThumbprints": Counter({"ABC": 1}),
                "firstJs5RequestTimestamp": None,
                "firstArchiveRequestTimestamp": None,
                "firstJs5ResponseTimestamp": None,
                "firstArchiveResponseTimestamp": None,
                "proxyArchiveRequestBySource": defaultdict(bool),
                "responseHeaderCount": 1,
                "responseBytes": 10,
                "archiveRequestCount": 1,
                "crashDetected": False,
                "exceptionCount": 0,
                "fatalExceptionCount": 0,
                "nonFatalGraphicsExceptionCount": 0,
                "tlsAnomalies": [],
                "tlsContextEstablished": True,
                "tlsAppDataObserved": True,
                "tlsEncryptCount": 1,
                "tlsDecryptCount": 1,
                "firstTlsEncryptTimestamp": None,
                "firstTlsDecryptTimestamp": None,
                "tlsRemoteCertObserved": True,
                "tlsConnectionInfoObserved": True,
                "tlsAttributeCounts": Counter({"SECPKG_ATTR_REMOTE_CERT_CONTEXT": 1}),
                "fileOpenCounts": Counter(),
                "fileBytesRead": Counter(),
                "worldStages": ["appearance"],
                "directExternal443Targets": set(),
                "resolvedHosts": set(),
                "loadedModuleNames": {"libcef.dll"},
                "cefObserved": True,
                "cryptoModuleObserved": True,
                "eventCount": 1,
                "categoryCounts": Counter(),
                "contentErrors": [],
                "lastProcessSample": {},
                "latestWindowTitle": "",
                "localMitm443Seen": False,
                "directExternal443Seen": False,
                "worldWindowSelectionSkipped": False,
                "worldWindowSelectionSkipReason": "",
            }
            artifact = build_summary_artifact(
                args,
                status="ok",
                paths=paths,
                runtime_build=947,
                launch_mode="launch",
                client_pid=123,
                launch={},
                launch_evaluation={"canonicalMitmLaunch": True},
                summary=summary,
                world_window="1:10",
            )
        self.assertEqual(artifact["build"], 947)
        self.assertEqual(artifact["summary"]["canonicalRouteStatus"], "canonical")
        self.assertIn("latestSummaryJson", artifact["artifacts"])
        self.assertTrue(artifact["summary"]["cefObserved"])
        self.assertIn("libcef.dll", artifact["summary"]["loadedModuleNames"])
        self.assertEqual(artifact["summary"]["contentRouteSources"], {"client-http": 1})
        self.assertEqual(artifact["summary"]["proxyRouteModes"], {"mitm": 1})
        self.assertEqual(artifact["summary"]["proxyMitmWrapStatuses"], {"ok": 1})

    def test_update_summary_records_module_and_resolution_observations(self) -> None:
        summary = {
            "eventCount": 0,
            "categoryCounts": Counter(),
            "worldStages": [],
            "worldBootstrapObserved": False,
            "rebuildTailTimestamp": None,
            "awaitingReadySignalCount": 0,
            "localContentMitmObserved": False,
            "localMsRequestsObserved": False,
            "proxyRawGameObserved": False,
            "proxySecureGameTlsObserved": False,
            "proxySecureGamePassthroughObserved": False,
            "proxyHttpContentTlsObserved": False,
            "proxyMitmHandshakeOkObserved": False,
            "proxyMitmHandshakeFailedObserved": False,
            "contentSessionRoutes": Counter(),
            "proxyMitmWrapStatuses": Counter(),
            "proxyRouteModes": Counter(),
            "contentRouteSources": Counter(),
            "proxySecureGameBackendFirstObserved": False,
            "tlsClienthelloSnis": Counter(),
            "tlsCertSubjects": Counter(),
            "tlsCertIssuers": Counter(),
            "tlsCertThumbprints": Counter(),
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "responseBytes": 0,
            "firstJs5RequestTimestamp": None,
            "firstArchiveRequestTimestamp": None,
            "firstJs5ResponseTimestamp": None,
            "firstArchiveResponseTimestamp": None,
            "proxyArchiveRequestBySource": defaultdict(bool),
            "fileOpenCounts": Counter(),
            "fileBytesRead": Counter(),
            "tlsAnomalies": [],
            "tlsContextEstablished": False,
            "tlsAppDataObserved": False,
            "tlsEncryptCount": 0,
            "tlsDecryptCount": 0,
            "firstTlsEncryptTimestamp": None,
            "firstTlsDecryptTimestamp": None,
            "tlsRemoteCertObserved": False,
            "tlsConnectionInfoObserved": False,
            "tlsAttributeCounts": Counter(),
            "contentErrors": [],
            "crashDetected": False,
            "exceptionCount": 0,
            "fatalExceptionCount": 0,
            "nonFatalGraphicsExceptionCount": 0,
            "js5SummaryCount": 0,
            "js5LiveRequestCount": 0,
            "js5LiveResponseCount": 0,
            "js5ReferenceTable255RequestCount": 0,
            "js5ReferenceTable255ResponseCount": 0,
            "js5ReferenceTable255ArchiveCounts": Counter(),
            "lastProcessSample": {},
            "windowObserved": False,
            "latestWindowTitle": "",
            "localMitm443Seen": False,
            "directExternal443Seen": False,
            "directExternal443Targets": set(),
            "resolvedHosts": set(),
            "loadedModuleNames": set(),
            "loadedModulePaths": set(),
            "cefObserved": False,
            "cryptoModuleObserved": False,
        }
        update_summary(
            summary,
            {
                "category": "client.module",
                "action": "snapshot",
                "details": {"moduleName": "libcef.dll", "path": "C:\\client\\libcef.dll"},
                "timestamp": "2026-03-17T03:00:00+00:00",
                "source": "hooks",
            },
        )
        update_summary(
            summary,
            {
                "category": "proxy.content",
                "action": "route-source",
                "details": {"routeSource": "backend"},
                "timestamp": "2026-03-17T03:00:01+00:00",
                "source": "content-log",
            },
        )
        update_summary(
            summary,
            {
                "category": "client.net",
                "action": "resolve",
                "details": {"host": "127.0.0.1", "service": "443"},
                "timestamp": "2026-03-17T03:00:01+00:00",
                "source": "hooks",
            },
        )
        self.assertTrue(summary["cefObserved"])
        self.assertIn("libcef.dll", summary["loadedModuleNames"])
        self.assertIn("127.0.0.1", summary["resolvedHosts"])
        self.assertEqual(summary["contentRouteSources"]["backend"], 1)
        self.assertTrue(summary["proxySecureGameBackendFirstObserved"])

    def test_update_summary_records_live_js5_reference_loop(self) -> None:
        summary = {
            "eventCount": 0,
            "categoryCounts": Counter(),
            "worldStages": [],
            "worldBootstrapObserved": False,
            "rebuildTailTimestamp": None,
            "awaitingReadySignalCount": 0,
            "localContentMitmObserved": False,
            "localMsRequestsObserved": False,
            "proxyRawGameObserved": False,
            "proxySecureGameTlsObserved": False,
            "proxySecureGamePassthroughObserved": False,
            "proxyHttpContentTlsObserved": False,
            "proxyMitmHandshakeOkObserved": False,
            "proxyMitmHandshakeFailedObserved": False,
            "contentSessionRoutes": Counter(),
            "proxyMitmWrapStatuses": Counter(),
            "proxyRouteModes": Counter(),
            "contentRouteSources": Counter(),
            "proxySecureGameBackendFirstObserved": False,
            "tlsClienthelloSnis": Counter(),
            "tlsCertSubjects": Counter(),
            "tlsCertIssuers": Counter(),
            "tlsCertThumbprints": Counter(),
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "responseBytes": 0,
            "firstJs5RequestTimestamp": None,
            "firstArchiveRequestTimestamp": None,
            "firstJs5ResponseTimestamp": None,
            "firstArchiveResponseTimestamp": None,
            "proxyArchiveRequestBySource": defaultdict(bool),
            "fileOpenCounts": Counter(),
            "fileBytesRead": Counter(),
            "tlsAnomalies": [],
            "tlsContextEstablished": False,
            "tlsAppDataObserved": False,
            "tlsEncryptCount": 0,
            "tlsDecryptCount": 0,
            "firstTlsEncryptTimestamp": None,
            "firstTlsDecryptTimestamp": None,
            "tlsRemoteCertObserved": False,
            "tlsConnectionInfoObserved": False,
            "tlsAttributeCounts": Counter(),
            "contentErrors": [],
            "crashDetected": False,
            "exceptionCount": 0,
            "fatalExceptionCount": 0,
            "nonFatalGraphicsExceptionCount": 0,
            "js5SummaryCount": 0,
            "js5LiveRequestCount": 0,
            "js5LiveResponseCount": 0,
            "js5ReferenceTable255RequestCount": 0,
            "js5ReferenceTable255ResponseCount": 0,
            "js5ReferenceTable255ArchiveCounts": Counter(),
            "lastProcessSample": {},
            "windowObserved": False,
            "latestWindowTitle": "",
            "localMitm443Seen": False,
            "directExternal443Seen": False,
            "directExternal443Targets": set(),
            "resolvedHosts": set(),
            "loadedModuleNames": set(),
            "loadedModulePaths": set(),
            "cefObserved": False,
            "cryptoModuleObserved": False,
        }
        update_summary(
            summary,
            {
                "category": "proxy.js5",
                "action": "request",
                "details": {"requestKind": "reference-table", "index": 255, "archive": 12},
                "timestamp": "2026-03-25T02:00:00+00:00",
                "source": "server-log",
            },
        )
        self.assertEqual(summary["js5LiveRequestCount"], 1)
        self.assertEqual(summary["js5ReferenceTable255RequestCount"], 1)
        self.assertEqual(summary["js5ReferenceTable255ArchiveCounts"][12], 1)

    def test_update_summary_records_route_mode_and_clienthello_sni(self) -> None:
        summary = {
            "eventCount": 0,
            "categoryCounts": Counter(),
            "worldStages": [],
            "worldBootstrapObserved": False,
            "rebuildTailTimestamp": None,
            "awaitingReadySignalCount": 0,
            "localContentMitmObserved": False,
            "localMsRequestsObserved": False,
            "proxyRawGameObserved": False,
            "proxySecureGameTlsObserved": True,
            "proxySecureGamePassthroughObserved": False,
            "proxyHttpContentTlsObserved": False,
            "proxyMitmHandshakeOkObserved": False,
            "proxyMitmHandshakeFailedObserved": False,
            "contentSessionRoutes": Counter({"tls-secure-game": 1}),
            "proxyMitmWrapStatuses": Counter(),
            "proxyRouteModes": Counter(),
            "contentRouteSources": Counter(),
            "proxySecureGameBackendFirstObserved": False,
            "tlsClienthelloSnis": Counter(),
            "tlsCertSubjects": Counter(),
            "tlsCertIssuers": Counter(),
            "tlsCertThumbprints": Counter(),
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "responseBytes": 0,
            "firstJs5RequestTimestamp": None,
            "firstArchiveRequestTimestamp": None,
            "firstJs5ResponseTimestamp": None,
            "firstArchiveResponseTimestamp": None,
            "proxyArchiveRequestBySource": defaultdict(bool),
            "fileOpenCounts": Counter(),
            "fileBytesRead": Counter(),
            "tlsAnomalies": [],
            "tlsContextEstablished": False,
            "tlsAppDataObserved": False,
            "tlsEncryptCount": 0,
            "tlsDecryptCount": 0,
            "firstTlsEncryptTimestamp": None,
            "firstTlsDecryptTimestamp": None,
            "tlsRemoteCertObserved": False,
            "tlsConnectionInfoObserved": False,
            "tlsAttributeCounts": Counter(),
            "contentErrors": [],
            "crashDetected": False,
            "exceptionCount": 0,
            "fatalExceptionCount": 0,
            "nonFatalGraphicsExceptionCount": 0,
            "js5SummaryCount": 0,
            "lastProcessSample": {},
            "windowObserved": False,
            "latestWindowTitle": "",
            "localMitm443Seen": False,
            "directExternal443Seen": False,
            "directExternal443Targets": set(),
            "resolvedHosts": set(),
            "loadedModuleNames": set(),
            "loadedModulePaths": set(),
            "cefObserved": False,
            "cryptoModuleObserved": False,
        }
        update_summary(
            summary,
            {
                "category": "proxy.content",
                "action": "route-mode",
                "details": {"routeMode": "passthrough"},
                "timestamp": "2026-03-17T03:00:01+00:00",
                "source": "content-log",
            },
        )
        update_summary(
            summary,
            {
                "category": "proxy.content",
                "action": "clienthello-sni",
                "details": {"tlsClienthelloSni": "localhost"},
                "timestamp": "2026-03-17T03:00:02+00:00",
                "source": "content-log",
            },
        )
        update_summary(
            summary,
            {
                "category": "proxy.content",
                "action": "wrap-status",
                "details": {"tlsServerWrapStatus": "eof"},
                "timestamp": "2026-03-17T03:00:03+00:00",
                "source": "content-log",
            },
        )
        update_summary(
            summary,
            {
                "category": "proxy.content",
                "action": "cert-subject",
                "details": {"tlsCertSubject": "CN=lobby45a.runescape.com"},
                "timestamp": "2026-03-17T03:00:04+00:00",
                "source": "content-log",
            },
        )
        self.assertTrue(summary["proxySecureGamePassthroughObserved"])
        self.assertEqual(summary["proxyRouteModes"]["passthrough"], 1)
        self.assertEqual(summary["tlsClienthelloSnis"]["localhost"], 1)
        self.assertEqual(summary["proxyMitmWrapStatuses"]["eof"], 1)
        self.assertTrue(summary["proxyMitmHandshakeFailedObserved"])
        self.assertEqual(summary["tlsCertSubjects"]["CN=lobby45a.runescape.com"], 1)

    def test_update_summary_records_tls_context_and_app_data(self) -> None:
        summary = {
            "eventCount": 0,
            "categoryCounts": Counter(),
            "worldStages": [],
            "worldBootstrapObserved": False,
            "rebuildTailTimestamp": None,
            "awaitingReadySignalCount": 0,
            "localContentMitmObserved": False,
            "localMsRequestsObserved": False,
            "proxyRawGameObserved": False,
            "proxySecureGameTlsObserved": False,
            "proxySecureGamePassthroughObserved": False,
            "proxyHttpContentTlsObserved": False,
            "proxyMitmHandshakeOkObserved": False,
            "proxyMitmHandshakeFailedObserved": False,
            "contentSessionRoutes": Counter(),
            "proxyMitmWrapStatuses": Counter(),
            "proxyRouteModes": Counter(),
            "contentRouteSources": Counter(),
            "proxySecureGameBackendFirstObserved": False,
            "tlsClienthelloSnis": Counter(),
            "tlsCertSubjects": Counter(),
            "tlsCertIssuers": Counter(),
            "tlsCertThumbprints": Counter(),
            "archiveRequestCount": 0,
            "responseHeaderCount": 0,
            "responseBytes": 0,
            "firstJs5RequestTimestamp": None,
            "firstArchiveRequestTimestamp": None,
            "firstJs5ResponseTimestamp": None,
            "firstArchiveResponseTimestamp": None,
            "proxyArchiveRequestBySource": defaultdict(bool),
            "fileOpenCounts": Counter(),
            "fileBytesRead": Counter(),
            "tlsAnomalies": [],
            "tlsContextEstablished": False,
            "tlsAppDataObserved": False,
            "tlsEncryptCount": 0,
            "tlsDecryptCount": 0,
            "firstTlsEncryptTimestamp": None,
            "firstTlsDecryptTimestamp": None,
            "tlsRemoteCertObserved": False,
            "tlsConnectionInfoObserved": False,
            "tlsAttributeCounts": Counter(),
            "contentErrors": [],
            "crashDetected": False,
            "exceptionCount": 0,
            "fatalExceptionCount": 0,
            "nonFatalGraphicsExceptionCount": 0,
            "js5SummaryCount": 0,
            "lastProcessSample": {},
            "windowObserved": False,
            "latestWindowTitle": "",
            "localMitm443Seen": False,
            "directExternal443Seen": False,
            "directExternal443Targets": set(),
            "resolvedHosts": set(),
            "loadedModuleNames": set(),
            "loadedModulePaths": set(),
            "cefObserved": False,
            "cryptoModuleObserved": False,
        }
        update_summary(
            summary,
            {
                "category": "client.tls",
                "action": "initialize-security-context",
                "details": {"status": 0, "api": "InitializeSecurityContextA"},
                "timestamp": "2026-03-17T03:00:00+00:00",
                "source": "hooks",
            },
        )
        update_summary(
            summary,
            {
                "category": "client.tls",
                "action": "query-context-attributes",
                "details": {
                    "status": 0,
                    "attributeName": "SECPKG_ATTR_REMOTE_CERT_CONTEXT",
                    "api": "QueryContextAttributesA",
                },
                "timestamp": "2026-03-17T03:00:01+00:00",
                "source": "hooks",
            },
        )
        update_summary(
            summary,
            {
                "category": "client.tls",
                "action": "encrypt-message",
                "details": {
                    "status": 0,
                    "bufferSummary": {"totalBytes": 181},
                    "api": "EncryptMessage",
                },
                "timestamp": "2026-03-17T03:00:02+00:00",
                "source": "hooks",
            },
        )
        self.assertTrue(summary["tlsContextEstablished"])
        self.assertTrue(summary["tlsRemoteCertObserved"])
        self.assertTrue(summary["tlsAppDataObserved"])
        self.assertEqual(summary["tlsEncryptCount"], 1)
        self.assertEqual(summary["tlsAttributeCounts"]["SECPKG_ATTR_REMOTE_CERT_CONTEXT"], 1)

    def test_prepare_world_window_baseline_skips_large_logs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            world_log = Path(tmpdir) / "world.log"
            world_log.write_bytes(b"x" * 16)
            baseline, skipped, reason = prepare_world_window_baseline(world_log, max_prescan_bytes=8)
        self.assertEqual(baseline, [])
        self.assertTrue(skipped)
        self.assertIn("world-log-too-large", reason)

    def test_should_retry_hook_target_only_for_empty_failed_attach(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "hook.jsonl"
            output_path.write_text("", encoding="utf-8")
            process = Mock()
            process.poll.return_value = 1
            target = {
                "pid": 123,
                "process": process,
                "output": output_path,
                "attempts": 1,
                "lastStartEpoch": 1.0,
            }
            self.assertTrue(should_retry_hook_target(target, {123}, 3.0))
            output_path.write_text('{"ok":true}\n', encoding="utf-8")
            self.assertFalse(should_retry_hook_target(target, {123}, 3.0))


if __name__ == "__main__":
    unittest.main()
