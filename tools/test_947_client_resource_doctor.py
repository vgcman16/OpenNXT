from __future__ import annotations

import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

try:
    from tools.run_947_client_resource_doctor import (
        DEFAULT_CONFIG_URL,
        DownloadEntry,
        inspect_directory,
        parse_download_entries,
    )
except ModuleNotFoundError:
    from run_947_client_resource_doctor import (
        DEFAULT_CONFIG_URL,
        DownloadEntry,
        inspect_directory,
        parse_download_entries,
    )


class ClientResourceDoctorTest(TestCase):
    def test_default_config_url_matches_live_like_947_route(self) -> None:
        self.assertIn("downloadMetadataSource=patched", DEFAULT_CONFIG_URL)
        self.assertIn("contentRouteRewrite=0", DEFAULT_CONFIG_URL)
        self.assertIn("gameHostRewrite=0", DEFAULT_CONFIG_URL)
        self.assertIn("worldUrlRewrite=0", DEFAULT_CONFIG_URL)
        self.assertIn("codebaseRewrite=0", DEFAULT_CONFIG_URL)
        self.assertIn("baseConfigSource=live", DEFAULT_CONFIG_URL)
        self.assertIn("liveCache=0", DEFAULT_CONFIG_URL)

    def test_parse_download_entries_collects_name_crc_and_hash(self) -> None:
        entries = parse_download_entries(
            "\n".join(
                [
                    "download_name_0=libEGL.dll",
                    "download_crc_0=123",
                    "download_hash_0=abc",
                    "download_name_3=rs2client.exe",
                    "download_crc_3=456",
                ]
            )
        )

        self.assertEqual(
            [
                DownloadEntry(slot=0, name="libEGL.dll", expected_crc=123, expected_hash="abc"),
                DownloadEntry(slot=3, name="rs2client.exe", expected_crc=456, expected_hash=None),
            ],
            entries,
        )

    def test_inspect_directory_reports_match_mismatch_and_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matching_bytes = b"match"
            mismatching_bytes = b"stale"
            (root / "good.bin").write_bytes(matching_bytes)
            (root / "bad.bin").write_bytes(mismatching_bytes)
            entries = [
                DownloadEntry(
                    slot=0,
                    name="good.bin",
                    expected_crc=zlib.crc32(matching_bytes) & 0xFFFFFFFF,
                    expected_hash=None,
                ),
                DownloadEntry(
                    slot=1,
                    name="bad.bin",
                    expected_crc=(zlib.crc32(matching_bytes) + 1) & 0xFFFFFFFF,
                    expected_hash=None,
                ),
                DownloadEntry(
                    slot=2,
                    name="missing.bin",
                    expected_crc=99,
                    expected_hash=None,
                ),
            ]

            results = inspect_directory("local", root, entries)

        self.assertEqual(["match", "crc-mismatch", "missing"], [result.status for result in results])
        self.assertEqual("good.bin", results[0].name)
        self.assertEqual("bad.bin", results[1].name)
        self.assertEqual("missing-file", results[2].reason)
