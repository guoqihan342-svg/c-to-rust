from __future__ import annotations

import json
from typing import Any

from .ledger_run_transition import CompletionProjection, RunProjection
from .ledger_security import LedgerError


def require_completed_receipt_transitions(
    connection: Any, *, run_id: str, receipt_sha256: str,
    projection: RunProjection,
) -> None:
    units = connection.execute(
        """select unit_id,status,resumable_status from migration_units
           where run_id=? order by unit_id""", (run_id,),
    ).fetchall()
    events = connection.execute(
        """select scope,unit_id,command_kind,from_status,to_status,
                  to_resumable_status,reason,evidence_sha256,
                  from_completion_json,to_completion_json
           from transitions where run_id=? and command_kind in
           ('project_run_finalizing','project_unit_completed','project_run_completed')
           order by transition_id""", (run_id,),
    ).fetchall()
    run_events = [row for row in events if row["scope"] == "run"]
    unit_events = {
        str(row["unit_id"]): row for row in events if row["scope"] == "unit"
    }
    if (
        projection.status != "completed" or not units
        or len(unit_events) != len(units)
        or set(unit_events) != {str(row["unit_id"]) for row in units}
    ):
        raise LedgerError("completed project receipt transition set is incomplete")
    valid_run = (
        _valid_legacy_run_event(run_events, receipt_sha256)
        if projection.completion.epoch == 0
        else _valid_finalizing_run_events(run_events, projection, receipt_sha256)
    )
    if not valid_run:
        raise LedgerError("completed project run is not finalization-bound")
    for unit in units:
        event = unit_events[str(unit["unit_id"])]
        if (
            (unit["status"], unit["resumable_status"]) != ("completed", "terminal")
            or event["command_kind"] != "project_unit_completed"
            or event["to_status"] != "completed"
            or event["to_resumable_status"] != "terminal"
            or (event["reason"], event["evidence_sha256"])
            != ("project_gate_bundle_passed", receipt_sha256)
        ):
            raise LedgerError("completed project unit is not receipt-bound")


def _valid_legacy_run_event(events: list[Any], receipt_sha256: str) -> bool:
    if len(events) != 1:
        return False
    event = events[0]
    return (
        event["command_kind"] == "project_run_completed"
        and (event["from_status"], event["to_status"]) == ("active", "completed")
        and (event["reason"], event["evidence_sha256"])
        == ("project_gate_bundle_passed", receipt_sha256)
    )


def _valid_finalizing_run_events(
    events: list[Any], projection: RunProjection, receipt_sha256: str,
) -> bool:
    if len(events) != 2:
        return False
    finalizing, completed = events
    try:
        frozen = _completion(finalizing["to_completion_json"])
        published = _completion(completed["to_completion_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return (
        finalizing["command_kind"] == "project_run_finalizing"
        and (finalizing["from_status"], finalizing["to_status"])
        == ("active", "finalizing")
        and finalizing["evidence_sha256"] == projection.completion.gate_bundle_sha256
        and completed["command_kind"] == "project_run_completed"
        and (completed["from_status"], completed["to_status"])
        == ("finalizing", "completed")
        and completed["evidence_sha256"] == receipt_sha256
        and frozen.receipt_sha256 is None
        and published == projection.completion
        and published.receipt_sha256 == receipt_sha256
    )


def _completion(raw: Any) -> CompletionProjection:
    value = json.loads(str(raw))
    if json.dumps(value, sort_keys=True, separators=(",", ":")) != raw:
        raise ValueError("completion transition binding is not canonical")
    return CompletionProjection.from_payload(value)


__all__ = ["require_completed_receipt_transitions"]
