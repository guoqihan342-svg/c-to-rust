from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.closure_paths import (
    bind_repository_artifact,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


class GeneratedClosureStatusSecurityTests(unittest.TestCase):
    def symlink_or_skip(
        self,
        link: Path,
        target: str | Path,
        *,
        target_is_directory: bool = False,
    ) -> None:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except (NotImplementedError, OSError) as error:
            self.skipTest(f"symbolic links unavailable: {error}")

    def test_reopen_rejects_forged_blocked_status_without_blockers(self) -> None:
        closure = {
            "status": "blocked",
            "blockers": [],
            "compile_database": None,
            "generated_stage_facts": None,
            "target_link_closure": None,
        }

        verification = verify_generated_build_closure(Path.cwd(), closure)

        self.assertEqual("blocked", verification["status"])
        self.assertIn("generated_closure_status_mismatch", {
            item["kind"] for item in verification["blockers"]
        })

    def test_reopen_rejects_forged_outer_ready_status(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-status-") as temporary:
            root = Path(temporary)
            source = root / "src/unit.c"
            source.parent.mkdir()
            source.write_text("int unit(void) { return 1; }\n", encoding="utf-8")
            build = root / "build"
            (build / "CMakeFiles/app.dir").mkdir(parents=True)
            (build / "unit.o").write_bytes(b"object")
            (build / "CMakeFiles/app.dir/link.txt").write_text(
                "clang unit.o -o app\n", encoding="utf-8",
            )
            database = build / "compile_commands.json"
            database.write_text(json.dumps([{
                "directory": str(build),
                "file": str(source),
                "arguments": ["clang", "-c", str(source), "-o", "unit.o"],
                "output": "unit.o",
            }]), encoding="utf-8")
            closure = discover_project(
                root, compile_database=database,
            )["generated_build_closure"]
            self.assertEqual("blocked", closure["status"])
            closure["status"] = "ready"
            closure["blockers"] = []

            verification = verify_generated_build_closure(root, closure)

            self.assertEqual("blocked", verification["status"])
            self.assertIn("generated_closure_status_mismatch", {
                item["kind"] for item in verification["blockers"]
            })

    def test_directory_binding_rejects_absolute_internal_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-link-absolute-") as temporary:
            root = Path(temporary)
            bound = root / "bound"
            bound.mkdir()
            target = bound / "target.h"
            target.write_text("inside\n", encoding="utf-8")
            self.symlink_or_skip(bound / "alias.h", target.resolve())

            with self.assertRaisesRegex(ValueError, "linked_path_component"):
                bind_repository_artifact(root, "bound", kind="directory")

    def test_directory_binding_rejects_relative_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-link-escape-") as temporary:
            root = Path(temporary)
            bound = root / "bound"
            bound.mkdir()
            (root / "outside.h").write_text("outside\n", encoding="utf-8")
            self.symlink_or_skip(bound / "alias.h", "../outside.h")

            with self.assertRaisesRegex(ValueError, "linked_path_component"):
                bind_repository_artifact(root, "bound", kind="directory")

    def test_directory_binding_rejects_dangling_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-link-dangling-") as temporary:
            root = Path(temporary)
            bound = root / "bound"
            bound.mkdir()
            self.symlink_or_skip(bound / "alias.h", "missing.h")

            with self.assertRaisesRegex(ValueError, "linked_path_component"):
                bind_repository_artifact(root, "bound", kind="directory")

    def test_directory_binding_rejects_symlink_chain_cycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-link-cycle-") as temporary:
            root = Path(temporary)
            bound = root / "bound"
            bound.mkdir()
            self.symlink_or_skip(bound / "first", "second")
            self.symlink_or_skip(bound / "second", "first")

            with self.assertRaisesRegex(ValueError, "linked_path_component"):
                bind_repository_artifact(root, "bound", kind="directory")

    def test_directory_binding_rejects_directory_alias_cycle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-link-dir-cycle-") as temporary:
            root = Path(temporary)
            bound = root / "bound"
            child = bound / "child"
            child.mkdir(parents=True)
            self.symlink_or_skip(
                child / "back", "..", target_is_directory=True
            )

            with self.assertRaisesRegex(ValueError, "linked_path_component"):
                bind_repository_artifact(root, "bound", kind="directory")

    def test_file_binding_still_rejects_internal_relative_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="closure-file-link-") as temporary:
            root = Path(temporary)
            target = root / "target.o"
            target.write_bytes(b"object")
            self.symlink_or_skip(root / "alias.o", "target.o")

            with self.assertRaisesRegex(ValueError, "linked_path_component"):
                bind_repository_artifact(root, "alias.o", kind="file")


if __name__ == "__main__":
    unittest.main()
