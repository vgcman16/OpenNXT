from __future__ import annotations

import unittest

try:
    from tools.run_947_ghidra_crash_bundle import (
        collect_module_backtrace_addresses,
        resolve_fault_target,
        render_markdown,
    )
except ModuleNotFoundError:
    from run_947_ghidra_crash_bundle import (
        collect_module_backtrace_addresses,
        resolve_fault_target,
        render_markdown,
    )


class GhidraCrashBundleTest(unittest.TestCase):
    def test_resolve_fault_target_prefers_explicit_rva(self) -> None:
        target = resolve_fault_target(
            correlation={},
            image_base=0x140000000,
            size_of_image=0x1000000,
            explicit_rva=0x590DE8,
            fault_event=None,
        )

        self.assertEqual(0x590DE8, target.fault_rva)
        self.assertEqual("0x0000000140590de8", target.fault_va)

    def test_resolve_fault_target_uses_correlation_address(self) -> None:
        target = resolve_fault_target(
            correlation={"hookFaultAddress": "0x140590de8"},
            image_base=0x140000000,
            size_of_image=0x1000000,
            explicit_rva=None,
            fault_event=None,
        )

        self.assertEqual(0x590DE8, target.fault_rva)
        self.assertEqual("0x0000000140590de8", target.fault_va)

    def test_resolve_fault_target_uses_runtime_image_base_for_aslr_address(self) -> None:
        target = resolve_fault_target(
            correlation={"hookFaultAddress": "0x7ff7a32b0de8"},
            image_base=0x140000000,
            size_of_image=0x1000000,
            explicit_rva=None,
            fault_event=None,
            runtime_image_base=0x7FF7A2D20000,
        )

        self.assertEqual(0x590DE8, target.fault_rva)
        self.assertEqual("0x0000000140590de8", target.fault_va)

    def test_render_markdown_mentions_bundle_and_function(self) -> None:
        markdown = render_markdown(
            {
                "clienterrorBundle": "nxtclienterror-20260329-test",
                "hookPath": "hook.jsonl",
                "faultTarget": {"faultRva": "0x00590de8", "faultVa": "0x0000000140590de8"},
                "ghidraRawPath": "raw.json",
                "project": {"projectDir": "proj", "projectName": "name"},
                "bootstrap": {"performed": True},
                "ghidraRaw": {
                    "targetAddress": "0x140590de8",
                    "instructionWindow": [{"address": "0x140590de8"}],
                    "targetReferences": [],
                    "inspectedAddresses": [{"requestedAddress": "0x14053ff14"}],
                    "function": {
                        "name": "FUN_140590bc0",
                        "entryPoint": "0x140590bc0",
                        "body": "0x140590bc0-0x1405910ef",
                        "callers": [{"callerName": "caller"}],
                    },
                },
                "decodedReport": {"message": "Main crash"},
                "summary": {"decodeVariant": "url-safe-asterisk"},
                "correlation": {"hookFaultExceptionType": "access-violation"},
            }
        )

        self.assertIn("947 Ghidra Crash Bundle", markdown)
        self.assertIn("FUN_140590bc0", markdown)
        self.assertIn("Main crash", markdown)
        self.assertIn("Extra inspected addresses", markdown)

    def test_collect_module_backtrace_addresses_keeps_unique_internal_frames(self) -> None:
        addresses = collect_module_backtrace_addresses(
            fault_event=type(
                "FaultEventStub",
                (),
                {
                    "backtrace": [
                        {"address": "0x14053ff14", "symbol": "frame1"},
                        {"address": "0x140540457", "symbol": "frame2"},
                        {"address": "0x140590de8", "symbol": "fault"},
                        {"address": "0x7ffd59c2e8d7", "symbol": "kernel"},
                        {"address": "0x14053ff14", "symbol": "dup"},
                    ]
                },
            )(),
            image_base=0x140000000,
            size_of_image=0x1000000,
            fault_va="0x0000000140590de8",
            explicit_addresses=["0x1402b1227"],
        )

        self.assertEqual(
            [
                "0x00000001402b1227",
                "0x000000014053ff14",
                "0x0000000140540457",
            ],
            addresses,
        )


if __name__ == "__main__":
    unittest.main()
