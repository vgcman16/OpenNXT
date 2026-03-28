from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_946_scene_delivery_aid import build_artifact, parse_content_capture_log, parse_js5_session_log, render_markdown


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2))


class SceneDeliveryAidTest(unittest.TestCase):
    def test_parse_content_capture_log_ignores_tls_secure_game_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session-01.log"
            write_text(
                path,
                "\n".join(
                    [
                        "session#1 start=2026-03-16T18:00:00.000000Z",
                        "session#1 mode=tls initial-peek=16 03 03 00 a9",
                        "session#1 session-route=tls-secure-game",
                        "tls-client->remote first-chunk-1 bytes=7 hex=0f 00 00 01 02 03 04",
                        "session#1 end=2026-03-16T18:00:01.000000Z",
                    ]
                ),
            )

            summary = parse_content_capture_log(path)

        self.assertEqual(summary, {})

    def test_parse_js5_session_log_distinguishes_reference_tables_and_archives(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "session-01.log"
            write_text(
                log_path,
                "\n".join(
                    [
                        "session#1 start=2026-03-16T18:00:00.000000Z",
                        "session#1 request opcode=33 priority=true nxt=true build=946 master-reference-table",
                        "session#1 request opcode=1 priority=true nxt=false build=946 reference-table[18]",
                        "session#1 request opcode=33 priority=true nxt=true build=946 archive[5,1234]",
                        "session#1 response-header index=5 archive=1234 priority=true compression=0 fileSize=20 containerBytes=25 archive[5,1234]",
                        "session#1 end=2026-03-16T18:00:05.000000Z",
                    ]
                ),
            )

            summary = parse_js5_session_log(log_path)

        self.assertEqual(summary["requestCount"], 3)
        self.assertEqual(summary["referenceTableRequests"], 1)
        self.assertEqual(summary["archiveRequests"], 1)
        self.assertEqual(summary["responseHeaderCount"], 1)
        self.assertEqual(summary["sceneDeliveryState"], "archive-delivery-observed")

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    def test_structured_overlapping_capture_beats_legacy_fallback(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            js5_dir = root / "js5"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"
            runtime_dir = root / "runtime"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
                        "2026-03-16T18:00:01.000000Z world-send-rebuild-tail mode=0",
                        "2026-03-16T18:00:03.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_text(
                js5_dir / "session-01.log",
                "\n".join(
                    [
                        "session#1 start=2026-03-16T17:00:00.000000Z",
                        "session#1 request opcode=1 priority=true nxt=false build=946 reference-table[18]",
                        "session#1 end=2026-03-16T17:00:03.000000Z",
                    ]
                ),
            )
            write_json(
                js5_dir / "summary-20260316-180000.json",
                {
                    "tool": "js5-proxy-recorder",
                    "schemaVersion": 1,
                    "status": "ok",
                    "sessions": [
                        {
                            "sessionId": 1,
                            "status": "ok",
                            "startTimestamp": "2026-03-16T18:00:00.500000Z",
                            "endTimestamp": "2026-03-16T18:00:05.000000Z",
                            "requestCount": 3,
                            "masterReferenceRequests": 1,
                            "referenceTableRequests": 1,
                            "archiveRequests": 1,
                            "responseHeaderCount": 1,
                            "responseBytes": 31,
                            "firstRequestAtMillis": 100,
                            "firstArchiveRequestAtMillis": 250,
                            "firstResponseHeaderAtMillis": 400,
                            "firstArchiveResponseAtMillis": 400,
                            "sessionLog": str(js5_dir / "session-structured.log"),
                            "sessionJsonl": str(js5_dir / "session-structured.jsonl"),
                        }
                    ],
                },
            )
            write_text(js5_dir / "session-structured.jsonl", "{}\n")
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"tool": "prefetch-table-compare", "status": "ok", "summary": {"comparisonState": "match"}})

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    world_window=None,
                    js5_session_dir=js5_dir,
                    content_capture_dir=root / "content",
                    runtime_trace_dir=runtime_dir,
                    clienterror_dir=root / "clienterror",
                    checksum_report_json=checksum_json,
                    prefetch_report_json=prefetch_json,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["summary"]["overlapConfidence"], "exact")
        self.assertEqual(artifact["summary"]["sceneDeliveryState"], "archive-delivery-observed")
        self.assertEqual(artifact["js5"]["captureFormat"], "structured")
        self.assertEqual(artifact["correlation"]["firstArchiveResponseSeconds"], 0.9)

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    def test_legacy_overlap_is_fallback_and_reference_tables_only(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            js5_dir = root / "js5"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
                        "2026-03-16T18:00:01.000000Z world-send-rebuild-tail mode=0",
                        "2026-03-16T18:00:03.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_text(
                js5_dir / "session-01.log",
                "\n".join(
                    [
                        "session#1 start=2026-03-16T18:00:00.500000Z",
                        "session#1 request opcode=33 priority=true nxt=true build=946 master-reference-table",
                        "session#1 request opcode=1 priority=true nxt=false build=946 reference-table[18]",
                        "session#1 end=2026-03-16T18:00:04.000000Z",
                    ]
                ),
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"tool": "prefetch-table-compare", "status": "partial", "summary": {"comparisonState": "inconclusive-no-remote-table"}})

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    world_window=None,
                    js5_session_dir=js5_dir,
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    clienterror_dir=root / "clienterror",
                    checksum_report_json=checksum_json,
                    prefetch_report_json=prefetch_json,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["summary"]["overlapConfidence"], "fallback")
        self.assertEqual(artifact["summary"]["sceneDeliveryState"], "reference-tables-only")
        self.assertIn("reference-tables-only", render_markdown(artifact))

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    def test_missing_overlap_reports_capture_gap(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            js5_dir = root / "js5"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
                        "2026-03-16T18:00:03.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_json(
                js5_dir / "summary-20260316-170000.json",
                {
                    "tool": "js5-proxy-recorder",
                    "schemaVersion": 1,
                    "status": "ok",
                    "sessions": [
                        {
                            "sessionId": 1,
                            "status": "ok",
                            "startTimestamp": "2026-03-16T17:00:00.000000Z",
                            "endTimestamp": "2026-03-16T17:00:03.000000Z",
                            "requestCount": 2,
                            "referenceTableRequests": 2,
                            "archiveRequests": 0,
                            "responseHeaderCount": 0,
                            "responseBytes": 5,
                            "sessionLog": str(js5_dir / "session-old.log"),
                            "sessionJsonl": str(js5_dir / "session-old.jsonl"),
                        }
                    ],
                },
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"summary": {}})

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    world_window=None,
                    js5_session_dir=js5_dir,
                    content_capture_dir=root / "content",
                    runtime_trace_dir=root / "runtime",
                    clienterror_dir=root / "clienterror",
                    checksum_report_json=checksum_json,
                    prefetch_report_json=prefetch_json,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["summary"]["overlapConfidence"], "missing")
        self.assertEqual(artifact["summary"]["sceneDeliveryState"], "capture-missing")
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "capture-missing")

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    @patch("run_946_scene_delivery_aid.DEFAULT_BLACK_SCREEN_CAPTURE_JSON")
    def test_capture_bundle_prelogin_regression_is_reported_explicitly(
        self,
        capture_bundle_json: patch,
        _: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"
            capture_json = root / "black-screen-capture.json"

            write_text(world_log, "")
            write_json(
                capture_json,
                {
                    "status": "partial",
                    "inputs": {"worldLog": str(world_log)},
                    "summary": {
                        "statusReason": "prelogin-route-regression",
                        "worldWindowSelected": "",
                        "overlapAchieved": False,
                    },
                    "launchEvaluation": {
                        "canonicalMitmLaunch": True,
                        "hostRewrite": "0",
                        "lobbyHostRewrite": "0",
                        "contentRouteRewrite": "1",
                        "contentRouteMode": "content-only-local-mitm",
                        "nonCanonicalHostRewrite": False,
                    },
                },
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"summary": {}})

            with patch("run_946_scene_delivery_aid.DEFAULT_BLACK_SCREEN_CAPTURE_JSON", capture_json):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        world_window=None,
                        js5_session_dir=root / "js5",
                        content_capture_dir=root / "content",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        checksum_report_json=checksum_json,
                        prefetch_report_json=prefetch_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "prelogin-route-regression")

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    def test_live_watch_secure_game_without_http_does_not_fake_scene_overlap(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"
            live_watch_path = root / "live-watch.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
                        "2026-03-16T18:00:03.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_json(
                live_watch_path,
                {
                    "tool": "watch_rs2client_live",
                    "status": "ok",
                    "inputs": {"worldLog": str(world_log)},
                    "summary": {
                        "terminalState": "prelogin-secure-game",
                        "sessionStartedAt": "2026-03-16T18:00:00.000000Z",
                        "sessionEndedAt": "2026-03-16T18:00:04.000000Z",
                        "sessionDurationSeconds": 4.0,
                        "localContentMitmObserved": False,
                        "localMsRequestsObserved": False,
                        "proxySecureGameTlsObserved": True,
                        "proxyHttpContentTlsObserved": False,
                        "archiveRequestCount": 0,
                        "responseHeaderCount": 0,
                        "responseBytes": 0,
                    },
                },
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"tool": "prefetch-table-compare", "status": "ok", "summary": {"comparisonState": "match"}})
            with patch("run_946_scene_delivery_aid.DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON", live_watch_path):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        world_window=None,
                        js5_session_dir=root / "js5",
                        content_capture_dir=root / "content",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        checksum_report_json=checksum_json,
                        prefetch_report_json=prefetch_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["summary"]["overlapConfidence"], "missing")
        self.assertEqual(artifact["summary"]["selectedCaptureFormat"], "missing")
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "prelogin-route-regression")

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    @patch("run_946_scene_delivery_aid.DEFAULT_BLACK_SCREEN_CAPTURE_JSON")
    def test_capture_bundle_content_route_bypass_is_reported_explicitly(
        self,
        capture_bundle_json: patch,
        _: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"
            capture_json = root / "black-screen-capture.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
                        "2026-03-16T18:00:03.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_json(
                capture_json,
                {
                    "status": "partial",
                    "inputs": {"worldLog": str(world_log)},
                    "summary": {
                        "statusReason": "content-route-bypassed-local-mitm",
                        "worldWindowSelected": "1:3",
                        "overlapAchieved": False,
                        "freshLocalTlsSessionCount": 0,
                        "localMsRequestsObserved": False,
                        "localMitm443ConnectionCount": 0,
                        "directExternal443ConnectionCount": 2,
                    },
                    "launchEvaluation": {
                        "canonicalMitmLaunch": True,
                        "hostRewrite": "0",
                        "lobbyHostRewrite": "0",
                        "contentRouteRewrite": "1",
                        "contentRouteMode": "content-only-local-mitm",
                        "nonCanonicalHostRewrite": False,
                    },
                },
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"summary": {}})

            with patch("run_946_scene_delivery_aid.DEFAULT_BLACK_SCREEN_CAPTURE_JSON", capture_json):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        world_window=None,
                        js5_session_dir=root / "js5",
                        content_capture_dir=root / "content",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        checksum_report_json=checksum_json,
                        prefetch_report_json=prefetch_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["status"], "partial")
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "content-route-bypassed-local-mitm")

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    @patch("run_946_scene_delivery_aid.DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON")
    def test_live_watch_summary_can_supply_capture_when_scattered_logs_are_missing(
        self,
        live_watch_json: patch,
        _: patch,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"
            watcher_json = root / "latest-summary.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T18:00:00.000000Z world-stage stage=appearance",
                        "2026-03-16T18:00:01.000000Z world-send-rebuild-tail mode=0",
                        "2026-03-16T18:00:03.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_json(
                watcher_json,
                {
                    "status": "ok",
                    "inputs": {"worldLog": str(world_log)},
                    "summary": {
                        "sessionStartedAt": "2026-03-16T18:00:00.100000+00:00",
                        "sessionEndedAt": "2026-03-16T18:00:04.000000+00:00",
                        "sessionDurationSeconds": 3.9,
                        "localContentMitmObserved": True,
                        "localMsRequestsObserved": True,
                        "archiveRequestCount": 1,
                        "responseHeaderCount": 1,
                        "responseBytes": 128,
                        "firstJs5RequestSeconds": 0.3,
                        "firstArchiveRequestSeconds": 0.4,
                        "firstJs5ResponseSeconds": 0.6,
                        "firstArchiveResponseSeconds": 0.6,
                        "worldWindowSelected": "1:3",
                        "deepHooksEnabled": True,
                        "terminalState": "black-screen-plateau",
                    },
                    "artifacts": {"latestSessionJsonl": str(root / "latest-session.jsonl")},
                },
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"summary": {}})

            with patch("run_946_scene_delivery_aid.DEFAULT_CLIENT_LIVE_WATCH_SUMMARY_JSON", watcher_json):
                artifact = build_artifact(
                    SimpleNamespace(
                        world_log=world_log,
                        world_window=None,
                        js5_session_dir=root / "js5",
                        content_capture_dir=root / "content",
                        runtime_trace_dir=root / "runtime",
                        clienterror_dir=root / "clienterror",
                        checksum_report_json=checksum_json,
                        prefetch_report_json=prefetch_json,
                        output_dir=root,
                    )
                )

        self.assertEqual(artifact["summary"]["selectedCaptureFormat"], "live-watch")
        self.assertEqual(artifact["summary"]["overlapConfidence"], "exact")
        self.assertTrue(artifact["summary"]["liveWatchPresent"])

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    def test_content_proxy_overlap_detects_local_js5_no_response(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            content_dir = root / "content"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T23:10:05.000000Z world-stage stage=appearance",
                        "2026-03-16T23:10:05.500000Z world-send-rebuild-tail mode=0",
                        "2026-03-16T23:10:06.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_text(
                content_dir / "session-35-20260316-230400.log",
                "\n".join(
                    [
                        "session#35 start=2026-03-16T23:10:05.309799+00:00",
                        "session#35 client=('127.0.0.1', 50709)",
                        "session#35 mode=tls initial-peek=16 03 03 00 a9",
                        "session#35 tls-client-sni=localhost",
                        "session#35 remote=127.0.0.1:43595",
                        "tls-client->remote first-chunk-1 bytes=80 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 32 35 35 26 6b 3d 39 34 36 26 67 3d 32 35 35 26 63 3d 30 26 76 3d 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "session#35 bytes tls-client->remote=80 remote->tls-client=0",
                        "session#35 end=2026-03-16T23:10:06.561671+00:00",
                    ]
                ),
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"summary": {}})

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    world_window=None,
                    js5_session_dir=root / "js5",
                    content_capture_dir=content_dir,
                    runtime_trace_dir=root / "runtime",
                    clienterror_dir=root / "clienterror",
                    checksum_report_json=checksum_json,
                    prefetch_report_json=prefetch_json,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["summary"]["selectedCaptureFormat"], "content-proxy")
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "content-proxy-no-response")

    @patch("run_946_scene_delivery_aid.input_fingerprint", return_value="fingerprint")
    def test_content_proxy_detects_truncated_archive_delivery(self, _: patch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_log = root / "world.log"
            content_dir = root / "content"
            checksum_json = root / "checksum.json"
            prefetch_json = root / "prefetch.json"

            write_text(
                world_log,
                "\n".join(
                    [
                        "2026-03-16T23:10:05.000000Z world-stage stage=appearance",
                        "2026-03-16T23:10:05.500000Z world-send-rebuild-tail mode=0",
                        "2026-03-16T23:10:06.000000Z world-stage stage=interfaces",
                    ]
                ),
            )
            write_text(
                content_dir / "session-36-20260316-230400.log",
                "\n".join(
                    [
                        "session#36 start=2026-03-16T23:10:06.309799+00:00",
                        "session#36 client=('127.0.0.1', 50709)",
                        "session#36 mode=tls initial-peek=16 03 03 00 a9",
                        "session#36 tls-client-sni=localhost",
                        "session#36 remote=content.runescape.com:443",
                        "tls-client->remote first-chunk-1 bytes=100 hex=47 45 54 20 2f 6d 73 3f 6d 3d 30 26 61 3d 34 30 26 6b 3d 39 34 36 26 67 3d 33 38 33 35 34 26 63 3d 2d 38 35 31 37 34 35 35 35 34 26 76 3d 31 35 34 34 34 34 39 31 36 30 20 48 54 54 50 2f 31 2e 31 0d 0a 48 6f 73 74 3a 20 6c 6f 63 61 6c 68 6f 73 74 0d 0a 41 63 63 65 70 74 3a 20 2a 2f 2a 0d 0a 0d 0a",
                        "remote->tls-client first-chunk-1 bytes=394 hex=48 54 54 50 2f 31 2e 31 20 32 30 30 20 4f 4b 0d 0a 43 6f 6e 74 65 6e 74 2d 6c 65 6e 67 74 68 3a 20 38 36 37 35 38 0d 0a 0d 0a",
                        "remote->tls-client first-chunk-2 bytes=1460 hex=17 03 03 40 18 00 00 00 00 00 00 00 02 9a",
                        "session#36 bytes tls-client->remote=100 remote->tls-client=1854",
                        "session#36 end=2026-03-16T23:10:07.561671+00:00",
                    ]
                ),
            )
            write_json(checksum_json, {"tool": "checksum-table-compare", "status": "ok", "summary": {"entryMismatchCount": 0}})
            write_json(prefetch_json, {"summary": {}})

            artifact = build_artifact(
                SimpleNamespace(
                    world_log=world_log,
                    world_window=None,
                    js5_session_dir=root / "js5",
                    content_capture_dir=content_dir,
                    runtime_trace_dir=root / "runtime",
                    clienterror_dir=root / "clienterror",
                    checksum_report_json=checksum_json,
                    prefetch_report_json=prefetch_json,
                    output_dir=root,
                )
            )

        self.assertEqual(artifact["status"], "ok")
        self.assertEqual(artifact["summary"]["selectedCaptureFormat"], "content-proxy")
        self.assertEqual(artifact["summary"]["truncatedJs5SessionCount"], 1)
        self.assertEqual(artifact["verdict"]["likelyBlocker"], "archive-delivery-truncated")


if __name__ == "__main__":
    unittest.main()
