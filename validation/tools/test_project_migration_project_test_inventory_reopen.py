from __future__ import annotations

import copy
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.artifacts import (
    content_sha256, write_json_artifact,
)
from validation.tools._project_migration_harness.project_test_inventory import (
    inventory_from_ctest_observation,
)
from validation.tools._project_migration_harness.project_test_inventory_validation import (
    reopen_manifest_project_test_inventory,
)
from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase,
)


class ProjectTestInventoryReopenTests(BuildIRHostBindingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.artifacts = self.root / "artifacts"
        self.build_directory = self.project_root / "build"
        self.build_directory.mkdir()
        self.binary = self.build_directory / "program"
        self.binary.write_bytes(b"program")
        self.build_ir = self.standard_build_ir()
        self.build_ref = write_json_artifact(
            self.artifacts, "plan/build-ir.json", self.build_ir,
        )
        self.observation = self._observation()
        self.observation_ref = write_json_artifact(
            self.artifacts, "plan/ctest.json", self.observation,
        )
        self.inventory = inventory_from_ctest_observation(
            self.project_root, self.build_ir, self.observation,
            source_observation=self.observation_ref,
        )
        self.inventory_ref = write_json_artifact(
            self.artifacts, "plan/project-tests.json", self.inventory,
        )
        collector = mock.patch(
            "validation.tools._project_migration_harness."
            "project_test_inventory_validation.collect_ctest_json",
            return_value={"status": "collected", "observation": self.observation},
        )
        self.collector = collector.start()
        self.addCleanup(collector.stop)

    def test_reopens_inventory_and_source_executable_content(self) -> None:
        reopened = reopen_manifest_project_test_inventory(
            repo_root=self.project_root, artifact_root=self.artifacts,
            migration_manifest=self._manifest(),
        )

        self.assertEqual(self.inventory, reopened)
        self.assertEqual("ready", reopened["status"])

    def test_source_executable_content_drift_fails_closed(self) -> None:
        self.binary.write_bytes(b"changed")

        with self.assertRaisesRegex(
            ValueError, "project_test_source_executable_(size|content)_drifted",
        ):
            reopen_manifest_project_test_inventory(
                repo_root=self.project_root, artifact_root=self.artifacts,
                migration_manifest=self._manifest(),
            )

    def test_inventory_derivation_drift_fails_closed(self) -> None:
        changed = copy.deepcopy(self.inventory)
        changed["tests"][0]["timeout_seconds"] = 31
        changed["inventory_sha256"] = content_sha256({
            key: value for key, value in changed.items()
            if key != "inventory_sha256"
        })
        changed_ref = write_json_artifact(
            self.artifacts, "plan/project-tests-changed.json", changed,
        )

        with self.assertRaisesRegex(
            ValueError, "project_test_inventory_derivation_drifted",
        ):
            reopen_manifest_project_test_inventory(
                repo_root=self.project_root, artifact_root=self.artifacts,
                migration_manifest=self._manifest(changed_ref),
            )

    def test_live_ctest_inventory_drift_fails_closed(self) -> None:
        changed = copy.deepcopy(self.observation)
        changed["payload"]["tests"][0]["name"] = "replacement-suite"
        changed["observation_sha256"] = content_sha256({
            key: value for key, value in changed.items()
            if key != "observation_sha256"
        })
        self.collector.return_value = {
            "status": "collected", "observation": changed,
        }

        with self.assertRaisesRegex(
            ValueError, "project_test_inventory_observation_drifted",
        ):
            reopen_manifest_project_test_inventory(
                repo_root=self.project_root, artifact_root=self.artifacts,
                migration_manifest=self._manifest(),
            )

    def test_make_inventory_reopens_with_the_same_adapter(self) -> None:
        inventory = copy.deepcopy(self.inventory)
        inventory["adapter"] = "make-dry-run-v1"
        inventory["inventory_sha256"] = content_sha256({
            key: value for key, value in inventory.items()
            if key != "inventory_sha256"
        })
        inventory_ref = write_json_artifact(
            self.artifacts, "plan/project-tests-make.json", inventory,
        )
        module = (
            "validation.tools._project_migration_harness."
            "project_test_inventory_validation."
        )
        self.collector.reset_mock()
        with (
            mock.patch(
                module + "collect_make_test_dry_run",
                return_value={
                    "status": "collected", "observation": self.observation,
                },
            ) as make_collector,
            mock.patch(
                module + "inventory_from_make_observation",
                return_value=inventory,
            ) as make_deriver,
        ):
            reopened = reopen_manifest_project_test_inventory(
                repo_root=self.project_root, artifact_root=self.artifacts,
                migration_manifest=self._manifest(inventory_ref),
            )

        self.assertEqual(inventory, reopened)
        make_collector.assert_called_once()
        make_deriver.assert_called_once()
        self.collector.assert_not_called()

    def _manifest(self, inventory_ref: dict | None = None) -> dict:
        return {
            "build_ir": {"status": "bound", "artifact": self.build_ref},
            "project_test_inventory": {
                "status": "bound",
                "artifact": inventory_ref or self.inventory_ref,
            },
        }

    def _observation(self) -> dict:
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
            "stderr_sha256": "d" * 64, "stderr_size_bytes": 0,
            "payload": {
                "kind": "ctestInfo", "version": {"major": 1, "minor": 0},
                "tests": [{
                    "name": "source-suite", "command": [str(self.binary)],
                    "properties": [{
                        "name": "WORKING_DIRECTORY",
                        "value": str(self.build_directory),
                    }],
                }],
            },
            "semantic_gate": False,
        }
        value["observation_sha256"] = content_sha256(value)
        return value


if __name__ == "__main__":
    unittest.main()
