from __future__ import annotations

from copy import deepcopy
import json

from validation.tools._project_migration_harness.controller import (
    ingest_worker_result,
    promote_verified_candidate,
)
from validation.tools._project_migration_harness.candidate_final_verifier import (
    verify_candidate_final,
)
from validation.tools._project_migration_harness.candidate_semantic_context import (
    current_semantic_context,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.orchestrator import plan_project
from validation.tools._project_migration_harness.project_completion_build_ir import (
    verify_project_final_build_ir,
)
from validation.tools._project_migration_harness.worker_result_contracts import (
    normalize_worker_result,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


EXPECTED_ADMISSION = {
    "admission_scope": "candidate-only",
    "quarantine_required": True,
    "promotion_requires": ["generated_build_closure_verified"],
}


class ProjectMigrationCandidateAdmissionTests(ProjectMigrationControllerCase):
    def incomplete_plan(self, *, required: bool = True) -> dict:
        source_path = self.source / "unit.c"
        source_path.write_text("int unit(void) { return 1; }\n", encoding="utf-8")
        database = self.source / "compile_commands.json"
        database.write_text(json.dumps([{
            "directory": ".",
            "file": "unit.c",
            "arguments": ["clang", "-c", "unit.c", "-o", "unit.o"],
            "output": "unit.o",
        }]), encoding="utf-8")
        return plan_project(
            self.source,
            harness_root=self.harness,
            out_root="target/run",
            compile_database=database,
            run_id="candidate-admission-run",
            max_concurrency=2,
            require_build_closure=required,
        )

    def test_plan_binds_candidate_only_scope_without_semantic_credit(self) -> None:
        plan = self.incomplete_plan()

        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertEqual("dispatch_candidate_only_workers", plan["execution"]["next_action"])
        self.assertEqual("candidate-only", plan["execution"]["candidate_admission_scope"])
        self.assertFalse(plan["execution"]["candidate_promotion_allowed"])
        self.assertTrue(plan["scheduler"]["ready_worker_ids"])
        self.assertEqual(0, plan["claim_boundary"]["translation_coverage_numerator"])
        self.assertFalse(plan["claim_boundary"]["semantic_gate"])
        for assignment in plan["portfolio"]["assignments"]:
            self.assertEqual(
                EXPECTED_ADMISSION,
                {key: assignment["launch_policy"][key] for key in EXPECTED_ADMISSION},
            )
            self.assertEqual(
                64, len(assignment["launch_policy"]["admission_binding_sha256"]),
            )

    def test_bounded_source_remains_candidate_only_when_closure_is_incomplete(self) -> None:
        plan = self.incomplete_plan(required=False)

        self.assertFalse(plan["execution"]["build_closure_ready"])
        self.assertEqual("candidate-only", plan["execution"]["candidate_admission_scope"])
        self.assertFalse(plan["execution"]["candidate_promotion_allowed"])
        self.assertEqual("dispatch_candidate_only_workers", plan["execution"]["next_action"])

    def test_candidate_is_quarantined_and_lower_authority_rejects_promotion(self) -> None:
        plan = self.incomplete_plan()
        ledger = self.ledger()
        launch = next(
            item for item in self.dispatch(plan, ledger)["launches"]
            if item["role"] == "translator"
        )
        request = self.request(launch)
        self.assertEqual(
            EXPECTED_ADMISSION,
            {key: request["output_contract"][key] for key in EXPECTED_ADMISSION},
        )
        self.assertEqual(64, len(request["output_contract"]["admission_binding_sha256"]))
        response = self.common(request) | {
            "candidate_source": "pub fn unit() -> i32 { 1 }\n",
        }

        malformed = deepcopy(request)
        malformed["launch_policy"]["quarantine_required"] = False
        with self.assertRaisesRegex(ValueError, "candidate admission policy"):
            normalize_worker_result(malformed, response)

        recorded = ingest_worker_result(
            response,
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=launch["worker_id"],
        )
        artifact = next(
            item for item in ledger.orchestration_rows(plan["run_id"])["artifacts"]
            if item["artifact_id"] == recorded["artifact_id"]
        )
        metadata = json.loads(artifact["metadata_json"])
        self.assertEqual(
            EXPECTED_ADMISSION,
            {key: metadata[key] for key in EXPECTED_ADMISSION},
        )
        self.assertEqual(64, len(metadata["admission_binding_sha256"]))
        with self.assertRaisesRegex(LedgerError, "candidate-only artifact"):
            promote_verified_candidate(
                ledger=ledger,
                run_id=plan["run_id"],
                unit_id=launch["unit_id"],
                candidate_artifact_id=recorded["artifact_id"],
                verifier_record_id="compile-record",
                gate_record_id="final-record",
            )
        with self.assertRaisesRegex(LedgerError, "candidate-only artifact"):
            current_semantic_context(
                ledger, plan["run_id"], launch["unit_id"],
                recorded["artifact_id"], "wave-provisional",
            )
        with self.assertRaisesRegex(LedgerError, "candidate-only artifact"):
            verify_candidate_final(
                ledger=ledger,
                out_root=self.out_root,
                out_root_rel="target/run",
                run_id=plan["run_id"],
                unit_id=launch["unit_id"],
                candidate_artifact_id=recorded["artifact_id"],
            )
        state = ledger.unit_states(plan["run_id"])[0]
        self.assertEqual("candidate-ready", state["status"])
        self.assertNotEqual("last_good", state["resumable_status"])
        manifest = self.load("target/run/plan/integration-manifest.json")
        completion = verify_project_final_build_ir(
            migration_manifest=manifest,
            repo_root=self.source,
            artifact_root=self.out_root,
        )
        self.assertEqual("blocked", completion["status"])
        self.assertEqual(
            "generated_build_closure_not_bound",
            completion["blockers"][0]["kind"],
        )

    def test_semantic_admission_metadata_must_match_bound_manifest(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        launch = next(
            item for item in self.dispatch(plan, ledger)["launches"]
            if item["role"] == "translator"
        )
        request = self.request(launch)
        self.assertEqual("semantic-eligible", request["launch_policy"]["admission_scope"])
        recorded = ingest_worker_result(
            self.common(request) | {
                "candidate_source": "pub fn unit() -> i32 { 1 }\n",
            },
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=launch["worker_id"],
        )
        artifact_id = recorded["artifact_id"]
        with ledger.connect() as connection:
            row = connection.execute(
                "select metadata_json from artifacts where artifact_id=?",
                (artifact_id,),
            ).fetchone()
            metadata = json.loads(row["metadata_json"])
            metadata["admission_binding_sha256"] = "0" * 64
            connection.execute(
                "update artifacts set metadata_json=? where artifact_id=?",
                (json.dumps(metadata, sort_keys=True), artifact_id),
            )
        with self.assertRaisesRegex(LedgerError, "admission binding drifted"):
            promote_verified_candidate(
                ledger=ledger,
                run_id=plan["run_id"],
                unit_id=launch["unit_id"],
                candidate_artifact_id=artifact_id,
                verifier_record_id="compile-record",
                gate_record_id="final-record",
            )


if __name__ == "__main__":
    import unittest
    unittest.main()
