from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .gate_candidate_sets import assert_current_candidate_set
from .ledger_project_gates import _require_latest_project_passes
from .ledger_schema import _now_text, _require_sha256, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import (
    TransitionAuthority, load_run_projection, load_unit_projection,
)
from .ledger_transition_commands import (
    project_run_completed_command, project_unit_completed_command,
)
from .project_completion_invariants import (
    require_project_interface_ready, require_quiescent_last_good_run,
)
from .project_completion_receipt import (
    read_completion_receipt, validate_completion_receipt_bindings,
)
from .project_final_barrier import require_project_final_candidate_passes


class ProjectCompletionLedgerMixin:
    def complete_project_run(
        self, *, run_id: str, candidate_set_sha256: str,
    ) -> dict[str, Any]:
        candidate_set = _require_sha256(candidate_set_sha256, "candidate_set_sha256")
        with self.connect() as connection, atomic(connection):
            require_quiescent_last_good_run(connection, run_id)
            require_project_interface_ready(connection, run_id)
            assert_current_candidate_set(
                connection, run_id, candidate_set, database_path=self.path,
            )
            require_project_final_candidate_passes(
                self, connection, run_id, candidate_set,
            )
            records = _require_latest_project_passes(
                self, connection, run_id, candidate_set, include_final=True,
            )
            verifier_ids = {str(row["verifier_id"]) for row, _ in records}
            if len(verifier_ids) < 2:
                raise LedgerError("project completion requires independent host authorities")
            receipt, reference = _validated_completion_receipt(
                self, run_id=run_id, candidate_set_sha256=candidate_set,
                records=records,
            )
            receipt_sha256 = str(reference["sha256"])
            now = _now_text()
            units = connection.execute(
                """select unit_id,status,resumable_status from migration_units
                   where run_id=? order by unit_id""", (run_id,),
            ).fetchall()
            authority = TransitionAuthority(connection)
            for unit in units:
                unit_id = str(unit["unit_id"])
                authority.apply(
                    project_unit_completed_command(
                        run_id=run_id, unit_id=unit_id,
                        expected=load_unit_projection(connection, run_id, unit_id),
                        candidate_set_sha256=candidate_set,
                        completion_receipt_sha256=receipt_sha256,
                    ),
                    created_at=now,
                )
            authority.apply_run(
                project_run_completed_command(
                    run_id=run_id, anchor_unit_id=str(units[0]["unit_id"]),
                    expected=load_run_projection(connection, run_id),
                    candidate_set_sha256=candidate_set,
                    completion_receipt_sha256=receipt_sha256,
                ),
                created_at=now,
            )
            _require_completed_receipt_transitions(
                connection, run_id=run_id, receipt_sha256=receipt_sha256,
            )
            reopened, reopened_reference = _validated_completion_receipt(
                self, run_id=run_id, candidate_set_sha256=candidate_set,
                records=records,
            )
            if reopened != receipt or reopened_reference != reference:
                raise LedgerError("project completion receipt changed before ledger commit")
            return {"receipt": dict(receipt), "reference": dict(reference)}

    def reopen_completed_project_run(
        self, *, run_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection, atomic(connection, immediate=False):
            run = connection.execute(
                "select status from project_runs where run_id=?", (run_id,),
            ).fetchone()
            if run is None:
                raise LedgerError("project completion run does not exist")
            if run["status"] != "completed":
                return None
            try:
                receipt, reference = read_completion_receipt(self.path)
            except (LedgerError, OSError, TypeError, ValueError) as error:
                raise LedgerError(
                    "completed project receipt cannot be reopened",
                ) from error
            candidate_set = _require_sha256(
                str(receipt.get("candidate_set_sha256")),
                "candidate_set_sha256",
            )
            require_project_final_candidate_passes(
                self, connection, run_id, candidate_set,
            )
            records = _require_latest_project_passes(
                self, connection, run_id, candidate_set, include_final=True,
            )
            validate_completion_receipt_bindings(
                receipt, reference, run_id=run_id,
                candidate_set_sha256=candidate_set,
                project_gate_records=records,
            )
            _require_completed_receipt_transitions(
                connection, run_id=run_id,
                receipt_sha256=str(reference["sha256"]),
            )
            return {"receipt": dict(receipt), "reference": dict(reference)}


def _validated_completion_receipt(
    ledger: Any, *, run_id: str, candidate_set_sha256: str,
    records: list[tuple[Any, Mapping[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        receipt, reference = read_completion_receipt(ledger.path)
        validate_completion_receipt_bindings(
            receipt, reference, run_id=run_id,
            candidate_set_sha256=candidate_set_sha256,
            project_gate_records=records,
        )
    except (LedgerError, OSError, TypeError, ValueError) as error:
        if isinstance(error, LedgerError):
            raise
        raise LedgerError("project completion receipt validation failed") from error
    return receipt, reference


def _require_completed_receipt_transitions(
    connection: Any, *, run_id: str, receipt_sha256: str,
) -> None:
    run = connection.execute(
        "select status from project_runs where run_id=?", (run_id,),
    ).fetchone()
    units = connection.execute(
        """select unit_id,status,resumable_status from migration_units
           where run_id=? order by unit_id""", (run_id,),
    ).fetchall()
    transitions = connection.execute(
        """select scope,unit_id,command_kind,to_status,to_resumable_status,
                  reason,evidence_sha256 from transitions where run_id=?
           and command_kind in ('project_unit_completed','project_run_completed')
           order by transition_id""", (run_id,),
    ).fetchall()
    run_events = [row for row in transitions if row["scope"] == "run"]
    unit_events = {
        str(row["unit_id"]): row
        for row in transitions if row["scope"] == "unit"
    }
    if (
        run is None or run["status"] != "completed" or not units
        or len(run_events) != 1 or len(unit_events) != len(units)
        or set(unit_events) != {str(row["unit_id"]) for row in units}
    ):
        raise LedgerError("completed project receipt transition set is incomplete")
    expected = ("project_gate_bundle_passed", receipt_sha256)
    run_event = run_events[0]
    if (
        run_event["command_kind"] != "project_run_completed"
        or run_event["to_status"] != "completed"
        or (run_event["reason"], run_event["evidence_sha256"]) != expected
    ):
        raise LedgerError("completed project run is not receipt-bound")
    for unit in units:
        event = unit_events[str(unit["unit_id"])]
        if (
            unit["status"] != "completed"
            or unit["resumable_status"] != "terminal"
            or event["command_kind"] != "project_unit_completed"
            or event["to_status"] != "completed"
            or event["to_resumable_status"] != "terminal"
            or (event["reason"], event["evidence_sha256"]) != expected
        ):
            raise LedgerError("completed project unit is not receipt-bound")


__all__ = ["ProjectCompletionLedgerMixin"]
