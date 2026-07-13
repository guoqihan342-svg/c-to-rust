from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    write_bytes_artifact,
    write_json_artifact,
)
from validation.tools._project_migration_harness.build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_KIND, BUILD_IR_SCHEMA_VERSION, finalize_build_ir,
)
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
    canonical_rust_project_ir_bytes,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    RustProjectIRError,
    module_id_for_candidate,
    reopen_rust_project_ir_bindings,
    validate_rust_project_ir,
)
def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()
def _ref(label: str, *, path: str) -> dict[str, object]:
    return {"path": path, "sha256": _sha(label), "size_bytes": len(label)}
def _evidence(build_sha: str, unit_id: str, candidate_sha: str) -> dict[str, object]:
    return {
        "build_ir_sha256s": [build_sha],
        "dag_unit_ids": [unit_id],
        "candidate_sha256s": [candidate_sha],
    }
def _valid_build_ir(compiler: str = "clang") -> dict:
    provenance = {"raw_fact_role": "discovery"}
    source = {
        "path": "src/input.c", "kind": "file", "materialized": True,
        "sha256": _sha("c-source"), "size_bytes": 8,
    }
    metadata = {
        "path": "build/compile_commands.json", "kind": "file", "materialized": True,
        "sha256": _sha("compile-db"), "size_bytes": 10,
    }
    output = {"path": "build/input.o", "kind": "file", "materialized": False}
    unit = {
        "unit_id": "translation-unit", "variant_index": 0, "variant_count": 1,
        "source": source, "working_directory": ".", "compiler": compiler,
        "compiler_wrappers": [], "language": "c", "toolchain_id": "toolchain-clang",
        "includes": [], "defines": [], "redacted_define_count": 0,
        "compile_arguments": {
            "semantic_flags": [], "expanded_argv_sha256": _sha("argv"),
            "response_files": [],
        },
        "output": output, "provenance": provenance,
    }
    raw_refs = [
        {"role": role, "path": f"facts/{index}.json", "sha256": _sha(role),
         "size_bytes": index + 1}
        for index, role in enumerate((
            "discovery", "generated-build-closure",
            "generated-build-closure-verification",
        ))
    ]
    return finalize_build_ir({
        "schema_version": BUILD_IR_SCHEMA_VERSION, "artifact_kind": BUILD_IR_KIND,
        "status": "ready", "extractor": dict(BUILD_IR_EXTRACTOR),
        "raw_fact_refs": raw_refs, "build_metadata": [metadata],
        "translation_units": [unit], "source_inputs": [source],
        "generated_inputs": [], "targets": [], "target_closure": [],
        "toolchains": [], "external_dependencies": [],
        "abi_facts": [{"unit_id": "translation-unit", "provenance": provenance}],
        "boundaries": [], "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    })
def _bound_payload(
    root: Path, dag: dict, build_ir: dict | None = None, *, include_module: bool = True,
    extra_build_ir: bool = False,
) -> dict:
    dag_ref = write_json_artifact(root, "facts/migration-dag.json", dag)
    build_ref = write_json_artifact(
        root, "facts/build-ir.json", build_ir or _valid_build_ir(),
    )
    build_refs = [build_ref]
    if extra_build_ir:
        build_refs.append(write_json_artifact(root, "facts/build-ir-extra.json",
                                              _valid_build_ir("other-cc")))
    source = write_bytes_artifact(root, "candidates/unit.rs", b"pub fn value() {}\n")
    module_id = module_id_for_candidate(source["sha256"])
    evidence = _evidence(build_ref["sha256"], "u", source["sha256"])
    return build_rust_project_ir(
        migration_dag_ref=dag_ref, build_ir_refs=build_refs,
        candidate_refs=[{"unit_id": "u", "artifact_id": "candidate-u", "source": source}],
        crate={"crate_id": "crate-u", "edition": "2021", "crate_types": ["rlib"],
               "root_module_id": module_id, "targets": ["library"], "evidence": evidence},
        modules=([{"module_id": module_id, "parent_module_id": None,
                   "rust_path": "src/lib.rs", "unit_id": "u",
                   "candidate_sha256": source["sha256"], "visibility": "crate",
                   "evidence": evidence}] if include_module else []),
    )
def _base_input(*, left_unit: str = "unit-left", right_unit: str = "unit-right") -> dict:
    build = _ref("build", path="facts/build-ir.json")
    left_sha, right_sha = _sha("left"), _sha("right")
    left_module = module_id_for_candidate(left_sha)
    right_module = module_id_for_candidate(right_sha)
    candidates = [
        {"unit_id": left_unit, "artifact_id": "candidate-left",
         "source": {"path": "candidates/left.rs", "sha256": left_sha, "size_bytes": 4}},
        {"unit_id": right_unit, "artifact_id": "candidate-right",
         "source": {"path": "candidates/right.rs", "sha256": right_sha, "size_bytes": 5}},
    ]
    modules = [
        {"module_id": left_module, "parent_module_id": None, "rust_path": "src/lib.rs",
         "unit_id": left_unit, "candidate_sha256": left_sha, "visibility": "crate",
         "evidence": _evidence(build["sha256"], left_unit, left_sha)},
        {"module_id": right_module, "parent_module_id": left_module,
         "rust_path": f"src/{right_module}.rs", "unit_id": right_unit,
         "candidate_sha256": right_sha, "visibility": "private",
         "evidence": _evidence(build["sha256"], right_unit, right_sha)},
    ]
    crate_evidence = {
        "build_ir_sha256s": [build["sha256"]],
        "dag_unit_ids": sorted([left_unit, right_unit]),
        "candidate_sha256s": sorted([left_sha, right_sha]),
    }
    return {
        "migration_dag_ref": _ref("dag", path="facts/migration-dag.json"),
        "build_ir_refs": [build], "candidate_refs": candidates,
        "crate": {"crate_id": "crate-content-bound", "edition": "2021",
                  "crate_types": ["rlib"], "root_module_id": left_module,
                  "targets": ["library"], "evidence": crate_evidence},
        "modules": modules,
        "public_api": [{
            "declaration_id": "api-value", "module_id": left_module,
            "symbol": "value", "kind": "function", "signature": "fn()->i32",
            "visibility": "public", "evidence": _evidence(build["sha256"], left_unit, left_sha),
        }],
        "shared_types": [], "global_ownership": [], "initialization": [],
        "ffi_boundaries": [], "cfgs": [], "features": [],
        "unsafe_obligations": [{
            "obligation_id": "unsafe-raw-read", "module_id": right_module,
            "kind": "raw-pointer-read", "reason_code": "c-pointer-semantics",
            "source_span": {"path": "candidates/right.rs", "start_line": 1,
                            "start_column": 1, "end_line": 1, "end_column": 4},
            "evidence": _evidence(build["sha256"], right_unit, right_sha),
        }],
    }
class RustProjectIRTests(unittest.TestCase):
    def test_canonical_order_and_unit_rename_preserve_interface_projection(self) -> None:
        original_input = _base_input()
        original = build_rust_project_ir(**original_input)
        shuffled = dict(original_input)
        shuffled["candidate_refs"] = list(reversed(original_input["candidate_refs"]))
        shuffled["modules"] = list(reversed(original_input["modules"]))
        self.assertEqual(
            canonical_rust_project_ir_bytes(original), canonical_rust_project_ir_bytes(
                build_rust_project_ir(**shuffled)),
        )
        renamed = build_rust_project_ir(**_base_input(
            left_unit="opaque-alpha", right_unit="opaque-beta"))
        self.assertNotEqual(original["ir_sha256"], renamed["ir_sha256"])
        self.assertEqual(original["interface_sha256"], renamed["interface_sha256"])
        self.assertNotIn(b"unit-left", canonical_rust_project_ir_bytes(renamed))
    def test_reopens_every_binding_and_rejects_artifact_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rust-project-ir-") as temporary:
            root = Path(temporary)
            payload = _bound_payload(
                root, {"schema_version": 1, "dag": {"u": []}, "dag_order": ["u"]},
            )
            self.assertEqual("domain-bound", reopen_rust_project_ir_bindings(payload, root)["status"])
            for relative in (
                "facts/migration-dag.json", "facts/build-ir.json", "candidates/unit.rs",
            ):
                with self.subTest(relative=relative):
                    path = root / relative
                    original = path.read_bytes()
                    path.write_bytes(original + b" ")
                    with self.assertRaisesRegex(RustProjectIRError, "content drifted"):
                        reopen_rust_project_ir_bindings(payload, root)
                    path.write_bytes(original)
    def test_canonical_invalid_build_ir_and_semantic_drift_fail_closed(self) -> None:
        cases = [("schema", {"schema_version": 1})]
        drifted = _valid_build_ir()
        drifted["translation_units"][0]["compiler"] = "other-compiler"
        cases.append(("semantic", drifted))
        for label, build_ir in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                payload = _bound_payload(
                    Path(temporary),
                    {"schema_version": 1, "dag": {"u": []}, "dag_order": ["u"]},
                    build_ir,
                )
                with self.assertRaisesRegex(RustProjectIRError, "BuildIR validation failed"):
                    reopen_rust_project_ir_bindings(payload, Path(temporary))
    def test_domain_unit_and_evidence_coverage_fail_closed(self) -> None:
        cases = [
            ("unknown-unit", {"schema_version": 1, "dag": {"other": []},
                              "dag_order": ["other"]}, "candidate units", {}),
            ("unknown-dependency", {"schema_version": 1, "dag": {"u": ["missing"]},
                                    "dag_order": ["u"]}, "dependency closure", {}),
            ("missing-module", {"schema_version": 1, "dag": {"u": []},
                                "dag_order": ["u"]}, "module units",
             {"include_module": False}),
            ("uncovered-build-ir", {"schema_version": 1, "dag": {"u": []},
                                     "dag_order": ["u"]}, "evidence does not cover",
             {"extra_build_ir": True}),
        ]
        for label, dag, message, options in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = _bound_payload(root, dag, **options)
                with self.assertRaisesRegex(RustProjectIRError, message):
                    reopen_rust_project_ir_bindings(payload, root)
    def test_ir_field_drift_is_rejected_before_coordination(self) -> None:
        payload = build_rust_project_ir(**_base_input())
        payload["public_api"][0]["signature"] = "fn()->u64"
        with self.assertRaisesRegex(RustProjectIRError, "hash drifted"):
            validate_rust_project_ir(payload)
        with self.assertRaises(RustProjectIRError):
            coordinate_project_interfaces(payload)
    def test_clean_coordination_is_candidate_only(self) -> None:
        result = coordinate_project_interfaces(build_rust_project_ir(**_base_input()))
        self.assertEqual("candidate-ready", result["status"])
        self.assertEqual([], result["diagnostics"])
        self.assertEqual([], result["project_repair_queue"]["items"])
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertFalse(result["claim_boundary"]["semantic_pass"])
    def test_conflicts_enter_only_the_bounded_project_repair_queue(self) -> None:
        values = _base_input()
        build_sha = values["build_ir_refs"][0]["sha256"]
        modules = values["modules"]
        left, right = modules[0], modules[1]
        orphan_sha = _sha("orphan")
        orphan = {
            "unit_id": "unit-orphan", "artifact_id": "candidate-orphan",
            "source": {"path": "candidates/orphan.rs", "sha256": orphan_sha, "size_bytes": 6},
        }
        orphan_module = module_id_for_candidate(orphan_sha)
        values["candidate_refs"].append(orphan)
        values["modules"].append({
            "module_id": orphan_module, "parent_module_id": None,
            "rust_path": f"src/{orphan_module}.rs", "unit_id": "unit-orphan",
            "candidate_sha256": orphan_sha, "visibility": "private",
            "evidence": _evidence(build_sha, "unit-orphan", orphan_sha),
        })
        values["crate"]["evidence"] = {
            "build_ir_sha256s": [build_sha],
            "dag_unit_ids": ["unit-left", "unit-orphan", "unit-right"],
            "candidate_sha256s": sorted([
                left["candidate_sha256"], right["candidate_sha256"], orphan_sha,
            ]),
        }
        values["public_api"].append({
            "declaration_id": "api-value-conflict", "module_id": right["module_id"],
            "symbol": "value", "kind": "function", "signature": "fn()->u64",
            "visibility": "public",
            "evidence": _evidence(build_sha, "unit-right", right["candidate_sha256"]),
        })
        values["shared_types"] = [
            {"declaration_id": "type-left", "module_id": left["module_id"],
             "name": "Shared", "kind": "struct", "layout_sha256": _sha("layout-a"),
             "repr": "C", "evidence": _evidence(build_sha, "unit-left", left["candidate_sha256"])},
            {"declaration_id": "type-right", "module_id": right["module_id"],
             "name": "Shared", "kind": "struct", "layout_sha256": _sha("layout-b"),
             "repr": "C", "evidence": _evidence(build_sha, "unit-right", right["candidate_sha256"])},
        ]
        values["initialization"] = [
            {"init_id": "init-left", "module_id": left["module_id"], "function": "init_a",
             "phase": "startup", "after": ["init-right"],
             "evidence": _evidence(build_sha, "unit-left", left["candidate_sha256"])},
            {"init_id": "init-right", "module_id": right["module_id"], "function": "init_b",
             "phase": "startup", "after": ["init-left"],
             "evidence": _evidence(build_sha, "unit-right", right["candidate_sha256"])},
            {"init_id": "init-tail", "module_id": right["module_id"], "function": "init_c",
             "phase": "startup", "after": ["init-left"],
             "evidence": _evidence(build_sha, "unit-right", right["candidate_sha256"])},
        ]
        result = coordinate_project_interfaces(build_rust_project_ir(**values), max_repairs=3)
        codes = {item["code"] for item in result["diagnostics"]}
        self.assertTrue({
            "conflicting_public_api", "conflicting_shared_type",
            "cyclic_initialization", "orphan_module",
        } <= codes)
        cycle = next(item for item in result["diagnostics"] if item["code"] == "cyclic_initialization")
        self.assertNotIn("init-tail", cycle["entity_ids"])
        queue = result["project_repair_queue"]
        self.assertEqual(3, queue["item_count"])
        self.assertGreater(queue["overflow_count"], 0)
        self.assertTrue(all(item["assigned_unit_id"] is None for item in queue["items"]))
        self.assertFalse(queue["policy"]["generated_glue_allowed"])
        self.assertFalse(result["claim_boundary"]["semantic_pass"])
        self.assertNotIn("source", result)
if __name__ == "__main__":
    unittest.main()
