from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3, canonical_rust_project_ir_v3_bytes,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    module_id_for_target_candidate,
)
from validation.tools._project_migration_harness.rust_project_ir_validation import (
    validate_rust_project_ir,
)


BUILD_SHA = "b" * 64
CANDIDATE_SHA = "c" * 64
BINDING_SHA = "d" * 64


def _ref(path: str, digest: str) -> dict:
    return {"path": path, "sha256": digest, "size_bytes": 1}


def _evidence() -> dict:
    return {
        "build_ir_sha256s": [BUILD_SHA],
        "dag_unit_ids": ["group-a"],
        "candidate_sha256s": [CANDIDATE_SHA],
    }


def _input(**changes: object) -> dict:
    module_id = module_id_for_target_candidate(
        "namespace-a", "group-a", CANDIDATE_SHA, ["source-a"],
    )
    values = {
        "migration_dag_ref": _ref("plan/dag.json", "a" * 64),
        "migration_graph_ref": _ref("plan/graph.json", "e" * 64),
        "build_ir_refs": [_ref("plan/build-ir.json", BUILD_SHA)],
        "candidate_refs": [{
            "unit_id": "group-a", "artifact_id": "candidate-a",
            "source": _ref("candidates/a.rs", CANDIDATE_SHA),
        }],
        "workspace": {
            "workspace_id": "workspace-a", "resolver": "2",
            "package_ids": ["package-a"],
            "default_package_ids": ["package-a"], "evidence": _evidence(),
        },
        "packages": [{
            "package_id": "package-a", "name": "package_a",
            "build_ir_target_id": "archive-a", "product_kind": "static-library",
            "dependency_package_ids": [], "target_ids": ["target-a"],
            "module_ids": [module_id], "evidence": _evidence(),
        }],
        "targets": [{
            "target_id": "target-a", "package_id": "package-a",
            "name": "target_a", "kind": "lib",
            "crate_types": ["staticlib", "rlib"],
            "build_ir_target_id": "archive-a", "module_ids": [module_id],
            "input_occurrences": [
                {"ordinal": 0, "role": "archive-input",
                 "dependency_target_id": None, "binding_sha256": BINDING_SHA},
                {"ordinal": 1, "role": "archive-input",
                 "dependency_target_id": None, "binding_sha256": BINDING_SHA},
            ],
            "ordered_link_arguments": ["-lm", "-lm"], "evidence": _evidence(),
        }],
        "modules": [{
            "module_id": module_id, "package_id": "package-a",
            "target_id": "target-a", "target_namespace_id": "namespace-a",
            "rust_path": f"packages/package-a/src/{module_id}.rs",
            "unit_id": "group-a", "source_unit_ids": ["source-a"],
            "candidate_sha256": CANDIDATE_SHA, "visibility": "crate",
            "evidence": _evidence(),
        }],
    }
    values.update(changes)
    return values


class RustProjectIRV3BuilderTests(unittest.TestCase):
    def test_builder_preserves_occurrence_and_link_argument_order(self) -> None:
        value = build_rust_project_ir_v3(**_input())

        self.assertEqual([0, 1], [
            item["ordinal"] for item in value["targets"][0]["input_occurrences"]
        ])
        self.assertEqual(
            [BINDING_SHA, BINDING_SHA],
            [item["binding_sha256"]
             for item in value["targets"][0]["input_occurrences"]],
        )
        self.assertEqual(["-lm", "-lm"], value["targets"][0]["ordered_link_arguments"])
        self.assertEqual("ready", value["topology_status"])
        self.assertFalse(value["claim_boundary"]["semantic_gate"])
        self.assertEqual(0, value["claim_boundary"]["translation_coverage_numerator"])

    def test_generic_validator_dispatches_v3_and_bytes_are_canonical(self) -> None:
        value = build_rust_project_ir_v3(**_input())

        validate_rust_project_ir(value)
        self.assertIn(b'"schema_version": 3', canonical_rust_project_ir_v3_bytes(value))

    def test_builder_canonicalizes_set_like_fields_only(self) -> None:
        values = _input()
        values["targets"][0]["crate_types"] = ["staticlib", "rlib"]
        value = build_rust_project_ir_v3(**values)

        self.assertEqual(["rlib", "staticlib"], value["targets"][0]["crate_types"])
        self.assertEqual(["-lm", "-lm"], value["targets"][0]["ordered_link_arguments"])

    def test_invalid_occurrence_order_fails_closed(self) -> None:
        values = _input()
        values["targets"][0]["input_occurrences"][1]["ordinal"] = 2

        with self.assertRaisesRegex(ValueError, "occurrences are not canonical"):
            build_rust_project_ir_v3(**values)

    def test_structured_blocker_sets_blocked_without_semantic_credit(self) -> None:
        value = build_rust_project_ir_v3(**_input(topology_blockers=[{
            "code": "entrypoint-unproven", "entity_kind": "target",
            "entity_id": "target-a",
        }]))

        self.assertEqual("blocked", value["topology_status"])
        self.assertEqual(0, value["claim_boundary"]["translation_coverage_numerator"])

    def test_hash_drift_is_rejected(self) -> None:
        value = build_rust_project_ir_v3(**_input())
        forged = copy.deepcopy(value)
        forged["targets"][0]["ordered_link_arguments"].append("-lpthread")

        with self.assertRaisesRegex(ValueError, "interface hash drifted"):
            validate_rust_project_ir(forged)


if __name__ == "__main__":
    unittest.main()
