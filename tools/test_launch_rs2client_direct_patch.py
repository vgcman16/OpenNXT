from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launch_rs2client_direct_patch import (
    extract_startup_contract_hint,
    infer_client_variant,
    parse_args,
    parse_resolve_redirect_specs,
    uses_secure_retail_startup_contract,
    write_startup_contract_hint,
    write_summary_output,
)


class LaunchRs2ClientDirectPatchTest(unittest.TestCase):
    def test_infer_client_variant_from_executable_parent(self) -> None:
        variant = infer_client_variant(
            Path(r"C:\repo\data\clients\947\win64c\original\rs2client.exe")
        )
        self.assertEqual(variant, "original")

    def test_extract_startup_contract_hint_prefers_explicit_download_metadata_source(self) -> None:
        hint = extract_startup_contract_hint(
            client_exe=Path(r"C:\repo\data\clients\947\win64c\patched\rs2client.exe"),
            client_args=[
                "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
                "binaryType=6&downloadMetadataSource=original"
            ],
            process_pid=1234,
        )

        self.assertEqual(hint["clientVariant"], "patched")
        self.assertEqual(hint["downloadMetadataSource"], "original")
        self.assertEqual(hint["pid"], 1234)

    def test_extract_startup_contract_hint_preserves_explicit_live_download_metadata_source(self) -> None:
        hint = extract_startup_contract_hint(
            client_exe=Path(r"C:\repo\external\rs2client.exe"),
            client_args=[
                "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
                "binaryType=6&downloadMetadataSource=live"
            ],
            process_pid=5678,
        )

        self.assertEqual(hint["clientVariant"], "")
        self.assertEqual(hint["downloadMetadataSource"], "live")
        self.assertEqual(hint["pid"], 5678)

    def test_extract_startup_contract_hint_falls_back_to_client_variant(self) -> None:
        hint = extract_startup_contract_hint(
            client_exe=Path(r"C:\repo\data\clients\947\win64c\compressed\rs2client.exe"),
            client_args=["https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6"],
        )

        self.assertEqual(hint["clientVariant"], "compressed")
        self.assertEqual(hint["downloadMetadataSource"], "compressed")

    def test_parse_resolve_redirect_specs_normalizes_hosts(self) -> None:
        redirects = parse_resolve_redirect_specs(
            [
                "RS.CONFIG.RUNESCAPE.COM=localhost",
                "content.runescape.com=127.0.0.1",
            ]
        )
        self.assertEqual(
            redirects,
            {
                "rs.config.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
            },
        )

    def test_parse_resolve_redirect_specs_rejects_bad_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_resolve_redirect_specs(["missing-separator"])

    def test_uses_secure_retail_startup_contract_detects_secure_retail_config_arg(self) -> None:
        self.assertTrue(
            uses_secure_retail_startup_contract(
                [
                    "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
                    "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
                    "&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
                ]
            )
        )

    def test_uses_secure_retail_startup_contract_ignores_local_config_arg(self) -> None:
        self.assertFalse(
            uses_secure_retail_startup_contract(
                [
                    "http://localhost:8080/jav_config.ws?"
                    "binaryType=6&hostRewrite=0&contentRouteRewrite=1"
                ]
            )
        )

    def test_write_summary_output_replaces_file_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "summary.json"
            summary_path.write_text('{"summaryStage":"old"}', encoding="utf-8")

            write_summary_output(summary_path, {"summaryStage": "ready", "pid": 1234})

            self.assertEqual(
                json.loads(summary_path.read_text(encoding="utf-8")),
                {"summaryStage": "ready", "pid": 1234},
            )
            self.assertFalse((Path(temp_dir) / "summary.json.tmp").exists())

    def test_write_startup_contract_hint_uses_direct_patch_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "summary.json"
            hint_path = write_startup_contract_hint(
                summary_path,
                {"downloadMetadataSource": "original", "clientVariant": "original"},
            )

            self.assertEqual(hint_path, Path(temp_dir) / "latest-startup-contract.json")
            self.assertEqual(
                json.loads(hint_path.read_text(encoding="utf-8"))["downloadMetadataSource"],
                "original",
            )

    def test_parse_args_accepts_resource_gate_probe_flags(self) -> None:
        args = parse_args(
            [
                "--client-exe",
                "client.exe",
                "--working-dir",
                "workdir",
                "--summary-output",
                "summary.json",
                "--resource-gate-output-root",
                "resource-gate",
                "--producer-output-root",
                "producer",
                "--loading-state-output-root",
                "loading-state",
                "--resource-gate-force-record21-on-open",
                "--resource-gate-force-recorde-on-open",
                "--resource-gate-force-recorde-on-dispatch-return",
                "--resource-gate-force-recordd-clear-on-dispatch-return",
                "--resource-gate-force-owner-stage-clear-when-drained",
            ]
        )

        self.assertEqual(args.resource_gate_output_root, "resource-gate")
        self.assertEqual(args.producer_output_root, "producer")
        self.assertEqual(args.loading_state_output_root, "loading-state")
        self.assertTrue(args.resource_gate_force_record21_on_open)
        self.assertTrue(args.resource_gate_force_recorde_on_open)
        self.assertTrue(args.resource_gate_force_recorde_on_dispatch_return)
        self.assertTrue(args.resource_gate_force_recordd_clear_on_dispatch_return)
        self.assertTrue(args.resource_gate_force_owner_stage_clear_when_drained)
        self.assertEqual(args.resource_gate_idle_selector_rva, 0x594270)
        self.assertEqual(args.loading_state_state_copy_rva, 0x593010)
        self.assertEqual(args.loading_state_gate_rva, 0x594A10)
        self.assertEqual(args.loading_state_callsite_rva, 0x59109C)


if __name__ == "__main__":
    unittest.main()
