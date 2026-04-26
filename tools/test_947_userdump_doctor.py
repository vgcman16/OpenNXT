from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

try:
    from tools.run_947_userdump_doctor import (
        ModuleSpan,
        decode_access_operation,
        resolve_primary_exe_path,
        resolve_module_for_address,
        select_focus_thread_summary,
        stack_qwords_from_bytes,
    )
except ModuleNotFoundError:
    from run_947_userdump_doctor import (
        ModuleSpan,
        decode_access_operation,
        resolve_primary_exe_path,
        resolve_module_for_address,
        select_focus_thread_summary,
        stack_qwords_from_bytes,
    )


class UserdumpDoctorTest(unittest.TestCase):
    def test_decode_access_operation_maps_execute(self) -> None:
        self.assertEqual("execute", decode_access_operation([8, 0x3B0060E3]))
        self.assertEqual("read", decode_access_operation([0]))
        self.assertEqual("write", decode_access_operation([1]))
        self.assertEqual("unknown-9", decode_access_operation([9]))
        self.assertIsNone(decode_access_operation([]))

    def test_resolve_module_for_address_returns_matching_span(self) -> None:
        spans = [
            ModuleSpan(name="foo.dll", base=0x1000, size=0x200),
            ModuleSpan(name="rs2client.exe", base=0x7FF700000000, size=0x100000),
        ]

        span = resolve_module_for_address(spans, 0x7FF700005904)

        self.assertIsNotNone(span)
        self.assertEqual("rs2client.exe", span.name)
        self.assertIsNone(resolve_module_for_address(spans, 0x99999999))

    def test_stack_qwords_marks_primary_module_rvas(self) -> None:
        primary = ModuleSpan(name="rs2client.exe", base=0x7FF700000000, size=0x200000)
        spans = [primary, ModuleSpan(name="foo.dll", base=0x180000000, size=0x10000)]
        data = (
            (0x7FF700005904).to_bytes(8, "little")
            + (0x180000100).to_bytes(8, "little")
            + (0x1234).to_bytes(8, "little")
        )

        qwords = stack_qwords_from_bytes(0x1000, data, spans, primary)

        self.assertEqual("0x00007ff700005904", qwords[0]["value"])
        self.assertEqual("rs2client.exe", qwords[0]["module"])
        self.assertEqual("0x00005904", qwords[0]["rva"])
        self.assertEqual("foo.dll", qwords[1]["module"])
        self.assertNotIn("rva", qwords[1])
        self.assertNotIn("module", qwords[2])

    def test_select_focus_thread_summary_prefers_primary_module_thread(self) -> None:
        summaries = [
            {"threadId": 10, "moduleName": r"C:\Windows\System32\ntdll.dll", "moduleRva": "0x001656e4"},
            {"threadId": 11, "moduleName": r"C:\game\rs2client.exe", "moduleRva": "0x005963d8", "isPrimaryModule": True},
            {"threadId": 12, "moduleName": r"C:\Windows\System32\kernel32.dll", "moduleRva": "0x00012345"},
        ]

        focus = select_focus_thread_summary(summaries)

        self.assertIsNotNone(focus)
        assert focus is not None
        self.assertEqual(11, focus["threadId"])

    def test_resolve_primary_exe_path_uses_module_path_when_present(self) -> None:
        with TemporaryDirectory() as temp_dir:
            exe_path = Path(temp_dir) / "rs2client.exe"
            exe_path.write_bytes(b"MZ")

            resolved = resolve_primary_exe_path(
                ModuleSpan(name=str(exe_path), base=0x1000, size=0x2000),
                "rs2client.exe",
            )

        self.assertEqual(exe_path, resolved)


if __name__ == "__main__":
    unittest.main()
