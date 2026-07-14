from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import write_json_artifact
from validation.tools._project_migration_harness.build_ir import (
    canonical_build_ir_bytes, finalize_build_ir, safe_posix_path,
)
from validation.tools._project_migration_harness.build_ir_projection import project_build_ir
from validation.tools._project_migration_harness.build_ir_validation import (
    validate_build_ir, verify_build_ir_artifact,
)
from validation.tools._project_migration_harness.discovery import discover_project
from validation.tools._project_migration_harness.generated_closure import (
    verify_generated_build_closure,
)
from validation.tools._project_migration_harness.orchestrator import plan_project


class ProjectMigrationBuildIRTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-build-ir-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_empty_normalized_path_fails_closed_without_index_error(self) -> None:
        self.assertFalse(safe_posix_path("."))

    def _write(self, root: Path, relative: str, value: str | bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path

    def _project(self, name: str) -> tuple[Path, Path]:
        root = self.base / name
        root.mkdir()
        self._write(root, "CMakeLists.txt", "add_executable(sample src/unit.c)\n")
        self._write(root, "src/unit.c", "int unit(void) { return VALUE; }\n")
        self._write(root, "build/generated/config.h", "#define VALUE 7\n")
        self._write(root, "build/unit.o", b"object-v1")
        self._write(root, "build/program.bin", b"program-v1")
        self._write(
            root, "build/CMakeFiles/sample.dir/link.txt",
            "clang unit.o -o program.bin -lm\n",
        )
        database = self._write(root, "build/compile_commands.json", json.dumps([{
            "directory": str(root),
            "file": "src/unit.c",
            "arguments": [
                "clang", "-std=c11", "-DVALUE=7", "-Ibuild/generated",
                "-c", "src/unit.c", "-o", "build/unit.o",
            ],
            "output": "build/unit.o",
        }]))
        return root, database

    def _materialize(self, name: str) -> tuple[Path, Path, dict, dict]:
        root, database = self._project(name)
        output = self.base / f"{name}-out"
        output.mkdir()
        discovery = discover_project(root, compile_database=database)
        self.assertEqual("ready", discovery["status"], discovery)
        closure = discovery["generated_build_closure"]
        closure_verification = verify_generated_build_closure(root, closure)
        refs = []
        for role, relative, payload in (
            ("discovery", "plan/discovery.json", discovery),
            ("generated-build-closure", "plan/generated-build-closure.json", closure),
            ("generated-build-closure-verification",
             "plan/generated-build-closure-verification.json", closure_verification),
        ):
            refs.append({"role": role, **write_json_artifact(output, relative, payload)})
        build_ir = project_build_ir(discovery, closure, closure_verification, refs)
        reference = write_json_artifact(output, "plan/build-ir.json", build_ir)
        return root, output, build_ir, reference

    def test_canonical_build_ir_covers_build_semantics_without_raw_adapter_shapes(self) -> None:
        root, output, build_ir, reference = self._materialize("canonical")

        validate_build_ir(build_ir)
        verification = verify_build_ir_artifact(root, output, reference)
        encoded = (output / "plan/build-ir.json").read_bytes()

        self.assertEqual("verified", verification["status"], verification)
        self.assertEqual(canonical_build_ir_bytes(build_ir), encoded)
        self.assertEqual("ready", build_ir["status"])
        self.assertEqual(2, len(build_ir["targets"]))
        self.assertEqual(["-lm"], [item["name"] for item in build_ir["external_dependencies"]])
        self.assertEqual("compiler-default", build_ir["abi_facts"][0]["data_model"])
        self.assertNotIn("generated_stage_facts", json.dumps(build_ir))
        self.assertNotIn("meson_introspection", json.dumps(build_ir))
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(), reference["sha256"]
        )

    def test_repository_root_rename_preserves_semantic_projection(self) -> None:
        _root_a, _out_a, first, _ref_a = self._materialize("renamed-a")
        _root_b, _out_b, second, _ref_b = self._materialize("renamed-b")

        self.assertNotEqual(
            first["raw_fact_refs"][0]["sha256"],
            second["raw_fact_refs"][0]["sha256"],
        )
        self.assertEqual(first["semantic_sha256"], second["semantic_sha256"])
        self.assertEqual(first["target_closure"], second["target_closure"])
        self.assertEqual(
            [item["unit_id"] for item in first["translation_units"]],
            [item["unit_id"] for item in second["translation_units"]],
        )

    def test_meson_target_sources_and_dependencies_use_generic_build_ir_shapes(self) -> None:
        root, output, original, _reference = self._materialize("meson-projection")
        generated_path = self._write(
            root, "build/generated/derived.c", "int derived(void) { return 1; }\n"
        )
        generated_raw = generated_path.read_bytes()
        discovery = json.loads((output / "plan/discovery.json").read_text(encoding="utf-8"))
        closure = copy.deepcopy(discovery["generated_build_closure"])
        link_output = closure["target_link_closure"]["targets"][0]["output"]
        closure["generated_stage_facts"]["meson_introspection"] = {
            "status": "ready",
            "targets": [{
                "id": "identity-free-target", "name": "sample", "type": "executable",
                "outputs": [{**link_output, "materialized": True}],
                "target_dependency_ids": [],
                "external_dependency_names": ["threads"],
                "source_groups": [{
                    "kind": "compiler", "language": "c",
                    "compiler_summary": {"sha256": "0" * 64, "item_count": 1},
                    "parameters_summary": {"sha256": "1" * 64, "item_count": 1},
                    "sources": [discovery["translation_units"][0]["source"]],
                    "generated_sources": [{
                        "path": "build/generated/derived.c", "kind": "file",
                        "materialized": True,
                        "sha256": hashlib.sha256(generated_raw).hexdigest(),
                        "size_bytes": len(generated_raw),
                    }],
                }],
            }],
        }
        discovery["generated_build_closure"] = closure
        projected = project_build_ir(
            discovery, closure,
            {"schema_version": 1, "status": "verified", "blockers": []},
            original["raw_fact_refs"],
        )

        validate_build_ir(projected)
        self.assertIn("threads", {
            item["name"] for item in projected["external_dependencies"]
        })
        self.assertIn("build/generated/derived.c", {
            item["binding"]["path"] for item in projected["generated_inputs"]
        })
        executable = next(item for item in projected["targets"]
                          if item["kind"] == "link")
        self.assertFalse(executable["compile_argument_sets"])
        self.assertTrue(executable["provenance"]["meson_source_groups"])

    def test_source_and_build_metadata_drift_fail_closed(self) -> None:
        root, output, _build_ir, reference = self._materialize("input-drift")
        (root / "src/unit.c").write_text("int unit(void) { return 9; }\n", encoding="utf-8")

        source_drift = verify_build_ir_artifact(root, output, reference)

        self.assertEqual("blocked", source_drift["status"])
        self.assertIn("artifact_sha256_drift", {
            item["kind"] for item in source_drift["blockers"]
        })

        root, output, _build_ir, reference = self._materialize("metadata-drift")
        database = root / "build/compile_commands.json"
        database.write_text(database.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        metadata_drift = verify_build_ir_artifact(root, output, reference)
        self.assertEqual("blocked", metadata_drift["status"])
        self.assertIn("build_ir_generated_closure_drift", {
            item["kind"] for item in metadata_drift["blockers"]
        })

    def test_rewritten_projection_and_target_order_are_rejected(self) -> None:
        root, output, build_ir, _reference = self._materialize("projection-drift")
        altered = copy.deepcopy(build_ir)
        altered["toolchains"][0]["identity"] = "caller-reported"
        altered = finalize_build_ir(altered)
        reference = write_json_artifact(output, "plan/build-ir.json", altered)

        projection = verify_build_ir_artifact(root, output, reference)

        self.assertIn("build_ir_projection_drift", {
            item["kind"] for item in projection["blockers"]
        })

        altered = copy.deepcopy(build_ir)
        altered["target_closure"] = list(reversed(altered["target_closure"]))
        altered = finalize_build_ir(altered)
        reference = write_json_artifact(output, "plan/build-ir.json", altered)
        ordered = verify_build_ir_artifact(root, output, reference)
        self.assertIn("build_ir_target_closure_invalid", {
            item["kind"] for item in ordered["blockers"]
        })

        altered = copy.deepcopy(build_ir)
        altered["translation_units"].append(
            copy.deepcopy(altered["translation_units"][0])
        )
        altered = finalize_build_ir(altered)
        reference = write_json_artifact(output, "plan/build-ir.json", altered)
        duplicate = verify_build_ir_artifact(root, output, reference)
        self.assertIn("build_ir_translation_unit_order_invalid", {
            item["kind"] for item in duplicate["blockers"]
        })

    def test_worker_admission_drift_stops_before_dag_and_ledger(self) -> None:
        root, database = self._project("admission")
        harness = self.base / "admission-harness"
        harness.mkdir()
        blocked = {
            "schema_version": 1, "status": "blocked", "build_ir_sha256": None,
            "semantic_sha256": None, "verified_binding_count": 0,
            "blockers": [{"kind": "simulated_build_ir_drift"}],
        }
        with patch(
            "validation.tools._project_migration_harness.orchestrator.verify_build_ir_artifact",
            return_value=blocked,
        ):
            plan = plan_project(
                root, harness_root=harness, out_root="target/run",
                compile_database=database, require_build_closure=True,
            )

        self.assertEqual("blocked", plan["status"])
        self.assertEqual(
            ["build_ir_worker_admission_blocked"], plan["blockers"],
        )
        self.assertNotIn("migration_graph", plan["artifacts"])
        self.assertNotIn("portfolio_dag", plan["artifacts"])
        self.assertFalse((harness / "target/run/harness/assignments").exists())
        self.assertFalse(
            (harness / "target/run/state/project-migration.sqlite3").exists()
        )

    def test_build_ir_contract_failure_records_sanitized_error_code(self) -> None:
        root, database = self._project("contract-error")
        harness = self.base / "contract-error-harness"
        harness.mkdir()
        with patch(
            "validation.tools._project_migration_harness.orchestrator."
            "materialize_selected_build_ir_stage",
            side_effect=ValueError("build_ir_tool_ninja_reopen_blocked"),
        ):
            plan = plan_project(
                root,
                harness_root=harness,
                out_root="target/run",
                compile_database=database,
            )

        self.assertEqual(["build_ir_contract_invalid"], plan["blockers"])
        reference = plan["artifacts"]["build_ir_contract_error"]
        artifact = harness / "target/run" / reference["path"]
        diagnostic = json.loads(artifact.read_text(encoding="utf-8"))
        self.assertEqual("build_ir_tool_ninja_reopen_blocked", diagnostic["kind"])
        self.assertFalse(diagnostic["claim_boundary"]["semantic_gate"])


if __name__ == "__main__":
    unittest.main()
