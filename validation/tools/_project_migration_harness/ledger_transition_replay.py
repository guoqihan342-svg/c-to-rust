from __future__ import annotations

import sqlite3
from typing import Any

from .ledger_security import LedgerError
from .ledger_transition_audit import run_event_rows, unit_event_rows
from .ledger_transition_policy import (
    RunProjection, RunTransitionCommand, TransitionCommand, UnitProjection,
    UnitState, assert_run_transition_allowed, assert_transition_allowed,
)


def load_unit_projection(
    connection: sqlite3.Connection, run_id: str, unit_id: str,
) -> UnitProjection:
    row = connection.execute(
        """select status,resumable_status,state_version from migration_units
           where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if row is None:
        raise LedgerError("migration unit does not exist")
    try:
        return UnitProjection(
            UnitState(str(row["status"]), str(row["resumable_status"])),
            int(row["state_version"]),
        )
    except (TypeError, ValueError) as error:
        raise LedgerError("migration unit projection is invalid") from error


def load_run_projection(
    connection: sqlite3.Connection, run_id: str,
) -> RunProjection:
    row = connection.execute(
        "select status,state_version from project_runs where run_id=?", (run_id,),
    ).fetchone()
    if row is None:
        raise LedgerError("project run does not exist")
    try:
        return RunProjection(str(row["status"]), int(row["state_version"]))
    except (TypeError, ValueError) as error:
        raise LedgerError("project run projection is invalid") from error


def assert_unit_event_projection(
    connection: sqlite3.Connection, run_id: str, unit_id: str,
) -> UnitProjection:
    row = connection.execute(
        """select initial_status,initial_resumable_status,status,resumable_status,
                  state_version,last_good_artifact_id from migration_units
           where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if row is None:
        raise LedgerError("migration unit does not exist")
    try:
        projection = UnitProjection(
            UnitState(
                str(row["initial_status"]), str(row["initial_resumable_status"]),
            ),
            0,
        )
        last_good: str | None = None
        for event in unit_event_rows(
            connection, run_id=run_id, unit_id=unit_id,
        ):
            command = _unit_command(event)
            if (
                command.expected != projection.state
                or command.expected_version != projection.version
                or int(event["to_version"]) != projection.version + 1
            ):
                raise LedgerError("unit transition event chain is discontinuous")
            if command.set_last_good_artifact_id is not None:
                last_good = command.set_last_good_artifact_id
            elif (
                command.clear_last_good_if is not None
                and last_good == command.clear_last_good_if
            ):
                last_good = None
            projection = UnitProjection(command.target, int(event["to_version"]))
        current = UnitProjection(
            UnitState(str(row["status"]), str(row["resumable_status"])),
            int(row["state_version"]),
        )
    except (TypeError, ValueError) as error:
        raise LedgerError("unit transition event is invalid") from error
    if current != projection:
        raise LedgerError("unit transition projection does not match immutable events")
    if row["last_good_artifact_id"] != last_good:
        raise LedgerError("unit last-good projection does not match immutable events")
    return current


def assert_run_event_projection(
    connection: sqlite3.Connection, run_id: str,
) -> RunProjection:
    row = connection.execute(
        """select initial_status,status,state_version from project_runs
           where run_id=?""", (run_id,),
    ).fetchone()
    if row is None:
        raise LedgerError("project run does not exist")
    try:
        projection = RunProjection(str(row["initial_status"]), 0)
        for event in run_event_rows(connection, run_id=run_id):
            command = _run_command(event)
            if (
                command.expected_status != projection.status
                or command.expected_version != projection.version
                or int(event["to_version"]) != projection.version + 1
            ):
                raise LedgerError("run transition event chain is discontinuous")
            projection = RunProjection(command.target_status, int(event["to_version"]))
        current = RunProjection(str(row["status"]), int(row["state_version"]))
    except (TypeError, ValueError) as error:
        raise LedgerError("run transition event is invalid") from error
    if current != projection:
        raise LedgerError("run transition projection does not match immutable events")
    return current


def audit_transition_projections(
    connection: sqlite3.Connection, run_id: str,
) -> dict[str, Any]:
    run = assert_run_event_projection(connection, run_id)
    unit_ids = [str(row[0]) for row in connection.execute(
        "select unit_id from migration_units where run_id=? order by unit_id",
        (run_id,),
    ).fetchall()]
    if not unit_ids:
        raise LedgerError("transition projection audit requires migration units")
    units = [
        assert_unit_event_projection(connection, run_id, unit_id)
        for unit_id in unit_ids
    ]
    return {
        "run_id": run_id,
        "run_status": run.status,
        "run_state_version": run.version,
        "unit_count": len(units),
        "unit_state_versions": {
            unit_id: projection.version
            for unit_id, projection in zip(unit_ids, units)
        },
    }


def _unit_command(row: Any) -> TransitionCommand:
    command = TransitionCommand(
        command_kind=str(row["command_kind"]),
        command_id=str(row["command_id"]),
        run_id=str(row["run_id"]),
        unit_id=str(row["unit_id"]),
        expected=UnitState(
            str(row["from_status"]), str(row["from_resumable_status"]),
        ),
        expected_version=int(row["from_version"]),
        target=UnitState(
            str(row["to_status"]), str(row["to_resumable_status"]),
        ),
        reason=str(row["reason"]),
        evidence_sha256=str(row["evidence_sha256"]),
        attempt_id=row["attempt_id"],
        fencing_token=row["fencing_token"],
        clear_last_good_if=row["clear_last_good_if"],
        set_last_good_artifact_id=row["set_last_good_artifact_id"],
    )
    assert_transition_allowed(command)
    return command


def _run_command(row: Any) -> RunTransitionCommand:
    command = RunTransitionCommand(
        command_kind=str(row["command_kind"]),
        command_id=str(row["command_id"]),
        run_id=str(row["run_id"]),
        anchor_unit_id=str(row["unit_id"]),
        expected_status=str(row["from_status"]),
        expected_version=int(row["from_version"]),
        target_status=str(row["to_status"]),
        reason=str(row["reason"]),
        evidence_sha256=str(row["evidence_sha256"]),
        attempt_id=row["attempt_id"],
        fencing_token=row["fencing_token"],
    )
    assert_run_transition_allowed(command)
    return command


__all__ = [
    "assert_run_event_projection", "assert_unit_event_projection",
    "audit_transition_projections",
    "load_run_projection", "load_unit_projection",
]
