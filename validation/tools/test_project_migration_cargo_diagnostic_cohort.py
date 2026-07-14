from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from validation.tools._project_migration_harness.project_cargo_diagnostic_cohort import (
    decide_cargo_diagnostic_cohort,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_intake import (
    CargoDiagnosticPartition,
)
from validation.tools._project_migration_harness.project_cargo_verifier import (
    verify_project_cargo,
)


class ProjectMigrationCargoDiagnosticCohortTests(unittest.TestCase):
    def test_unique_failed_cohort_admits_repairs(self) -> None:
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed",
            checks={"cargo-check": _check("failed", [_error()])},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={"cargo-check": _partition()},
            candidate_members=[_member()],
        )
        self.assertTrue(decision.admits_repairs)
        self.assertEqual("admitted", decision.status)

    def test_failed_check_may_omit_later_test_gate(self) -> None:
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed",
            checks={"cargo-check": _check("failed", [_error()])},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={"cargo-check": _partition()},
            candidate_members=[_member()],
        )
        self.assertIsNone(decision.blocker_code)

    def test_stale_partition_blocks_all_repair_admission(self) -> None:
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed",
            checks={"cargo-check": _check("failed", [_error()])},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={
                "cargo-check": CargoDiagnosticPartition(
                    {}, [], "unit-path-not-unique",
                ),
            },
            candidate_members=[_member()],
        )
        self.assertFalse(decision.admits_repairs)
        self.assertEqual("unit-path-not-unique", decision.blocker_code)

    def test_mixed_failure_reaches_neither_project_nor_unit_repair(self) -> None:
        ledger = mock.MagicMock()
        ledger.bind_current_candidate_set.return_value = "c" * 64
        context = {
            "project_input_sha256": "d" * 64,
            "rust_project_ir": {
                "ir_sha256": "e" * 64, "interface_sha256": "f" * 64,
                "modules": [{
                    "unit_id": "unit", "candidate_sha256": "a" * 64,
                    "rust_path": f"src/unit_{'a' * 64}.rs",
                    "module_id": "module-unit",
                }],
                "public_api": [{"symbol": "shared", "module_id": "module-a"}],
            },
        }
        diagnostics = [
            {
                **_error(), "code": "e0432", "file": "src/lib.rs",
                "message": "unresolved import `shared`",
            },
            {
                **_error(), "code": "rustc-diagnostic", "file": "",
                "message": "linking with `cc` failed",
            },
        ]
        execution = {
            "status": "failed",
            "checks": [{
                "command": ["cargo", "check"],
                "status": "failed", "diagnostics": diagnostics,
            }],
        }
        recorded = mock.Mock(side_effect=lambda **values: {
            "gate_status": "failed", "record_id": values["gate_kind"],
        })
        module = (
            "validation.tools._project_migration_harness.project_cargo_verifier"
        )
        with (
            mock.patch(f"{module}.current_candidate_members", return_value=[_member()]),
            mock.patch(f"{module}.load_managed_project_context", return_value=context),
            mock.patch(f"{module}.run_cargo_project_gates", return_value=execution),
            mock.patch(
                f"{module}.project_cargo_observation",
                side_effect=lambda *args, **kwargs: {
                    "outcome": "executed" if args[1] is not None else "blocked",
                },
            ),
            mock.patch(f"{module}.record_host_project_observation", recorded),
            mock.patch(f"{module}.record_candidate_gate") as candidate_gate,
        ):
            result = verify_project_cargo(
                ledger=ledger, run_id="run", project_root=Path("project"),
                runtime_root=Path("runtime"), out_root=Path("out"),
                out_root_rel="target/run",
            )
        self.assertEqual("diagnostic-unclassified", result[
            "diagnostic_admission"
        ]["blocker_code"])
        self.assertEqual([], result["project_diagnostic_intakes"])
        self.assertEqual([], result["candidate_repair_gates"])
        candidate_gate.assert_not_called()
        self.assertTrue(all(
            call.kwargs["project_diagnostic_input"] is None
            for call in recorded.call_args_list
        ))

    def test_duplicate_content_owner_blocks_all_repair_admission(self) -> None:
        duplicate = {
            **_member(), "unit_id": "other", "artifact_id": "other-candidate",
        }
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed",
            checks={"cargo-check": _check("failed", [_error()])},
            observations={"cargo-check": {"outcome": "executed"}},
            partitions={"cargo-check": _partition()},
            candidate_members=[_member(), duplicate],
        )
        self.assertEqual("candidate-content-not-unique", decision.blocker_code)

    def test_blocked_environment_never_admits_diagnostics(self) -> None:
        decision = decide_cargo_diagnostic_cohort(
            execution_status="blocked",
            checks={}, observations={}, partitions={},
            candidate_members=[_member()],
        )
        self.assertEqual("cargo-execution-blocked", decision.blocker_code)

    def test_invalid_gate_order_fails_closed(self) -> None:
        decision = decide_cargo_diagnostic_cohort(
            execution_status="failed",
            checks={
                "cargo-check": _check("failed", [_error()]),
                "cargo-test": _check("failed", [_error(stage="cargo-test")]),
            },
            observations={
                "cargo-check": {"outcome": "executed"},
                "cargo-test": {"outcome": "executed"},
            },
            partitions={
                "cargo-check": _partition(), "cargo-test": _partition(),
            },
            candidate_members=[_member()],
        )
        self.assertEqual("cargo-gate-order-invalid", decision.blocker_code)

    def test_clean_check_and_test_need_no_repair_admission(self) -> None:
        decision = decide_cargo_diagnostic_cohort(
            execution_status="passed",
            checks={
                "cargo-check": _check("passed", []),
                "cargo-test": _check("passed", []),
            },
            observations={
                "cargo-check": {"outcome": "executed"},
                "cargo-test": {"outcome": "executed"},
            },
            partitions={}, candidate_members=[_member()],
        )
        self.assertEqual("not-applicable", decision.status)
        self.assertFalse(decision.admits_repairs)


def _member() -> dict:
    return {
        "unit_id": "unit", "artifact_id": "candidate",
        "content_sha256": "a" * 64,
    }


def _error(stage: str = "cargo-check") -> dict:
    return {
        "code": "e0308", "stage": stage, "message": "mismatched types",
        "file": f"src/unit_{'a' * 64}.rs", "line": 1, "column": 1,
        "level": "error", "origin": "rustc-compiler-message",
    }


def _check(status: str, diagnostics: list[dict]) -> dict:
    return {"status": status, "diagnostics": diagnostics}


def _partition() -> CargoDiagnosticPartition:
    return CargoDiagnosticPartition(
        {("unit", "candidate"): [_error()]}, [], None,
    )


if __name__ == "__main__":
    unittest.main()
