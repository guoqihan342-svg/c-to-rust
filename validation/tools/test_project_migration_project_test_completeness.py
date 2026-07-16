from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_completeness import (
    derive_project_test_completeness, validate_project_test_completeness,
)
from validation.tools._project_migration_harness.project_test_mapping import (
    derive_project_test_mapping,
)
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    direct_two_package_ir,
)


class ProjectTestCompletenessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ir, _sources = direct_two_package_ir()
        self.inventory = _inventory(["build-target-bin"])
        self.mapping = derive_project_test_mapping(self.inventory, self.ir)
        self.assertEqual("ready", self.mapping["status"])

    def test_exact_case_and_target_closure_is_ready_and_reopenable(self) -> None:
        completeness = derive_project_test_completeness(
            self.inventory, self.mapping, self.ir,
        )

        self.assertEqual("ready", completeness["status"])
        self.assertEqual([], completeness["blockers"])
        self.assertEqual(["test-0"], completeness["case_ids"])
        self.assertEqual(0, completeness["counts"]["silent_skip_count"])
        validate_project_test_completeness(
            completeness, self.inventory, self.mapping,
        )

    def test_zero_inventory_cannot_produce_ready_completeness(self) -> None:
        inventory = _inventory([])
        mapping = derive_project_test_mapping(inventory, self.ir)

        completeness = derive_project_test_completeness(
            inventory, mapping, self.ir,
        )

        self.assertEqual("blocked", completeness["status"])
        self.assertEqual(
            "project_test_completeness_canonical_mapping_blocked",
            completeness["blockers"][0]["code"],
        )

    def test_missing_required_test_id_is_rejected(self) -> None:
        inventory = _inventory(["build-target-bin", "build-target-bin"])
        mapping = derive_project_test_mapping(inventory, self.ir)
        changed = copy.deepcopy(mapping)
        changed["mappings"][0]["test_ids"].pop()
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            inventory, changed, self.ir,
        )

        self.assertEqual("blocked", completeness["status"])
        self.assertEqual(1, completeness["counts"]["silent_skip_count"])
        self.assertIn(
            "project_test_required_case_omitted",
            _blocker_codes(completeness),
        )

    def test_extra_mapped_test_id_is_rejected(self) -> None:
        changed = copy.deepcopy(self.mapping)
        changed["mappings"][0]["test_ids"].append("test-extra")
        changed["mappings"][0]["test_ids"].sort()
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            self.inventory, changed, self.ir,
        )

        self.assertEqual(1, completeness["counts"]["extra_mapped_test_count"])
        self.assertIn(
            "project_test_extra_mapped_case", _blocker_codes(completeness),
        )

    def test_duplicate_mapped_test_id_is_rejected(self) -> None:
        changed = copy.deepcopy(self.mapping)
        changed["mappings"][0]["test_ids"].append("test-0")
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            self.inventory, changed, self.ir,
        )

        self.assertEqual(
            1, completeness["counts"]["duplicate_mapped_test_count"],
        )
        self.assertIn(
            "project_test_case_mapped_multiple_times",
            _blocker_codes(completeness),
        )

    def test_mapping_without_cases_is_rejected(self) -> None:
        changed = copy.deepcopy(self.mapping)
        changed["mappings"][0]["test_ids"] = []
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            self.inventory, changed, self.ir,
        )

        self.assertEqual(1, completeness["counts"]["zero_test_mapping_count"])
        self.assertIn(
            "project_test_zero_case_mapping", _blocker_codes(completeness),
        )

    def test_one_rust_target_cannot_cover_two_source_test_targets(self) -> None:
        ir, _sources = direct_two_package_ir(second_package_executable=True)
        inventory = _inventory(["build-target-bin", "build-target-lib"])
        mapping = derive_project_test_mapping(inventory, ir)
        changed = copy.deepcopy(mapping)
        changed["mappings"][1]["rust_target_id"] = changed["mappings"][0][
            "rust_target_id"
        ]
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(inventory, changed, ir)

        self.assertEqual(
            1,
            completeness["counts"]["duplicate_rust_target_binding_count"],
        )
        self.assertIn(
            "project_test_rust_target_bound_multiple_times",
            _blocker_codes(completeness),
        )

    def test_one_source_target_cannot_split_across_two_mapping_entries(self) -> None:
        inventory = _inventory(["build-target-bin", "build-target-bin"])
        mapping = derive_project_test_mapping(inventory, self.ir)
        changed = copy.deepcopy(mapping)
        first = changed["mappings"][0]
        second = copy.deepcopy(first)
        first["test_ids"] = ["test-0"]
        second["test_ids"] = ["test-1"]
        second["rust_target_id"] = "forged-second-target"
        second["rust_target_name"] = "forged_second_target"
        changed["mappings"].append(second)
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            inventory, changed, self.ir,
        )

        self.assertEqual(
            1,
            completeness["counts"]["duplicate_source_target_binding_count"],
        )
        self.assertIn(
            "project_test_source_target_bound_multiple_times",
            _blocker_codes(completeness),
        )

    def test_closed_but_forged_mapping_is_rejected_against_ir_derivation(self) -> None:
        changed = copy.deepcopy(self.mapping)
        changed["mappings"][0]["rust_target_name"] = "forged"
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            self.inventory, changed, self.ir,
        )

        self.assertEqual("blocked", completeness["status"])
        self.assertIn(
            "project_test_mapping_derivation_drifted",
            _blocker_codes(completeness),
        )

    def test_mapping_entry_requires_complete_reopenable_schema(self) -> None:
        changed = copy.deepcopy(self.mapping)
        changed["mappings"][0].pop("source_executable_paths")
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(
            self.inventory, changed, self.ir,
        )

        self.assertEqual("blocked", completeness["status"])
        self.assertIn(
            "project_test_mapping_schema_invalid",
            _blocker_codes(completeness),
        )

    def test_test_ids_cannot_move_between_source_targets(self) -> None:
        ir, _sources = direct_two_package_ir(second_package_executable=True)
        inventory = _inventory(["build-target-bin", "build-target-lib"])
        mapping = derive_project_test_mapping(inventory, ir)
        changed = copy.deepcopy(mapping)
        left, right = changed["mappings"]
        left["test_ids"], right["test_ids"] = right["test_ids"], left["test_ids"]
        _rehash_mapping(changed)

        completeness = derive_project_test_completeness(inventory, changed, ir)

        self.assertEqual(
            2, completeness["counts"]["source_target_binding_drift_count"],
        )
        self.assertIn(
            "project_test_source_target_binding_drifted",
            _blocker_codes(completeness),
        )


def _inventory(target_ids: list[str]) -> dict:
    tests = []
    for index, target_id in enumerate(target_ids):
        tests.append({
            "source_index": index, "name": f"suite-{index}",
            "source_target_id": target_id,
            "source_executable": {
                "path": f"build/suite-{index}", "kind": "file",
                "materialized": True, "sha256": f"{index + 1:x}" * 64,
                "size_bytes": 1,
            },
            "arguments": [], "working_directory": "build", "environment": {},
            "timeout_seconds": 30, "test_id": f"test-{index}",
        })
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "ready", "adapter": "ctest-json-v1",
        "source_observation": {
            "path": "plan/ctest.json", "sha256": "b" * 64,
            "size_bytes": 1,
        },
        "build_directory": "build", "tests": tests, "blockers": [],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


def _rehash_mapping(mapping: dict) -> None:
    mapping["mapping_sha256"] = content_sha256({
        key: value for key, value in mapping.items() if key != "mapping_sha256"
    })


def _blocker_codes(completeness: dict) -> set[str]:
    return {str(item["code"]) for item in completeness["blockers"]}


if __name__ == "__main__":
    unittest.main()
