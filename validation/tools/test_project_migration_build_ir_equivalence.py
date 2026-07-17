from __future__ import annotations

from collections.abc import Mapping
import copy
from pathlib import Path
import tempfile
from typing import Any
import unittest

from validation.tools._project_migration_harness.build_ir import (
    LEGACY_BUILD_IR_EXTRACTOR, LEGACY_BUILD_IR_SCHEMA_VERSION,
    finalize_build_ir, stable_build_id,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    BuildIRValidationError, validate_build_ir,
    verify_build_ir_artifact,
)
from validation.tools.project_migration_build_ir_equivalence_test_support import (
    load_expected_common_contract, materialize_cmake_lane,
    materialize_make_lane, materialize_ninja_lane,
)


EXCLUDED_FIELDS = [
    "boundaries",
    "build_metadata",
    "claim_boundary.adapter_fields",
    "generated_inputs.materialization",
    "provenance",
    "raw_fact_refs",
    "semantic_sha256",
    "status",
    "targets.compile_argument_sets",
    "targets.ordered_link_arguments",
    "targets.output_materialization",
    "toolchains",
    "translation_units.compile_arguments.direct_argv",
    "translation_units.compile_arguments.direct_argv_sha256",
    "translation_units.compile_arguments.expanded_argv_sha256",
    "translation_units.output_materialization",
    "translation_units.response_files",
    "translation_units.toolchain_id",
    "translation_units.unit_id",
]


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def _logical_binding(value: Any, *, source: bool = False) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "common_contract_binding_invalid")
    materialized = value.get("materialized")
    expected = {"path", "kind", "materialized"}
    if materialized is True:
        expected.update({"sha256", "size_bytes"})
    _require(set(value) == expected, "common_contract_binding_shape_invalid")
    result = {"path": value["path"], "kind": value["kind"]}
    if source:
        _require(materialized is True, "common_contract_source_not_materialized")
        result.update({"sha256": value["sha256"], "size_bytes": value["size_bytes"]})
    return result


