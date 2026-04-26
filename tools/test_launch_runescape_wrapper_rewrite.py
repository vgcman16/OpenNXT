import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.launch_runescape_wrapper_rewrite import (
    _build_2ab698_null_param2_guard_trampoline,
    _build_3699b2_world_metadata_guard_trampoline,
    _build_58fa83_master_table_presence_guard_trampoline,
    SPECIAL_GUARDED_JUMP_BYPASS_SPECS,
    _build_59002d_guard_trampoline,
    _build_5902d5_state_guard_trampoline,
    _build_5927f2_master_table_publish_guard_trampoline,
    _build_590ccb_force_first_compare_trampoline,
    _build_590cf1_force_second_compare_trampoline,
    _build_590de8_empty_compare_guard_trampoline,
    _build_590ec9_archive_state_slot_guard_trampoline,
    _build_59c1ea_force_length_gate_trampoline,
    _build_59c2a0_compare_mirror_trampoline,
    _build_590c58_master_table_guard_trampoline,
    _build_590c72_sentinel_trampoline,
    _encode_absolute_jump,
    KNOWN_INLINE_PATCHES,
    KNOWN_JUMP_BYPASS_BLOCKS,
    build_connect_redirects,
    build_effective_rewrite_map,
    build_secure_retail_world_fleet_hosts,
    build_wrapper_spawn_script,
    build_route_resolve_redirects,
    should_auto_redirect_route_hosts,
    cleanup_spawned_processes,
    cleanup_wrapper_after_child_ready,
    build_param_rewrite_map,
    build_route_rewrite_map,
    extract_param_map,
    files_equal,
    find_embedded_rsa_key,
    load_rsa_moduli,
    load_rewrite_jav_config,
    normalize_jump_bypass_specs,
    normalize_patch_offsets,
    parse_resolve_redirect_specs,
    query_process_command_line,
    query_process_path,
    refresh_accepted_child_exe,
    resolve_fetch_config_uri,
    rebuild_windows_command_line,
    rewrite_param_tokens,
    tokenize_windows_command_line,
)


