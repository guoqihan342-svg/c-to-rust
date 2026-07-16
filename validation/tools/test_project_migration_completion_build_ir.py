from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.ledger_run_contract import (
    load_migration_contract,
)
from validation.tools._project_migration_harness.project_completion_build_ir import (
    build_ir_allows_completion, verify_project_final_build_ir,
)
from validation.tools._project_migration_harness.project_migration_cli import (
    parse_args,
)
from validation.tools.project_migration_completion_build_ir_test_support import (
    BUILD_VERIFIER, CompletionBuildIRCase, PROJECT_TEST_EVIDENCE, VERIFIED,
)

class ProjectMigrationCompletionBuildIRTests(CompletionBuildIRCase):
    def _run_completion(self, *args, **kwargs):
        return self.run_completion(*args, **kwargs)

    def test_plan_profile_defaults_to_competition_and_accepts_development(self) -> None:
        default = parse_args(["plan", "--repo-root", "."])
        development = parse_args([
            "plan", "--repo-root", ".", "--profile", "development",
        ])
        self.assertEqual("competition", default.profile)
        self.assertEqual("development", development.profile)

    def test_complete_repo_root_is_a_path_locator(self) -> None:
        parsed = parse_args([
            "complete", "--db", "state.sqlite3", "--run-id", "run",
            "--repo-root", ".",
        ])
        self.assertEqual(Path("."), parsed.repo_root)

    def test_manifest_bound_build_ir_reference_cannot_be_replaced_by_caller(self) -> None:
        reference = {
            "path": "plan/build-ir.json",
            "sha256": "a" * 64,
            "size_bytes": 123,
        }
        manifest = {
            "schema_version": 1,
            "profile": "competition",
            "build_ir": {"status": "bound", "artifact": reference},
        }
        verified = {
            "schema_version": 1,
            "status": "verified",
            "blockers": [],
            "build_ir_sha256": "a" * 64,
            "semantic_sha256": "b" * 64,
            "toolchain_profile": "competition", "closure_complete": True,
            "verified_binding_count": 3,
        }
        with (
            mock.patch(BUILD_VERIFIER, return_value=verified) as verifier,
            mock.patch(
                BUILD_VERIFIER.rsplit(".", 1)[0] + ".verify_manifest_generated_closure",
                return_value=VERIFIED,
            ),
        ):
            result = verify_project_final_build_ir(
                migration_manifest=manifest,
                repo_root=self.harness,
                artifact_root=self.out_root,
            )
        self.assertEqual("verified", result["status"])
        self.assertTrue(
            result["claim_boundary"]["competition_profile_build_ir_verified"],
        )
        self.assertFalse(result["claim_boundary"]["competition_exact"])
        self.assertEqual(reference, verifier.call_args.args[2])
        with self.assertRaises(TypeError):
            verify_project_final_build_ir(
                migration_manifest=manifest,
                repo_root=self.harness,
                artifact_root=self.out_root,
                reference={"path": "caller.json"},
            )

    def test_competition_manifest_requires_existing_repo_root(self) -> None:
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
        result = verify_project_final_build_ir(
            migration_manifest=manifest,
            repo_root=None,
            artifact_root=self.out_root,
        )
        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            [{"kind": "competition_repo_root_missing"}],
            result["blockers"],
        )
        self.assertFalse(
            result["claim_boundary"]["competition_profile_build_ir_verified"],
        )

    def test_legacy_manifest_without_repo_root_is_compatibility_only(self) -> None:
        with self.ledger.connect() as connection:
            _contract, manifest = load_migration_contract(
                self.ledger.path, connection, "run",
            )
        with mock.patch(BUILD_VERIFIER) as verifier:
            result = verify_project_final_build_ir(
                migration_manifest=manifest,
                repo_root=None,
                artifact_root=self.out_root,
            )
        self.assertEqual("compatibility-skipped", result["status"])
        self.assertFalse(
            result["claim_boundary"]["competition_profile_build_ir_verified"],
        )
        self.assertFalse(result["claim_boundary"]["semantic_gate"])
        self.assertFalse(build_ir_allows_completion(result))
        verifier.assert_not_called()

    def test_initial_build_ir_drift_blocks_every_candidate_and_project_runner(self) -> None:
        blocked = {
            "schema_version": 1,
            "status": "blocked",
            "blockers": [{"kind": "build_ir_projection_drift"}],
        }
        result, runners = self._run_completion([blocked])
        self.assertEqual("blocked", result["status"])
        self.assertEqual("project-final-build-ir-verification", result["stage"])
        self.assertEqual(["build_ir_projection_drift"], result["blockers"])
        runners["build_ir"].assert_called_once()
        for name, runner in runners.items():
            if name != "build_ir":
                runner.assert_not_called()

    def test_second_build_ir_drift_blocks_project_final_and_completion_receipt(self) -> None:
        blocked = {
            "schema_version": 1,
            "status": "blocked",
            "blockers": [{"kind": "build_ir_sha256_drift"}],
        }
        result, runners = self._run_completion([VERIFIED, blocked])
        self.assertEqual(2, runners["build_ir"].call_count)
        self.assertEqual("project-final-build-ir-verification", result["stage"])
        self.assertEqual(["build_ir_sha256_drift"], result["blockers"])
        runners["repair"].assert_not_called()
        runners["project_final"].assert_not_called()
        runners["complete"].assert_not_called()
        self.assertFalse(
            (self.out_root / "completion" / "completion-receipt.json").exists(),
        )

    def test_project_logic_mismatch_stops_completion_and_requests_repair(self) -> None:
        semantic = {
            "schema_version": 1,
            "status": "repair-required",
            "blockers": [],
            "candidate_repair": {
                "status": "repair-required", "affected_unit_ids": ["unit"],
            },
        }
        result, runners = self._run_completion(
            [VERIFIED], project_semantic_result=semantic,
        )
        self.assertEqual("waiting", result["status"])
        self.assertEqual("project-final-semantic-repair-ready", result["stage"])
        self.assertEqual(semantic, result["project_semantics"])
        runners["build_ir"].assert_called_once()
        runners["project_final"].assert_not_called()
        runners["complete"].assert_not_called()
        self.assertFalse(
            (self.out_root / "completion" / "completion-receipt.json").exists(),
        )

    def test_success_binds_both_build_ir_verification_artifacts(self) -> None:
        result, runners = self._run_completion([VERIFIED, VERIFIED])
        self.assertEqual(2, runners["build_ir"].call_count)
        first_call, second_call = runners["build_ir"].call_args_list
        self.assertEqual(first_call.args, second_call.args)
        receipt_ref = result["completion_receipt"]
        receipt = json.loads(
            (self.out_root / receipt_ref["path"]).read_text(encoding="utf-8")
        )
        bindings = receipt["build_ir_verifications"]
        self.assertEqual({
            "before_candidate_execution",
            "before_project_final",
        }, set(bindings))
        self.assertEqual(
            "completion/project-final-build-ir-before-candidate-execution.json",
            bindings["before_candidate_execution"]["path"],
        )
        self.assertEqual(
            "completion/project-final-build-ir-before-project-final.json",
            bindings["before_project_final"]["path"],
        )
        self.assertEqual(PROJECT_TEST_EVIDENCE, receipt["project_test_evidence"])
        runners["evidence_reopen"].assert_called_once()

    def test_oracle_evidence_drift_blocks_before_project_final_and_completion(self) -> None:
        result, runners = self._run_completion(
            [VERIFIED, VERIFIED],
            evidence_reopen_error=ValueError("project_test_oracle_artifact_drifted"),
        )
        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "project-final-oracle-evidence-revalidation", result["stage"],
        )
        self.assertEqual(
            ["project_test_oracle_artifact_drifted"], result["blockers"],
        )
        runners["project_final"].assert_not_called()
        runners["complete"].assert_not_called()
        self.assertFalse(
            (self.out_root / "completion" / "completion-receipt.json").exists(),
        )


if __name__ == "__main__":
    unittest.main()
