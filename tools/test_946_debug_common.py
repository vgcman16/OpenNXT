from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protocol_946_debug_common import cleanup_ghidra_project_clone, clone_ghidra_project


def touch(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class DebugCommonCloneTest(unittest.TestCase):
    def test_clone_copies_project_and_skips_lock_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "ghidra"
            touch(project_dir / "demo.gpr", "gpr")
            touch(project_dir / "demo.rep" / "project.prp", "rep")
            touch(project_dir / "demo.rep" / "nested.lock", "lock")
            touch(project_dir / "demo.lock", "lock")
            touch(project_dir / "demo.lock~", "lock")

            clone = clone_ghidra_project(
                project_dir=project_dir,
                project_name="demo",
                clone_root=root / "clones",
                clone_label="opcode-113",
            )

            clone_dir = Path(clone["cloneProjectDir"])
            self.assertTrue((clone_dir / "demo.gpr").exists())
            self.assertTrue((clone_dir / "demo.rep" / "project.prp").exists())
            self.assertFalse((clone_dir / "demo.lock").exists())
            self.assertFalse((clone_dir / "demo.lock~").exists())
            self.assertFalse((clone_dir / "demo.rep" / "nested.lock").exists())

            cleanup = cleanup_ghidra_project_clone(clone)
            self.assertEqual(cleanup["status"], "cleaned")
            self.assertFalse(clone_dir.exists())

    def test_clone_names_are_unique(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            project_dir = root / "ghidra"
            touch(project_dir / "demo.gpr", "gpr")
            touch(project_dir / "demo.rep" / "project.prp", "rep")

            clone_a = clone_ghidra_project(project_dir=project_dir, project_name="demo", clone_root=root / "clones", clone_label="67")
            clone_b = clone_ghidra_project(project_dir=project_dir, project_name="demo", clone_root=root / "clones", clone_label="67")

            self.assertNotEqual(clone_a["cloneProjectDir"], clone_b["cloneProjectDir"])
            cleanup_ghidra_project_clone(clone_a)
            cleanup_ghidra_project_clone(clone_b)


if __name__ == "__main__":
    unittest.main()
