from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from trace_rs2client_map_gate import build_hook_script, empty_summary, finalize_summary, normalize_payload, update_summary


class TraceRs2ClientMapGateTest(unittest.TestCase):
    def test_build_hook_script_includes_cache_and_tls_hooks(self) -> None:
        script = build_hook_script(160, verbose=True)
        self.assertIn("const MAX_PREVIEW_BYTES = 160;", script)
        self.assertIn("const VERBOSE = true;", script)
        self.assertIn("CreateFileW", script)
        self.assertIn("SetFilePointerEx", script)
        self.assertIn(r"main_file_cache\.idx(\d+)$", script)
        self.assertIn("idx-lookup", script)
        self.assertIn("EncryptMessage", script)
        self.assertIn("DecryptMessage", script)
        self.assertIn("client.http", script)

    def test_normalize_payload_sets_defaults(self) -> None:
        payload = normalize_payload({"path": "x"})
        self.assertEqual(payload["category"], "client.unknown")
        self.assertEqual(payload["action"], "event")
        self.assertIn("timestamp", payload)

    def test_summary_tracks_idx_lookups_and_ms_requests(self) -> None:
        summary = empty_summary()
        update_summary(
            summary,
            {
                "category": "client.cache",
                "action": "idx-lookup",
                "indexId": 5,
                "archiveId": 1234,
            },
        )
        update_summary(
            summary,
            {
                "category": "client.http",
                "action": "request",
                "firstLine": "GET /ms?m=0&a=255&g=123 HTTP/1.1",
            },
        )
        update_summary(
            summary,
            {
                "category": "client.http",
                "action": "request",
                "firstLine": "GET /ms?m=5&a=1234&g=5678 HTTP/1.1",
            },
        )
        update_summary(
            summary,
            {
                "category": "client.http",
                "action": "response",
                "firstLine": "HTTP/1.1 200 OK",
            },
        )
        artifact = finalize_summary(summary)
        self.assertEqual(artifact["idxLookupCount"], 1)
        self.assertEqual(artifact["idxLookupsByIndex"]["5"], 1)
        self.assertEqual(artifact["idxArchiveIdsByIndex"]["5"], [1234])
        self.assertEqual(artifact["httpRequestCount"], 2)
        self.assertEqual(artifact["httpMsRequestCount"], 2)
        self.assertEqual(artifact["httpNonReferenceRequestCount"], 1)
        self.assertEqual(artifact["httpResponseCount"], 1)


if __name__ == "__main__":
    unittest.main()
