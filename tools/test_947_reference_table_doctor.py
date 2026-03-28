from __future__ import annotations

import unittest

try:
    from tools.run_947_reference_table_doctor import (
        ChecksumTableEntry,
        DiffSummary,
        LocalReferenceTableInfo,
        build_hex_diff_window,
        build_reference_request,
        classify_archive,
        compare_bytes,
        decode_checksum_table_payload,
        derive_hot_archives,
        parse_archives,
        parse_js5_reply,
        parse_send_chunks,
        select_handshake_and_template,
    )
except ImportError:
    from run_947_reference_table_doctor import (
        ChecksumTableEntry,
        DiffSummary,
        LocalReferenceTableInfo,
        build_hex_diff_window,
        build_reference_request,
        classify_archive,
        compare_bytes,
        decode_checksum_table_payload,
        derive_hot_archives,
        parse_archives,
        parse_js5_reply,
        parse_send_chunks,
        select_handshake_and_template,
    )


def build_reply(archive: int, container_payload: bytes, *, handshake: int = 0, priority: bool = True) -> bytes:
    archive_hash = archive if priority else (archive | 0x80000000)
    envelope = bytes([255]) + archive_hash.to_bytes(4, "big")
    prefix = b"\x00" + len(container_payload).to_bytes(4, "big")
    return bytes([handshake]) + envelope + prefix + container_payload


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

    def test_derive_hot_archives_uses_repeated_requests_and_adds_master(self) -> None:
        log_text = "\n".join(
            [
                "Queued js5 request #1 from /127.0.0.1:1: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=28), available=true",
                "Queued js5 request #2 from /127.0.0.1:1: opcode=1, priority=true, nxt=false, build=947, occurrence=2, reference-table(index=255, archive=28), available=true",
                "Queued js5 request #3 from /127.0.0.1:1: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=62), available=true",
                "Queued js5 request #4 from /127.0.0.1:1: opcode=1, priority=true, nxt=false, build=947, occurrence=2, reference-table(index=255, archive=62), available=true",
                "Queued js5 request #5 from /127.0.0.1:1: opcode=1, priority=true, nxt=false, build=947, occurrence=1, reference-table(index=255, archive=31), available=false",
            ]
        )

        self.assertEqual([28, 62, 255], derive_hot_archives(log_text))

    def test_parse_js5_reply_separates_frame_and_payload(self) -> None:
        reply = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd"), handshake=6))

        self.assertEqual(6, reply.handshake_response)
        self.assertEqual(28, reply.header.archive)
        self.assertEqual(bytes.fromhex("00000000090000000004aabbccdd"), reply.payload_bytes)
        self.assertEqual(bytes.fromhex("ff0000001c00000000090000000004aabbccdd"), reply.frame_bytes)
        self.assertEqual(b"", reply.trailing_bytes)

    def test_frame_and_payload_diffs_are_reported_separately(self) -> None:
        local = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd")))
        live = parse_js5_reply(build_reply(29, bytes.fromhex("0000000004aabbccdd")))

        frame_diff = compare_bytes(local.frame_bytes, live.frame_bytes)
        payload_diff = compare_bytes(local.payload_bytes, live.payload_bytes)

        self.assertEqual("mismatch", frame_diff.state)
        self.assertEqual("match", payload_diff.state)

    def test_decode_checksum_table_payload_supports_master_entries(self) -> None:
        entry_zero = (
            bytes.fromhex("11223344")
            + bytes.fromhex("00000065")
            + bytes.fromhex("00000007")
            + bytes.fromhex("00000080")
            + (b"\x01" * 64)
        )
        entry_one = (
            bytes.fromhex("55667788")
            + bytes.fromhex("00000066")
            + bytes.fromhex("00000008")
            + bytes.fromhex("00000090")
            + (b"\x02" * 64)
        )
        dump = decode_checksum_table_payload(b"\x02" + entry_zero + entry_one + b"\xaa\xbb")

        self.assertEqual(2, dump.entry_count)
        self.assertEqual(0x11223344, dump.entries[0].crc)
        self.assertEqual(0x55667788, dump.entries[1].crc)
        self.assertEqual("aabb", dump.signature_hex)

    def test_build_hex_diff_window_renders_first_mismatch_context(self) -> None:
        diff = DiffSummary(
            state="mismatch",
            common_prefix_bytes=2,
            first_diff_offset=2,
            local_remaining_bytes=2,
            live_remaining_bytes=2,
        )

        window = build_hex_diff_window(b"\x00\x01\x02\x03", b"\x00\x01\x09\x0a", diff, window_bytes=1)

        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(1, window.start_offset)
        self.assertEqual(3, window.end_offset)
        self.assertEqual("0102", window.local_hex)
        self.assertEqual("0109", window.live_hex)

    def test_classify_archive_flags_master_entry_disagreement_with_retail(self) -> None:
        local = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd")))
        live = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd")))
        local_master = ChecksumTableEntry(28, 0x11111111, 100, 7, 128, "00" * 64)
        live_master = ChecksumTableEntry(28, 0x22222222, 100, 7, 128, "00" * 64)

        flags = classify_archive(
            archive=28,
            payload_diff=compare_bytes(local.payload_bytes, live.payload_bytes),
            local_master_entry=local_master,
            live_master_entry=live_master,
            local_reference_table=None,
            local_reply=local,
            live_reply=live,
        )

        self.assertIn("master-entry-disagrees-with-retail", flags)

    def test_classify_archive_flags_body_disagreement_with_retail(self) -> None:
        local = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd")))
        live = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccee")))

        flags = classify_archive(
            archive=28,
            payload_diff=compare_bytes(local.payload_bytes, live.payload_bytes),
            local_master_entry=None,
            live_master_entry=None,
            local_reference_table=None,
            local_reply=local,
            live_reply=live,
        )

        self.assertIn("local-reference-table-body-disagrees-with-retail", flags)

    def test_classify_archive_flags_master_entry_disagreement_with_local_table(self) -> None:
        local = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd")))
        live = parse_js5_reply(build_reply(28, bytes.fromhex("0000000004aabbccdd")))
        local_master = ChecksumTableEntry(28, 0x11111111, 100, 7, 128, "00" * 64)
        local_truth = LocalReferenceTableInfo(
            archive=28,
            path="C:/cache/js5-28.jcache",
            raw_bytes=64,
            raw_sha256="abc",
            raw_crc32=0x33333333,
            stored_crc32=0x33333333,
            raw_version=101,
            stored_version=101,
        )

        flags = classify_archive(
            archive=28,
            payload_diff=compare_bytes(local.payload_bytes, live.payload_bytes),
            local_master_entry=local_master,
            live_master_entry=local_master,
            local_reference_table=local_truth,
            local_reply=local,
            live_reply=live,
        )

        self.assertIn("local-master-entry-disagrees-with-local-table", flags)


if __name__ == "__main__":
    unittest.main()
