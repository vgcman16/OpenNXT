from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

try:
    from tools.repair_947_source_reference_tables import (
        backup_existing_reference_table,
        load_repair_plan,
        parse_archive_csv,
        resolve_build_and_token,
        write_reference_table,
    )
except ImportError:
    from repair_947_source_reference_tables import (
        backup_existing_reference_table,
        load_repair_plan,
        parse_archive_csv,
        resolve_build_and_token,
        write_reference_table,
    )


class Repair947SourceReferenceTablesTest(unittest.TestCase):
    def test_parse_archive_csv(self) -> None:
        self.assertEqual([2, 3, 12], parse_archive_csv("2, 3,12"))
        self.assertIsNone(parse_archive_csv(None))

    def test_load_repair_plan_uses_mismatch_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            doctor_json = Path(temp_dir) / "reference-table-doctor.json"
            doctor_json.write_text(
                json.dumps(
                    {
                        "results": [
                            {"archive": 2, "mismatch_flags": ["local-reference-table-body-disagrees-with-retail"]},
                            {"archive": 24, "mismatch_flags": []},
                            {"archive": 57, "mismatch_flags": ["response-header-mismatch"]},
                            {"archive": 255, "mismatch_flags": ["local-reference-table-body-disagrees-with-retail"]},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            plan = load_repair_plan(doctor_json)

            self.assertEqual([2, 57], [entry.archive for entry in plan])

    def test_resolve_build_and_token_falls_back_to_param_10(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            fallback = Path(temp_dir) / "jav_config.ws"
            fallback.write_text(
                "\n".join(
                    [
                        "param=10=STATIC_TOKEN",
                        "param=29=SESSION_TOKEN",
                        "server_version=947",
                    ]
                ),
                encoding="iso-8859-1",
            )

            build, token, source = resolve_build_and_token("http://127.0.0.1:1/jav_config.ws", fallback)

            self.assertEqual(947, build)
            self.assertEqual("STATIC_TOKEN", token)
            self.assertTrue(source.startswith("file:"))

    def test_backup_and_write_reference_table_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            cache_path = temp_root / "js5-2.jcache"
            backup_dir = temp_root / "backups"
            old_payload = b"\x00\x00\x00\x00\x04old!"
            new_payload = b"\x00\x00\x00\x00\x04new!"

            connection = sqlite3.connect(cache_path)
            try:
                connection.execute(
                    "CREATE TABLE cache_index(KEY INTEGER PRIMARY KEY, DATA BLOB, VERSION INTEGER, CRC INTEGER)"
                )
                connection.execute(
                    "INSERT INTO cache_index(KEY, DATA, VERSION, CRC) VALUES(1, ?, ?, ?)",
                    (sqlite3.Binary(old_payload), -1, 0x12345678),
                )
                connection.commit()
            finally:
                connection.close()

            backup_path, stored_version = backup_existing_reference_table(cache_path, backup_dir, 2)
            self.assertIsNotNone(backup_path)
            self.assertEqual(-1, stored_version)
            assert backup_path is not None
            self.assertEqual(old_payload, backup_path.read_bytes())

            write_reference_table(cache_path, new_payload, stored_version=7, crc32_value=0xDEADBEEF)

            connection = sqlite3.connect(cache_path)
            try:
                row = connection.execute(
                    "SELECT DATA, VERSION, CRC FROM cache_index WHERE KEY = 1"
                ).fetchone()
            finally:
                connection.close()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertEqual(new_payload, bytes(row[0]))
            self.assertEqual(7, row[1])
            self.assertEqual(0xDEADBEEF, row[2])


if __name__ == "__main__":
    unittest.main()
