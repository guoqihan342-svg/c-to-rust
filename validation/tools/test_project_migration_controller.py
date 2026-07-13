import unittest
from unittest import mock

from validation.tools._project_migration_harness.controller import (
    ingest_worker_result,
    integrate_verified_project,
    promote_verified_candidate,
    verify_integrated_project,
    verify_project_cargo,
)
from validation.tools._project_migration_harness.ledger_verifier import (
    CANDIDATE_REQUIRED_GATES,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


class ProjectMigrationControllerTests(ProjectMigrationControllerCase):
    def test_candidate_review_gates_last_good_and_cargo_reconstruction(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        translator = self.dispatch(plan, ledger)["launches"][0]
        self.assertEqual("translator", translator["role"])
        request = self.request(translator)
        candidate = self.common(request) | {
            "candidate_source": "pub fn unit() -> i32 { 1 }\n",
        }
        recorded = ingest_worker_result(
            candidate,
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=translator["worker_id"],
        )
        candidate_id = recorded["artifact_id"]

        reviewer = self.dispatch(plan, ledger)["launches"][0]
        self.assertEqual("reviewer", reviewer["role"])
        review_request = self.request(reviewer)
        review = self.common(review_request) | {
            "candidate_artifact_sha256": review_request["input_facts"][
                "candidate_artifact_sha256"
            ],
            "findings": [],
        }
        ingest_worker_result(
            review,
            ledger=ledger,
            harness_root=self.harness,
            run_id=plan["run_id"],
            worker_id=reviewer["worker_id"],
        )

        verifier_ids = []
        for index, family in enumerate(sorted(CANDIDATE_REQUIRED_GATES)):
            record_id = f"verify-{index}-{family}"
            verifier_ids.append(record_id)
            self.host_pass(
                ledger, plan["run_id"], translator["unit_id"], candidate_id,
                record_id, family,
            )
        self.host_pass(
            ledger, plan["run_id"], translator["unit_id"], candidate_id,
            "final-gate", "final-verification",
        )
        promoted = promote_verified_candidate(
            ledger=ledger,
            run_id=plan["run_id"],
            unit_id=translator["unit_id"],
            candidate_artifact_id=candidate_id,
            verifier_record_id=verifier_ids[0],
            gate_record_id="final-gate",
        )
        self.assertEqual("last-good", promoted["status"])
        self.assertEqual("last_good", ledger.unit_states(plan["run_id"])[0]["resumable_status"])

        manifest = self.load("target/run/plan/integration-manifest.json")
        project = self.harness / "target/generated-project"
        integrated = integrate_verified_project(
            manifest,
            ledger=ledger,
            run_id=plan["run_id"],
            candidate_root=self.out_root,
            candidate_root_rel="target/run",
            project_root=project,
        )
        self.assertEqual("integrated", integrated["status"])
        self.assertEqual(
            ledger.bind_current_candidate_set(run_id=plan["run_id"]),
            integrated["candidate_set_sha256"],
        )
        self.assertIn("candidate_descriptor_sha256", integrated)
        self.assertTrue((project / "Cargo.toml").is_file())
        self.assertTrue((project / "Cargo.lock").is_file())
        self.assertFalse(integrated["semantic_gate"])
        integration_gate = verify_integrated_project(
            ledger=ledger,
            run_id=plan["run_id"],
            project_root=project,
            out_root=self.out_root,
            out_root_rel="target/run",
        )
        self.assertEqual("passed", integration_gate["gate_status"])
        self.assertTrue(integration_gate["verification"]["matched_candidate_set"])
        cargo_execution = {
            "schema_version": 1,
            "status": "passed",
            "checks": [
                {
                    "command": ["cargo", command],
                    "status": "passed",
                    "returncode": 0,
                    "timed_out": False,
                    "cargo_executed": True,
                    "diagnostics": [],
                }
                for command in ("check", "test")
            ],
            "sandbox": {
                "status": "executed",
                "contract": {
                    "backend": "bubblewrap-v1",
                    "network": "unshared",
                    "project_input": "read-only",
                },
            },
            "diagnostics": [],
        }
        with mock.patch(
            "validation.tools._project_migration_harness.project_cargo_verifier."
            "run_cargo_project_gates",
            return_value=cargo_execution,
        ):
            cargo_gate = verify_project_cargo(
                ledger=ledger,
                run_id=plan["run_id"],
                project_root=project,
                runtime_root=self.harness / "target/cargo-runtime",
                out_root=self.out_root,
                out_root_rel="target/run",
            )
        self.assertEqual("passed", cargo_gate["status"])
        self.assertEqual(
            ["passed", "passed"],
            [item["gate_status"] for item in cargo_gate["records"]],
        )
        candidate_sha = next(
            item["content_sha256"]
            for item in ledger.orchestration_rows(plan["run_id"])["artifacts"]
            if item["artifact_id"] == candidate_id
        )
        failed_execution = {
            **cargo_execution,
            "status": "failed",
            "checks": [{
                "command": ["cargo", "check"],
                "status": "failed",
                "returncode": 1,
                "timed_out": False,
                "cargo_executed": True,
                "diagnostics": [{
                    "code": "rustc-type-error",
                    "stage": "cargo-check",
                    "message": "type mismatch",
                    "file": f"src/unit_{candidate_sha}.rs",
                    "line": 1,
                    "column": 1,
                }],
            }],
        }
        with mock.patch(
            "validation.tools._project_migration_harness.project_cargo_verifier."
            "run_cargo_project_gates",
            return_value=failed_execution,
        ):
            failed_cargo = verify_project_cargo(
                ledger=ledger,
                run_id=plan["run_id"],
                project_root=project,
                runtime_root=self.harness / "target/cargo-runtime-2",
                out_root=self.out_root,
                out_root_rel="target/run",
            )
        self.assertEqual("failed", failed_cargo["status"])
        self.assertEqual(1, len(failed_cargo["candidate_repair_gates"]))
        self.assertEqual(
            "retry-ready", ledger.unit_states(plan["run_id"])[0]["status"]
        )

if __name__ == "__main__":
    unittest.main()
