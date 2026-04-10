from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from tools.run_947_client_crash_rva_doctor import (
        decode_clienterror_report,
        find_matching_fault_event,
        find_runtime_module_base,
        load_fault_events,
        parse_key_value_lines,
        select_latest_clienterror_bundle,
        summarize_backtrace_rvas,
        va_to_rva,
    )
except ImportError:
    from run_947_client_crash_rva_doctor import (
        decode_clienterror_report,
        find_matching_fault_event,
        find_runtime_module_base,
        load_fault_events,
        parse_key_value_lines,
        select_latest_clienterror_bundle,
        summarize_backtrace_rvas,
        va_to_rva,
    )


class ClientCrashRvaDoctorTest(unittest.TestCase):
    def test_parse_key_value_lines_reads_pairs(self) -> None:
        parsed = parse_key_value_lines(["foo=bar", "baz=qux", "blank"])

        self.assertEqual({"foo": "bar", "baz": "qux"}, parsed)

    def test_select_latest_clienterror_bundle_chooses_newest_summary(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            older = root / "older.summary.txt"
            newer = root / "newer.summary.txt"
            older.write_text("message=older\n", encoding="utf-8")
            newer.write_text("message=newer\n", encoding="utf-8")
            (root / "newer.correlation.txt").write_text("hookFaultAddress=0x1\n", encoding="utf-8")
            (root / "newer.decoded.bin").write_bytes(b"Hi\x00")
            older.touch()
            newer.touch()

            bundle = select_latest_clienterror_bundle(root)

            self.assertEqual("newer", bundle.stem)
            self.assertEqual(root / "newer.correlation.txt", bundle.correlation_path)
            self.assertEqual(root / "newer.decoded.bin", bundle.decoded_path)

    def test_decode_clienterror_report_splits_message_and_qwords(self) -> None:
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "report.decoded.bin"
            path.write_bytes(b"Main crash\x00" + (0x1234).to_bytes(8, "little") + b"ABC")

            report = decode_clienterror_report(path, max_qwords=4)

            self.assertEqual("Main crash", report.message)
            self.assertEqual(["0x0000000000001234"], report.qwords)
            self.assertEqual(22, report.raw_length)
            self.assertTrue(report.printable_tail.endswith("ABC"))

    def test_load_fault_events_and_find_matching_fault_event(self) -> None:
        with TemporaryDirectory() as tmpdir:
            hook_path = Path(tmpdir) / "latest-client-only-hook.jsonl"
            hook_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "action": "fault",
                                "timestamp": 1774780890.617,
                                "exceptionType": "access-violation",
                                "address": "0x7ff7a32b0de8",
                                "memory": {"address": "0x774e", "operation": "read"},
                                "context": {"r15": "0x1a"},
                                "backtrace": [{"address": "0x140590de8", "symbol": "fault"}],
                            }
                        ),
                        ""
                    ]
                ),
                encoding="utf-8",
            )
            events = load_fault_events(hook_path)

            matched = find_matching_fault_event(
                events,
                {
                    "hookFaultTimestamp": "2026-03-29T10:41:30.617000Z",
                    "hookFaultAddress": "0x7ff7a32b0de8",
                    "hookFaultExceptionType": "access-violation",
                },
            )

            self.assertIsNotNone(matched)
            assert matched is not None
            self.assertEqual("0x774e", matched.memory_address)
            self.assertEqual("0x1a", matched.context["r15"])

    def test_find_runtime_module_base_reads_rs2client_snapshot(self) -> None:
        with TemporaryDirectory() as tmpdir:
            hook_path = Path(tmpdir) / "latest-client-only-hook.jsonl"
            exe_path = Path(tmpdir) / "rs2client.exe"
            exe_path.write_bytes(b"MZ")
            hook_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "action": "snapshot",
                                "category": "client.module",
                                "moduleName": "rs2client.exe",
                                "path": str(exe_path),
                                "base": "0x7ff7a2d20000",
                            }
                        ),
                        ""
                    ]
                ),
                encoding="utf-8",
            )

            module_base = find_runtime_module_base(hook_path, exe_path)

            self.assertEqual(0x7FF7A2D20000, module_base)

    def test_va_to_rva_and_backtrace_summary_filter_internal_frames(self) -> None:
        image_base = 0x140000000
        size_of_image = 0x1000000

        self.assertEqual(0x590DE8, va_to_rva("0x140590de8", image_base, size_of_image))
        self.assertIsNone(va_to_rva("0x7ffc8999e8d7", image_base, size_of_image))

        frames = summarize_backtrace_rvas(
            [
                {"address": "0x140590de8", "symbol": "fault"},
                {"address": "0x7ffc8999e8d7", "symbol": "kernel"},
            ],
            image_base=image_base,
            size_of_image=size_of_image,
        )

        self.assertEqual(
            [{"address": "0x140590de8", "rva": "0x00590de8", "symbol": "fault"}],
            frames,
        )


if __name__ == "__main__":
    unittest.main()
