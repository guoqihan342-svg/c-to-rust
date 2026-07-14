from __future__ import annotations

from unittest import mock

from validation.tools._project_migration_harness.project_completion_build_ir import (
    verify_project_final_build_ir,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


BUILD_VERIFIER = (
    "validation.tools._project_migration_harness."
    "project_completion_build_ir.verify_build_ir_artifact"
)


class ProjectMigrationCompletionNativeLinkTests(
    ProjectMigrationGateAuthorityCase,
):
    def test_unresolved_native_link_config_blocks_completion_boundary(self) -> None:
        manifest = {
            "schema_version": 1,
            "profile": "competition",
            "build_ir": {
                "status": "bound",
                "artifact": {
                    "path": "plan/build-ir.json",
                    "sha256": "a" * 64,
                    "size_bytes": 123,
                },
            },
        }
        verification = {
            "schema_version": 1,
            "status": "verified",
            "blockers": [],
            "toolchain_profile": "competition",
            "native_link_config_resolved": False,
            "unresolved_native_dependency_count": 1,
        }
        with mock.patch(BUILD_VERIFIER, return_value=verification):
            result = verify_project_final_build_ir(
                migration_manifest=manifest,
                repo_root=self.harness,
                artifact_root=self.out_root,
            )
        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            [{"kind": "native_link_config_unresolved"}], result["blockers"],
        )
        self.assertFalse(result["native_link_config_resolved"])
