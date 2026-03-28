from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_946_active_sub_aid import (
    active_sub_candidate_names,
    confidence_and_notes,
    export_target,
    write_draft_field_file,
)


class ActiveSubAidTest(unittest.TestCase):
    def test_active_sub_candidate_names_collects_suggested_and_exact_names(self) -> None:
        names = active_sub_candidate_names(
            {
                "suggestedName": "",
                "exactCandidateNames": ["IF_OPENSUB_ACTIVE_PLAYER", "IF_OPENSUB_ACTIVE_NPC", "OTHER"],
            }
        )
        self.assertEqual(names, ["IF_OPENSUB_ACTIVE_NPC", "IF_OPENSUB_ACTIVE_PLAYER"])

    def test_confidence_is_high_when_recovery_matches_named_sibling(self) -> None:
        confidence, notes = confidence_and_notes(
            ["ushort", "ushort", "intv1", "ubytec", "intv1"],
            {"IF_OPENSUB_ACTIVE_OBJ": ["ushort", "ushort", "intv1", "ubytec", "intv1"]},
            [],
        )
        self.assertEqual(confidence, "high")
        self.assertTrue(notes)

    def test_write_draft_field_file_uses_dedicated_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = write_draft_field_file(Path(tmpdir), 67, ["IF_OPENSUB_ACTIVE_PLAYER"], ["ushort", "ushort"])
            self.assertTrue(Path(path).exists())
            self.assertIn("IF_OPENSUB_ACTIVE_PLAYER", Path(path).name)

    @mock.patch("run_946_active_sub_aid.cleanup_ghidra_project_clone")
    @mock.patch("run_946_active_sub_aid.run_headless_postscript")
    @mock.patch("run_946_active_sub_aid.clone_ghidra_project")
    def test_export_target_uses_isolated_clone_and_records_cleanup(
        self,
        clone_project: mock.Mock,
        run_headless: mock.Mock,
        cleanup_clone: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ghidra_dir = root / "ghidra-home"
            (ghidra_dir / "support").mkdir(parents=True, exist_ok=True)
            (ghidra_dir / "support" / "analyzeHeadless.bat").write_text("echo headless", encoding="utf-8")
            project_dir = root / "project"
            (project_dir / "demo.rep").mkdir(parents=True, exist_ok=True)
            (project_dir / "demo.gpr").write_text("gpr", encoding="utf-8")
            (project_dir / "demo.rep" / "project.prp").write_text("rep", encoding="utf-8")
            clone_project.return_value = {
                "cloneStrategy": "disposable-project-clone",
                "cloneProjectDir": str(root / "clone-67"),
                "cloneProjectName": "demo",
            }
            cleanup_clone.return_value = {"status": "cleaned", "path": str(root / "clone-67"), "error": ""}
            export_root = root / "exports"
            export_json = export_root / "parserFields" / "opcode-67_IF_OPENSUB_ACTIVE_PLAYER.json"

            def run_headless_side_effect(**_: object) -> dict[str, object]:
                export_json.parent.mkdir(parents=True, exist_ok=True)
                export_json.write_text(
                    '{"recoveryMode":"decompiler-c","decompileAttempted":true,"decompileCompleted":true,'
                    '"analysisNotes":["Decompiler completed quickly."],'
                    '"fields":[{"candidateType":"ushort"},{"candidateType":"intv1"}]}',
                    encoding="utf-8",
                )
                return {"returnCode": 0, "stdoutText": "ok", "stderrText": ""}

            run_headless.side_effect = run_headless_side_effect
            args = SimpleNamespace(
                ghidra_dir=ghidra_dir,
                ghidra_project_dir=project_dir,
                ghidra_project_name="demo",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                analyze=False,
                headless_timeout_seconds=120,
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
            )

            result = export_target(
                {
                    "opcode": 67,
                    "evidence": {"parserTarget": "1400abcd0", "parserName": "FUN_1400abcd0"},
                    "exactCandidateNames": ["IF_OPENSUB_ACTIVE_PLAYER"],
                },
                args,
                export_root,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["errorKind"], "")
        self.assertEqual(result["cloneStrategy"], "disposable-project-clone")
        self.assertEqual(result["cloneCleanupStatus"], "cleaned")
        self.assertEqual(result["recoveryMode"], "decompiler-c")
        self.assertTrue(result["decompileAttempted"])
        self.assertTrue(result["decompileCompleted"])
        self.assertEqual(result["analysisNotes"], ["Decompiler completed quickly."])

    @mock.patch("run_946_active_sub_aid.cleanup_ghidra_project_clone")
    @mock.patch("run_946_active_sub_aid.run_headless_postscript")
    @mock.patch("run_946_active_sub_aid.clone_ghidra_project")
    def test_export_target_reports_lock_failure_distinctly(
        self,
        clone_project: mock.Mock,
        run_headless: mock.Mock,
        cleanup_clone: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ghidra_dir = root / "ghidra-home"
            (ghidra_dir / "support").mkdir(parents=True, exist_ok=True)
            (ghidra_dir / "support" / "analyzeHeadless.bat").write_text("echo headless", encoding="utf-8")
            project_dir = root / "project"
            (project_dir / "demo.rep").mkdir(parents=True, exist_ok=True)
            (project_dir / "demo.gpr").write_text("gpr", encoding="utf-8")
            (project_dir / "demo.rep" / "project.prp").write_text("rep", encoding="utf-8")
            clone_project.return_value = {
                "cloneStrategy": "disposable-project-clone",
                "cloneProjectDir": str(root / "clone-116"),
                "cloneProjectName": "demo",
            }
            cleanup_clone.return_value = {"status": "cleaned", "path": str(root / "clone-116"), "error": ""}
            run_headless.return_value = {
                "returnCode": 1,
                "stdoutText": "ERROR LockException: Unable to lock project!",
                "stderrText": "",
            }
            args = SimpleNamespace(
                ghidra_dir=ghidra_dir,
                ghidra_project_dir=project_dir,
                ghidra_project_name="demo",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                analyze=False,
                headless_timeout_seconds=120,
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
            )

            result = export_target(
                {
                    "opcode": 116,
                    "evidence": {"parserTarget": "1400beef0", "parserName": "FUN_1400beef0"},
                    "exactCandidateNames": ["IF_OPENSUB_ACTIVE_NPC"],
                },
                args,
                root / "exports",
            )

        self.assertEqual(result["status"], "export-failed")
        self.assertEqual(result["errorKind"], "project-lock")

    @mock.patch("run_946_active_sub_aid.cleanup_ghidra_project_clone")
    @mock.patch("run_946_active_sub_aid.run_headless_postscript")
    @mock.patch("run_946_active_sub_aid.clone_ghidra_project")
    def test_export_target_accepts_pcode_fallback_with_non_empty_fields(
        self,
        clone_project: mock.Mock,
        run_headless: mock.Mock,
        cleanup_clone: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ghidra_dir = root / "ghidra-home"
            (ghidra_dir / "support").mkdir(parents=True, exist_ok=True)
            (ghidra_dir / "support" / "analyzeHeadless.bat").write_text("echo headless", encoding="utf-8")
            project_dir = root / "project"
            (project_dir / "demo.rep").mkdir(parents=True, exist_ok=True)
            (project_dir / "demo.gpr").write_text("gpr", encoding="utf-8")
            (project_dir / "demo.rep" / "project.prp").write_text("rep", encoding="utf-8")
            clone_project.return_value = {
                "cloneStrategy": "disposable-project-clone",
                "cloneProjectDir": str(root / "clone-67"),
                "cloneProjectName": "demo",
            }
            cleanup_clone.return_value = {"status": "cleaned", "path": str(root / "clone-67"), "error": ""}
            export_root = root / "exports"
            export_json = export_root / "parserFields" / "opcode-67_IF_OPENSUB_ACTIVE_NPC.json"

            def run_headless_side_effect(**_: object) -> dict[str, object]:
                export_json.parent.mkdir(parents=True, exist_ok=True)
                export_json.write_text(
                    '{"recoveryMode":"pcode-fallback","decompileAttempted":true,"decompileCompleted":false,'
                    '"analysisNotes":["Recovered parser fields from instruction fallback."],'
                    '"fields":[{"candidateType":"intv1"},{"candidateType":"ushort128"},{"candidateType":"ubytec"}]}',
                    encoding="utf-8",
                )
                return {"returnCode": 0, "stdoutText": "ok", "stderrText": ""}

            run_headless.side_effect = run_headless_side_effect
            args = SimpleNamespace(
                ghidra_dir=ghidra_dir,
                ghidra_project_dir=project_dir,
                ghidra_project_name="demo",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                analyze=False,
                headless_timeout_seconds=120,
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
            )

            result = export_target(
                {
                    "opcode": 67,
                    "evidence": {"parserTarget": "1400fbba0", "parserName": "FUN_1400fbba0"},
                    "exactCandidateNames": ["IF_OPENSUB_ACTIVE_NPC"],
                },
                args,
                export_root,
            )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["recoveryMode"], "pcode-fallback")
        self.assertTrue(result["decompileAttempted"])
        self.assertFalse(result["decompileCompleted"])
        self.assertEqual(result["exportedFieldTypes"], ["intv1", "ushort128", "ubytec"])

    @mock.patch("run_946_active_sub_aid.cleanup_ghidra_project_clone")
    @mock.patch("run_946_active_sub_aid.run_headless_postscript")
    @mock.patch("run_946_active_sub_aid.clone_ghidra_project")
    def test_export_target_keeps_failure_when_fallback_recovers_no_fields(
        self,
        clone_project: mock.Mock,
        run_headless: mock.Mock,
        cleanup_clone: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ghidra_dir = root / "ghidra-home"
            (ghidra_dir / "support").mkdir(parents=True, exist_ok=True)
            (ghidra_dir / "support" / "analyzeHeadless.bat").write_text("echo headless", encoding="utf-8")
            project_dir = root / "project"
            (project_dir / "demo.rep").mkdir(parents=True, exist_ok=True)
            (project_dir / "demo.gpr").write_text("gpr", encoding="utf-8")
            (project_dir / "demo.rep" / "project.prp").write_text("rep", encoding="utf-8")
            clone_project.return_value = {
                "cloneStrategy": "disposable-project-clone",
                "cloneProjectDir": str(root / "clone-67"),
                "cloneProjectName": "demo",
            }
            cleanup_clone.return_value = {"status": "cleaned", "path": str(root / "clone-67"), "error": ""}
            export_root = root / "exports"
            export_json = export_root / "parserFields" / "opcode-67_IF_OPENSUB_ACTIVE_NPC.json"

            def run_headless_side_effect(**_: object) -> dict[str, object]:
                export_json.parent.mkdir(parents=True, exist_ok=True)
                export_json.write_text(
                    '{"recoveryMode":"pcode-fallback","decompileAttempted":true,"decompileCompleted":false,'
                    '"analysisNotes":["Fallback could not classify any coherent fields."],"fields":[]}',
                    encoding="utf-8",
                )
                return {"returnCode": 0, "stdoutText": "ok", "stderrText": ""}

            run_headless.side_effect = run_headless_side_effect
            args = SimpleNamespace(
                ghidra_dir=ghidra_dir,
                ghidra_project_dir=project_dir,
                ghidra_project_name="demo",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                analyze=False,
                headless_timeout_seconds=120,
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
            )

            result = export_target(
                {
                    "opcode": 67,
                    "evidence": {"parserTarget": "1400fbba0", "parserName": "FUN_1400fbba0"},
                    "exactCandidateNames": ["IF_OPENSUB_ACTIVE_NPC"],
                },
                args,
                export_root,
            )

        self.assertEqual(result["status"], "export-failed")
        self.assertEqual(result["recoveryMode"], "pcode-fallback")
        self.assertEqual(result["exportedFieldTypes"], [])


if __name__ == "__main__":
    unittest.main()
