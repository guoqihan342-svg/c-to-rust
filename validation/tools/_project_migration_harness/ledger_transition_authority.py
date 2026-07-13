from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping

from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_audit import (
    command_rows, encode_run_command, encode_unit_command,
)
from .ledger_transition_policy import (
    RunTransitionCommand, TransitionCommand, UnitState,
    assert_run_transition_allowed, assert_transition_allowed,
)


@dataclass(frozen=True, slots=True)
class TransitionResult:
    applied: bool
    transition_id: int
    previous: UnitState
    current: UnitState


@dataclass(frozen=True, slots=True)
class RunTransitionResult:
    applied: bool
    transition_id: int
    previous_status: str
    current_status: str


class TransitionAuthority:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def apply(
        self, command: TransitionCommand, *, created_at: str | None = None,
    ) -> TransitionResult:
        with atomic(self.connection):
            replay = self._find_unit_replay(command)
            if replay is not None:
                return replay
            assert_transition_allowed(command)
            current = load_unit_state(self.connection, command.run_id, command.unit_id)
            if current != command.expected:
                raise LedgerError("transition expected unit state is stale")
            timestamp = created_at or _now_text()
            cursor = self._append(
                run_id=command.run_id, unit_id=command.unit_id,
                from_status=command.expected.status, to_status=command.target.status,
                reason=encode_unit_command(command), attempt_id=command.attempt_id,
                fencing_token=command.fencing_token, created_at=timestamp,
            )
            updated = self.connection.execute(
                """update migration_units set status=?,resumable_status=?,
                   last_good_artifact_id=case
                     when ? is not null then ?
                     when ? is not null and last_good_artifact_id=? then null
                     else last_good_artifact_id end,
                   updated_at=? where run_id=? and unit_id=? and status=?
                   and resumable_status=?""",
                (
                    command.target.status, command.target.resumable_status,
                    command.set_last_good_artifact_id, command.set_last_good_artifact_id,
                    command.clear_last_good_if, command.clear_last_good_if, timestamp,
                    command.run_id, command.unit_id, command.expected.status,
                    command.expected.resumable_status,
                ),
            )
            if updated.rowcount != 1:
                raise LedgerError("transition projection lost its expected unit state")
            return TransitionResult(
                True, int(cursor.lastrowid), command.expected, command.target,
            )

    def apply_run(
        self, command: RunTransitionCommand, *, created_at: str | None = None,
    ) -> RunTransitionResult:
        with atomic(self.connection):
            replay = self._find_run_replay(command)
            if replay is not None:
                return replay
            assert_run_transition_allowed(command)
            if load_run_state(self.connection, command.run_id) != command.expected_status:
                raise LedgerError("transition expected run state is stale")
            if not self.connection.execute(
                "select 1 from migration_units where run_id=? and unit_id=?",
                (command.run_id, command.anchor_unit_id),
            ).fetchone():
                raise LedgerError("run transition anchor unit does not exist")
            timestamp = created_at or _now_text()
            cursor = self._append(
                run_id=command.run_id, unit_id=command.anchor_unit_id,
                from_status=command.expected_status, to_status=command.target_status,
                reason=encode_run_command(command), attempt_id=command.attempt_id,
                fencing_token=command.fencing_token, created_at=timestamp,
            )
            updated = self.connection.execute(
                """update project_runs set status=?,updated_at=?
                   where run_id=? and status=?""",
                (command.target_status, timestamp, command.run_id, command.expected_status),
            )
            if updated.rowcount != 1:
                raise LedgerError("transition projection lost its expected run state")
            return RunTransitionResult(
                True, int(cursor.lastrowid), command.expected_status, command.target_status,
            )

    def bound_unit_expected(
        self, *, run_id: str, unit_id: str, command_id: str,
    ) -> UnitState | None:
        matches = command_rows(
            self.connection, run_id=run_id, unit_id=None,
            command_id=command_id, scope="unit",
        )
        if not matches:
            return None
        row, payload = _one(matches)
        if row["unit_id"] != unit_id:
            raise LedgerError("transition command_id changed its unit binding")
        return _unit_state(row["from_status"], payload["expected_resumable_status"])

    def _find_unit_replay(self, command: TransitionCommand) -> TransitionResult | None:
        matches = command_rows(
            self.connection, run_id=command.run_id, unit_id=None,
            command_id=command.command_id, scope="unit",
        )
        if not matches:
            return None
        row, payload = _one(matches)
        expected = _unit_state(row["from_status"], payload["expected_resumable_status"])
        target = _unit_state(row["to_status"], payload["target_resumable_status"])
        binding = (
            row["unit_id"] == command.unit_id
            and expected == command.expected
            and target == command.target
            and payload["reason"] == command.reason
            and payload["evidence_sha256"] == command.evidence_sha256
            and payload.get("clear_last_good_if") == command.clear_last_good_if
            and payload.get("set_last_good_artifact_id") == command.set_last_good_artifact_id
            and row["attempt_id"] == command.attempt_id
            and row["fencing_token"] == command.fencing_token
        )
        if not binding:
            raise LedgerError("transition command_id replay changed its evidence binding")
        return TransitionResult(False, int(row["transition_id"]), expected, target)

    def _find_run_replay(
        self, command: RunTransitionCommand,
    ) -> RunTransitionResult | None:
        matches = command_rows(
            self.connection, run_id=command.run_id, unit_id=None,
            command_id=command.command_id, scope="run",
        )
        if not matches:
            return None
        row, payload = _one(matches)
        binding = (
            row["unit_id"] == command.anchor_unit_id
            and row["from_status"] == command.expected_status
            and row["to_status"] == command.target_status
            and payload["reason"] == command.reason
            and payload["evidence_sha256"] == command.evidence_sha256
            and row["attempt_id"] == command.attempt_id
            and row["fencing_token"] == command.fencing_token
        )
        if not binding:
            raise LedgerError("run command_id replay changed its evidence binding")
        return RunTransitionResult(
            False, int(row["transition_id"]),
            str(row["from_status"]), str(row["to_status"]),
        )

    def _append(self, **values: Any) -> sqlite3.Cursor:
        return self.connection.execute(
            """insert into transitions(run_id,unit_id,from_status,to_status,reason,
               attempt_id,fencing_token,created_at) values (?,?,?,?,?,?,?,?)""",
            (
                values["run_id"], values["unit_id"], values["from_status"],
                values["to_status"], values["reason"], values["attempt_id"],
                values["fencing_token"], values["created_at"],
            ),
        )


