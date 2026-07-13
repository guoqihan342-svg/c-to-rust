from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .ledger_schema import _now_text, atomic
from .ledger_security import LedgerError
from .ledger_transition_audit import command_rows
from .ledger_transition_policy import (
    RunProjection, RunTransitionCommand, TransitionCommand, UnitProjection,
    UnitState, assert_run_transition_allowed, assert_transition_allowed,
)
from .ledger_transition_replay import (
    assert_run_event_projection, assert_unit_event_projection,
    load_run_projection, load_unit_projection,
)


@dataclass(frozen=True, slots=True)
class TransitionResult:
    applied: bool
    transition_id: int
    previous: UnitProjection
    current: UnitProjection


@dataclass(frozen=True, slots=True)
class RunTransitionResult:
    applied: bool
    transition_id: int
    previous: RunProjection
    current: RunProjection


class TransitionAuthority:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def apply(
        self, command: TransitionCommand, *, created_at: str | None = None,
    ) -> TransitionResult:
        with atomic(self.connection):
            replay = self._find_unit_replay(command)
            if replay is not None:
                assert_unit_event_projection(
                    self.connection, command.run_id, command.unit_id,
                )
                return replay
            assert_unit_event_projection(
                self.connection, command.run_id, command.unit_id,
            )
            assert_transition_allowed(command)
            current = load_unit_projection(
                self.connection, command.run_id, command.unit_id,
            )
            expected = UnitProjection(command.expected, command.expected_version)
            if current != expected:
                raise LedgerError("transition expected unit state/version is stale")
            timestamp = created_at or _now_text()
            cursor = self._append_unit(command, timestamp)
            updated = self.connection.execute(
                """update migration_units set status=?,resumable_status=?,
                   state_version=state_version+1,
                   last_good_artifact_id=case
                     when ? is not null then ?
                     when ? is not null and last_good_artifact_id=? then null
                     else last_good_artifact_id end,
                   updated_at=? where run_id=? and unit_id=? and status=?
                   and resumable_status=? and state_version=?""",
                (
                    command.target.status, command.target.resumable_status,
                    command.set_last_good_artifact_id,
                    command.set_last_good_artifact_id,
                    command.clear_last_good_if, command.clear_last_good_if,
                    timestamp, command.run_id, command.unit_id,
                    command.expected.status, command.expected.resumable_status,
                    command.expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise LedgerError("transition projection lost its expected unit state/version")
            projected = UnitProjection(command.target, command.expected_version + 1)
            if assert_unit_event_projection(
                self.connection, command.run_id, command.unit_id,
            ) != projected:
                raise LedgerError("unit transition projection audit failed")
            return TransitionResult(
                True, int(cursor.lastrowid), expected, projected,
            )

    def apply_run(
        self, command: RunTransitionCommand, *, created_at: str | None = None,
    ) -> RunTransitionResult:
        with atomic(self.connection):
            replay = self._find_run_replay(command)
            if replay is not None:
                assert_run_event_projection(self.connection, command.run_id)
                return replay
            assert_run_event_projection(self.connection, command.run_id)
            assert_run_transition_allowed(command)
            current = load_run_projection(self.connection, command.run_id)
            expected = RunProjection(
                command.expected_status, command.expected_version,
            )
            if current != expected:
                raise LedgerError("transition expected run state/version is stale")
            if not self.connection.execute(
                "select 1 from migration_units where run_id=? and unit_id=?",
                (command.run_id, command.anchor_unit_id),
            ).fetchone():
                raise LedgerError("run transition anchor unit does not exist")
            timestamp = created_at or _now_text()
            cursor = self._append_run(command, timestamp)
            updated = self.connection.execute(
                """update project_runs set status=?,state_version=state_version+1,
                   updated_at=? where run_id=? and status=? and state_version=?""",
                (
                    command.target_status, timestamp, command.run_id,
                    command.expected_status, command.expected_version,
                ),
            )
            if updated.rowcount != 1:
                raise LedgerError("transition projection lost its expected run state/version")
            projected = RunProjection(
                command.target_status, command.expected_version + 1,
            )
            if assert_run_event_projection(self.connection, command.run_id) != projected:
                raise LedgerError("run transition projection audit failed")
            return RunTransitionResult(
                True, int(cursor.lastrowid), expected, projected,
            )

    def bound_unit_expected(
        self, *, run_id: str, unit_id: str, command_kind: str,
        command_id: str,
    ) -> UnitProjection | None:
        matches = command_rows(
            self.connection, run_id=run_id,
            command_id=command_id, scope="unit",
        )
        if not matches:
            return None
        row = _one(matches)
        if row["unit_id"] != unit_id or row["command_kind"] != command_kind:
            raise LedgerError("transition command_id changed its unit/kind binding")
        return _unit_projection(row, "from")

    def _find_unit_replay(
        self, command: TransitionCommand,
    ) -> TransitionResult | None:
        matches = command_rows(
            self.connection, run_id=command.run_id,
            command_id=command.command_id, scope="unit",
        )
        if not matches:
            return None
        row = _one(matches)
        previous = _unit_projection(row, "from")
        current = _unit_projection(row, "to")
        binding = (
            row["unit_id"] == command.unit_id
            and row["command_kind"] == command.command_kind
            and previous == UnitProjection(command.expected, command.expected_version)
            and current == UnitProjection(command.target, command.expected_version + 1)
            and row["reason"] == command.reason
            and row["evidence_sha256"] == command.evidence_sha256
            and row["clear_last_good_if"] == command.clear_last_good_if
            and row["set_last_good_artifact_id"] == command.set_last_good_artifact_id
            and row["attempt_id"] == command.attempt_id
            and row["fencing_token"] == command.fencing_token
        )
        if not binding:
            raise LedgerError("transition command_id replay changed its evidence binding")
        return TransitionResult(
            False, int(row["transition_id"]), previous, current,
        )

    def _find_run_replay(
        self, command: RunTransitionCommand,
    ) -> RunTransitionResult | None:
        matches = command_rows(
            self.connection, run_id=command.run_id,
            command_id=command.command_id, scope="run",
        )
        if not matches:
            return None
        row = _one(matches)
        previous = RunProjection(str(row["from_status"]), int(row["from_version"]))
        current = RunProjection(str(row["to_status"]), int(row["to_version"]))
        binding = (
            row["unit_id"] == command.anchor_unit_id
            and row["command_kind"] == command.command_kind
            and previous == RunProjection(
                command.expected_status, command.expected_version,
            )
            and current == RunProjection(
                command.target_status, command.expected_version + 1,
            )
            and row["reason"] == command.reason
            and row["evidence_sha256"] == command.evidence_sha256
            and row["attempt_id"] == command.attempt_id
            and row["fencing_token"] == command.fencing_token
        )
        if not binding:
            raise LedgerError("run command_id replay changed its evidence binding")
        return RunTransitionResult(
            False, int(row["transition_id"]), previous, current,
        )

    def _append_unit(
        self, command: TransitionCommand, created_at: str,
    ) -> sqlite3.Cursor:
        return self._append(
            scope="unit", command=command,
            unit_id=command.unit_id,
            from_status=command.expected.status,
            to_status=command.target.status,
            from_resumable=command.expected.resumable_status,
            to_resumable=command.target.resumable_status,
            clear_last_good_if=command.clear_last_good_if,
            set_last_good_artifact_id=command.set_last_good_artifact_id,
            created_at=created_at,
        )

    def _append_run(
        self, command: RunTransitionCommand, created_at: str,
    ) -> sqlite3.Cursor:
        return self._append(
            scope="run", command=command,
            unit_id=command.anchor_unit_id,
            from_status=command.expected_status,
            to_status=command.target_status,
            from_resumable=None, to_resumable=None,
            clear_last_good_if=None, set_last_good_artifact_id=None,
            created_at=created_at,
        )

    def _append(self, **values: Any) -> sqlite3.Cursor:
        command = values["command"]
        return self.connection.execute(
            """insert into transitions(
               run_id,unit_id,scope,command_kind,command_id,
               from_status,to_status,from_resumable_status,to_resumable_status,
               from_version,to_version,reason,evidence_sha256,attempt_id,
               fencing_token,clear_last_good_if,set_last_good_artifact_id,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                command.run_id, values["unit_id"], values["scope"],
                command.command_kind, command.command_id,
                values["from_status"], values["to_status"],
                values["from_resumable"], values["to_resumable"],
                command.expected_version, command.expected_version + 1,
                command.reason, command.evidence_sha256,
                command.attempt_id, command.fencing_token,
                values["clear_last_good_if"],
                values["set_last_good_artifact_id"], values["created_at"],
            ),
        )


def load_unit_state(
    connection: sqlite3.Connection, run_id: str, unit_id: str,
) -> UnitState:
    return load_unit_projection(connection, run_id, unit_id).state


def load_run_state(connection: sqlite3.Connection, run_id: str) -> str:
    return load_run_projection(connection, run_id).status


def _unit_projection(row: sqlite3.Row, prefix: str) -> UnitProjection:
    return UnitProjection(
        UnitState(
            str(row[f"{prefix}_status"]),
            str(row[f"{prefix}_resumable_status"]),
        ),
        int(row[f"{prefix}_version"]),
    )


def _one(matches: list[sqlite3.Row]) -> sqlite3.Row:
    if len(matches) != 1:
        raise LedgerError("transition command_id is duplicated in the ledger")
    return matches[0]


__all__ = [
    "RunTransitionResult", "TransitionAuthority", "TransitionResult",
    "load_run_projection", "load_run_state", "load_unit_projection",
    "load_unit_state",
]
