from __future__ import annotations

import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_completion_coordinator import (
    resume_project_completion,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


class ProjectMigrationCompletionCoordinatorTests(
    ProjectMigrationGateAuthorityCase,
):
    def _verified_build_ir(self):
        return mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.verify_project_final_build_ir",
            return_value={
                "schema_version": 1,
                "status": "verified",
                "blockers": [],
                "native_link_config_resolved": True,
                "unresolved_native_dependency_count": 0,
            },
        )

    def test_fixed_paths_and_project_final_scope_reach_first_semantic_runner(self) -> None:
        self.promote_current_candidate()
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.verify_candidate_compile",
            return_value={"schema_version": 1, "status": "passed"},
        ) as compile_runner, mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.run_oracle_replay_diff_candidate",
            return_value={
                "schema_version": 1, "status": "blocked",
                "reason_code": "semantic_adapter_unavailable",
            },
        ) as semantic_runner:
            with self._verified_build_ir():
                result = resume_project_completion(
                    ledger=self.ledger, run_id="run", harness_root=self.harness,
                )
        self.assertEqual("blocked", result["status"])
        self.assertEqual("project-final-oracle-replay-diff", result["stage"])
        self.assertEqual(
            ["unit:oracle-replay-diff:semantic_adapter_unavailable"],
            result["blockers"],
        )
        kwargs = compile_runner.call_args.kwargs
        self.assertEqual("project-final", kwargs["verification_scope"])
        self.assertEqual(self.out_root.resolve(), kwargs["candidate_root"].resolve())
        self.assertEqual(
            (self.out_root / "completion" / "quarantine").resolve(),
            kwargs["quarantine_root"].resolve(),
        )
        self.assertEqual(
            (self.out_root / "completion" / "runtime").resolve(),
            kwargs["runtime_root"].resolve(),
        )
        semantic_kwargs = semantic_runner.call_args.kwargs
        self.assertEqual("project-final", semantic_kwargs["verification_scope"])
        self.assertEqual(self.out_root.resolve(), semantic_kwargs["out_root"].resolve())
        with self.ledger.connect() as connection:
            status = connection.execute(
                "select status from project_runs where run_id='run'"
            ).fetchone()[0]
        self.assertEqual("active", status)

    def test_semantic_runners_have_fixed_order_before_candidate_final(self) -> None:
        self.promote_current_candidate()
        calls = []

        def passed(name):
            def run(**kwargs):
                calls.append((name, kwargs["verification_scope"]))
                return {"schema_version": 1, "status": "passed"}
            return run

        patches = [
            mock.patch(
                "validation.tools._project_migration_harness."
                f"project_completion_coordinator.{name}", side_effect=passed(family),
            )
            for name, family in (
                ("run_oracle_replay_diff_candidate", "oracle-replay-diff"),
                ("run_negative_candidate", "negative"),
                ("run_unsafe_alias_candidate", "unsafe-alias"),
                ("run_abi_layout_candidate", "abi-layout"),
            )
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.verify_candidate_compile",
            return_value={"schema_version": 1, "status": "passed"},
        ), mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator._missing_candidate_semantic_gates",
            return_value=["stop-before-final"],
        ), self._verified_build_ir():
            result = resume_project_completion(
                ledger=self.ledger, run_id="run", harness_root=self.harness,
            )
        self.assertEqual([
            ("oracle-replay-diff", "project-final"),
            ("negative", "project-final"),
            ("unsafe-alias", "project-final"),
            ("abi-layout", "project-final"),
        ], calls)
        self.assertEqual("project-final-semantic-runners", result["stage"])

    def test_incomplete_units_wait_without_running_candidate_code(self) -> None:
        with mock.patch(
            "validation.tools._project_migration_harness."
            "project_completion_coordinator.verify_candidate_compile",
        ) as compile_runner:
            result = resume_project_completion(
                ledger=self.ledger, run_id="run", harness_root=self.harness,
            )
        self.assertEqual("waiting", result["status"])
        self.assertEqual("awaiting-all-last-good", result["stage"])
        compile_runner.assert_not_called()

    def test_partial_rust_project_ir_blocks_project_final_publication(self) -> None:
        self.promote_current_candidate()
        passed = {"schema_version": 1, "status": "passed"}
        partial = {
            "schema_version": 1, "status": "integrated",
            "rust_project_ir_completeness": {
                "status": "partial",
                "unresolved_sections": ["public-signature", "shared-type-layout"],
            },
        }
        with (
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_completion_coordinator.verify_candidate_compile",
                return_value=passed,
            ),
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_completion_coordinator._semantic_runner",
                return_value=lambda **_: passed,
            ),
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_completion_coordinator._missing_candidate_semantic_gates",
                return_value=[],
            ),
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_completion_coordinator.verify_candidate_final",
                return_value=passed,
            ),
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_completion_coordinator.integrate_verified_project",
                return_value=partial,
            ) as integration_runner,
            mock.patch(
                "validation.tools._project_migration_harness."
                "project_completion_coordinator.verify_integrated_project",
            ) as integration_gate,
            self._verified_build_ir(),
        ):
            result = resume_project_completion(
                ledger=self.ledger, run_id="run", harness_root=self.harness,
            )

        self.assertEqual("blocked", result["status"])
        self.assertEqual(
            "project-final-rust-project-ir-incomplete", result["stage"],
        )
        self.assertEqual([
            "unresolved-interface:public-signature",
            "unresolved-interface:shared-type-layout",
        ], result["blockers"])
        self.assertNotIn(
            "repair_dispatch_permit", integration_runner.call_args.kwargs,
        )
        integration_gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
