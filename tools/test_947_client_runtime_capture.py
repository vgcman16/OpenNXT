from __future__ import annotations

from pathlib import Path
import unittest


SCRIPT_PATH = Path(__file__).resolve().parent / "start_947_client_only_runtime_capture.ps1"
PYTHON_COORDINATOR_PATH = Path(__file__).resolve().parent / "run_947_client_only_capture_cycle.py"


class ClientRuntimeCaptureScriptTest(unittest.TestCase):
    def test_runtime_capture_script_wires_expected_tools(self) -> None:
        text = SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn("Get-CimInstance Win32_Process", text)
        self.assertIn("start_947_client_userdump.ps1", text)
        self.assertIn("start_947_client_crash_probe.ps1", text)
        self.assertIn("launch-client-only.ps1", text)
        self.assertIn("$preexistingProcessIds", text)
        self.assertIn("$attachedProcessIds", text)
        self.assertIn("RepairR15AtStateCapture", text)
        self.assertIn("FunctionStartRva", text)
        self.assertIn("FaultRva", text)
        self.assertIn("StateCaptureRva", text)

    def test_python_capture_cycle_uses_async_userdump_startup(self) -> None:
        text = PYTHON_COORDINATOR_PATH.read_text(encoding="utf-8")

        self.assertIn("subprocess.Popen(", text)
        self.assertIn("start_947_client_userdump.ps1", text)
        self.assertIn("list_procdump_pids()", text)
        self.assertIn("Timed out waiting for ProcDump monitor startup", text)
        self.assertIn("trace_947_application_resource_gate.py", text)
        self.assertIn("trace_947_application_resource_state.py", text)
        self.assertIn("trace_947_application_resource_bridge.py", text)
        self.assertIn("trace_947_prelogin_producer_path.py", text)
        self.assertIn("--ignore-existing-processes", text)
        self.assertIn("--wait-timeout-seconds", text)
        self.assertIn("--function-start-rva", text)
        self.assertIn("--fault-rva", text)
        self.assertIn("--state-capture-rva", text)
        self.assertIn("--probe-repair-r15-at-state-capture", text)
        self.assertIn("resourceGateTrace", text)
        self.assertIn("resourceStateTrace", text)
        self.assertIn("resourceBridgeTrace", text)
        self.assertIn("producerTrace", text)
        self.assertIn("gate_force_owner_stage_clear_when_drained", text)
        self.assertIn("gate_force_record_open_on_field1c", text)
        self.assertIn("gate_force_seed_dispatch_on_ptr178", text)
        self.assertIn("gate_force_direct_dispatch_on_state1", text)
        self.assertIn("gate_force_owner_stage_open_on_state1", text)
        self.assertIn("gate_force_idle_selector_latch_clear", text)
        self.assertIn("gate_force_idle_selector_timer_open", text)
        self.assertIn("gate_force_idle_selector_queue_empty", text)
        self.assertIn("gate_force_post_select_flag20_on_busy", text)
        self.assertIn("bridge_force_state1_on_ptr178", text)
        self.assertIn("bridge_force_selector_ready_on_ptr178", text)
        self.assertIn("bridge_force_owner_11d4a_open_on_special20", text)


if __name__ == "__main__":
    unittest.main()
