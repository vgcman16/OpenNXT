from __future__ import annotations

import unittest

from tools.run_947_ms_bootstrap_doctor import (
    FetchResult,
    compare_headers,
    infer_likely_blocker,
)


class MsBootstrapDoctorTests(unittest.TestCase):
    def test_detects_body_mismatch_before_header_mismatch(self) -> None:
        local = FetchResult(
            url="http://127.0.0.1/ms",
            status=200,
            headers={
                "server": "JAGeX/3.1",
                "content-type": "application/octet-stream",
                "cache-control": "public, max-age=25920000",
                "content-length": "12",
                "connection": "close",
            },
            body_length=12,
            body_sha256="a" * 64,
            first_64_hex="00",
        )
        live = FetchResult(
            url="https://content.runescape.com/ms",
            status=200,
            headers={
                "server": "JAGeX/3.1",
                "content-type": "application/octet-stream",
                "cache-control": "public, max-age=25920000",
                "content-length": "12",
                "connection": "close",
            },
            body_length=12,
            body_sha256="b" * 64,
            first_64_hex="00",
        )

        header_diffs = compare_headers(local.headers, live.headers)
        self.assertEqual({}, header_diffs)
        self.assertEqual("ms-bootstrap-body-mismatch", infer_likely_blocker(local, live, header_diffs))

    def test_detects_header_mismatch_when_body_matches(self) -> None:
        local = FetchResult(
            url="http://127.0.0.1/ms",
            status=200,
            headers={
                "server": "OpenNXT/1.0",
                "content-type": "application/octet-stream",
                "cache-control": "public, max-age=25920000",
                "content-length": "12",
                "connection": "close",
            },
            body_length=12,
            body_sha256="a" * 64,
            first_64_hex="00",
        )
        live = FetchResult(
            url="https://content.runescape.com/ms",
            status=200,
            headers={
                "server": "JAGeX/3.1",
                "content-type": "application/octet-stream",
                "cache-control": "public, max-age=25920000",
                "content-length": "12",
                "connection": "close",
            },
            body_length=12,
            body_sha256="a" * 64,
            first_64_hex="00",
        )

        header_diffs = compare_headers(local.headers, live.headers)
        self.assertIn("server", header_diffs)
        self.assertEqual("ms-bootstrap-header-mismatch", infer_likely_blocker(local, live, header_diffs))

    def test_detects_match(self) -> None:
        local = FetchResult(
            url="http://127.0.0.1/ms",
            status=200,
            headers={
                "server": "JAGeX/3.1",
                "content-type": "application/octet-stream",
                "cache-control": "public, max-age=25920000",
                "content-length": "12",
                "connection": "close",
            },
            body_length=12,
            body_sha256="a" * 64,
            first_64_hex="00",
        )
        live = FetchResult(
            url="https://content.runescape.com/ms",
            status=200,
            headers={
                "server": "JAGeX/3.1",
                "content-type": "application/octet-stream",
                "cache-control": "public, max-age=25920000",
                "content-length": "12",
                "connection": "close",
            },
            body_length=12,
            body_sha256="a" * 64,
            first_64_hex="00",
        )

        header_diffs = compare_headers(local.headers, live.headers)
        self.assertEqual({}, header_diffs)
        self.assertEqual("match", infer_likely_blocker(local, live, header_diffs))


if __name__ == "__main__":
    unittest.main()
