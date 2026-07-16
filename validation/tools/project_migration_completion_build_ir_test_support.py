from __future__ import annotations

from unittest import mock

from validation.tools._project_migration_harness.artifacts import content_sha256
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
COORDINATOR = (
    "validation.tools._project_migration_harness."
    "project_completion_coordinator."
)
PASSED = {"schema_version": 1, "status": "passed"}
VERIFIED = {
    "schema_version": 1,
    "artifact_kind": "project-final-build-ir-verification",
    "status": "verified", "blockers": [],
    "native_link_config_resolved": True, "closure_complete": True,
    "unresolved_native_dependency_count": 0,
}
INTEGRATED = {
    "schema_version": 1, "status": "integrated",
    "rust_project_ir_completeness": {
        "status": "complete", "unresolved_sections": [],
    },
}
PROJECT_TEST_EVIDENCE = {
    "schema_version": 1,
    "artifact_kind": "project-test-semantic-evidence-binding",
    "status": "verified",
    "inventory": {
        "path": "plan/project-test-inventory.json",
        "sha256": "1" * 64, "size_bytes": 101,
    },
    "mapping": {
        "path": "completion/project-test-mapping.json",
        "sha256": "2" * 64, "size_bytes": 202,
    },
    "oracle": {
        "path": "verification/project-test/oracle/" + "3" * 64 + ".json",
        "sha256": "3" * 64, "size_bytes": 303,
    },
    "summary": {
        "case_count": 1, "mismatch_count": 0, "crash_count": 0,
        "inventory_sha256": "4" * 64, "mapping_sha256": "5" * 64,
        "oracle_artifact_sha256": "3" * 64,
        "candidate_sha256": "6" * 64, "summary_sha256": "7" * 64,
    },
    "project_gate_record_id": "host-oracle-replay-record",
    "semantic_gate": False,
}
_INVARIANT = {"schema_version": 1, "artifact_kind": "test-finalization-invariant"}
FINALIZATION = {
    "completion_epoch": 1,
    "cohort_sha256": "8" * 64,
    "generation_sha256": "9" * 64,
    "gate_bundle_sha256": "a" * 64,
    "invariant": {"payload": _INVARIANT, "sha256": content_sha256(_INVARIANT)},
    "records": [],
}


class CompletionBuildIRCase(ProjectMigrationGateAuthorityCase):
    def run_completion(
        self, build_ir_results: list[dict], *, project_semantic_result: dict = PASSED,
        evidence_reopen_error: Exception | None = None,
    ) -> tuple[dict, dict[str, mock.Mock]]:
        self.promote_current_candidate()
        project_final_result = {
            "record_id": "project-final-record",
            "evidence": {
                "path": "project/final.json", "sha256": "c" * 64,
                "size_bytes": 12,
            },
        }
        with (
            mock.patch(
                BUILD_VERIFIER.rsplit(".", 1)[0] + ".verify_manifest_generated_closure",
                return_value=VERIFIED,
            ),
            mock.patch(BUILD_VERIFIER, side_effect=build_ir_results) as build_ir,
            mock.patch(COORDINATOR + "verify_candidate_compile", return_value=PASSED) as compile,
            mock.patch(
                COORDINATOR + "_semantic_runner", return_value=lambda **_: PASSED,
            ) as semantic_runner,
            mock.patch(
                COORDINATOR + "_missing_candidate_semantic_gates", return_value=[],
            ) as semantic_gates,
            mock.patch(COORDINATOR + "verify_candidate_final", return_value=PASSED) as final,
            mock.patch(COORDINATOR + "integrate_verified_project", return_value=INTEGRATED) as integration,
            mock.patch(COORDINATOR + "execute_project_repair_completion_step") as repair,
            mock.patch(
                COORDINATOR + "verify_integrated_project",
                return_value={"gate_status": "passed"},
            ) as integration_gate,
            mock.patch(COORDINATOR + "verify_project_cargo", return_value=PASSED) as cargo,
            mock.patch(
                COORDINATOR + "advance_project_verifier_phase", return_value=None,
            ) as verifier_phase,
            mock.patch(
                COORDINATOR + "verify_project_test_semantics",
                return_value=project_semantic_result,
            ) as project_semantics,
            mock.patch(
                COORDINATOR + "record_project_candidate_aggregate_gates",
                return_value=PASSED,
            ) as aggregate_gates,
            mock.patch(
                COORDINATOR + "reopen_project_test_semantic_evidence",
                return_value=PROJECT_TEST_EVIDENCE, side_effect=evidence_reopen_error,
            ) as evidence_reopen,
            mock.patch(
                COORDINATOR + "_record_host_project_final",
                return_value=project_final_result,
            ) as project_final,
            mock.patch.object(
                self.ledger, "begin_project_finalization",
                return_value=FINALIZATION,
            ),
            mock.patch(
                COORDINATOR + "complete_verified_project",
                return_value={"schema_version": 1, "status": "completed"},
            ) as complete,
        ):
            result = resume_project_completion(
                ledger=self.ledger, run_id="run", harness_root=self.harness,
                repo_root=self.harness,
            )
        return result, {
            "build_ir": build_ir, "compile": compile,
            "semantic_runner": semantic_runner, "semantic_gates": semantic_gates,
            "candidate_final": final, "integration": integration, "repair": repair,
            "integration_gate": integration_gate, "cargo": cargo,
            "verifier_phase": verifier_phase, "project_semantics": project_semantics,
            "aggregate_gates": aggregate_gates, "evidence_reopen": evidence_reopen,
            "project_final": project_final, "complete": complete,
        }


__all__ = [
    "BUILD_VERIFIER", "CompletionBuildIRCase", "PROJECT_TEST_EVIDENCE",
    "VERIFIED",
]
