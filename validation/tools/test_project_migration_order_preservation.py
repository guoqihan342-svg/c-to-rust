from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_ir_projection import project_build_ir
from validation.tools._project_migration_harness.build_ir_validation import validate_build_ir
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


class ProjectMigrationOrderPreservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="build-order-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    @staticmethod
    def _write(root: Path, relative: str, value: str | bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path

    def _materialize(
        self,
        name: str,
        kind: str,
        member_order: list[str],
        *,
        search_roots: list[str] | None = None,
    ) -> tuple[dict, dict, dict]:
        root = self.base / name
        root.mkdir()
        for stem in ("left", "right"):
            self._write(root, f"src/{stem}.c", f"int {stem}(void) {{ return 1; }}\n")
            self._write(root, f"build/{stem}.o", f"object-{stem}".encode())
        for search_root in search_roots or []:
            (root / "build" / search_root).mkdir(parents=True, exist_ok=True)

        output = "program.bin" if kind == "link" else "libsample.a"
        self._write(root, f"build/{output}", f"output-{kind}".encode())
        members = " ".join(member_order)
        if kind == "link":
            roots = " ".join(f"-L{value}" for value in search_roots or [])
            command = f"clang {members} {roots} -o {output}\n"
            cmake = "add_executable(sample src/left.c src/right.c)\n"
            target_kind = "link"
        elif kind == "archive":
            command = f"ar qc {output} {members}\n"
            cmake = "add_library(sample STATIC src/left.c src/right.c)\n"
            target_kind = "archive"
        else:
            raise ValueError("unsupported order fixture kind")
        self._write(root, "CMakeLists.txt", cmake)
        self._write(root, "build/CMakeFiles/sample.dir/link.txt", command)

        entries = []
        for stem in ("left", "right"):
            entries.append({
                "directory": str(root),
                "file": f"src/{stem}.c",
                "arguments": [
                    "clang", "-c", f"src/{stem}.c", "-o", f"build/{stem}.o",
                ],
                "output": f"build/{stem}.o",
            })
        database = self._write(
            root, "build/compile_commands.json", json.dumps(entries),
        )

        discovery = discover_project(root, compile_database=database)
        self.assertEqual("ready", discovery["status"], discovery)
        closure = discovery["generated_build_closure"]
        verification = verify_generated_build_closure(root, closure)
        self.assertEqual("verified", verification["status"], verification)

        evidence_root = self.base / f"{name}-evidence"
        evidence_root.mkdir()
        refs = []
        for role, relative, payload in (
            ("discovery", "plan/discovery.json", discovery),
            ("generated-build-closure", "plan/generated-build-closure.json", closure),
            ("generated-build-closure-verification", "plan/closure-verification.json",
             verification),
        ):
            refs.append({"role": role, **write_json_artifact(
                evidence_root, relative, payload,
            )})
        build_ir = project_build_ir(discovery, closure, verification, refs)
        validate_build_ir(build_ir)

        closure_target = closure["target_link_closure"]["targets"][0]
        build_target = next(
            item for item in build_ir["targets"] if item["kind"] == target_kind
        )
        for artifact in (closure, build_ir):
            self.assertIs(False, artifact["claim_boundary"]["semantic_gate"])
            self.assertEqual(
                0, artifact["claim_boundary"]["translation_coverage_numerator"],
            )
        return closure_target, build_target, build_ir

    @staticmethod
    def _closure_paths(target: dict) -> list[str]:
        return [item["path"] for item in target["inputs"]]

    @staticmethod
    def _build_paths(target: dict) -> list[str]:
        return [item["binding"]["path"] for item in target["ordered_inputs"]]

    def test_link_and_archive_order_are_identity_independent(self) -> None:
        forward = ["right.o", "left.o"]
        reverse = list(reversed(forward))
        expected_forward = ["build/right.o", "build/left.o"]
        expected_reverse = list(reversed(expected_forward))

        for kind in ("link", "archive"):
            with self.subTest(kind=kind):
                first = self._materialize(f"{kind}-identity-a", kind, forward)
                renamed = self._materialize(f"{kind}-identity-b", kind, forward)
                reordered = self._materialize(f"{kind}-identity-c", kind, reverse)

                self.assertEqual(expected_forward, self._closure_paths(first[0]))
                self.assertEqual(expected_forward, self._build_paths(first[1]))
                self.assertEqual(expected_forward, self._closure_paths(renamed[0]))
                self.assertEqual(expected_forward, self._build_paths(renamed[1]))
                self.assertEqual(first[2]["semantic_sha256"], renamed[2]["semantic_sha256"])
                self.assertEqual(expected_reverse, self._closure_paths(reordered[0]))
                self.assertEqual(expected_reverse, self._build_paths(reordered[1]))
                self.assertNotEqual(first[0]["argv_sha256"], reordered[0]["argv_sha256"])
                self.assertNotEqual(first[2]["semantic_sha256"], reordered[2]["semantic_sha256"])

    def test_repeated_link_inputs_and_search_roots_are_not_discarded(self) -> None:
        closure, target, _build_ir = self._materialize(
            "link-repeated",
            "link",
            ["right.o", "left.o", "right.o"],
            search_roots=["lib-right", "lib-left", "lib-right"],
        )

        expected = ["build/right.o", "build/left.o", "build/right.o"]
        self.assertEqual(expected, self._closure_paths(closure))
        self.assertEqual(expected, self._build_paths(target))
        self.assertEqual([0, 1, 2], [item["ordinal"] for item in target["ordered_inputs"]])
        self.assertEqual(
            ["build/lib-right", "build/lib-left", "build/lib-right"],
            [item["path"] for item in closure["search_roots"]],
        )

    def test_repeated_archive_members_are_not_discarded(self) -> None:
        closure, target, _build_ir = self._materialize(
            "archive-repeated",
            "archive",
            ["right.o", "left.o", "right.o"],
        )

        expected = ["build/right.o", "build/left.o", "build/right.o"]
        self.assertEqual(expected, self._closure_paths(closure))
        self.assertEqual(expected, self._build_paths(target))
        self.assertEqual([0, 1, 2], [item["ordinal"] for item in target["ordered_inputs"]])


if __name__ == "__main__":
    unittest.main()
