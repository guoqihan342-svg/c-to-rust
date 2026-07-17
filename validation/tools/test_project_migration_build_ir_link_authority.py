from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_SCHEMA_VERSION, LEGACY_BUILD_IR_EXTRACTOR,
    LEGACY_BUILD_IR_SCHEMA_VERSION, finalize_build_ir,
)
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError, validate_build_ir, verify_build_ir_artifact,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)
from validation.tools._project_migration_harness.link_closure_schema import (
    reopen_discovered_link_closure,
)


class BuildIRLinkAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="build-ir-link-authority-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "project"
        self.root.mkdir()
        self._write("CMakeLists.txt", "add_executable(sample src/unit.c)\n")
        self._write("src/unit.c", "int main(void) { return 0; }\n")
        self._write("build/unit.o", b"object")
        self._write("build/program", b"program")
        (self.root / "build/lib").mkdir()
        self._write(
            "build/CMakeFiles/sample.dir/link.txt",
            "clang unit.o -L lib -lm -o program\n",
        )
        self.database = self._write(
            "build/compile_commands.json",
            json.dumps([{
                "directory": str(self.root), "file": "src/unit.c",
                "arguments": [
                    "clang", "-c", "src/unit.c", "-o", "build/unit.o",
                ],
                "output": "build/unit.o",
            }]),
        )

    def test_current_authority_is_required_and_search_roots_are_closed(self) -> None:
        _root, _output, build_ir, _reference = self._materialize("current")

        self.assertEqual(BUILD_IR_EXTRACTOR, build_ir["extractor"])
        self.assertEqual(BUILD_IR_SCHEMA_VERSION, build_ir["schema_version"])
        target = next(item for item in build_ir["targets"] if item["kind"] == "link")
        self.assertIn("ordered_link_occurrences", target)
        self.assertEqual(1, len(target["ordered_link_search_roots"]))
        self.assertEqual([], target["link_response_files"])
        validate_build_ir(build_ir)

        stripped = copy.deepcopy(build_ir)
        stripped_target = next(
            item for item in stripped["targets"] if item["kind"] == "link"
        )
        stripped_target.pop("ordered_link_occurrences")
        stripped_target.pop("ordered_link_search_roots")
        stripped_target.pop("link_response_files")
        with self.assertRaisesRegex(BuildIRValidationError, "authority_scope"):
            validate_build_ir(finalize_build_ir(stripped))

        downgraded = copy.deepcopy(stripped)
        downgraded["schema_version"] = LEGACY_BUILD_IR_SCHEMA_VERSION
        downgraded["extractor"] = dict(LEGACY_BUILD_IR_EXTRACTOR)
        downgraded["claim_boundary"].pop("link_occurrence_authority")
        with self.assertRaisesRegex(BuildIRValidationError, "schema_extractor"):
            validate_build_ir(finalize_build_ir(downgraded))

        provenance_drift = copy.deepcopy(stripped)
        changed_target = next(
            item for item in provenance_drift["targets"] if item["kind"] == "link"
        )
        changed_target["provenance"] = {"raw_fact_role": "discovery"}
        provenance_drift["claim_boundary"].pop("link_occurrence_authority")
        with self.assertRaisesRegex(BuildIRValidationError, "authority_claim"):
            validate_build_ir(finalize_build_ir(provenance_drift))

        kind_drift = copy.deepcopy(stripped)
        changed_target = next(
            item for item in kind_drift["targets"] if item["kind"] == "link"
        )
        changed_target["kind"] = "object"
        kind_drift["claim_boundary"].pop("link_occurrence_authority")
        with self.assertRaisesRegex(BuildIRValidationError, "authority_claim"):
            validate_build_ir(finalize_build_ir(kind_drift))

        drifted = copy.deepcopy(build_ir)
        drifted_target = next(
            item for item in drifted["targets"] if item["kind"] == "link"
        )
        drifted_target["ordered_link_occurrences"] = [
            item for item in drifted_target["ordered_link_occurrences"]
            if item["kind"] != "search-root"
        ]
        for ordinal, item in enumerate(drifted_target["ordered_link_occurrences"]):
            item["ordinal"] = ordinal
        with self.assertRaisesRegex(BuildIRValidationError, "search_root_closure"):
            validate_build_ir(finalize_build_ir(drifted))

    def test_response_file_presence_is_content_bound_in_current_authority(self) -> None:
        self._write("build/link.rsp", "unit.o -L lib -lm\n")
        self._write(
            "build/CMakeFiles/sample.dir/link.txt",
            "clang @link.rsp -o program\n",
        )

        _root, _output, build_ir, _reference = self._materialize("response")

        target = next(item for item in build_ir["targets"] if item["kind"] == "link")
        self.assertEqual(1, len(target["link_response_files"]))
        self.assertEqual(
            {"ordinal", "binding_sha256"}, set(target["link_response_files"][0]),
        )
        self.assertNotIn("path", target["link_response_files"][0])

    def test_explicit_v1_closure_projects_v2_but_runtime_rejects_it(self) -> None:
        discovery = discover_project(self.root, compile_database=self.database)
        current = discovery["generated_build_closure"]
        legacy = copy.deepcopy(current)
        legacy["target_link_closure"] = reopen_discovered_link_closure(
            current["target_link_closure"], {"schema_version": 1},
        )
        legacy_discovery = copy.deepcopy(discovery)
        legacy_discovery["generated_build_closure"] = legacy
        verification = verify_generated_build_closure(self.root, legacy)
        self.assertEqual("verified", verification["status"], verification)
        output = self.base / "legacy-output"
        output.mkdir()
        refs = self._references(output, legacy_discovery, legacy, verification)
        build_ir = project_build_ir(
            legacy_discovery, legacy, verification, refs,
        )
        self.assertEqual(LEGACY_BUILD_IR_EXTRACTOR, build_ir["extractor"])
        self.assertEqual(
            LEGACY_BUILD_IR_SCHEMA_VERSION, build_ir["schema_version"],
        )
        self.assertNotIn(
            "link_occurrence_authority", build_ir["claim_boundary"],
        )
        self.assertFalse(any(
            "ordered_link_occurrences" in target for target in build_ir["targets"]
        ))
        reference = write_json_artifact(output, "plan/build-ir.json", build_ir)
        result = verify_build_ir_artifact(self.root, output, reference)
        self.assertEqual("blocked", result["status"], result)
        self.assertIn("build_ir_schema_extractor_invalid", {
            item["kind"] for item in result["blockers"]
        })

    def _materialize(self, name: str) -> tuple[Path, Path, dict, dict]:
        discovery = discover_project(self.root, compile_database=self.database)
        self.assertEqual("ready", discovery["status"], discovery)
        closure = discovery["generated_build_closure"]
        verification = verify_generated_build_closure(self.root, closure)
        self.assertEqual("verified", verification["status"], verification)
        output = self.base / f"{name}-output"
        output.mkdir()
        refs = self._references(output, discovery, closure, verification)
        build_ir = project_build_ir(discovery, closure, verification, refs)
        reference = write_json_artifact(output, "plan/build-ir.json", build_ir)
        result = verify_build_ir_artifact(self.root, output, reference)
        self.assertEqual("verified", result["status"], result)
        return self.root, output, build_ir, reference

    @staticmethod
    def _references(
        output: Path, discovery: dict, closure: dict, verification: dict,
    ) -> list[dict]:
        return [
            {"role": role, **write_json_artifact(output, path, payload)}
            for role, path, payload in (
                ("discovery", "plan/discovery.json", discovery),
                ("generated-build-closure", "plan/closure.json", closure),
                ("generated-build-closure-verification",
                 "plan/closure-verification.json", verification),
            )
        ]

    def _write(self, relative: str, value: str | bytes) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
