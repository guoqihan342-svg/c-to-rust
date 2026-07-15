from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_candidate_verification import (
    verify_candidate_project,
)
from validation.tools._project_migration_harness.project_verification import (
    run_cargo_generation_gates,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


MODULE = (
    "validation.tools._project_migration_harness."
    "project_candidate_verification"
)
EVIDENCE = f"{MODULE}_evidence"
PROJECT_VERIFICATION = (
    "validation.tools._project_migration_harness.project_verification"
)
VERIFIED_BUILD_IR = {"schema_version": 1, "status": "verified", "blockers": []}
NATIVE_BUILD_IR = {
    "schema_version": 1,
    "status": "blocked",
    "blockers": [{"kind": "native_link_config_unresolved"}],
    "native_link_config_resolved": False,
    "unresolved_native_dependency_count": 1,
}


class ProjectCandidateVerificationTests(ProjectMigrationControllerCase):
    def setUp(self) -> None:
        super().setUp()
        self.out_root.mkdir(parents=True)
        self.quarantine_root = self.harness / "target/candidate-quarantine"
        self.runtime_root = self.harness / "target/candidate-runtime"
        self.ledger_path = self.out_root / "state/project-migration.sqlite3"
        self.ir = {
            "ir_sha256": "a" * 64,
            "interface_sha256": "b" * 64,
            "native_link_requirements": [],
        }

    def test_native_trace_without_raw_capture_is_rejected_before_execution(self) -> None:
        with mock.patch(
            f"{PROJECT_VERIFICATION}._run_managed_cargo",
        ) as cargo_runner:
            with self.assertRaisesRegex(ValueError, "requires raw Cargo output"):
                run_cargo_generation_gates(
                    self.root / "generation-does-not-need-to-exist",
                    runtime_root=self.runtime_root,
                    capture_raw_output=False,
                    capture_native_link_trace=True,
                )
        cargo_runner.assert_not_called()

    def test_non_native_build_ir_blocker_runs_zero_cargo(self) -> None:
        blocker = {
            "schema_version": 1,
            "status": "blocked",
            "blockers": [{"kind": "generated_input_missing"}],
        }
        with self.pipeline(build_ir=blocker) as calls:
            result = self.verify()
        self.assertEqual("candidate_build_ir_blocked", result["reason_code"])
        self.assertEqual(["generated_input_missing"], result["blockers"])
        calls["materialize"].assert_not_called()
        calls["cargo"].assert_not_called()
        self.assert_candidate_only(result, cargo_executed=False)

    def test_detached_success_never_writes_final_state(self) -> None:
        execution = self.execution()
        bound = (execution, {}, self.observations(), {
            "cargo-check": "passed", "cargo-test": "passed",
        })
        with self.pipeline(execution=execution, bound=bound) as calls:
            result = self.verify()
        self.assertEqual("candidate-verified", result["status"])
        self.assertFalse((self.quarantine_root / "CURRENT").exists())
        self.assertFalse(self.ledger_path.exists())
        calls["cargo"].assert_called_once()
        self.assert_candidate_only(result)

    def test_native_candidate_forces_raw_trace_and_unresolved_stays_blocked(self) -> None:
        self.ir["native_link_requirements"] = [{"requirement_id": "native-lib"}]
        execution = self.execution()
        bound = (execution, {}, self.observations(), {
            "cargo-check": "passed", "cargo-test": "passed",
        })
        unresolved = {"schema_version": 1, "status": "blocked"}
        with self.pipeline(
            build_ir=NATIVE_BUILD_IR, execution=execution, bound=bound,
            native=unresolved,
        ) as calls:
            result = self.verify()
        self.assertEqual("blocked", result["status"])
        self.assertEqual(unresolved, result["native_link_settlement"])
        cargo_kwargs = calls["cargo"].call_args.kwargs
        self.assertIs(True, cargo_kwargs["capture_raw_output"])
        self.assertIs(True, cargo_kwargs["capture_native_link_trace"])
        self.assert_candidate_only(result)

    def test_post_cargo_evidence_failure_preserves_executed_state(self) -> None:
        execution = self.execution()
        with self.pipeline(execution=execution, bind_error=OSError("disk full")):
            result = self.verify()
        self.assertEqual("candidate_cargo_evidence_invalid", result["reason_code"])
        self.assert_candidate_only(result, cargo_executed=True)

    def test_missing_or_duplicate_check_cannot_be_candidate_verified(self) -> None:
        cases = {
            "missing-test": [["cargo", "check"]],
            "duplicate-check": [
                ["cargo", "check"], ["cargo", "check"],
                ["cargo", "test"],
            ],
        }
        for name, commands in cases.items():
            with self.subTest(name=name):
                execution = self.execution(commands)
                with (
                    self.pipeline(execution=execution, real_bind=True),
                    mock.patch(
                        f"{EVIDENCE}.persist_captured_native_link_trace",
                        side_effect=lambda value, **_: dict(value),
                    ),
                    mock.patch(
                        f"{EVIDENCE}.persist_captured_cargo_outputs",
                        side_effect=lambda value, **_: dict(value),
                    ),
                    mock.patch(
                        f"{EVIDENCE}.project_cargo_observation",
                        side_effect=lambda _execution, check, **_: {
                            "check_present": check is not None,
                        },
                    ),
                    mock.patch(
                        f"{EVIDENCE}.derive_project_cargo_status",
                        side_effect=lambda _gate, observation: (
                            "passed" if observation["check_present"] else "blocked"
                        ),
                    ),
                ):
                    result = self.verify()
                self.assertEqual("blocked", result["status"])
                self.assertNotEqual("candidate-verified", result["status"])
                self.assert_candidate_only(result)

    def verify(self) -> dict:
        return verify_candidate_project(
            run_id="candidate-project-run",
            migration_contract={"schema_version": 1},
            rust_project_ir=self.ir,
            candidate_descriptors=[],
            candidate_set_sha256="c" * 64,
            candidate_set_manifest={"schema_version": 1, "members": []},
            migration_manifest={"schema_version": 1},
            repo_root=self.source,
            artifact_root=self.out_root,
            quarantine_root=self.quarantine_root,
            runtime_root=self.runtime_root,
            ledger_path=self.ledger_path,
            out_root=self.out_root,
            out_root_rel="target/run",
        )

    @contextmanager
    def pipeline(
        self, *, build_ir: dict = VERIFIED_BUILD_IR,
        execution: dict | None = None, bound: tuple | None = None,
        native: dict | None = None, bind_error: Exception | None = None,
        real_bind: bool = False,
    ):
        execution = execution or self.execution()
        bound = bound or (execution, {}, self.observations(), {
            "cargo-check": "passed", "cargo-test": "passed",
        })
        generation = self.quarantine_root / "generations/candidate-generation"
        generation.mkdir(parents=True, exist_ok=True)
        materialized = {
            "schema_version": 1,
            "status": "materialized",
            "generation": {
                "path": "generations/candidate-generation",
                "sha256": "d" * 64,
                "immutable": True,
            },
            "last_good_updated": False,
            "cargo_executed": False,
        }
        with (
            mock.patch(
                f"{MODULE}.reopen_rust_project_ir_bindings",
                return_value={"bindings_sha256": "e" * 64},
            ) as reopen,
            mock.patch(
                f"{MODULE}.verify_project_final_build_ir",
                return_value=build_ir,
            ) as verify_build_ir,
            mock.patch(
                f"{MODULE}.validate_candidate_project_domain",
                return_value={
                    "run_id": "candidate-project-run",
                    "run_context_sha256": "1" * 64,
                    "dag_sha256": "2" * 64,
                    "integration_manifest": {
                        "path": "plan/dag.json", "sha256": "3" * 64,
                        "size_bytes": 1,
                    },
                    "candidate_set_sha256": "c" * 64,
                    "candidate_set_manifest_sha256": "4" * 64,
                    "rust_project_ir_sha256": "a" * 64,
                    "rust_project_interface_sha256": "b" * 64,
                    "rust_project_binding_sha256": "e" * 64,
                    "candidate_domain_context_sha256": "5" * 64,
                },
            ),
            mock.patch(
                f"{MODULE}.validate_candidate_project_verification",
                side_effect=lambda value: dict(value),
            ),
            mock.patch(
                f"{MODULE}.materialize_rust_project_ir_quarantine_generation",
                return_value=materialized,
            ) as materialize,
            mock.patch(
                f"{MODULE}.run_cargo_generation_gates", return_value=execution,
            ) as cargo,
            mock.patch(
                f"{MODULE}.settle_candidate_native_links",
                return_value=native,
            ) if native is not None else mock.patch(
                f"{MODULE}.settle_candidate_native_links",
                wraps=__import__(MODULE, fromlist=["settle_candidate_native_links"]).settle_candidate_native_links,
            ),
            mock.patch(
                f"{MODULE}.bind_candidate_cargo_evidence",
                side_effect=bind_error, return_value=bound,
            ) if not real_bind else mock.patch(
                f"{MODULE}.bind_candidate_cargo_evidence",
                wraps=__import__(MODULE, fromlist=["bind_candidate_cargo_evidence"]).bind_candidate_cargo_evidence,
            ),
        ):
            yield {
                "reopen": reopen, "build_ir": verify_build_ir,
                "materialize": materialize, "cargo": cargo,
            }

    @staticmethod
    def execution(commands: list[list[str]] | None = None) -> dict:
        commands = commands or [["cargo", "check"], ["cargo", "test"]]
        return {
            "schema_version": 1,
            "status": "passed",
            "cargo_executed": True,
            "project_input_sha256": "f" * 64,
            "checks": [{"command": command, "status": "passed"}
                       for command in commands],
        }

    @staticmethod
    def observations() -> dict[str, dict[str, object]]:
        return {
            "cargo-check": {"outcome": "executed"},
            "cargo-test": {"outcome": "executed"},
        }

    def assert_candidate_only(
        self, result: dict, *, cargo_executed: bool | None = None,
    ) -> None:
        self.assertEqual({
            "final_current_updated": False,
            "project_gate_records_written": 0,
            "candidate_only": True,
        }, result["state_effects"])
        self.assertEqual({
            "candidate_project_gate": result["status"] == "candidate-verified",
            "final_project_gate": False,
            "updates_final_current": False,
            "writes_project_gate_records": False,
            "semantic_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        }, result["claim_boundary"])
        if cargo_executed is not None:
            self.assertIs(cargo_executed, result["cargo_executed"])


if __name__ == "__main__":
    unittest.main()
