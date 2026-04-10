from __future__ import annotations

import unittest

try:
    from tools.trace_947_application_resource_state import build_script
except ModuleNotFoundError:
    from trace_947_application_resource_state import build_script  # type: ignore


class ApplicationResourceStateTraceTest(unittest.TestCase):
    def test_build_script_injects_requested_rvas(self) -> None:
        script = build_script(
            gate_rva=0x59671F,
            dispatch_rva=0x595530,
            select_next_rva=0x594270,
            scheduler_global_rva=0xE57B60,
        )

        self.assertIn("moduleBase.add(0x59671f)", script)
        self.assertIn("moduleBase.add(0x595530)", script)
        self.assertIn("moduleBase.add(0x594270)", script)
        self.assertIn("moduleBase.add(0xe57b60)", script)
        self.assertIn("event: \"resource-dispatch\"", script)
        self.assertIn("event: \"resource-select-next\"", script)
        self.assertIn("event: \"resource-gate\"", script)
        self.assertIn("field1cNonZeroCount", script)
        self.assertIn("ptr178SetCount", script)
        self.assertIn("ptr1c8SetCount", script)


if __name__ == "__main__":
    unittest.main()
