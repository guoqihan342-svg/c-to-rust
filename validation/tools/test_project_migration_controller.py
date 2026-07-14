import unittest
from unittest import mock
from copy import deepcopy
from pathlib import PurePosixPath

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
from validation.tools._project_migration_harness.integration_validation import (
    existing_state,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract, canonical_sha256,
)
from validation.tools.project_migration_controller_test_support import ProjectMigrationControllerCase
from validation.tools.project_migration_sandbox_test_support import (
    bind_cargo_output, bind_execution_plan, cargo_compiler_message,
)
from validation.tools.project_migration_project_diagnostic_test_support import verify_project_compile_intake


class ProjectMigrationControllerTests(ProjectMigrationControllerCase):
    def test_dispatch_materializes_context_before_lease_and_binds_request(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        assignment = plan["portfolio"]["assignments"][0]
        pages = [
            self.harness.joinpath(*PurePosixPath(item["path"]).parts)
            for item in assignment["context"]["pages"]
        ]
        self.assertTrue(pages)
        self.assertTrue(all(not page.exists() for page in pages))

        dispatched = self.dispatch(plan, self.ledger())

        self.assertTrue(all(page.is_file() for page in pages))
        launch = dispatched["launches"][0]
        request = self.request(launch)
        self.assertEqual(
            dispatched["context_materialization"],
            request["context_materialization"],
        )

    def test_catalog_drift_creates_no_attempt_or_lease(self) -> None:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        catalog = plan["portfolio"]["assignments"][0]["context"]["catalog"]
        self.harness.joinpath(*PurePosixPath(catalog["path"]).parts).write_text(
            "{}\n", encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
            self.dispatch(plan, ledger)
        with ledger.connect() as connection:
            attempts = connection.execute(
                "select count(*) from attempts where run_id=?", (plan["run_id"],)
            ).fetchone()[0]
            leases = connection.execute(
                "select count(*) from leases where run_id=?", (plan["run_id"],)
            ).fetchone()[0]
        self.assertEqual((0, 0), (attempts, leases))

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
        ordered = ["compile", *sorted(CANDIDATE_REQUIRED_GATES - {"compile"})]
        for index, family in enumerate(ordered):
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
        self.assertEqual("failed", integration_gate["gate_status"])
        self.assertTrue(integration_gate["verification"]["matched_candidate_set"])
        self.assertFalse(integration_gate["verification"]["interface_complete"])
        integration_evidence = self.load(integration_gate["evidence"]["path"])
        self.assertIn(
            "integration_interface_incomplete",
            integration_evidence["diagnostic_codes"],
        )
        project_input_sha256, managed = existing_state(project)
        self.assertTrue(managed)
        contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256="1" * 64,
            toolchain_sha256="2" * 64,
        )
        cargo_execution = bind_execution_plan({
            "schema_version": 1,
            "status": "passed",
            "cargo_executed": True,
            "project_input_sha256": project_input_sha256,
            "project_state_before": project_input_sha256,
            "project_state_after": project_input_sha256,
            "project_state_unchanged": True,
            "checks": [
                {
                    "command": CARGO_COMMANDS[f"cargo-{command}"],
                    "status": "passed",
                    "returncode": 0,
                    "timed_out": False,
                    "cargo_executed": True,
                    "stdout_sha256": "3" * 64,
                    "stderr_sha256": "4" * 64,
                    "sandbox_contract_sha256": contract.sha256,
                    "sandbox_command_sha256": canonical_sha256(
                        CARGO_COMMANDS[f"cargo-{command}"],
                    ),
                    "sandbox_launcher_argv_sha256": "5" * 64,
                    "diagnostics": [],
                }
                for command in ("check", "test")
            ],
            "sandbox": {
                "status": "executed",
                "contract": contract.payload(),
                "contract_sha256": contract.sha256,
            },
            "diagnostics": [],
        }, project_input_sha256)
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
        duplicate_execution = deepcopy(cargo_execution)
        duplicate_execution["checks"].append(
            deepcopy(duplicate_execution["checks"][0]),
        )
        with mock.patch(
            "validation.tools._project_migration_harness.project_cargo_verifier."
            "run_cargo_project_gates",
            return_value=duplicate_execution,
        ):
            duplicate_gate = verify_project_cargo(
                ledger=ledger,
                run_id=plan["run_id"],
                project_root=project,
                runtime_root=self.harness / "target/cargo-runtime-duplicate",
                out_root=self.out_root,
                out_root_rel="target/run",
            )
        self.assertEqual("failed", duplicate_gate["status"])
        project_failed = verify_project_compile_intake(
            ledger=ledger, run_id=plan["run_id"], project_root=project,
            harness_root=self.harness, out_root=self.out_root,
            cargo_execution=cargo_execution,
        )
        self.assertEqual([], project_failed["candidate_repair_gates"])
        self.assertEqual(1, len(project_failed["project_diagnostic_intakes"]))
        intakes = ledger.latest_project_diagnostic_intakes(
            run_id=plan["run_id"],
            candidate_set_sha256=integrated["candidate_set_sha256"],
            rust_project_ir_sha256=integrated["rust_project_ir_sha256"],
            project_input_sha256=project_input_sha256,
        )
        self.assertEqual(1, len(intakes))
        candidate_sha = next(
            item["content_sha256"]
            for item in ledger.orchestration_rows(plan["run_id"])["artifacts"]
            if item["artifact_id"] == candidate_id
        )
        failed_check = deepcopy(cargo_execution["checks"][0])
        failed_check.update({"status": "failed", "returncode": 1})
        bind_cargo_output(
            failed_check,
            stdout=cargo_compiler_message(
                code="rustc-type-error", message="type mismatch",
                file=f"src/unit_{candidate_sha}.rs",
            ),
        )
        failed_execution = {
            **deepcopy(cargo_execution),
            "status": "failed",
            "checks": [failed_check],
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
