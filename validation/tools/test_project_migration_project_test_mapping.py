from __future__ import annotations

import copy
from pathlib import Path
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_mapping import (
    derive_project_test_mapping,
)
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    direct_two_package_ir,
)


class ProjectTestMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ir, _sources = direct_two_package_ir()

    def test_build_target_identity_maps_test_to_rust_binary(self) -> None:
        mapping = derive_project_test_mapping(
            self.inventory("build-target-bin"), self.ir,
        )

        self.assertEqual("ready", mapping["status"])
        self.assertEqual([], mapping["blockers"])
        self.assertEqual(1, len(mapping["mappings"]))
        bound = mapping["mappings"][0]
        self.assertEqual("build-target-bin", bound["source_target_id"])
        self.assertEqual("package-bin", bound["rust_package_id"])
        self.assertEqual("target-bin", bound["rust_target_id"])
        self.assertEqual("target_bin", bound["rust_target_name"])

    def test_library_target_cannot_stand_in_for_test_executable(self) -> None:
        mapping = derive_project_test_mapping(
            self.inventory("build-target-lib"), self.ir,
        )

        self.assertEqual("blocked", mapping["status"])
        self.assertEqual(
            "project_test_rust_executable_binding_invalid",
            mapping["blockers"][0]["code"],
        )

    def test_unknown_target_blocks_without_name_guessing(self) -> None:
        mapping = derive_project_test_mapping(
            self.inventory("unknown-build-target"), self.ir,
        )

        self.assertEqual("blocked", mapping["status"])
        self.assertEqual(
            "project_test_rust_target_missing_or_ambiguous",
            mapping["blockers"][0]["code"],
        )

    def test_non_test_executable_does_not_pollute_test_inventory(self) -> None:
        ir, _sources = direct_two_package_ir(second_package_executable=True)

        mapping = derive_project_test_mapping(
            self.inventory("build-target-bin"), ir,
        )

        self.assertEqual("ready", mapping["status"])
        self.assertEqual([], mapping["blockers"])
        self.assertEqual(
            ["build-target-bin"],
            [item["source_target_id"] for item in mapping["mappings"]],
        )

    def test_invalid_ir_never_falls_back_to_test_name_matching(self) -> None:
        changed = copy.deepcopy(self.ir)
        changed["targets"][0]["name"] = "source-suite"
        mapping = derive_project_test_mapping(
            self.inventory("build-target-bin"), changed,
        )

        self.assertEqual("blocked", mapping["status"])
        self.assertEqual(
            "project_test_rust_project_ir_v3_invalid",
            mapping["blockers"][0]["code"],
        )

    @staticmethod
    def inventory(source_target_id: str) -> dict:
        executable = {
            "path": "build/source-suite", "kind": "file",
            "materialized": True, "sha256": "a" * 64, "size_bytes": 1,
        }
        test = {
            "source_index": 0, "name": "source-suite",
            "source_target_id": source_target_id,
            "source_executable": executable, "arguments": [],
            "working_directory": "build", "environment": {},
            "timeout_seconds": 30, "test_id": "test-a",
        }
        value = {
            "schema_version": 1, "artifact_kind": "project-test-inventory",
            "status": "ready", "adapter": "ctest-json-v1",
            "source_observation": {
                "path": "plan/ctest.json", "sha256": "b" * 64,
                "size_bytes": 1,
            },
            "build_directory": "build", "tests": [test], "blockers": [],
            "claim_boundary": {
                "semantic_gate": False, "translation_coverage_numerator": 0,
            },
        }
        value["inventory_sha256"] = content_sha256(value)
        return value


if __name__ == "__main__":
    unittest.main()
