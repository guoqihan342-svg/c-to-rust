from __future__ import annotations

import json
from typing import Any

from .ledger_run_transition import (
    CompletionProjection, RunProjection, RunTransitionCommand,
    assert_run_transition_allowed,
)
from .ledger_security import LedgerError
from .ledger_transition_audit import command_rows
from .ledger_transition_replay import (
    assert_run_event_projection, load_run_projection,
)


def apply_run_transition(
    connection: Any, command: RunTransitionCommand, *, created_at: str,
) -> tuple[bool, int, RunProjection, RunProjection]:
    replay = _find_replay(connection, command)
    if replay is not None:
        assert_run_event_projection(connection, command.run_id)
        return replay
    assert_run_event_projection(connection, command.run_id)
    assert_run_transition_allowed(command)
    if command.expected_status == "active" and command.target_status == "completed":
        raise LedgerError("new project completion must enter finalizing first")
    current = load_run_projection(connection, command.run_id)
    expected = RunProjection(
        command.expected_status, command.expected_version,
        command.expected_completion,
    )
    if current != expected:
        raise LedgerError("transition expected run state/version is stale")
    if not connection.execute(
        "select 1 from migration_units where run_id=? and unit_id=?",
        (command.run_id, command.anchor_unit_id),
    ).fetchone():
        raise LedgerError("run transition anchor unit does not exist")
    cursor = _append(connection, command, created_at)
    target = command.target_completion
    shadow_status = (
        command.expected_status
        if command.target_status == "finalizing" else command.target_status
    )
    updated = connection.execute(
        """update project_runs set status=?,completion_status=?,
           completion_epoch=?,completion_cohort_sha256=?,
           completion_generation_sha256=?,completion_gate_bundle_sha256=?,
           completion_invariant_sha256=?,completion_receipt_sha256=?,
           state_version=state_version+1,updated_at=?
           where run_id=? and completion_status=? and state_version=?""",
        (
            shadow_status, command.target_status, target.epoch,
            target.cohort_sha256, target.generation_sha256,
            target.gate_bundle_sha256, target.invariant_sha256,
            target.receipt_sha256, created_at, command.run_id,
            command.expected_status, command.expected_version,
        ),
    )
    if updated.rowcount != 1:
        raise LedgerError("transition projection lost its expected run state/version")
    projected = RunProjection(
        command.target_status, command.expected_version + 1, target,
    )
    if assert_run_event_projection(connection, command.run_id) != projected:
        raise LedgerError("run transition projection audit failed")
    return True, int(cursor.lastrowid), expected, projected


def _find_replay(
    connection: Any, command: RunTransitionCommand,
) -> tuple[bool, int, RunProjection, RunProjection] | None:
    matches = command_rows(
        connection, run_id=command.run_id,
        command_id=command.command_id, scope="run",
    )
    if not matches:
        return None
    if len(matches) != 1:
        raise LedgerError("transition command_id is duplicated in the ledger")
    row = matches[0]
    previous = RunProjection(
        str(row["from_status"]), int(row["from_version"]),
        _completion(row["from_completion_json"]),
    )
    current = RunProjection(
        str(row["to_status"]), int(row["to_version"]),
        _completion(row["to_completion_json"]),
    )
    binding = (
        row["unit_id"] == command.anchor_unit_id
        and row["command_kind"] == command.command_kind
        and previous == RunProjection(
            command.expected_status, command.expected_version,
            command.expected_completion,
        )
        and current == RunProjection(
            command.target_status, command.expected_version + 1,
            command.target_completion,
        )
        and row["reason"] == command.reason
        and row["evidence_sha256"] == command.evidence_sha256
        and row["attempt_id"] == command.attempt_id
        and row["fencing_token"] == command.fencing_token
    )
    if not binding:
        raise LedgerError("run command_id replay changed its evidence binding")
    return False, int(row["transition_id"]), previous, current


def _append(connection: Any, command: RunTransitionCommand, created_at: str) -> Any:
    return connection.execute(
        """insert into transitions(
           run_id,unit_id,scope,command_kind,command_id,
           from_status,to_status,from_resumable_status,to_resumable_status,
           from_version,to_version,reason,evidence_sha256,attempt_id,
           fencing_token,clear_last_good_if,set_last_good_artifact_id,created_at,
           from_completion_json,to_completion_json)
           values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            command.run_id, command.anchor_unit_id, "run", command.command_kind,
            command.command_id, command.expected_status, command.target_status,
            None, None, command.expected_version, command.expected_version + 1,
            command.reason, command.evidence_sha256, command.attempt_id,
            command.fencing_token, None, None, created_at,
            _canonical(command.expected_completion.payload()),
            _canonical(command.target_completion.payload()),
        ),
    )


def _completion(raw: Any) -> CompletionProjection:
    if not isinstance(raw, str):
        raise LedgerError("run completion transition binding is invalid")
    try:
        value = json.loads(raw)
        if _canonical(value) != raw:
            raise ValueError
        return CompletionProjection.from_payload(value)
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise LedgerError("run completion transition binding is invalid") from error


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


__all__ = ["apply_run_transition"]
