from __future__ import annotations

import sqlite3
import unittest

from validation.tools._project_migration_harness.ledger import LedgerError
from validation.tools._project_migration_harness.project_diagnostic_shape import (
    build_project_diagnostic,
)
from validation.tools._project_migration_harness.project_host_gates import (
    record_host_project_observation,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase, digest,
)


class ProjectMigrationProjectDiagnosticIntakeTests(
    ProjectMigrationGateAuthorityCase,
):
    def setUp(self) -> None:
        super().setUp()
        self.promote_current_candidate()
        self.candidate_set = self.ledger.bind_current_candidate_set(run_id="run")

    def test_failed_executed_gate_records_bound_immutable_intake(self) -> None:
        recorded = self._record(self.project_observation_value("cargo-check", "failed"))
        reference = recorded["project_diagnostic_intake"]
        loaded = self.ledger.latest_project_diagnostic_intakes(
            run_id="run", candidate_set_sha256=self.candidate_set,
            rust_project_ir_sha256=digest("rust-project-ir"),
            project_input_sha256=digest("manifest"),
        )
        self.assertEqual([reference["sha256"]], [item["artifact"]["sha256"] for item in loaded])
        intake = loaded[0]["intake"]
        self.assertEqual(recorded["record_id"], intake["gate_record_id"])
        self.assertEqual("executed", self.project_observation_value(
            "cargo-check", "failed",
        )["outcome"])
        with self.ledger.connect() as connection, self.assertRaisesRegex(
            sqlite3.IntegrityError, "immutable",
        ):
            connection.execute(
                "update project_diagnostic_intakes set diagnostic_count=2",
            )

    def test_blocked_environment_cannot_admit_or_record_intake(self) -> None:
        blocked = {
            "outcome": "blocked",
            "project_input_sha256": digest("manifest"),
            "project_state_unchanged": True,
            "blocker_code": "cargo_tool_unavailable",
            "sandbox": None,
            "check": None,
        }
        with self.assertRaisesRegex(
            LedgerError, "not a failed host observation",
        ):
            self._record(blocked)
        with self.ledger.connect() as connection:
            gate_count = connection.execute(
                "select count(*) from project_gate_records",
            ).fetchone()[0]
            intake_count = connection.execute(
                "select count(*) from project_diagnostic_intakes",
            ).fetchone()[0]
        self.assertEqual(0, gate_count)
        self.assertEqual(0, intake_count)

    def test_intake_content_tamper_is_rejected_on_reopen(self) -> None:
        recorded = self._record(self.project_observation_value("cargo-check", "failed"))
        reference = recorded["project_diagnostic_intake"]
        target = self.harness.joinpath(*reference["path"].split("/"))
        target.write_text("{}\n", encoding="utf-8")
        with self.assertRaises(LedgerError):
            self.ledger.latest_project_diagnostic_intakes(
                run_id="run", candidate_set_sha256=self.candidate_set,
                rust_project_ir_sha256=digest("rust-project-ir"),
                project_input_sha256=digest("manifest"),
            )

    def _record(self, observation: dict) -> dict:
        return record_host_project_observation(
            ledger=self.ledger, out_root=self.out_root,
            out_root_rel="target/run", run_id="run",
            gate_kind="cargo-check",
            candidate_set_sha256=self.candidate_set,
            observation=observation, diagnostic_codes=["e0432"],
            project_diagnostic_input={
                "rust_project_ir_sha256": digest("rust-project-ir"),
                "rust_project_interface_sha256": digest("project-interface"),
                "project_input_sha256": digest("manifest"),
                "diagnostics": [_diagnostic()],
            },
        )


def _diagnostic() -> dict:
    return {
        "family": "compile", "source_code": "e0432",
        "stage": "cargo-check", "message": "unresolved import `shared`",
        "location": {"file": "src/lib.rs", "line": 1, "column": 1},
        "project_diagnostic": build_project_diagnostic(
            code="project-verifier-e0432",
            entity_ids=["e0432", "file:src/lib.rs"],
            affected_module_ids=[],
        ),
    }


if __name__ == "__main__":
    unittest.main()
