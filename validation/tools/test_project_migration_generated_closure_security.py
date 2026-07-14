from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


class GeneratedClosureStatusSecurityTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
