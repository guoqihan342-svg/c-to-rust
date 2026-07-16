from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .ledger_project_finalizing import ProjectFinalizingLedgerMixin
from .ledger_run_transition import RunProjection
from .ledger_project_completion_transitions import (
    require_completed_receipt_transitions,
)
from .ledger_schema import _now_text, _require_sha256, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import (
    TransitionAuthority, load_run_projection, load_unit_projection,
)
from .ledger_transition_commands import (
    project_run_completed_command, project_unit_completed_command,
)
from .project_completion_context import reopen_completion_context
from .project_completion_invariant import (
    completion_invariant, invariant_reference, reopen_completed_invariant,
)
from .project_completion_receipt import (
    read_completion_receipt, validate_completion_receipt_bindings,
)


class ProjectCompletionLedgerMixin(ProjectFinalizingLedgerMixin):
    def complete_project_run(
        self, *, run_id: str, candidate_set_sha256: str,
    ) -> dict[str, Any]:
        candidate_set = _require_sha256(
            candidate_set_sha256, "candidate_set_sha256",
        )
        with self.connect() as connection:
            status = load_run_projection(connection, run_id).status
        if status == "active":
            self.begin_project_finalization(
                run_id=run_id, candidate_set_sha256=candidate_set,
            )
        with self.connect() as connection, atomic(connection):
            projection = load_run_projection(connection, run_id)
            if projection.status != "finalizing":
                raise LedgerError("project completion requires a finalizing run")
            context = _reopen_bound_context(
                self, connection, run_id, candidate_set, projection,
            )
            finalization = _finalization_binding(
                connection, run_id, projection, phase="last-good",
            )
            receipt, reference = _validated_completion_receipt(
                self, run_id=run_id, candidate_set_sha256=candidate_set,
                records=context["records"], finalization=finalization,
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
            completed = load_run_projection(connection, run_id)
            require_completed_receipt_transitions(
                connection, run_id=run_id, receipt_sha256=receipt_sha256,
                projection=completed,
            )
            reopened, reopened_reference = _validated_completion_receipt(
                self, run_id=run_id, candidate_set_sha256=candidate_set,
                records=context["records"], finalization=finalization,
            )
            if reopened != receipt or reopened_reference != reference:
                raise LedgerError("project completion receipt changed before ledger commit")
            reopen_completed_invariant(
                connection, expected=receipt["finalization"], run_id=run_id,
                completion_epoch=completed.completion.epoch,
                cohort_sha256=candidate_set,
                generation_sha256=str(completed.completion.generation_sha256),
                gate_bundle_sha256=str(completed.completion.gate_bundle_sha256),
            )
            return {"receipt": dict(receipt), "reference": dict(reference)}

    def reopen_completed_project_run(
        self, *, run_id: str,
    ) -> dict[str, Any] | None:
        with self.connect() as connection, atomic(connection, immediate=False):
            projection = load_run_projection(connection, run_id)
            if projection.status != "completed":
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
            context = reopen_completion_context(
                self, connection, run_id=run_id,
                candidate_set_sha256=candidate_set, completed=True,
            )
            if projection.completion.epoch == 0:
                finalization = None
            else:
                _reopen_bound_context(
                    self, connection, run_id, candidate_set, projection,
                    context=context,
                )
                value = receipt.get("finalization")
                if not isinstance(value, Mapping):
                    raise LedgerError("completed project finalization receipt is missing")
                finalization = {
                    "completion_epoch": projection.completion.epoch,
                    "cohort_sha256": candidate_set,
                    "generation_sha256": projection.completion.generation_sha256,
                    "gate_bundle_sha256": projection.completion.gate_bundle_sha256,
                    "invariant": value.get("invariant"),
                }
            validate_completion_receipt_bindings(
                receipt, reference, run_id=run_id,
                candidate_set_sha256=candidate_set,
                project_gate_records=context["records"],
                finalization=finalization,
            )
            require_completed_receipt_transitions(
                connection, run_id=run_id,
                receipt_sha256=str(reference["sha256"]),
                projection=projection,
            )
            if finalization is not None:
                reopen_completed_invariant(
                    connection, expected=receipt["finalization"], run_id=run_id,
                    completion_epoch=projection.completion.epoch,
                    cohort_sha256=candidate_set,
                    generation_sha256=str(projection.completion.generation_sha256),
                    gate_bundle_sha256=str(
                        projection.completion.gate_bundle_sha256
                    ),
                )
            return {"receipt": dict(receipt), "reference": dict(reference)}


def _reopen_bound_context(
    ledger: Any, connection: Any, run_id: str, candidate_set: str,
    projection: RunProjection, *, context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = context or reopen_completion_context(
        ledger, connection, run_id=run_id,
        candidate_set_sha256=candidate_set,
    )
    completion = projection.completion
    if (
        completion.cohort_sha256 != candidate_set
        or completion.generation_sha256 != context["generation_sha256"]
        or completion.gate_bundle_sha256 != context["gate_bundle_sha256"]
    ):
        raise LedgerError("project completion cohort/generation drifted")
    return context


def _finalization_binding(
    connection: Any, run_id: str, projection: RunProjection, *, phase: str,
) -> dict[str, Any]:
    completion = projection.completion
    invariant = invariant_reference(completion_invariant(
        connection, run_id=run_id,
        completion_epoch=completion.epoch,
        cohort_sha256=str(completion.cohort_sha256),
        generation_sha256=str(completion.generation_sha256),
        gate_bundle_sha256=str(completion.gate_bundle_sha256), phase=phase,
    ))
    if invariant["sha256"] != completion.invariant_sha256:
        raise LedgerError("project completion invariant binding drifted")
    return {
        "completion_epoch": completion.epoch,
        "cohort_sha256": completion.cohort_sha256,
        "generation_sha256": completion.generation_sha256,
        "gate_bundle_sha256": completion.gate_bundle_sha256,
        "invariant": invariant,
    }


def _validated_completion_receipt(
    ledger: Any, *, run_id: str, candidate_set_sha256: str,
    records: list[tuple[Any, Mapping[str, Any]]],
    finalization: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        receipt, reference = read_completion_receipt(ledger.path)
        validate_completion_receipt_bindings(
            receipt, reference, run_id=run_id,
            candidate_set_sha256=candidate_set_sha256,
            project_gate_records=records, finalization=finalization,
        )
    except (LedgerError, OSError, TypeError, ValueError) as error:
        if isinstance(error, LedgerError):
            raise
        raise LedgerError("project completion receipt validation failed") from error
    return receipt, reference


__all__ = ["ProjectCompletionLedgerMixin"]
