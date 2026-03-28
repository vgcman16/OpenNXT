from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_946_sender_aid import analyze_sender, select_sender_opcodes


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SenderAidTest(unittest.TestCase):
    def test_select_sender_opcodes_prefers_manual_and_handoff_targets(self) -> None:
        unresolved = {17: {}, 48: {}, 83: {}, 113: {}, 200: {}}
        handoff = {
            "suspects": [{"opcode": 113}, {"opcode": 48}],
            "topTargets": [
                {"kind": "client-opcode", "opcode": 113},
                {"kind": "client-opcode", "opcode": 83},
            ],
        }
        selected = select_sender_opcodes(
            handoff_payload=handoff,
            unresolved=unresolved,
            manual_opcodes=[48],
        )
        self.assertEqual(selected[:3], [48, 113, 83])
        self.assertIn(17, selected)

    def test_analyze_sender_reports_missing_sender(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            artifact = analyze_sender(
                opcode=17,
                candidate={"opcode": 17, "size": 4, "suggestedName": "", "familyLabel": ""},
                evidence_entry=None,
                handoff_entry=None,
                world_log=Path(tmpdir) / "missing-world.log",
                ghidra_dir=Path(tmpdir) / "ghidra",
                ghidra_project_dir=Path(tmpdir) / "project",
                ghidra_project_name="missing",
                ghidra_scripts=Path(tmpdir) / "scripts",
                program_name="rs2client.exe",
                decomp_log_dir=Path(tmpdir) / "fallback",
                ghidra_clone_root=Path(tmpdir) / "clones",
                keep_ghidra_clone=False,
                output_dir=Path(tmpdir) / "out",
            )
        self.assertEqual(artifact["status"], "missing-sender")
        self.assertEqual(artifact["errorKind"], "missing-sender")

    def test_analyze_sender_falls_back_to_existing_log_when_project_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            fallback_dir = root / "fallback"
            write_text(
                fallback_dir / "decomp-1400ced60.log",
                "void FUN_1400ced60(void) {\n  GetFocus();\n  return;\n}\n",
            )
            artifact = analyze_sender(
                opcode=113,
                candidate={
                    "opcode": 113,
                    "size": 4,
                    "suggestedName": "",
                    "familyLabel": "",
                    "evidence": {"primarySender": "1400ced60", "primarySenderName": "FUN_1400ced60"},
                },
                evidence_entry=None,
                handoff_entry={"observedCount": 2, "observedStageCounts": {"interfaces": 2}, "samplePreviews": []},
                world_log=root / "missing-world.log",
                ghidra_dir=root / "missing-ghidra",
                ghidra_project_dir=root / "missing-project",
                ghidra_project_name="missing",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                decomp_log_dir=fallback_dir,
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
                output_dir=root / "out",
            )
        self.assertEqual(artifact["status"], "clean")
        self.assertTrue(artifact["usedFallbackLogs"])
        self.assertIn("GetFocus", artifact["decompiledBody"])

    @mock.patch("run_946_sender_aid.cleanup_ghidra_project_clone")
    @mock.patch("run_946_sender_aid.run_headless_postscript")
    @mock.patch("run_946_sender_aid.clone_ghidra_project")
    def test_analyze_sender_uses_clone_and_reports_clean_result(
        self,
        clone_project: mock.Mock,
        run_headless: mock.Mock,
        cleanup_clone: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ghidra_dir = root / "ghidra-home"
            write_text(ghidra_dir / "support" / "analyzeHeadless.bat", "echo headless")
            project_dir = root / "project"
            write_text(project_dir / "demo.gpr", "gpr")
            write_text(project_dir / "demo.rep" / "project.prp", "rep")
            clone_project.return_value = {
                "cloneStrategy": "disposable-project-clone",
                "cloneProjectDir": str(root / "clone-113"),
                "cloneProjectName": "demo",
            }
            run_headless.side_effect = [
                {
                    "returnCode": 0,
                    "stdoutText": "INFO  Function: FUN_1400cec80 @ 1400cec80\nvoid FUN_1400cec80(void) {\n  return;\n}\n",
                    "stderrText": "",
                },
                {
                    "returnCode": 0,
                    "stdoutText": "INFO  DumpCallRefsForTarget.java completed without matching refs\n",
                    "stderrText": "",
                },
                {
                    "returnCode": 0,
                    "stdoutText": "140001000,1400aaaa0,113,4,UNCONDITIONAL_CALL,FUN_140010000,MOV EDX,113,MOV R8,4",
                    "stderrText": "",
                },
            ]
            cleanup_clone.return_value = {"status": "cleaned", "path": str(root / "clone-113"), "error": ""}

            artifact = analyze_sender(
                opcode=113,
                candidate={
                    "opcode": 113,
                    "size": 4,
                    "suggestedName": "",
                    "familyLabel": "",
                    "evidence": {"primarySender": "1400ced60", "primarySenderName": "FUN_1400ced60"},
                },
                evidence_entry=None,
                handoff_entry=None,
                world_log=root / "missing-world.log",
                ghidra_dir=ghidra_dir,
                ghidra_project_dir=project_dir,
                ghidra_project_name="demo",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                decomp_log_dir=root / "fallback",
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
                output_dir=root / "out",
            )

        self.assertEqual(artifact["status"], "clean")
        self.assertEqual(artifact["errorKind"], "")
        self.assertEqual(artifact["cloneStrategy"], "disposable-project-clone")
        self.assertEqual(artifact["cloneCleanupStatus"], "cleaned")
        self.assertEqual(artifact["resolvedFunctionName"], "FUN_1400cec80")
        self.assertEqual(artifact["resolvedFunctionEntry"], "1400cec80")
        self.assertEqual(artifact["callerLookupSource"], "resolved-containing-function")
        self.assertEqual(artifact["callerLookupAddress"], "1400cec80")
        self.assertEqual(len(artifact["callerRefs"]), 1)
        self.assertEqual(run_headless.call_count, 3)

    @mock.patch("run_946_sender_aid.cleanup_ghidra_project_clone")
    @mock.patch("run_946_sender_aid.run_headless_postscript")
    @mock.patch("run_946_sender_aid.clone_ghidra_project")
    def test_analyze_sender_classifies_true_lock_failure(
        self,
        clone_project: mock.Mock,
        run_headless: mock.Mock,
        cleanup_clone: mock.Mock,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            ghidra_dir = root / "ghidra-home"
            write_text(ghidra_dir / "support" / "analyzeHeadless.bat", "echo headless")
            project_dir = root / "project"
            write_text(project_dir / "demo.gpr", "gpr")
            write_text(project_dir / "demo.rep" / "project.prp", "rep")
            clone_project.return_value = {
                "cloneStrategy": "disposable-project-clone",
                "cloneProjectDir": str(root / "clone-113"),
                "cloneProjectName": "demo",
            }
            run_headless.side_effect = [
                {
                    "returnCode": 1,
                    "stdoutText": "ERROR LockException: Unable to lock project!",
                    "stderrText": "",
                },
                {
                    "returnCode": 1,
                    "stdoutText": "ERROR LockException: Unable to lock project!",
                    "stderrText": "",
                },
            ]
            cleanup_clone.return_value = {"status": "cleaned", "path": str(root / "clone-113"), "error": ""}

            artifact = analyze_sender(
                opcode=113,
                candidate={
                    "opcode": 113,
                    "size": 4,
                    "suggestedName": "",
                    "familyLabel": "",
                    "evidence": {"primarySender": "1400ced60", "primarySenderName": "FUN_1400ced60"},
                },
                evidence_entry=None,
                handoff_entry=None,
                world_log=root / "missing-world.log",
                ghidra_dir=ghidra_dir,
                ghidra_project_dir=project_dir,
                ghidra_project_name="demo",
                ghidra_scripts=root / "scripts",
                program_name="rs2client.exe",
                decomp_log_dir=root / "fallback",
                ghidra_clone_root=root / "clones",
                keep_ghidra_clone=False,
                output_dir=root / "out",
            )

        self.assertEqual(artifact["status"], "error-only")
        self.assertEqual(artifact["errorKind"], "project-lock")


if __name__ == "__main__":
    unittest.main()
