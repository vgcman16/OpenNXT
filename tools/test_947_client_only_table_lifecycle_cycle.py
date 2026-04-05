from __future__ import annotations

import unittest
from pathlib import Path

from tools import run_947_client_only_table_lifecycle_cycle as cycle


class ClientOnlyTableLifecycleCycleTest(unittest.TestCase):
    def test_powershell_args_include_script_and_extras(self) -> None:
        script = Path(r"C:\example\launch-client-only.ps1")
        args = cycle.powershell_args(script, "-GraphicsDevicePreference", "high-performance")
        self.assertEqual(args[:4], ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass"])
        self.assertEqual(args[4], "-File")
        self.assertEqual(args[5], str(script))
        self.assertEqual(args[6:], ["-GraphicsDevicePreference", "high-performance"])

    def test_start_tracer_command_shape_uses_process_wait(self) -> None:
        expected = [
            str(cycle.TOOLS / "trace_947_table_lifecycle.py"),
            "--process-name",
            "rs2client",
            "--ignore-existing-processes",
        ]
        self.assertIn("trace_947_table_lifecycle.py", expected[0])
        self.assertEqual(expected[1:], ["--process-name", "rs2client", "--ignore-existing-processes"])


if __name__ == "__main__":
    unittest.main()
