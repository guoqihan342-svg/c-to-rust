from __future__ import annotations

from typing import Any

from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_authority import (
    TransitionAuthority, load_run_projection,
)
from .ledger_transition_commands import project_run_finalizing_command
from .project_completion_context import reopen_completion_context
from .project_completion_invariant import (
    completion_invariant, invariant_reference,
)
from .project_completion_invariants import (
    require_project_interface_ready, require_quiescent_last_good_run,
)


class ProjectFinalizingLedgerMixin:
    def begin_project_finalization(
        self, *, run_id: str, candidate_set_sha256: str,
    ) -> dict[str, Any]:
        with self.connect() as connection, atomic(connection):
            projection = load_run_projection(connection, run_id)
            if projection.status == "finalizing":
                return _reopen_finalizing(
                    self, connection, run_id, candidate_set_sha256,
                )
            if projection.status != "active":
                raise LedgerError("project finalization requires an active run")
            require_quiescent_last_good_run(connection, run_id)
            require_project_interface_ready(connection, run_id)
            context = reopen_completion_context(
                self, connection, run_id=run_id,
                candidate_set_sha256=candidate_set_sha256,
            )
            epoch = projection.completion.epoch + 1
            invariant = invariant_reference(completion_invariant(
                connection, run_id=run_id, completion_epoch=epoch,
                cohort_sha256=context["cohort_sha256"],
                generation_sha256=context["generation_sha256"],
                gate_bundle_sha256=context["gate_bundle_sha256"],
                phase="last-good",
            ))
            units = connection.execute(
                "select unit_id from migration_units where run_id=? order by unit_id",
                (run_id,),
            ).fetchall()
            TransitionAuthority(connection).apply_run(
                project_run_finalizing_command(
                    run_id=run_id, anchor_unit_id=str(units[0][0]),
                    expected=projection, completion_epoch=epoch,
                    candidate_set_sha256=context["cohort_sha256"],
                    generation_sha256=context["generation_sha256"],
                    gate_bundle_sha256=context["gate_bundle_sha256"],
                    invariant_sha256=invariant["sha256"],
                ),
                created_at=_now_text(),
            )
            return _reopen_finalizing(
                self, connection, run_id, candidate_set_sha256,
                expected_invariant=invariant,
            )


def _reopen_finalizing(
    ledger: Any, connection: Any, run_id: str, candidate_set_sha256: str,
    *, expected_invariant: dict[str, Any] | None = None,
) -> dict[str, Any]:
    projection = load_run_projection(connection, run_id)
    completion = projection.completion
    if projection.status != "finalizing":
        raise LedgerError("project run is not finalizing")
    if completion.cohort_sha256 != candidate_set_sha256:
        raise LedgerError("project finalization cohort drifted")
    context = reopen_completion_context(
        ledger, connection, run_id=run_id,
        candidate_set_sha256=candidate_set_sha256,
    )
    if (
        completion.generation_sha256 != context["generation_sha256"]
        or completion.gate_bundle_sha256 != context["gate_bundle_sha256"]
    ):
        raise LedgerError("project finalization gate generation drifted")
    invariant = invariant_reference(completion_invariant(
        connection, run_id=run_id,
        completion_epoch=completion.epoch,
        cohort_sha256=candidate_set_sha256,
        generation_sha256=str(completion.generation_sha256),
        gate_bundle_sha256=str(completion.gate_bundle_sha256),
        phase="last-good",
    ))
    if (
        invariant["sha256"] != completion.invariant_sha256
        or expected_invariant is not None and invariant != expected_invariant
    ):
        raise LedgerError("project finalization invariant drifted")
    return {
        "completion_epoch": completion.epoch,
        "cohort_sha256": candidate_set_sha256,
        "generation_sha256": completion.generation_sha256,
        "gate_bundle_sha256": completion.gate_bundle_sha256,
        "invariant": invariant,
        "records": context["records"],
    }


__all__ = ["ProjectFinalizingLedgerMixin"]
