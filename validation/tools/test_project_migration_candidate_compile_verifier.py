from __future__ import annotations

from pathlib import Path
from unittest import mock

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.controller import ingest_worker_result
from validation.tools._project_migration_harness.candidate_compile_verifier import (
    verify_candidate_compile,
)
from validation.tools._project_migration_harness.candidate_compile_evidence import (
    FIXED_CARGO_CHECK,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    canonical_sha256,
)
from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.integration_validation import (
    existing_state,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)
from validation.tools.project_migration_sandbox_test_support import (
    bind_execution_plan,
)


class ProjectMigrationCandidateCompileVerifierTests(ProjectMigrationControllerCase):
    def test_sandboxed_compile_pass_records_cohort_bound_candidate_gate(self) -> None:
        plan, ledger, unit_id, candidate_id, candidate_sha = self.prepare_candidate()
        result = self.verify(plan, ledger, unit_id, candidate_id, _execution("passed"))
        self.assertEqual("passed", result["status"])
        self.assertEqual("passed", result["gate_status"])
        self.assertTrue(result["candidate_gate_recorded"])
        self.assertFalse(result["semantic_gate"])
        with ledger.connect() as connection:
            row = connection.execute(
                """select status,gate_family,evidence_path,metadata_json
                   from verifier_records where record_id=?""",
                (result["record_id"],),
            ).fetchone()
        self.assertEqual(("passed", "compile"), tuple(row[:2]))
        verdict = self.load(str(row["evidence_path"]))
        self.assertEqual(result["candidate_set_sha256"], verdict["candidate_set_sha256"])
        self.assertEqual(candidate_sha, verdict["candidate_sha256"])
        self.assertEqual(1, len(verdict["source_evidence"]))
        self.assertEqual("candidate-ready", ledger.unit_states(plan["run_id"])[0]["status"])

    def test_runner_uses_detached_generation_without_current_pointer(self) -> None:
        plan, ledger, unit_id, candidate_id, _ = self.prepare_candidate()
        quarantine = self.harness / "target/quarantine-real"
        with mock.patch(
            "validation.tools._project_migration_harness.candidate_compile_verifier."
            "run_cargo_generation_gates",
            side_effect=lambda generation, **_: _bound_execution(
                _execution("passed"), generation,
            ),
        ):
            result = verify_candidate_compile(
                ledger=ledger, run_id=plan["run_id"], unit_id=unit_id,
                candidate_artifact_id=candidate_id,
                candidate_root=self.out_root, candidate_root_rel="target/run",
                quarantine_root=quarantine,
                runtime_root=self.harness / "target/runtime-real",
                out_root=self.out_root, out_root_rel="target/run",
            )
        self.assertEqual("materialized", result["materialization"]["status"])
        generation = quarantine.joinpath(
            *Path(result["materialization"]["generation"]["path"]).parts
        )
        self.assertTrue((generation / "Cargo.toml").is_file())
        self.assertFalse((quarantine / "CURRENT").exists())
        self.assertFalse((quarantine / "RECOVERY").exists())

    def test_missing_sandbox_blocks_without_record_or_repair(self) -> None:
        plan, ledger, unit_id, candidate_id, _ = self.prepare_candidate()
        blocked = {
            "schema_version": 1, "status": "blocked", "checks": [],
            "sandbox": {"status": "blocked", "reason_code": "bubblewrap_unavailable"},
            "diagnostics": [{"code": "bubblewrap_unavailable", "stage": "cargo-sandbox"}],
        }
        result = self.verify(plan, ledger, unit_id, candidate_id, blocked)
        self.assertEqual("blocked", result["status"])
        self.assertEqual("bubblewrap_unavailable", result["reason_code"])
        self.assertFalse(result["candidate_gate_recorded"])
        self.assertEqual(0, self.verification_count(ledger, plan["run_id"]))
        self.assertEqual("candidate-ready", ledger.unit_states(plan["run_id"])[0]["status"])

    def test_forged_sandbox_contract_blocks_without_record(self) -> None:
        plan, ledger, unit_id, candidate_id, _ = self.prepare_candidate()
        execution = _execution("passed")
        execution["sandbox"]["contract"]["resource_limits"]["cpu_seconds"] = 1

        result = self.verify(plan, ledger, unit_id, candidate_id, execution)

        self.assertEqual("blocked", result["status"])
        self.assertEqual("candidate_compile_execution_untrusted", result["reason_code"])
        self.assertFalse(result["candidate_gate_recorded"])
        self.assertEqual(0, self.verification_count(ledger, plan["run_id"]))

    def test_integration_manifest_drift_blocks_before_materialization(self) -> None:
        plan, ledger, unit_id, candidate_id, _ = self.prepare_candidate()
        manifest = self.out_root / "plan/integration-manifest.json"
        manifest.write_text("{}\n", encoding="utf-8")

        with self.assertRaisesRegex(LedgerError, "contract revalidation failed"):
            self.verify(plan, ledger, unit_id, candidate_id, _execution("passed"))

    def test_module_local_compile_failure_records_repair_gate(self) -> None:
        plan, ledger, unit_id, candidate_id, candidate_sha = self.prepare_candidate()
        execution = _execution("failed", candidate_sha=candidate_sha)
        result = self.verify(plan, ledger, unit_id, candidate_id, execution)
        self.assertEqual("failed", result["status"])
        self.assertEqual("failed", result["gate_status"])
        self.assertTrue(result["candidate_gate_recorded"])
        self.assertEqual("retry-ready", ledger.unit_states(plan["run_id"])[0]["status"])

    def test_unattributed_compile_failure_stays_project_scoped(self) -> None:
        plan, ledger, unit_id, candidate_id, _ = self.prepare_candidate()
        execution = _execution("failed", candidate_sha=None)
        result = self.verify(plan, ledger, unit_id, candidate_id, execution)
        self.assertEqual("project-repair-required", result["status"])
        self.assertFalse(result["candidate_gate_recorded"])
        self.assertEqual(0, self.verification_count(ledger, plan["run_id"]))
        self.assertEqual("candidate-ready", ledger.unit_states(plan["run_id"])[0]["status"])

    def prepare_candidate(self) -> tuple[dict, object, str, str, str]:
        plan = self.plan("int unit(void) { return 1; }\n")
        ledger = self.ledger()
        launch = self.dispatch(plan, ledger)["launches"][0]
        request = self.request(launch)
        recorded = ingest_worker_result(
            self.common(request) | {"candidate_source": "pub fn unit() -> i32 { 1 }\n"},
            ledger=ledger, harness_root=self.harness,
            run_id=plan["run_id"], worker_id=launch["worker_id"],
        )
        candidate_id = str(recorded["artifact_id"])
        candidate = next(
            item for item in ledger.orchestration_rows(plan["run_id"])["artifacts"]
            if item["artifact_id"] == candidate_id
        )
        return plan, ledger, str(launch["unit_id"]), candidate_id, str(candidate["content_sha256"])

    def verify(
        self, plan: dict, ledger: object, unit_id: str,
        candidate_id: str, execution: dict,
    ) -> dict:
        with mock.patch(
            "validation.tools._project_migration_harness.candidate_compile_verifier."
            "run_cargo_generation_gates",
            side_effect=lambda generation, **_: _bound_execution(
                execution, generation,
            ),
        ):
            return verify_candidate_compile(
                ledger=ledger, run_id=plan["run_id"], unit_id=unit_id,
                candidate_artifact_id=candidate_id,
                candidate_root=self.out_root, candidate_root_rel="target/run",
                quarantine_root=self.harness / "target/quarantine",
                runtime_root=self.harness / "target/runtime",
                out_root=self.out_root, out_root_rel="target/run",
            )

    @staticmethod
    def verification_count(ledger: object, run_id: str) -> int:
        with ledger.connect() as connection:
            return int(connection.execute(
                "select count(*) from verifier_records where run_id=?", (run_id,),
            ).fetchone()[0])