def _common_contract(build_ir: Mapping[str, Any]) -> dict[str, Any]:
    _validate_verified_lane_shape(build_ir)
    boundary = build_ir["claim_boundary"]
    _require(boundary.get("semantic_gate") is False, "common_contract_semantic_gate")
    _require(
        boundary.get("translation_coverage_numerator") == 0,
        "common_contract_translation_numerator",
    )
    units = build_ir["translation_units"]
    _require(len(units) == 1, "common_contract_unit_cardinality")
    unit = units[0]
    source = _logical_binding(unit["source"], source=True)
    _require(
        build_ir["source_inputs"] == [unit["source"]],
        "common_contract_source_binding_mismatch",
    )
    _require(not unit["compile_arguments"]["response_files"], "common_contract_response")
    _require(not build_ir["external_dependencies"], "common_contract_external_dependency")

    targets = build_ir["targets"]
    _require(len(targets) == 2, "common_contract_target_cardinality")
    by_id = {target["target_id"]: target for target in targets}
    _require(len(by_id) == 2, "common_contract_target_identity")
    keys: dict[str, str] = {}
    for target_id, target in by_id.items():
        _require(target["kind"] in {"object", "link"}, "common_contract_target_kind")
        _require(len(target["outputs"]) == 1, "common_contract_target_output")
        output = _logical_binding(target["outputs"][0])
        _require(target["name"] == output["path"], "common_contract_target_name")
        keys[target_id] = f'{target["kind"]}:{output["path"]}'
    closure = build_ir["target_closure"]
    _require(set(closure) == set(by_id), "common_contract_target_closure")
    logical_closure = [keys[target_id] for target_id in closure]
    _require(
        logical_closure == ["object:build/unit.o", "link:build/program"],
        "common_contract_target_topology",
    )

    projected_targets = []
    for target_id in closure:
        target = by_id[target_id]
        projected_targets.append({
            "key": keys[target_id],
            "kind": target["kind"],
            "output": _logical_binding(target["outputs"][0]),
            "dependency_keys": [keys[item] for item in target["dependency_target_ids"]],
            "ordered_inputs": [{
                "ordinal": item["ordinal"],
                "role": item["role"],
                "binding": _logical_binding(item["binding"]),
                "dependency_key": (
                    keys[item["dependency_target_id"]]
                    if item["dependency_target_id"] is not None else None
                ),
            } for item in target["ordered_inputs"]],
        })
    object_target, link_target = projected_targets
    _require(
        object_target["dependency_keys"] == []
        and object_target["ordered_inputs"] == [{
            "ordinal": 0, "role": "source",
            "binding": {"path": source["path"], "kind": source["kind"]},
            "dependency_key": None,
        }],
        "common_contract_object_shape",
    )
    _require(
        link_target["dependency_keys"] == [object_target["key"]]
        and link_target["ordered_inputs"] == [{
            "ordinal": 0, "role": "link-input",
            "binding": object_target["output"],
            "dependency_key": object_target["key"],
        }],
        "common_contract_link_shape",
    )
    generated = build_ir["generated_inputs"]
    _require(
        [item["binding"]["path"] for item in generated]
        == ["build/program", "build/unit.o"],
        "common_contract_generated_outputs",
    )
    _require(
        {item["producer_target_id"] for item in generated} == set(by_id),
        "common_contract_generated_producers",
    )
    abi = build_ir["abi_facts"]
    _require(
        len(abi) == 1 and abi[0]["unit_id"] == unit["unit_id"]
        and abi[0]["toolchain_id"] == unit["toolchain_id"],
        "common_contract_abi_binding",
    )
    return {
        "schema_version": 1,
        "artifact_kind": "project-migration-build-ir-common-contract-test-only",
        "translation_units": [{
            "source": source,
            "working_directory": unit["working_directory"],
            "compiler": unit["compiler"],
            "compiler_wrappers": copy.deepcopy(unit["compiler_wrappers"]),
            "language": unit["language"],
            "variant_index": unit["variant_index"],
            "variant_count": unit["variant_count"],
            "includes": copy.deepcopy(unit["includes"]),
            "defines": copy.deepcopy(unit["defines"]),
            "redacted_define_count": unit["redacted_define_count"],
            "semantic_flags": copy.deepcopy(unit["compile_arguments"]["semantic_flags"]),
            "output": _logical_binding(unit["output"]),
        }],
        "source_inputs": [source],
        "targets": projected_targets,
        "target_closure": logical_closure,
        "abi_facts": [{
            "language": abi[0]["language"],
            "target_flags": copy.deepcopy(abi[0]["target_flags"]),
            "data_model": abi[0]["data_model"],
        }],
        "excluded_fields": list(EXCLUDED_FIELDS),
        "claim_boundary": {
            "role": "test-only-nonsemantic-common-build-contract",
            "does_not_prove": [
                "archive or multi-input link ordering", "build success",
                "program semantic equivalence", "toolchain equivalence",
            ],
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }


def _retained_adapter_differences(build_ir: Mapping[str, Any]) -> dict[str, Any]:
    _validate_verified_lane_shape(build_ir)
    return {
        "semantic_sha256": build_ir["semantic_sha256"],
        "status": build_ir["status"],
        "boundaries": copy.deepcopy(build_ir["boundaries"]),
        "raw_fact_refs": copy.deepcopy(build_ir["raw_fact_refs"]),
        "build_metadata": copy.deepcopy(build_ir["build_metadata"]),
        "claim_boundary": copy.deepcopy(build_ir["claim_boundary"]),
        "materialization": {
            "unit_outputs": [copy.deepcopy(item["output"]) for item in build_ir["translation_units"]],
            "generated": [copy.deepcopy(item["binding"]) for item in build_ir["generated_inputs"]],
            "target_outputs": [copy.deepcopy(item["outputs"]) for item in build_ir["targets"]],
            "target_inputs": [copy.deepcopy(item["ordered_inputs"]) for item in build_ir["targets"]],
        },
        "toolchains": copy.deepcopy(build_ir["toolchains"]),
        "translation_unit_evidence": [{
            "unit_id": item["unit_id"],
            "toolchain_id": item["toolchain_id"],
            "expanded_argv_sha256": item["compile_arguments"]["expanded_argv_sha256"],
            "response_files": copy.deepcopy(item["compile_arguments"]["response_files"]),
            "direct_argv": copy.deepcopy(item["compile_arguments"].get("direct_argv")),
            "direct_argv_sha256": item["compile_arguments"].get("direct_argv_sha256"),
        } for item in build_ir["translation_units"]],
        "target_evidence": [{
            "target_id": item["target_id"],
            "toolchain_id": item.get("toolchain_id"),
            "compile_argument_sets": copy.deepcopy(item["compile_argument_sets"]),
            "ordered_link_arguments": copy.deepcopy(item["ordered_link_arguments"]),
        } for item in build_ir["targets"]],
        "provenance": {
            "units": [copy.deepcopy(item["provenance"]) for item in build_ir["translation_units"]],
            "targets": [copy.deepcopy(item["provenance"]) for item in build_ir["targets"]],
            "generated": [copy.deepcopy(item["provenance"]) for item in build_ir["generated_inputs"]],
        },
    }


def _validate_verified_lane_shape(build_ir: Mapping[str, Any]) -> None:
    if build_ir.get("schema_version") == LEGACY_BUILD_IR_SCHEMA_VERSION:
        _require(build_ir.get("extractor") == LEGACY_BUILD_IR_EXTRACTOR, "common_contract_legacy_extractor_invalid")
        return
    validate_build_ir(build_ir)


class ProjectMigrationBuildIREquivalenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="build-ir-equivalence-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    def test_make_cmake_and_ninja_share_only_the_bounded_common_contract(self) -> None:
        cmake = materialize_cmake_lane(self.base, "identity-alpha")
        ninja = materialize_ninja_lane(self.base, "identity-gamma")
        make = materialize_make_lane(self.base, "identity-beta")
        expected = load_expected_common_contract()
        for lane in (cmake, ninja, make):
            self.assertEqual(expected, _common_contract(lane.build_ir))
            self.assertEqual("verified", lane.verification["status"])
            reopened = verify_build_ir_artifact(lane.project_root, lane.artifact_root, lane.build_ir_reference)
            self.assertEqual("verified", reopened["status"], reopened)
        self.assertEqual(cmake.build_ir["semantic_sha256"], ninja.build_ir["semantic_sha256"])
        self.assertNotEqual(cmake.build_ir["semantic_sha256"], make.build_ir["semantic_sha256"])
        expected_object_id = stable_build_id("target", {"kind": "object", "output": "build/unit.o"})
        for lane in (cmake, ninja, make):
            object_target = next(item for item in lane.build_ir["targets"] if item["kind"] == "object")
            self.assertEqual(expected_object_id, object_target["target_id"])
        cmake_retained = _retained_adapter_differences(cmake.build_ir)
        ninja_retained = _retained_adapter_differences(ninja.build_ir)
        make_retained = _retained_adapter_differences(make.build_ir)
        for key in ("raw_fact_refs", "build_metadata", "provenance"):
            self.assertNotEqual(cmake_retained[key], ninja_retained[key], key)
        for key in (
            "semantic_sha256", "status", "boundaries", "raw_fact_refs",
            "build_metadata", "claim_boundary", "materialization", "toolchains",
            "translation_unit_evidence", "target_evidence", "provenance",
        ):
            self.assertNotEqual(cmake_retained[key], make_retained[key], key)

    def test_valid_make_define_drift_changes_the_common_contract(self) -> None:
        baseline = materialize_make_lane(self.base, "baseline")
        changed = materialize_make_lane(self.base, "changed", define_value="8")
        baseline_contract = _common_contract(baseline.build_ir)
        changed_contract = _common_contract(changed.build_ir)
        self.assertEqual("verified", changed.verification["status"])
        self.assertNotEqual(baseline_contract, changed_contract)
        self.assertEqual(
            [{"name": "VALUE", "value": "8"}],
            changed_contract["translation_units"][0]["defines"],
        )
        self.assertFalse(changed_contract["claim_boundary"]["semantic_gate"])
        self.assertEqual(0, changed_contract["claim_boundary"]["translation_coverage_numerator"])

    def test_validator_rejects_promoted_semantic_claims(self) -> None:
        lane = materialize_cmake_lane(self.base, "claim-boundary")
        promoted = copy.deepcopy(lane.build_ir)
        promoted["claim_boundary"]["semantic_gate"] = True
        promoted = finalize_build_ir(promoted)
        with self.assertRaisesRegex(
            BuildIRValidationError, "build_ir_claim_boundary_invalid",
        ):
            validate_build_ir(promoted)


if __name__ == "__main__":
    unittest.main()