def load_unit_state(
    connection: sqlite3.Connection, run_id: str, unit_id: str,
) -> UnitState:
    row = connection.execute(
        """select status,resumable_status from migration_units
           where run_id=? and unit_id=?""",
        (run_id, unit_id),
    ).fetchone()
    if row is None:
        raise LedgerError("migration unit does not exist")
    return _unit_state(row["status"], row["resumable_status"])


def load_run_state(connection: sqlite3.Connection, run_id: str) -> str:
    row = connection.execute(
        "select status from project_runs where run_id=?", (run_id,),
    ).fetchone()
    if row is None:
        raise LedgerError("project run does not exist")
    return str(row["status"])


def _unit_state(status: Any, resumable_status: Any) -> UnitState:
    try:
        return UnitState(str(status), str(resumable_status))
    except ValueError as error:
        raise LedgerError("transition command unit state binding is invalid") from error


def _one(matches: list[tuple[sqlite3.Row, Mapping[str, Any]]]) -> tuple[sqlite3.Row, Mapping[str, Any]]:
    if len(matches) != 1:
        raise LedgerError("transition command_id is duplicated in the ledger")
    return matches[0]


__all__ = [
    "RunTransitionResult", "TransitionAuthority", "TransitionResult",
    "load_run_state", "load_unit_state",
]
