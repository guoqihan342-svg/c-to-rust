from __future__ import annotations

import unittest
from unittest import mock

from validation.tools._project_migration_harness.controller_project_gates import (
    complete_verified_project,
)
from validation.tools._project_migration_harness.gate_authority import (
    PROJECT_GATE_KINDS,
)
from validation.tools._project_migration_harness.ledger import (
    LedgerError, ProjectLedger,
)
from validation.tools._project_migration_harness.project_completion_coordinator import (
    resume_project_completion,
)
from validation.tools.project_migration_completion_receipt_test_support import (
    write_completion_receipt,
)
from validation.tools.project_migration_final_barrier_test_support import (
    record_project_final_candidate_bundle,
)
from validation.tools.project_migration_gate_authority_test_support import (
    ProjectMigrationGateAuthorityCase,
)


COMPLETION_LEDGER = (
    "validation.tools._project_migration_harness.ledger_project_completion."
)
COORDINATOR = (
    "validation.tools._project_migration_harness.project_completion_coordinator."
)


class ProjectMigrationCompletionReceiptRecoveryTests(
    ProjectMigrationGateAuthorityCase,
):
    def _ready(self, *, write_receipt: bool) -> tuple[str, dict | None]:
        self.promote_current_candidate()
        self.register_project_interface_ready()
        candidate_set = record_project_final_candidate_bundle(self)
        for kind in sorted(PROJECT_GATE_KINDS - {"final-verification"}):
            self.record_project_host_gate(
                kind, "passed", f"{kind}-completion-pass", candidate_set,
            )
        self.record_project_final("project-final-completion-pass", candidate_set)
        reference = (
            write_completion_receipt(self, candidate_set)
            if write_receipt else None
        )
        return candidate_set, reference

    def test_receipt_first_orphan_is_recoverable_after_reopen(self) -> None:
        candidate_set, _ = self._ready(write_receipt=False)
        with self.assertRaisesRegex(LedgerError, "receipt is missing"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set,
            )
        state = self.ledger.unit_states("run")[0]
        self.assertEqual(
            ("resume-ready", "last_good", "active"),
            (state["status"], state["resumable_status"], state["run_status"]),
        )

        reference = write_completion_receipt(self, candidate_set)
        reopened = ProjectLedger(self.database)
        self.assertIsNone(reopened.reopen_completed_project_run(run_id="run"))
        completion = complete_verified_project(
            ledger=reopened,
            run_id="run", candidate_set_sha256=candidate_set,
        )
        self.assertEqual(reference, completion["completion_receipt"])

        restarted = ProjectLedger(self.database)
        recovered = restarted.reopen_completed_project_run(run_id="run")
        self.assertIsNotNone(recovered)
        self.assertEqual(reference, recovered["reference"])
        with restarted.connect() as connection:
            bindings = connection.execute(
                """select distinct evidence_sha256 from transitions where run_id='run'
                   and command_kind in
                   ('project_unit_completed','project_run_completed')""",
            ).fetchall()
        self.assertEqual([reference["sha256"]], [str(row[0]) for row in bindings])

    def test_sqlite_failure_rolls_back_every_completion_projection(self) -> None:
        candidate_set, reference = self._ready(write_receipt=True)
        with (
            mock.patch(
                COMPLETION_LEDGER + "TransitionAuthority.apply_run",
                side_effect=LedgerError("fault_after_unit_transitions"),
            ),
            self.assertRaisesRegex(LedgerError, "fault_after_unit_transitions"),
        ):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set,
            )
        with self.ledger.connect() as connection:
            run = connection.execute(
                "select status from project_runs where run_id='run'",
            ).fetchone()
            unit = connection.execute(
                """select status,resumable_status from migration_units
                   where run_id='run'""",
            ).fetchone()
            events = connection.execute(
                """select count(*) from transitions where run_id='run'
                   and command_kind in
                   ('project_unit_completed','project_run_completed')""",
            ).fetchone()[0]
        self.assertEqual("active", run["status"])
        self.assertEqual(("resume-ready", "last_good"), tuple(unit))
        self.assertEqual(0, events)
        self.assertTrue((self.out_root / reference["path"]).is_file())

        restarted = ProjectLedger(self.database)
        completed = restarted.complete_project_run(
            run_id="run", candidate_set_sha256=candidate_set,
        )
        self.assertEqual(reference, completed["reference"])

    def test_completed_restart_reopens_receipt_before_any_worker_stage(self) -> None:
        candidate_set, reference = self._ready(write_receipt=True)
        self.ledger.complete_project_run(
            run_id="run", candidate_set_sha256=candidate_set,
        )
        restarted = ProjectLedger(self.database)
        with mock.patch(COORDINATOR + "advance_gate_pending_candidates") as advance:
            result = resume_project_completion(
                ledger=restarted, run_id="run", harness_root=self.harness,
            )
        self.assertEqual("completed", result["status"])
        self.assertTrue(result["semantic_gate"])
        self.assertEqual(reference, result["completion_receipt"])
        self.assertEqual("project-completion-receipt-reopened", result["stage"])
        advance.assert_not_called()

    def test_completed_receipt_drift_is_never_observed_as_completed(self) -> None:
        candidate_set, reference = self._ready(write_receipt=True)
        self.ledger.complete_project_run(
            run_id="run", candidate_set_sha256=candidate_set,
        )
        with (self.out_root / reference["path"]).open("ab") as handle:
            handle.write(b"\n")
        restarted = ProjectLedger(self.database)
        with self.assertRaisesRegex(LedgerError, "cannot be reopened"):
            restarted.reopen_completed_project_run(run_id="run")
        with self.assertRaisesRegex(LedgerError, "cannot be reopened"):
            restarted.unit_states("run")
        with mock.patch(COORDINATOR + "advance_gate_pending_candidates") as advance:
            result = resume_project_completion(
                ledger=restarted, run_id="run", harness_root=self.harness,
            )
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["semantic_gate"])
        self.assertEqual("project-completion-receipt-recovery", result["stage"])
        advance.assert_not_called()

    def test_caller_forged_receipt_record_is_rejected(self) -> None:
        candidate_set, _ = self._ready(write_receipt=False)
        write_completion_receipt(
            self, candidate_set, project_final_record_id="caller-claimed-final",
        )
        with self.assertRaisesRegex(LedgerError, "host evidence binding"):
            self.ledger.complete_project_run(
                run_id="run", candidate_set_sha256=candidate_set,
            )
        with self.ledger.connect() as connection:
            status = connection.execute(
                "select status from project_runs where run_id='run'",
            ).fetchone()[0]
        self.assertEqual("active", status)


if __name__ == "__main__":
    unittest.main()
