from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_inventory import (
    inventory_from_ctest_observation,
)


class ProjectTestInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="project-test-inventory-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.build = self.root / "build"
        self.build.mkdir()
        self.binary = self.build / "suite-bin"
        self.binary.write_bytes(b"native-test-binary")
        self.fixture = self.root / "fixture.txt"
        self.fixture.write_text("fixture", encoding="ascii")
        self.source_ref = {
            "path": "plan/ctest.json", "sha256": "d" * 64,
            "size_bytes": 10,
        }

    def test_ctest_command_maps_to_one_build_ir_target(self) -> None:
        observation = self.observation([{
            "name": "source-suite",
            "command": [str(self.binary), str(self.root / "fixture.txt"), "--strict"],
            "properties": [
                {"name": "WORKING_DIRECTORY", "value": str(self.build)},
                {"name": "TIMEOUT", "value": 45.0},
                {"name": "ENVIRONMENT", "value": ["MODE=portable"]},
            ],
        }])

        inventory = inventory_from_ctest_observation(
            self.root, self.build_ir(), observation,
            source_observation=self.source_ref,
        )

        self.assertEqual("ready", inventory["status"])
        self.assertEqual(1, len(inventory["tests"]))
        test = inventory["tests"][0]
        self.assertEqual("link-target", test["source_target_id"])
        self.assertEqual([
            {"kind": "repo-path", "path": "fixture.txt"},
            {"kind": "literal", "value": "--strict"},
        ], test["arguments"])
        self.assertEqual("build", test["working_directory"])
        self.assertEqual({
            "MODE": {"kind": "literal", "value": "portable"},
        }, test["environment"])
        self.assertEqual(45, test["timeout_seconds"])
        self.assertEqual(
            inventory["inventory_sha256"],
            content_sha256({key: value for key, value in inventory.items()
                            if key != "inventory_sha256"}),
        )

    def test_unmapped_executable_blocks_without_name_guessing(self) -> None:
        other = self.build / "other-bin"
        other.write_bytes(b"other")
        inventory = inventory_from_ctest_observation(
            self.root, self.build_ir(),
            self.observation([{"name": "x", "command": [str(other)]}]),
            source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual([], inventory["tests"])
        self.assertEqual(
            "project_test_executable_target_unmapped",
            inventory["blockers"][0]["code"],
        )

    def test_verdict_changing_ctest_property_fails_closed(self) -> None:
        inventory = inventory_from_ctest_observation(
            self.root, self.build_ir(), self.observation([{
                "name": "x", "command": [str(self.binary)],
                "properties": [{
                    "name": "PASS_REGULAR_EXPRESSION", "value": "accepted",
                }],
            }]), source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_property_unsupported",
            inventory["blockers"][0]["code"],
        )

    def test_embedded_repository_path_is_structured(self) -> None:
        inventory = inventory_from_ctest_observation(
            self.root, self.build_ir(), self.observation([{
                "name": "x",
                "command": [self.binary.as_posix(), f"--fixture={self.fixture.as_posix()}"],
            }]), source_observation=self.source_ref,
        )

        self.assertEqual("ready", inventory["status"], inventory)
        self.assertEqual({
            "kind": "repo-path-template", "prefix": "--fixture=",
            "path": "fixture.txt", "suffix": "",
        }, inventory["tests"][0]["arguments"][0])

    def test_external_embedded_path_fails_closed(self) -> None:
        inventory = inventory_from_ctest_observation(
            self.root, self.build_ir(), self.observation([{
                "name": "x", "command": [self.binary.as_posix(), "--fixture=/outside/input"],
            }]), source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual(
            "project_test_external_path_forbidden", inventory["blockers"][0]["code"],
        )

    def test_observation_hash_drift_blocks_all_tests(self) -> None:
        observation = self.observation([{
            "name": "x", "command": [str(self.binary)],
        }])
        observation["payload"]["tests"][0]["name"] = "drifted"

        inventory = inventory_from_ctest_observation(
            self.root, self.build_ir(), observation,
            source_observation=self.source_ref,
        )

        self.assertEqual("blocked", inventory["status"])
        self.assertEqual("project_test_ctest_schema_invalid", inventory["blockers"][0]["code"])

    def build_ir(self) -> dict:
        data = self.binary.read_bytes()
        return {
            "targets": [{
                "target_id": "link-target", "kind": "link",
                "outputs": [{
                    "path": "build/suite-bin", "kind": "file",
                    "materialized": True,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "size_bytes": len(data),
                }],
            }],
        }

    def observation(self, tests: list[dict]) -> dict:
        value = {
            "schema_version": 1,
            "artifact_kind": "ctest-json-v1-observation",
            "command": ["ctest", "--show-only=json-v1"],
            "build_directory": "build",
            "tool": {"basename": "ctest", "sha256": "a" * 64, "size_bytes": 1},
            "sandbox_launcher": {
                "basename": "bwrap", "sha256": "b" * 64, "size_bytes": 1,
            },
            "returncode": 0,
            "stdout_sha256": "c" * 64, "stdout_size_bytes": 1,
            "stderr_sha256": "e" * 64, "stderr_size_bytes": 0,
            "payload": {
                "kind": "ctestInfo", "version": {"major": 1, "minor": 0},
                "backtraceGraph": {"commands": [], "files": [], "nodes": []},
                "tests": copy.deepcopy(tests),
            },
            "semantic_gate": False,
        }
        value["observation_sha256"] = content_sha256(value)
        return value


if __name__ == "__main__":
    unittest.main()