class LaunchRuneScapeWrapperRewriteTest(unittest.TestCase):
    def test_normalize_patch_offsets_filters_disabled_caller_bypass(self) -> None:
        self.assertNotIn(0x58FF0F, KNOWN_INLINE_PATCHES)
        self.assertEqual([0x590001], normalize_patch_offsets(["0x58ff0f", "0x590001"]))

    def test_normalize_patch_offsets_filters_disabled_reference_table_loop_patch(self) -> None:
        self.assertEqual([0x590CF4], normalize_patch_offsets(["0x594a41", "0x590cf4"]))

    def test_normalize_patch_offsets_keeps_loading_state_rebuild_patch(self) -> None:
        self.assertEqual([0x590CF4, 0x590001], normalize_patch_offsets(["0x590cf4", "0x590001"]))

    def test_build_59002d_guard_trampoline_preserves_real_block(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x59002D, 0x5900A5)]
        overwritten = spec["expected"]
        stub = _build_59002d_guard_trampoline(
            trampoline_address=0x0000000180000000,
            skip_target_address=0x00000001405900A5,
            return_address=0x000000014059003B,
            overwritten_bytes=overwritten,
        )

        self.assertEqual(bytes.fromhex("48 85 DB"), stub[:3])
        self.assertEqual(bytes.fromhex("4C 39 E3"), stub[9:12])
        self.assertIn(overwritten, stub)
        self.assertIn(_encode_absolute_jump(0x000000014059003B), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x00000001405900A5)))

    def test_build_5902d5_state_guard_trampoline_only_skips_real_pending_entries(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x5902D5, 0x5903BD)]
        self.assertEqual(
            bytes.fromhex("41 80 FA 01 0F 84 DE 00 00 00 49 8B 00"),
            spec["expected"],
        )
        self.assertEqual(0x5902E2, spec["resumeOffset"])
        self.assertEqual("guard-5902d5", spec["builder"])

        stub = _build_5902d5_state_guard_trampoline(
            trampoline_address=0x0000000180001000,
            skip_target_address=0x00000001405903BD,
            return_address=0x00000001405902E2,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("41 80 FA 01 0F 85")))
        self.assertIn(bytes.fromhex("44 0F B6 8A 34 77 00 00 45 84 C9 0F 85"), stub)
        self.assertIn(bytes.fromhex("48 83 BA D8 77 00 00 00 0F 85"), stub)
        self.assertIn(bytes.fromhex("49 8B 00"), stub)
        self.assertIn(_encode_absolute_jump(0x00000001405902E2), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x00000001405903BD)))

    def test_build_590c58_master_table_guard_trampoline_only_falls_back_for_null_or_oob_tables(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x590C58, 0x590C81)]
        self.assertEqual(
            bytes.fromhex("48 8B 91 D0 30 00 00 4C 3B 52 10 73 0D"),
            spec["expected"],
        )
        self.assertEqual(0x590C65, spec["resumeOffset"])
        self.assertEqual("guard-590c58", spec["builder"])

        stub = _build_590c58_master_table_guard_trampoline(
            trampoline_address=0x0000000180001800,
            skip_target_address=0x0000000140590C81,
            return_address=0x0000000140590C65,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("48 8B 91 D0 30 00 00 48 85 D2 0F 84")))
        self.assertIn(bytes.fromhex("4C 3B 52 10 0F 83"), stub)
        self.assertIn(_encode_absolute_jump(0x0000000140590C65), stub)
        self.assertIn(bytes.fromhex("41 B8 FF FF FF FF 41 B9 FF FF FF FF"), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140590C81)))

    def test_build_58fa83_master_table_presence_guard_trampoline_skips_null_table_enrichment(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x58FA83, 0x58FB29)]
        self.assertEqual(
            bytes.fromhex("48 8B 81 D0 30 00 00 41 8B D5 44 8B 20"),
            spec["expected"],
        )
        self.assertEqual(0x58FA90, spec["resumeOffset"])
        self.assertEqual("guard-58fa83", spec["builder"])

        stub = _build_58fa83_master_table_presence_guard_trampoline(
            trampoline_address=0x0000000180001C00,
            skip_target_address=0x000000014058FB29,
            return_address=0x000000014058FA90,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("48 8B 81 D0 30 00 00 48 85 C0 0F 84")))
        self.assertIn(bytes.fromhex("41 8B D5 44 8B 20"), stub)
        self.assertIn(_encode_absolute_jump(0x000000014058FA90), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x000000014058FB29)))

    def test_build_59c1ea_force_length_gate_trampoline_forces_success_path(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x59C1EA, 0x59C21B)]
        self.assertEqual(
            bytes.fromhex("49 83 FE 41 74 2B 48 85 DB 74 0D 4D 85 F6 74 08"),
            spec["expected"],
        )
        self.assertEqual(0x59C21B, spec["resumeOffset"])
        self.assertEqual("force-length-59c1ea", spec["builder"])

        stub = _build_59c1ea_force_length_gate_trampoline(
            skip_target_address=0x000000014059C21B,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("41 BE 41 00 00 00")))
        self.assertIn(bytes.fromhex("48 C7 44 24 38 41 00 00 00"), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x000000014059C21B)))

    def test_build_59c2a0_compare_mirror_trampoline_preserves_real_compare_fail_path(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x59C2A0, 0x59C64F)]
        self.assertEqual(
            bytes.fromhex("41 0F B6 44 08 01 38 01 0F 85 A1 03 00 00"),
            spec["expected"],
        )
        self.assertEqual(0x59C2AE, spec["resumeOffset"])
        self.assertEqual("mirror-compare-59c2a0", spec["builder"])

        stub = _build_59c2a0_compare_mirror_trampoline(
            trampoline_address=0x0000000180002000,
            fail_target_address=0x000000014059C64F,
            return_address=0x000000014059C2AE,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("85 D2 0F 85")))
        self.assertIn(bytes.fromhex("4C 8D 5B 01 49 89 C9 41 BA 40 00 00 00"), stub)
        self.assertIn(bytes.fromhex("41 8A 01 41 88 03 49 FF C1 49 FF C3 41 83 EA 01"), stub)
        self.assertIn(bytes.fromhex("41 0F B6 44 08 01 38 01 0F 85"), stub)
        self.assertIn(_encode_absolute_jump(0x000000014059C2AE), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x000000014059C64F)))

    def test_known_inline_patches_include_recordstate_publish_redirect(self) -> None:
        self.assertEqual(
            {
                "expected": bytes.fromhex("C6 45 20 01"),
                "replacement": bytes.fromhex("C6 45 21 01"),
            },
            KNOWN_INLINE_PATCHES[0x597DB1],
        )

    def test_known_inline_patches_include_accepted_slot_publish_redirect(self) -> None:
        self.assertEqual(
            {
                "expected": bytes.fromhex("C6 43 28 01"),
                "replacement": bytes.fromhex("C6 43 29 01"),
            },
            KNOWN_INLINE_PATCHES[0x59687F],
        )

    def test_known_inline_patches_include_mode0_to_recordstate_redirect(self) -> None:
        self.assertEqual(
            {
                "expected": bytes.fromhex("74 3A"),
                "replacement": bytes.fromhex("74 2B"),
            },
            KNOWN_INLINE_PATCHES[0x596649],
        )

    def test_known_inline_patches_include_dispatch_helper_gate_bypasses(self) -> None:
        self.assertEqual(
            {
                "expected": bytes.fromhex("74 0B"),
                "replacement": bytes.fromhex("90 90"),
            },
            KNOWN_INLINE_PATCHES[0x5955A2],
        )
        self.assertEqual(
            {
                "expected": bytes.fromhex("0F 84 B2 00 00 00"),
                "replacement": bytes.fromhex("90 90 90 90 90 90"),
            },
            KNOWN_INLINE_PATCHES[0x5953E4],
        )

    def test_known_inline_patches_include_stale_owner_latch_bypass(self) -> None:
        self.assertEqual(
            {
                "expected": bytes.fromhex("0F 85 4D FD FF FF"),
                "replacement": bytes.fromhex("90 90 90 90 90 90"),
            },
            KNOWN_INLINE_PATCHES[0x5967E5],
        )

    def test_known_jump_bypass_blocks_include_type3_publication_gate(self) -> None:
        self.assertEqual(
            bytes.fromhex("75 08 B0 01 48 83 C4 70 5B C3"),
            KNOWN_JUMP_BYPASS_BLOCKS[0x59707D],
        )

    def test_known_jump_bypass_blocks_include_late_allocator_slow_path_guard(self) -> None:
        self.assertEqual(
            bytes.fromhex("49 8B 7E 78 49 3B BE 80 00 00 00 73 30"),
            KNOWN_JUMP_BYPASS_BLOCKS[0x7A3BC2],
        )

    def test_build_590c72_sentinel_trampoline_preserves_primary_object_family_path(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x590C72, 0x590DBA)]
        self.assertEqual(
            bytes.fromhex("44 8B 04 25 00 00 00 00 48 8B CE 44 8B 49 04"),
            spec["expected"],
        )
        self.assertEqual(0x590C81, spec["resumeOffset"])
        self.assertEqual("sentinel-590c72", spec["builder"])

        stub = _build_590c72_sentinel_trampoline(return_address=0x0000000140590C81)

        self.assertTrue(stub.startswith(bytes.fromhex("41 B8 FF FF FF FF 41 B9 FF FF FF FF")))
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140590C81)))

    def test_build_5927f2_master_table_publish_guard_trampoline_keeps_only_healthy_tables(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x5927F2, 0x592826)]
        self.assertEqual(
            bytes.fromhex("48 8B 38 4C 89 38 48 85 FF 74 29 48 8D 4F 08"),
            spec["expected"],
        )
        self.assertEqual(0x592801, spec["resumeOffset"])
        self.assertEqual("guarded-publish-5927f2", spec["builder"])

        stub = _build_5927f2_master_table_publish_guard_trampoline(
            trampoline_address=0x0000000180002200,
            skip_target_address=0x0000000140592826,
            return_address=0x0000000140592801,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("4D 85 FF 0F 84")))
        self.assertIn(bytes.fromhex("41 83 3F 42"), stub)
        self.assertIn(bytes.fromhex("49 83 7F 10 43"), stub)
        self.assertIn(bytes.fromhex("49 83 7F 18 00"), stub)
        self.assertIn(bytes.fromhex("4C 89 38"), stub)
        self.assertNotIn(bytes.fromhex("48 8B 38 4C 89 38 48 85 FF"), stub)
        self.assertNotIn(bytes.fromhex("49 8D 4F 08 49 BB"), stub)
        self.assertNotIn(bytes.fromhex("4C 89 F9 BA 20 00 00 00"), stub)
        self.assertNotIn(_encode_absolute_jump(0x0000000140592801), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140592826)))

    def test_build_590ccb_force_first_compare_trampoline_preserves_branch_shape(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x590CCB, 0x590CF1)]
        self.assertEqual(
            bytes.fromhex("41 3B C0 75 2A 84 D2 74 05 8B 47 20 EB 18"),
            spec["expected"],
        )
        self.assertEqual(0x590CD9, spec["resumeOffset"])
        self.assertEqual("force-compare-590ccb", spec["builder"])

        stub = _build_590ccb_force_first_compare_trampoline(
            trampoline_address=0x0000000180002400,
            return_address=0x0000000140590CD9,
            success_target_address=0x0000000140590CF1,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("89 D9 44 89 C0 84 D2 0F 84")))
        self.assertIn(bytes.fromhex("8B 47 20"), stub)
        self.assertIn(_encode_absolute_jump(0x0000000140590CF1), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140590CD9)))

    def test_build_590cf1_force_second_compare_trampoline_jumps_to_success_path(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x590CF1, 0x590DCB)]
        self.assertEqual(
            bytes.fromhex("41 3B C1 0F 84 D1 00 00 00 0F 57 C0"),
            spec["expected"],
        )
        self.assertEqual(0x590DCB, spec["resumeOffset"])
        self.assertEqual("force-compare-590cf1", spec["builder"])

        stub = _build_590cf1_force_second_compare_trampoline(
            success_target_address=0x0000000140590DCB,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("44 89 C8")))
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140590DCB)))

    def test_build_590de8_empty_compare_guard_trampoline_only_bypasses_the_empty_empty_fast_fail(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x590DE8, 0x590EC6)]
        self.assertEqual(
            bytes.fromhex("450fb68f347700004d8d87107700004584c9750d4939b7d87700000f84bd000000"),
            spec["expected"],
        )
        self.assertEqual(0x590E09, spec["resumeOffset"])
        self.assertEqual("guard-590de8", spec["builder"])

        stub = _build_590de8_empty_compare_guard_trampoline(
            trampoline_address=0x0000000180002600,
            skip_target_address=0x0000000140590EC6,
            return_address=0x0000000140590E09,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("45 0F B6 8F 34 77 00 00 4D 8D 87 10 77 00 00 45 84 C9 0F 85")))
        self.assertIn(bytes.fromhex("49 83 BF D8 77 00 00 00 0F 85"), stub)
        self.assertIn(bytes.fromhex("48 85 FF 0F 84"), stub)
        self.assertIn(bytes.fromhex("80 7F 24 00 0F 84"), stub)
        self.assertIn(bytes.fromhex("83 3F 00 0F 84"), stub)
        self.assertIn(bytes.fromhex("83 7F 20 00 0F 84"), stub)
        self.assertIn(bytes.fromhex("8B 07 41 89 87 10 77 00 00"), stub)
        self.assertIn(bytes.fromhex("8B 47 20 41 89 87 30 77 00 00"), stub)
        self.assertIn(bytes.fromhex("41 C6 87 34 77 00 00 01"), stub)
        self.assertIn(bytes.fromhex("48 83 BF 98 00 00 00 00 0F 85"), stub)
        self.assertIn(bytes.fromhex("48 83 BF C8 00 00 00 00 0F 85"), stub)
        self.assertIn(_encode_absolute_jump(0x0000000140590E09), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140590EC6)))

    def test_build_590ec9_archive_state_slot_guard_trampoline_treats_missing_slot_as_unknown_state(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x590EC9, 0x590EDA)]
        self.assertEqual(
            bytes.fromhex("48c1e0054a8b8418100c01000fb6541801"),
            spec["expected"],
        )
        self.assertEqual(0x590EDA, spec["resumeOffset"])
        self.assertEqual("guard-590ec9", spec["builder"])

        stub = _build_590ec9_archive_state_slot_guard_trampoline(
            trampoline_address=0x0000000180002700,
            return_address=0x0000000140590EDA,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("48 C1 E0 05 4A 8B 84 18 10 0C 01 00 48 85 C0 0F 84")))
        self.assertIn(bytes.fromhex("48 83 F8 FF 0F 84"), stub)
        self.assertIn(bytes.fromhex("48 3D 00 00 01 00 0F 82"), stub)
        self.assertIn(bytes.fromhex("0F B6 54 18 01"), stub)
        self.assertIn(bytes.fromhex("31 D2"), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x0000000140590EDA)))

    def test_build_2ab698_null_param2_guard_trampoline_only_skips_null_param2_plus8(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x2AB698, 0x2AB7F7)]
        self.assertEqual(
            bytes.fromhex("48 8B 72 08 4C 8B FA 4C 8B F1 49 8D 53 A8 48 83 C1 20 41 8B F8"),
            spec["expected"],
        )
        self.assertEqual(0x2AB6AD, spec["resumeOffset"])
        self.assertEqual("guard-2ab698", spec["builder"])

        stub = _build_2ab698_null_param2_guard_trampoline(
            trampoline_address=0x0000000180003400,
            skip_target_address=0x00000001402AB7F7,
            return_address=0x00000001402AB6AD,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("48 8B 72 08 48 85 F6 0F 84")))
        self.assertIn(bytes.fromhex("4C 8B FA 4C 8B F1 49 8D 53 A8 48 83 C1 20 41 8B F8"), stub)
        self.assertIn(_encode_absolute_jump(0x00000001402AB6AD), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x00000001402AB7F7)))

    def test_build_3699b2_world_metadata_guard_trampoline_skips_poisoned_param1_base(self) -> None:
        spec = SPECIAL_GUARDED_JUMP_BYPASS_SPECS[(0x3699B2, 0x3699F2)]
        self.assertEqual(
            bytes.fromhex("4C 8B 11 44 89 41 0C 49 8B 5A 18 33 C9 8B C1"),
            spec["expected"],
        )
        self.assertEqual(0x3699C1, spec["resumeOffset"])
        self.assertEqual("guard-3699b2", spec["builder"])

        stub = _build_3699b2_world_metadata_guard_trampoline(
            trampoline_address=0x0000000180003600,
            skip_target_address=0x00000001403699F2,
            return_address=0x00000001403699C1,
        )

        self.assertTrue(stub.startswith(bytes.fromhex("4C 8B 11 44 89 41 0C 4D 85 D2 0F 84")))
        self.assertIn(bytes.fromhex("49 81 FA 00 00 01 00 0F 82"), stub)
        self.assertIn(bytes.fromhex("4C 89 D0 48 C1 E0 10 48 C1 F8 10 4C 39 D0 0F 85"), stub)
        self.assertIn(bytes.fromhex("49 8B 5A 18 48 85 DB 0F 84"), stub)
        self.assertIn(bytes.fromhex("48 81 FB 00 00 01 00 0F 82"), stub)
        self.assertIn(bytes.fromhex("48 89 D8 48 C1 E0 10 48 C1 F8 10 48 39 D8 0F 85"), stub)
        self.assertIn(bytes.fromhex("33 C9 8B C1"), stub)
        self.assertIn(bytes.fromhex("31 C0 89 41 10"), stub)
        self.assertIn(_encode_absolute_jump(0x00000001403699C1), stub)
        self.assertTrue(stub.endswith(_encode_absolute_jump(0x00000001403699F2)))

    def test_parse_args_supports_repeatable_wrapper_extra_args(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--wrapper-extra-arg=--useAngle",
            "--wrapper-extra-arg=--another-flag",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(["--useAngle", "--another-flag"], args.wrapper_extra_arg)

    def test_parse_args_supports_repeatable_accepted_child_exe(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--accepted-child-exe",
            r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            "--accepted-child-exe",
            r"C:\RuneScape\alt\rs2client.exe",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                r"C:\RuneScape\alt\rs2client.exe",
            ],
            args.accepted_child_exe,
        )

    def test_parse_args_supports_optional_child_hook_capture(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--child-hook-output",
            r"C:\child-trace.jsonl",
            "--child-hook-verbose",
            "--child-hook-duration-seconds",
            "30",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(r"C:\child-trace.jsonl", args.child_hook_output)
        self.assertTrue(args.child_hook_verbose)
        self.assertEqual(30, args.child_hook_duration_seconds)

    def test_parse_args_supports_optional_rsa_config(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--rsa-config",
            r"C:\rsa.toml",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(r"C:\rsa.toml", args.rsa_config)

    def test_parse_args_supports_optional_js5_rsa_source_exe(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--js5-rsa-source-exe",
            r"C:\original-rs2client.exe",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(r"C:\original-rs2client.exe", args.js5_rsa_source_exe)

    def test_parse_args_supports_repeatable_resolve_redirects(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--resolve-redirect",
            "rs.config.runescape.com=localhost",
            "--resolve-redirect",
            "content.runescape.com=localhost",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual(
            ["rs.config.runescape.com=localhost", "content.runescape.com=localhost"],
            args.resolve_redirect,
        )

    def test_parse_args_supports_rewrite_scope(self) -> None:
        from unittest.mock import patch
        from tools.launch_runescape_wrapper_rewrite import parse_args

        argv = [
            "launch_runescape_wrapper_rewrite.py",
            "--wrapper-exe",
            r"C:\RuneScape.exe",
            "--config-uri",
            "http://localhost:8080/jav_config.ws",
            "--trace-output",
            r"C:\trace.jsonl",
            "--rewrite-scope",
            "routes",
        ]
        with patch("sys.argv", argv):
            args = parse_args()

        self.assertEqual("routes", args.rewrite_scope)

    def test_parse_resolve_redirect_specs_normalizes_hosts(self) -> None:
        self.assertEqual(
            {
                "rs.config.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
            },
            parse_resolve_redirect_specs(
                [" RS.CONFIG.RUNESCAPE.COM = localhost ", "content.runescape.com=127.0.0.1"]
            ),
        )

    def test_parse_resolve_redirect_specs_preserves_wildcard_hosts(self) -> None:
        self.assertEqual(
            {"world*.runescape.com": "localhost"},
            parse_resolve_redirect_specs([" WORLD*.RUNESCAPE.COM = localhost "]),
        )

    def test_normalize_patch_offsets_accepts_hex_and_decimal(self) -> None:
        self.assertEqual([0x590C72, 0x590F92], normalize_patch_offsets(["0x590c72", "5836690"]))

    def test_normalize_jump_bypass_specs_accepts_hex_and_decimal(self) -> None:
        self.assertEqual(
            [(0x590C72, 0x590DCB), (0x59002D, 0x5900A5)],
            normalize_jump_bypass_specs(["0x590c72:0x590dcb", "5832749:5832869"]),
        )

    def test_normalize_jump_bypass_specs_drops_known_bad_r15_skip(self) -> None:
        self.assertEqual(
            [(0x590C72, 0x590DBA)],
            normalize_jump_bypass_specs(["0x590f92:0x5910eb", "0x590c72:0x590dba"]),
        )

    def test_normalize_jump_bypass_specs_drops_stale_compare_skip(self) -> None:
        self.assertEqual(
            [(0x59002D, 0x5900A5)],
            normalize_jump_bypass_specs(["0x59034d:0x5903c6", "0x59002d:0x5900a5"]),
        )

    def test_normalize_jump_bypass_specs_drops_disabled_reference_table_loop_cluster(self) -> None:
        self.assertEqual(
            [(0x590C72, 0x590DBA)],
            normalize_jump_bypass_specs(
                [
                    "0x590c72:0x590dba",
                    "0x594a88:0x594aa1",
                    "0x594a91:0x594aa1",
                    "0x594aa6:0x594aba",
                    "0x594aaf:0x594aba",
                    "0x59c64f:0x59c2be",
                ]
            ),
        )

    def test_normalize_jump_bypass_specs_drops_disabled_late_state_loading_bypasses(self) -> None:
        self.assertEqual(
            [(0x59002D, 0x5900A5)],
            normalize_jump_bypass_specs(
                [
                    "0x59002d:0x5900a5",
                    "0x594da8:0x594dc1",
                    "0x594dc6:0x594dda",
                    "0x72ad28:0x72ad46",
                    "0x72b3a8:0x72b3c6",
                ]
            ),
        )

    def test_normalize_jump_bypass_specs_drops_disabled_bootstrap_copy_bypass(self) -> None:
        self.assertEqual(
            [(0x59002D, 0x5900A5), (0x590C72, 0x590DBA)],
            normalize_jump_bypass_specs(
                [
                    "0x59002d:0x5900a5",
                    "0x590c72:0x590dba",
                ]
            ),
        )

    def test_files_equal_matches_content_across_different_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            left = temp_path / "left.exe"
            right = temp_path / "right.exe"
            payload = b"OpenNXT-wrapper-content-match"
            left.write_bytes(payload)
            right.write_bytes(payload)

            self.assertTrue(files_equal(str(left), str(right)))

    def test_files_equal_rejects_different_content(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            left = temp_path / "left.exe"
            right = temp_path / "right.exe"
            left.write_bytes(b"left")
            right.write_bytes(b"right")

            self.assertFalse(files_equal(str(left), str(right)))

    def test_refresh_accepted_child_exe_replaces_mismatched_destination(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "patched-rs2client.exe"
            destination = temp_path / "installed-rs2client.exe"
            payload = b"OpenNXT-patched-rs2client"
            source.write_bytes(payload)
            destination.write_bytes(b"stale-runtime-child")

            result = refresh_accepted_child_exe(str(source), str(destination))

            self.assertIsNotNone(result)
            self.assertEqual(payload, destination.read_bytes())
            self.assertEqual(str(source), result["source"])
            self.assertEqual(str(destination), result["destination"])
            self.assertEqual(len(payload), result["size"])

    def test_refresh_accepted_child_exe_skips_when_destination_matches(self) -> None:
        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source = temp_path / "patched-rs2client.exe"
            destination = temp_path / "installed-rs2client.exe"
            payload = b"OpenNXT-identical-child"
            source.write_bytes(payload)
            destination.write_bytes(payload)

            result = refresh_accepted_child_exe(str(source), str(destination))

            self.assertIsNone(result)
            self.assertEqual(payload, destination.read_bytes())

    def test_extract_param_map_reads_param_lines(self) -> None:
        config = "\n".join(
            [
                "codebase=http://localhost:8080/",
                "param=3=localhost",
                "param=35=http://localhost:8080",
                "param=49=localhost",
            ]
        )

        result = extract_param_map(config)

        self.assertEqual(
            {
                "3": "localhost",
                "35": "http://localhost:8080",
                "49": "localhost",
            },
            result,
        )

    def test_resolve_fetch_config_uri_keeps_secure_retail_config_uri(self) -> None:
        original = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
            "&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
        )

        rewritten = resolve_fetch_config_uri(original)

        self.assertEqual(original, rewritten)

    def test_resolve_fetch_config_uri_rewrites_public_config_host_to_local_endpoint_when_local_rewrite_requested(self) -> None:
        original = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0"
            "&codebaseRewrite=1&baseConfigSource=live&liveCache=1"
        )

        rewritten = resolve_fetch_config_uri(original)

        self.assertEqual(
            "http://localhost:8080/jav_config.ws?binaryType=6&hostRewrite=0&contentRouteRewrite=0&worldUrlRewrite=0&codebaseRewrite=1&baseConfigSource=live&liveCache=1",
            rewritten,
        )

    def test_resolve_fetch_config_uri_keeps_existing_local_config_uri(self) -> None:
        original = "http://localhost:8080/jav_config.ws?binaryType=6"
        self.assertEqual(original, resolve_fetch_config_uri(original))

    def test_load_rewrite_jav_config_prefers_explicit_snapshot_file(self) -> None:
        with TemporaryDirectory() as temp_dir:
            rewrite_file = Path(temp_dir) / "startup.ws"
            rewrite_file.write_text("param=35=http://localhost:8080/k=5", encoding="utf-8")

            fetched_uris: list[str] = []

            def fake_fetch(uri: str) -> str:
                fetched_uris.append(uri)
                return "param=35=https://world62.runescape.com/k=5"

            config_text, details = load_rewrite_jav_config(
                "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6",
                rewrite_config_file=str(rewrite_file),
                fetcher=fake_fetch,
            )

        self.assertEqual("param=35=http://localhost:8080/k=5", config_text)
        self.assertEqual([], fetched_uris)
        self.assertEqual(
            {
                "source": "file",
                "path": str(rewrite_file),
                "fetchUri": None,
            },
            details,
        )

    def test_load_rewrite_jav_config_uses_resolved_fetch_uri_without_snapshot_file(self) -> None:
        fetched_uris: list[str] = []

        def fake_fetch(uri: str) -> str:
            fetched_uris.append(uri)
            return "param=35=http://localhost:8080/k=5"

        config_text, details = load_rewrite_jav_config(
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?binaryType=6&codebaseRewrite=1",
            fetcher=fake_fetch,
        )

        self.assertEqual("param=35=http://localhost:8080/k=5", config_text)
        self.assertEqual(
            [
                "http://localhost:8080/jav_config.ws?binaryType=6&codebaseRewrite=1",
            ],
            fetched_uris,
        )
        self.assertEqual("fetch", details["source"])
        self.assertIsNone(details["path"])
        self.assertEqual(
            "http://localhost:8080/jav_config.ws?binaryType=6&codebaseRewrite=1",
            details["fetchUri"],
        )

    def test_should_auto_redirect_route_hosts_false_for_retail_shaped_947_startup(self) -> None:
        config_uri = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
            "&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
        )
        self.assertFalse(should_auto_redirect_route_hosts(config_uri))

    def test_should_auto_redirect_route_hosts_true_for_retail_shaped_947_startup_when_forced(self) -> None:
        config_uri = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
            "&worldUrlRewrite=0&codebaseRewrite=0&gameHostRewrite=0"
        )
        self.assertTrue(
            should_auto_redirect_route_hosts(
                config_uri,
                force_secure_retail_startup_redirects=True,
            )
        )

    def test_should_auto_redirect_route_hosts_true_when_local_route_rewrite_requested(self) -> None:
        config_uri = (
            "http://localhost:8080/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=1"
            "&worldUrlRewrite=1&codebaseRewrite=1"
        )
        self.assertTrue(should_auto_redirect_route_hosts(config_uri))

    def test_should_auto_redirect_route_hosts_true_for_retail_host_when_local_rewrite_requested(self) -> None:
        config_uri = (
            "https://rs.config.runescape.com/k=5/l=0/jav_config.ws?"
            "binaryType=6&hostRewrite=0&lobbyHostRewrite=0&contentRouteRewrite=0"
            "&worldUrlRewrite=0&codebaseRewrite=1&gameHostRewrite=0"
        )
        self.assertTrue(should_auto_redirect_route_hosts(config_uri))

    def test_load_rsa_moduli_reads_login_and_js5_moduli(self) -> None:
        with TemporaryDirectory() as temp_dir:
            rsa_path = Path(temp_dir) / "rsa.toml"
            rsa_path.write_text(
                "\n".join(
                    [
                        "[login]",
                        'modulus = "abcd"',
                        "[js5]",
                        'modulus = "ef01"',
                    ]
                ),
                encoding="utf-8",
            )

            result = load_rsa_moduli(rsa_path)

        self.assertEqual({"login": "abcd", "js5": "ef01"}, result)

    def test_find_embedded_rsa_key_matches_null_delimited_ascii_hex(self) -> None:
        embedded = "a" * 256
        payload = b"\x00" + embedded.encode("ascii") + b"\x00\x00\x00" + b"suffix"

        offset, value = find_embedded_rsa_key(payload, 1024)

        self.assertEqual(1, offset)
        self.assertEqual(embedded, value)

    def test_build_route_rewrite_map_keeps_only_route_fields(self) -> None:
        route_map = build_route_rewrite_map(
            {
                "2": "1144",
                "3": "localhost",
                "29": "session-token",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            }
        )

        self.assertEqual(
            {
                "3": "localhost",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            },
            route_map,
        )

    def test_build_param_rewrite_map_keeps_all_param_fields(self) -> None:
        rewrite_map = build_param_rewrite_map(
            {
                "2": "1144",
                "3": "localhost",
                "27": "5",
                "29": "session-token",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            }
        )

        self.assertEqual(
            {
                "2": "1144",
                "3": "localhost",
                "27": "5",
                "29": "session-token",
                "35": "http://localhost:8080",
                "37": "localhost",
                "40": "http://localhost:8080",
                "49": "localhost",
            },
            rewrite_map,
        )

    def test_build_wrapper_spawn_script_hooks_brokered_process_creation_apis(self) -> None:
        script = build_wrapper_spawn_script(r"C:\game\rs2client.exe")

        self.assertIn('installCreateProcessHook("kernelbase.dll", "CreateProcessInternalW", 1, 2, 8, "wide");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessAsUserW", 1, 2, 8, "wide");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessAsUserA", 1, 2, 8, "ansi");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessWithTokenW", 2, 3, 6, "wide");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessWithTokenA", 2, 3, 6, "ansi");', script)
        self.assertIn('installCreateProcessHook("advapi32.dll", "CreateProcessWithLogonW", 4, 5, 8, "wide");', script)
        self.assertIn('installShellExecuteHook("shell32.dll", "ShellExecuteA", 2, 3, 4, "ansi");', script)
        self.assertIn('installShellExecuteHook("shell32.dll", "ShellExecuteW", 2, 3, 4, "wide");', script)
        self.assertIn('installShellExecuteExHook("shell32.dll", "ShellExecuteExA", "ansi");', script)
        self.assertIn('installShellExecuteExHook("shell32.dll", "ShellExecuteExW", "wide");', script)
        self.assertIn('installCreateFileHook("kernelbase.dll", "CreateFileW", 0, 1, 2, 4, "wide");', script)
        self.assertIn('installMoveFileHook("kernelbase.dll", "MoveFileExW", 0, 1, 2, "wide");', script)
        self.assertIn('installCopyFileHook("kernelbase.dll", "CopyFileExW", 0, 1, "wide");', script)
        self.assertIn('installReplaceFileHook("kernelbase.dll", "ReplaceFileW", 0, 1, 2, "wide");', script)

    def test_build_wrapper_spawn_script_can_one_shot_override_first_eligible_child_spawn(self) -> None:
        script = build_wrapper_spawn_script(r"C:\game\rs2client.exe")

        self.assertIn("const overrideState = { consumed: false };", script)
        self.assertIn("const tracedChildTargets = [];", script)
        self.assertIn('return "direct-match";', script)
        self.assertIn('return "one-shot";', script)
        self.assertIn('if (haystack.indexOf("runescape.exe") !== -1 || haystack.indexOf("jagexlauncher") !== -1) {', script)
        self.assertIn("overrideState.consumed = true;", script)
        self.assertIn("matchKind: matchKind,", script)

    def test_build_wrapper_spawn_script_can_trace_installed_child_file_ops(self) -> None:
        script = build_wrapper_spawn_script(
            r"C:\game\rs2client.exe",
            [r"C:\ProgramData\Jagex\launcher\rs2client.exe"],
        )

        self.assertIn('const tracedChildTargets = ["c:\\\\programdata\\\\jagex\\\\launcher\\\\rs2client.exe"];', script)
        self.assertIn('sendObservedProcessEvent("wrapper-child-createprocess-observed"', script)
        self.assertIn('sendTrackedFileEvent("wrapper-file-create-observed"', script)
        self.assertIn('sendTrackedFileEvent("wrapper-file-move-observed"', script)
        self.assertIn('sendTrackedFileEvent("wrapper-file-copy-observed"', script)
        self.assertIn('sendTrackedFileEvent("wrapper-file-replace-observed"', script)

    def test_build_effective_rewrite_map_uses_full_param_map(self) -> None:
        rewrite_map = build_effective_rewrite_map(
            "\n".join(
                [
                    "param=2=1140",
                    "param=3=localhost",
                    "param=18=1362217156",
                    "param=29=session-token",
                    "param=35=http://localhost:8080/k=5",
                    "param=37=localhost",
                    "param=40=http://localhost:8080/k=5",
                    "param=49=localhost",
                ]
            )
        )

        self.assertEqual(
            {
                "2": "1140",
                "3": "localhost",
                "18": "1362217156",
                "29": "session-token",
                "35": "http://localhost:8080/k=5",
                "37": "localhost",
                "40": "http://localhost:8080/k=5",
                "49": "localhost",
            },
            rewrite_map,
        )

    def test_build_effective_rewrite_map_can_limit_to_route_params(self) -> None:
        rewrite_map = build_effective_rewrite_map(
            "\n".join(
                [
                    "param=2=1140",
                    "param=3=localhost",
                    "param=18=1362217156",
                    "param=29=session-token",
                    "param=35=http://localhost:8080/k=5",
                    "param=37=localhost",
                    "param=40=http://localhost:8080/k=5",
                    "param=49=localhost",
                ]
            ),
            rewrite_scope="routes",
        )

        self.assertEqual(
            {
                "3": "localhost",
                "35": "http://localhost:8080/k=5",
                "37": "localhost",
                "40": "http://localhost:8080/k=5",
                "49": "localhost",
            },
            rewrite_map,
        )

    def test_build_route_resolve_redirects_derives_world_lobby_and_content_hosts(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "lobby48a.runescape.com",
                "35": "https://world31.runescape.com/k=5",
                "37": "content.runescape.com",
                "40": "https://world31.runescape.com/k=5",
                "49": "content.runescape.com",
            }
        )

        self.assertEqual(
            {
                "lobby48a.runescape.com": "localhost",
                "world31.runescape.com": "localhost",
                "content.runescape.com": "localhost",
            },
            redirects,
        )

    def test_build_route_resolve_redirects_includes_codebase_host(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "lobby48a.runescape.com",
                "37": "content.runescape.com",
                "49": "content.runescape.com",
            },
            jav_config_text="codebase=https://world34.runescape.com/k=5\nparam=3=lobby48a.runescape.com",
        )

        self.assertEqual(
            {
                "lobby48a.runescape.com": "localhost",
                "content.runescape.com": "localhost",
                "world34.runescape.com": "localhost",
            },
            redirects,
        )

    def test_build_secure_retail_world_fleet_hosts_covers_expected_range(self) -> None:
        hosts = build_secure_retail_world_fleet_hosts()

        self.assertEqual(
            ["content*.runescape.com", "world*.runescape.com", "lobby*.runescape.com"],
            hosts,
        )

    def test_build_route_resolve_redirects_can_include_secure_retail_world_fleet(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "lobby48a.runescape.com",
                "37": "content.runescape.com",
            },
            include_secure_retail_world_fleet=True,
        )

        self.assertEqual("localhost", redirects["lobby48a.runescape.com"])
        self.assertEqual("localhost", redirects["content.runescape.com"])
        self.assertEqual("localhost", redirects["content*.runescape.com"])
        self.assertEqual("localhost", redirects["world*.runescape.com"])
        self.assertEqual("localhost", redirects["lobby*.runescape.com"])
        self.assertNotIn("rs.config.runescape.com", redirects)

    def test_build_route_resolve_redirects_secure_retail_startup_can_exclude_content_hosts(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "lobby48a.runescape.com",
                "37": "content.runescape.com",
                "49": "content.runescape.com",
                "35": "https://world31.runescape.com/k=5",
            },
            include_secure_retail_world_fleet=True,
            include_content_hosts=False,
        )

        self.assertEqual("localhost", redirects["lobby48a.runescape.com"])
        self.assertEqual("localhost", redirects["world31.runescape.com"])
        self.assertEqual("localhost", redirects["content*.runescape.com"])
        self.assertEqual("localhost", redirects["world*.runescape.com"])
        self.assertEqual("localhost", redirects["lobby*.runescape.com"])
        self.assertNotIn("content.runescape.com", redirects)

    def test_build_connect_redirects_skips_wildcard_source_hosts(self) -> None:
        def fake_resolver(host: str, *_args):
            if host == "content.runescape.com":
                return [(None, None, None, None, ("1.2.3.4", 0))]
            raise AssertionError(f"Unexpected wildcard resolution attempt for {host!r}")

        redirects = build_connect_redirects(
            {
                "world*.runescape.com": "localhost",
                "lobby*.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
            },
            resolver=fake_resolver,
        )

        self.assertEqual({"1.2.3.4": "127.0.0.1"}, redirects)

    def test_build_route_resolve_redirects_skips_loopback_hosts(self) -> None:
        redirects = build_route_resolve_redirects(
            {
                "3": "localhost",
                "35": "https://localhost/k=5",
                "37": "127.0.0.1",
                "40": "https://[::1]/k=5",
                "49": "::1",
            }
        )

        self.assertEqual({}, redirects)

    def test_build_connect_redirects_resolves_ips_for_redirected_hosts(self) -> None:
        def fake_resolver(host: str, *_args):
            if host == "world34.runescape.com":
                return [
                    (None, None, None, None, ("8.26.16.159", 0)),
                    (None, None, None, None, ("8.26.16.159", 0)),
                ]
            if host == "content.runescape.com":
                return [
                    (None, None, None, None, ("91.235.140.195", 0)),
                    (None, None, None, None, ("91.235.140.196", 0)),
                ]
            raise OSError("unresolved")

        redirects = build_connect_redirects(
            {
                "world34.runescape.com": "localhost",
                "content.runescape.com": "127.0.0.1",
                "missing.runescape.com": "localhost",
            },
            resolver=fake_resolver,
        )

        self.assertEqual(
            {
                "8.26.16.159": "localhost",
                "91.235.140.195": "127.0.0.1",
                "91.235.140.196": "127.0.0.1",
            },
            redirects,
        )

    def test_build_connect_redirects_skips_wildcard_hosts(self) -> None:
        def fake_resolver(_host: str, *_args):
            raise AssertionError("wildcard redirect should not reach the resolver")

        redirects = build_connect_redirects(
            {
                "world*.runescape.com": "localhost",
                "lobby*.runescape.com": "localhost",
            },
            resolver=fake_resolver,
        )

        self.assertEqual({}, redirects)

    def test_rewrite_param_tokens_replaces_only_mapped_values(self) -> None:
        arguments = [
            r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            "35",
            "https://world42.runescape.com/k=5",
            "37",
            "content.runescape.com",
            "launcher",
            "6374",
        ]
        rewritten, changes = rewrite_param_tokens(arguments, {"35": "http://localhost:8080", "37": "localhost"})

        self.assertEqual("http://localhost:8080", rewritten[2])
        self.assertEqual("localhost", rewritten[4])
        self.assertEqual("launcher", rewritten[5])
        self.assertEqual("6374", rewritten[6])
        self.assertEqual(
            [
                {"param": "35", "old": "https://world42.runescape.com/k=5", "new": "http://localhost:8080"},
                {"param": "37", "old": "content.runescape.com", "new": "localhost"},
            ],
            changes,
        )

    def test_tokenize_and_rebuild_round_trip_simple_wrapper_command(self) -> None:
        command_line = (
            '"C:\\ProgramData\\Jagex\\launcher\\rs2client.exe" '
            '"35" "https://world42.runescape.com/k=5" '
            '"37" "content.runescape.com" '
            '"launcher" "6374"'
        )

        tokens = tokenize_windows_command_line(command_line)
        rebuilt = rebuild_windows_command_line(tokens)

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "35",
                "https://world42.runescape.com/k=5",
                "37",
                "content.runescape.com",
                "launcher",
                "6374",
            ],
            tokens,
        )
        self.assertEqual(
            'C:\\ProgramData\\Jagex\\launcher\\rs2client.exe 35 https://world42.runescape.com/k=5 37 content.runescape.com launcher 6374',
            rebuilt,
        )
        self.assertEqual(tokens, tokenize_windows_command_line(rebuilt))

    def test_rewrite_param_tokens_does_not_treat_numeric_values_as_keys(self) -> None:
        arguments = [
            r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            "15",
            "",
            "27",
            "79",
            "26",
            "false",
            "21",
            "loading",
            "launcher",
            "6674",
        ]

        rewritten, changes = rewrite_param_tokens(arguments, {"27": "5", "21": "loading2"})

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "15",
                "",
                "27",
                "5",
                "26",
                "false",
                "21",
                "loading2",
                "launcher",
                "6674",
            ],
            rewritten,
        )
        self.assertEqual(
            [
                {"param": "27", "old": "79", "new": "5"},
                {"param": "21", "old": "loading", "new": "loading2"},
            ],
            changes,
        )

    def test_tokenize_preserves_empty_quoted_arguments(self) -> None:
        command_line = (
            '"C:\\ProgramData\\Jagex\\launcher\\rs2client.exe" '
            '"15" "" "27" "140" "launcher" "635C"'
        )

        tokens = tokenize_windows_command_line(command_line)

        self.assertEqual(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "15",
                "",
                "27",
                "140",
                "launcher",
                "635C",
            ],
            tokens,
        )

    def test_rebuild_windows_command_line_uses_minimal_quoting(self) -> None:
        rebuilt = rebuild_windows_command_line(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                "15",
                "",
                "27",
                "140",
                "https://world48.runescape.com/k=5",
                "launcher",
                "635C",
            ]
        )

        self.assertEqual(
            'C:\\ProgramData\\Jagex\\launcher\\rs2client.exe 15 "" 27 140 https://world48.runescape.com/k=5 launcher 635C',
            rebuilt,
        )

    def test_cleanup_spawned_processes_targets_child_before_wrapper_and_dedupes(self) -> None:
        from unittest.mock import patch

        recorded_calls: list[list[str]] = []

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(args, **kwargs):
            recorded_calls.append(list(args))
            return Completed()

        with patch("tools.launch_runescape_wrapper_rewrite.subprocess.run", side_effect=fake_run), patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_path", return_value=None
        ), patch("tools.launch_runescape_wrapper_rewrite.query_process_command_line", return_value=None):
            cleanup_results = cleanup_spawned_processes(200, 100, "missing-child")

        self.assertEqual(
            [
                ["taskkill", "/PID", "100", "/T", "/F"],
                ["taskkill", "/PID", "200", "/T", "/F"],
            ],
            recorded_calls,
        )
        self.assertEqual([100, 200], [entry["pid"] for entry in cleanup_results])

    def test_cleanup_spawned_processes_uses_stop_process_fallback_when_taskkill_leaves_process_alive(self) -> None:
        from unittest.mock import patch

        recorded_calls: list[list[str]] = []

        class Completed:
            def __init__(self, returncode: int = 0) -> None:
                self.returncode = returncode
                self.stdout = ""
                self.stderr = ""

        def fake_run(args, **kwargs):
            recorded_calls.append(list(args))
            return Completed()

        query_results = iter(
            [
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                None,
                None,
                None,
            ]
        )

        def fake_query_process_path(_pid: int):
            return next(query_results)

        with patch("tools.launch_runescape_wrapper_rewrite.subprocess.run", side_effect=fake_run), patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_path", side_effect=fake_query_process_path
        ), patch("tools.launch_runescape_wrapper_rewrite.query_process_command_line", return_value=None), patch(
            "tools.launch_runescape_wrapper_rewrite.time.sleep"
        ):
            cleanup_results = cleanup_spawned_processes(200, 100, "missing-child")

        self.assertEqual(
            [
                ["taskkill", "/PID", "100", "/T", "/F"],
                ["powershell", "-NoProfile", "-Command", "Stop-Process -Id 100 -Force -ErrorAction SilentlyContinue"],
                ["taskkill", "/PID", "200", "/T", "/F"],
            ],
            recorded_calls,
        )
        self.assertTrue(cleanup_results[0]["aliveAfterTaskkill"])
        self.assertFalse(cleanup_results[0]["aliveAfterFallback"])

    def test_cleanup_wrapper_after_child_ready_skips_termination_to_preserve_child(self) -> None:
        from unittest.mock import patch

        recorded_events: list[dict[str, object]] = []

        with patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_path",
            side_effect=[
                r"C:\RuneScape.exe",
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
                r"C:\ProgramData\Jagex\launcher\rs2client.exe",
            ],
        ), patch(
            "tools.launch_runescape_wrapper_rewrite.query_process_command_line",
            return_value=None,
        ), patch(
            "tools.launch_runescape_wrapper_rewrite.terminate_process_only",
        ) as terminate_process_only:
            result = cleanup_wrapper_after_child_ready(200, 100, recorded_events.append)

        terminate_process_only.assert_not_called()
        self.assertEqual(
            {
                "pid": 200,
                "skipped": True,
                "reason": "preserve-wrapper-child-lifetime",
                "childAliveAfterSkip": True,
            },
            result,
        )
        self.assertEqual("wrapper-cleanup-skipped", recorded_events[0]["action"])

    def test_query_process_helpers_tolerate_timeout(self) -> None:
        from unittest.mock import patch

        timeout = subprocess.TimeoutExpired(cmd=["powershell"], timeout=10)
        with patch("tools.launch_runescape_wrapper_rewrite.subprocess.run", side_effect=timeout):
            self.assertIsNone(query_process_command_line(1234))
            self.assertIsNone(query_process_path(1234))

    def test_read_remote_process_image_base_retries_partial_copy(self) -> None:
        from unittest.mock import patch
        import tools.launch_runescape_wrapper_rewrite as rewrite

        attempts = {"count": 0}

        def fake_once(_pid: int) -> int:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise OSError(299, "ReadProcessMemory failed at 0x872b76b000")
            return 0x140000000

        with patch.object(rewrite, "_read_remote_process_image_base_once", side_effect=fake_once), patch.object(
            rewrite.time, "sleep"
        ) as sleep_mock:
            self.assertEqual(0x140000000, rewrite.read_remote_process_image_base(1234))

        self.assertEqual(3, attempts["count"])
        self.assertEqual(2, sleep_mock.call_count)

    def test_read_remote_process_image_layout_retries_incomplete_headers(self) -> None:
        from unittest.mock import patch
        import tools.launch_runescape_wrapper_rewrite as rewrite

        attempts = {"count": 0}

        def fake_once(_pid: int) -> tuple[int, int]:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise ValueError("Process image at 0x140000000 is missing DOS header")
            return 0x140000000, 0xF41000

        with patch.object(rewrite, "_read_remote_process_image_layout_once", side_effect=fake_once), patch.object(
            rewrite.time, "sleep"
        ) as sleep_mock:
            self.assertEqual((0x140000000, 0xF41000), rewrite.read_remote_process_image_layout(1234))

        self.assertEqual(3, attempts["count"])
        self.assertEqual(2, sleep_mock.call_count)


if __name__ == "__main__":
    unittest.main()
