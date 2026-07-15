from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import (
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_facts import file_binding
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    verify_build_ir_artifact,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_build_ir import (
    reopen_build_ir_compile_database, stable_unit_key,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)


class C2RustProjectBaselineBuildIRTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="c2rust-build-ir-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.repo = self.base / "repo"
        self.artifacts = self.base / "artifacts"
        (self.repo / "src").mkdir(parents=True)
        (self.repo / "include").mkdir()
        (self.repo / "build/CMakeFiles/program.dir").mkdir(parents=True)
        self._write("CMakeLists.txt", "add_executable(program src/unit.c)\n")
        self._write("src/unit.c", "int unit(void) { return MODE; }\n")
        self._write("src/other.c", "int other(void) { return 0; }\n")
        self._write("include/config.h", "#define CONFIG 1\n")
        self._write("debug.rsp", "-Iinclude -DMODE=1 -std=c11 -O0\n")
        self._write("other.rsp", "-Iinclude -DMODE=9 -std=c11\n")
        self._write("build/debug.o", b"debug-object")
        self._write("build/release.o", b"release-object")
        self._write("build/program", b"linked-program")
        self._write(
            "build/CMakeFiles/program.dir/link.txt",
            "clang build/debug.o build/release.o -o build/program\n",
        )
        self.entries = [
            self._entry(
                ["clang", "@debug.rsp", "-c", "src/unit.c", "-o", "build/debug.o"],
                "build/debug.o",
            ),
            self._entry(
                [
                    "clang", "-Iinclude", "-DMODE=2", "-std=c17", "-O3",
                    "-c", "src/unit.c", "-o", "build/release.o",
                ],
                "build/release.o",
            ),
        ]
        self.database = self.repo / "build/compile_commands.json"
        self.database.write_text(json.dumps(self.entries), encoding="utf-8")

    def test_same_source_variants_get_independent_bound_databases(self) -> None:
        reference = self._materialize()

        with patch("subprocess.Popen") as process:
            reopened = self._reopen(reference)

        self.assertFalse(process.called)
        self.assertEqual(file_binding(self.repo, self.database), reopened.database_binding)
        self.assertEqual(
            reopened.semantic_sha256,
            reopened.build_ir_payload()["semantic_sha256"],
        )
        self.assertEqual(2, len(reopened.units))
        self.assertEqual({0, 1}, {unit.entry_index for unit in reopened.units})
        self.assertEqual(2, len({unit.unit_key for unit in reopened.units}))
        self.assertEqual(2, len({unit.database_binding["path"] for unit in reopened.units}))
        for unit in reopened.units:
            with self.subTest(entry_index=unit.entry_index):
                self.assertEqual([self.entries[unit.entry_index]], unit.database_payload())
                self.assertEqual(
                    hashlib.sha256(unit.database_bytes).hexdigest(),
                    unit.database_binding["sha256"],
                )
                self.assertEqual(len(unit.database_bytes), unit.database_binding["size_bytes"])
                self.assertNotIn(unit.unit_id, unit.database_binding["path"])
                self.assertEqual(
                    "compile_commands.json",
                    PurePosixPath(unit.database_binding["path"]).name,
                )

    def test_metadata_and_database_content_drift_fail_closed(self) -> None:
        alternate = self.repo / "build/alternate-compile-commands.json"
        alternate.write_bytes(self.database.read_bytes())

        def metadata_drift(discovery: dict) -> None:
            discovery["compile_database"].update(file_binding(self.repo, alternate))

        reference = self._materialize(metadata_drift)
        self._assert_blocked(reference, "compile_database_binding_mismatch")

        reference = self._materialize()
        self.database.write_bytes(self.database.read_bytes() + b"\n")
        self._assert_blocked(reference, "verification_failed")

    def test_entry_index_and_hash_drift_fail_closed(self) -> None:
        cases = (
            (
                "entry_index_invalid",
                lambda discovery: self._unit(discovery, 0)["entry"].update(index=99),
            ),
            (
                "entry_sha256_mismatch",
                lambda discovery: self._unit(discovery, 0)["entry"].update(
                    sha256="0" * 64,
                ),
            ),
        )
        for code, mutate in cases:
            with self.subTest(code=code):
                reference = self._materialize(mutate)
                self._assert_blocked(reference, code)

    def test_compile_facts_are_reparsed_from_the_selected_entry(self) -> None:
        def source_drift(discovery: dict) -> None:
            self._unit(discovery, 0)["source"] = file_binding(
                self.repo, self.repo / "src/other.c",
            )

        def output_drift(discovery: dict) -> None:
            self._unit(discovery, 0)["output"] = "build/other.o"

        def working_directory_drift(discovery: dict) -> None:
            self._unit(discovery, 0)["working_directory"] = "build"

        def argv_drift(discovery: dict) -> None:
            self._unit(discovery, 0)["expanded_argv_sha256"] = "f" * 64

        def response_drift(discovery: dict) -> None:
            self._unit(discovery, 0)["response_files"] = [
                file_binding(self.repo, self.repo / "other.rsp"),
            ]

        cases = (
            ("source_mismatch", source_drift),
            ("working_directory_mismatch", working_directory_drift),
            ("output_mismatch", output_drift),
            ("expanded_argv_mismatch", argv_drift),
            ("response_files_mismatch", response_drift),
        )
        for code, mutate in cases:
            with self.subTest(code=code):
                reference = self._materialize(mutate)
                self._assert_blocked(reference, code)

    def test_malicious_unit_id_is_never_a_path_component(self) -> None:
        malicious = "../../outside\\payload:C:/tmp/owned"

        first = stable_unit_key(malicious)
        second = stable_unit_key(malicious)
        path = PurePosixPath(f"units/{first}/input/compile_commands.json")

        self.assertEqual(first, second)
        self.assertRegex(first, r"\A[0-9a-f]{64}\Z")
        self.assertNotIn(malicious, path.as_posix())
        self.assertNotIn("..", path.parts)
        self.assertNotIn("\\", path.as_posix())
        self.assertNotIn(":", path.as_posix())

    def _materialize(self, mutate=None) -> dict:
        discovery = discover_project(self.repo, compile_database=self.database)
        self.assertEqual("ready", discovery["status"], discovery)
        if mutate is not None:
            mutate(discovery)
        closure = discovery["generated_build_closure"]
        closure_verification = verify_generated_build_closure(self.repo, closure)
        refs = []
        for role, relative, payload in (
            ("discovery", "plan/discovery.json", discovery),
            ("generated-build-closure", "plan/closure.json", closure),
            ("generated-build-closure-verification", "plan/closure-verification.json",
             closure_verification),
        ):
            refs.append({
                "role": role,
                **write_json_artifact(self.artifacts, relative, payload),
            })
        build_ir = project_build_ir(
            discovery, closure, closure_verification, refs,
        )
        reference = write_json_artifact(
            self.artifacts, "plan/build-ir.json", build_ir,
        )
        verification = verify_build_ir_artifact(
            self.repo, self.artifacts, reference,
        )
        self.assertEqual("verified", verification["status"], verification)
        return reference

    def _reopen(self, reference: dict):
        return reopen_build_ir_compile_database(
            repo_root=self.repo, artifact_root=self.artifacts,
            build_ir_reference=reference, compile_database=self.database,
        )

    def _assert_blocked(self, reference: dict, code: str) -> None:
        with patch("subprocess.Popen") as process:
            with self.assertRaisesRegex(ValueError, f"c2rust_build_ir_{code}"):
                self._reopen(reference)
        self.assertFalse(process.called)

    def _entry(self, arguments: list[str], output: str) -> dict:
        return {
            "directory": str(self.repo),
            "file": str(self.repo / "src/unit.c"),
            "arguments": arguments,
            "output": output,
        }

    @staticmethod
    def _unit(discovery: dict, entry_index: int) -> dict:
        return next(
            unit for unit in discovery["translation_units"]
            if unit["entry"]["index"] == entry_index
        )

    def _write(self, relative: str, value: str | bytes) -> Path:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