def _execution(status: str, *, candidate_sha: str | None = None) -> dict:
    sandbox_contract = SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256=content_sha256("sandbox-launcher"),
        toolchain_sha256=content_sha256("toolchain"),
    )
    contract = sandbox_contract.sha256
    failed = status == "failed"
    diagnostic = {
        "code": "rustc-type-error", "stage": "cargo-check",
        "message": "type mismatch", "line": 1, "column": 1,
    }
    if candidate_sha is not None:
        diagnostic["file"] = f"src/unit_{candidate_sha}.rs"
    return {
        "schema_version": 1, "status": status,
        "project_state_unchanged": True,
        "checks": [{
            "command": list(FIXED_CARGO_CHECK), "status": status,
            "cargo_executed": True, "returncode": 1 if failed else 0,
            "timed_out": False,
            "stdout_sha256": content_sha256("stdout"),
            "stderr_sha256": content_sha256("stderr"),
            "sandbox_contract_sha256": contract,
            "sandbox_command_sha256": canonical_sha256(FIXED_CARGO_CHECK),
            "sandbox_launcher_argv_sha256": content_sha256("argv"),
            "diagnostics": [diagnostic] if failed else [],
        }],
        "sandbox": {
            "status": "executed", "contract_sha256": contract,
            "contract": sandbox_contract.payload(),
        },
        "diagnostics": [],
    }


def _bound_execution(execution: dict, generation: Path) -> dict:
    if execution.get("status") == "blocked":
        return execution
    input_sha256, managed = existing_state(generation)
    if not managed:
        raise AssertionError("test quarantine generation is not managed")
    return bind_execution_plan(execution, input_sha256)


if __name__ == "__main__":
    import unittest
    unittest.main()
