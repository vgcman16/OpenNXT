from __future__ import annotations

import unittest

try:
    from tools.run_947_reference_table_doctor import (
        build_reference_request,
        compare_bytes,
        parse_archives,
        parse_send_chunks,
        select_handshake_and_template,
    )
except ImportError:
    from run_947_reference_table_doctor import (
        build_reference_request,
        compare_bytes,
        parse_archives,
        parse_send_chunks,
        select_handshake_and_template,
    )


class ReferenceTableDoctorTest(unittest.TestCase):
    def test_select_handshake_and_template_uses_first_four_chunks_and_fifth_request(self) -> None:
        text = "\n".join(
            [
                "raw-client->remote first-chunk-1 bytes=1 hex=01",
                "raw-client->remote first-chunk-2 bytes=1 hex=02",
                "raw-client->remote first-chunk-3 bytes=1 hex=03",
                "raw-client->remote first-chunk-4 bytes=1 hex=04",
                "raw-client->remote first-chunk-5 bytes=10 hex=01 ff 00 00 00 15 03 b3 a2 4e",
            ]
        )

        chunks = parse_send_chunks(text)
        handshake, template = select_handshake_and_template(chunks)

        self.assertEqual(4, len(handshake))
        self.assertEqual(b"\x01\xff\x00\x00\x00\x15\x03\xb3\xa2\x4e", template)

    def test_build_reference_request_replaces_archive_big_endian(self) -> None:
        payload = build_reference_request(bytes.fromhex("01ff0000001503b3a24e"), 0x62)

        self.assertEqual(bytes.fromhex("01ff0000006203b3a24e"), payload)

    def test_parse_archives_accepts_csv(self) -> None:
        self.assertEqual([2, 3, 12], parse_archives("2,3,12"))

    def test_compare_bytes_reports_mismatch(self) -> None:
        diff = compare_bytes(b"\x01\x02", b"\x01\x03")

        self.assertEqual("mismatch", diff.state)
        self.assertEqual(1, diff.common_prefix_bytes)
        self.assertEqual(1, diff.first_diff_offset)


if __name__ == "__main__":
    unittest.main()
