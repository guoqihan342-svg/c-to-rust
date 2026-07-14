from __future__ import annotations

from unittest import mock

from validation.tools._project_migration_harness.project_completion_build_ir import (
    build_ir_allows_candidate_execution, build_ir_allows_completion,
    verify_project_final_build_ir,
)
from validation.tools._project_migration_harness.project_completion_coordinator import (
    resume_project_completion,
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

    def test_native_only_blocker_admits_candidate_work_but_not_completion(self) -> None:
        verification = {
            "schema_version": 1,
            "status": "blocked",
            "blockers": [{"kind": "native_link_config_unresolved"}],
            "native_link_config_resolved": False,
            "unresolved_native_dependency_count": 7,
        }

        self.assertTrue(build_ir_allows_candidate_execution(verification))
        self.assertFalse(build_ir_allows_completion(verification))
        verification["blockers"].append({"kind": "c_toolchain_evidence_drift"})
        self.assertFalse(build_ir_allows_candidate_execution(verification))

    def test_completion_reaches_candidate_compile_with_native_only_blocker(self) -> None:
        self.promote_current_candidate()
        native_only = {
            "schema_version": 1,
            "status": "blocked",
            "blockers": [{"kind": "native_link_config_unresolved"}],
            "native_link_config_resolved": False,
            "unresolved_native_dependency_count": 1,
        }
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.verify_project_final_build_ir",
            return_value=native_only,
        ), mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.verify_candidate_compile",
            return_value={"schema_version": 1, "status": "blocked"},
        ) as compile_runner:
            result = resume_project_completion(
                ledger=self.ledger, run_id="run", harness_root=self.harness,
            )

        self.assertEqual("project-final-candidate-compile", result["stage"])
        compile_runner.assert_called_once()
