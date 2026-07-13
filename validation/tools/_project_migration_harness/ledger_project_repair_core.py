from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .ledger_project_repair_replay import assert_project_repair_projection
from .ledger_security import LedgerError, assert_no_secrets
from .project_repair_policy import (
    ProjectRepairProjection, assert_project_repair_transition,
)


@dataclass(frozen=True, slots=True)
class ProjectRepairTransitionResult:
    applied: bool
    event_id: int
    attempt_id: str | None
    previous: ProjectRepairProjection
    current: ProjectRepairProjection


class ProjectRepairCore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def _expected(
        self, run_id: str, queue_sha: str, repair_id: str,
        status: str, version: int,
    ) -> ProjectRepairProjection:
        current = assert_project_repair_projection(
            self.connection, run_id=run_id, queue_sha256=queue_sha,
            repair_id=repair_id,
        )
        if current.status != status or current.version != version:
            raise LedgerError("project repair expected state/version is stale")
        return current

    def _append_and_project(
        self, run_id: str, queue_sha: str, repair_id: str, command_id: str,
        kind: str, reason: str, evidence: str, attempt_id: str | None,
        previous: ProjectRepairProjection, current: ProjectRepairProjection,
        timestamp: str,
    ) -> ProjectRepairTransitionResult:
        assert_project_repair_transition(previous, current, command_kind=kind)
        cursor = self.connection.execute(
            """insert into project_repair_events(
               run_id,project_repair_queue_sha256,repair_id,command_kind,command_id,
               from_status,to_status,from_version,to_version,
               from_attempt_count,to_attempt_count,from_active_attempt_id,
               to_active_attempt_id,from_candidate_ir_sha256,to_candidate_ir_sha256,
               evidence_sha256,attempt_id,reason,created_at)
               values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id, queue_sha, repair_id, kind, command_id,
                previous.status, current.status, previous.version, current.version,
                previous.attempt_count, current.attempt_count,
                previous.active_attempt_id, current.active_attempt_id,
                previous.candidate_ir_sha256, current.candidate_ir_sha256,
                evidence, attempt_id, reason, timestamp,
            ),
        )
        updated = self.connection.execute(
            """update project_repair_items set status=?,state_version=?,attempt_count=?,
               active_attempt_id=?,candidate_ir_sha256=?,updated_at=?
               where run_id=? and project_repair_queue_sha256=? and repair_id=?
               and status=? and state_version=? and attempt_count=?
               and active_attempt_id is ? and candidate_ir_sha256 is ?""",
            (
                current.status, current.version, current.attempt_count,
                current.active_attempt_id, current.candidate_ir_sha256, timestamp,
                run_id, queue_sha, repair_id, previous.status, previous.version,
                previous.attempt_count, previous.active_attempt_id,
                previous.candidate_ir_sha256,
            ),
        )
        if updated.rowcount != 1:
            raise LedgerError("project repair projection lost its expected state/version")
        if assert_project_repair_projection(
            self.connection, run_id=run_id, queue_sha256=queue_sha,
            repair_id=repair_id,
        ) != current:
            raise LedgerError("project repair projection audit failed")
        return ProjectRepairTransitionResult(
            True, int(cursor.lastrowid), attempt_id, previous, current,
        )

    def _event_replay(
        self, run_id: str, command_id: str, queue_sha: str, repair_id: str,
        **expected: Any,
    ) -> ProjectRepairTransitionResult | None:
        rows = self.connection.execute(
            "select * from project_repair_events where run_id=? and command_id=?",
            (run_id, command_id),
        ).fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise LedgerError("project repair command_id is duplicated")
        row = rows[0]
        previous = _event_projection(row, "from", self._max_attempts(row))
        current = _event_projection(row, "to", previous.max_attempts)
        binding = (
            row["project_repair_queue_sha256"] == queue_sha
            and row["repair_id"] == repair_id
            and row["command_kind"] == expected["kind"]
            and previous.status == expected["expected_status"]
            and previous.version == expected["expected_version"]
            and current.status == expected["target_status"]
            and row["evidence_sha256"] == expected["evidence_sha256"]
            and row["attempt_id"] == expected["attempt_id"]
            and current.candidate_ir_sha256 == expected["candidate_ir_sha256"]
            and row["reason"] == expected["reason"]
        )
        if not binding:
            raise LedgerError("project repair command_id replay changed its evidence binding")
        assert_project_repair_projection(
            self.connection, run_id=run_id, queue_sha256=queue_sha,
            repair_id=repair_id,
        )
        return ProjectRepairTransitionResult(
            False, int(row["event_id"]), expected["attempt_id"], previous, current,
        )

    def _command_target(self, run_id: str, command_id: str) -> str | None:
        rows = self.connection.execute(
            """select to_status from project_repair_events
               where run_id=? and command_id=?""",
            (run_id, command_id),
        ).fetchall()
        if len(rows) > 1:
            raise LedgerError("project repair command_id is duplicated")
        return None if not rows else str(rows[0]["to_status"])

    def _max_attempts(self, row: sqlite3.Row) -> int:
        value = self.connection.execute(
            """select max_attempts from project_repair_items where run_id=?
               and project_repair_queue_sha256=? and repair_id=?""",
            (row["run_id"], row["project_repair_queue_sha256"], row["repair_id"]),
        ).fetchone()
        if value is None:
            raise LedgerError("project repair event references a missing item")
        return int(value[0])

    def _attempt(self, attempt_id: str) -> sqlite3.Row:
        row = self.connection.execute(
            "select * from project_repair_attempts where attempt_id=?", (attempt_id,),
        ).fetchone()
        if row is None:
            raise LedgerError("project repair attempt does not exist")
        return row

    def _assert_attempt_binding(
        self, attempt_id: str, *, worker_id: str, input_sha256: str,
        status: str | None, output_ir_sha256: str | None = None,
        metadata_json: str | None = None, lease_ttl_seconds: int | None = None,
        error_key: str | None = None, check_error_key: bool = False,
    ) -> None:
        row = self._attempt(attempt_id)
        if (
            row["worker_id"] != worker_id or row["input_sha256"] != input_sha256
            or (status is not None and row["status"] != status)
            or (status is not None and row["output_ir_sha256"] != output_ir_sha256)
            or (metadata_json is not None and row["metadata_json"] != metadata_json)
            or (
                lease_ttl_seconds is not None
                and row["lease_ttl_seconds"] != lease_ttl_seconds
            )
            or (check_error_key and row["error_key"] != error_key)
        ):
            raise LedgerError("project repair attempt replay changed its binding")

    def _require_artifact_evidence(
        self, *, run_id: str, queue_sha256: str, repair_id: str,
        evidence_sha256: str, attempt_id: str | None = None,
    ) -> None:
        statement = (
            """select 1 from project_repair_artifacts where run_id=?
               and project_repair_queue_sha256=? and repair_id=?
               and content_sha256=?"""
        )
        parameters: tuple[Any, ...] = (
            run_id, queue_sha256, repair_id, evidence_sha256,
        )
        if attempt_id is not None:
            statement += " and attempt_id=?"
            parameters += (attempt_id,)
        if self.connection.execute(statement + " limit 1", parameters).fetchone() is None:
            raise LedgerError(
                "project repair terminal evidence is not bound to an immutable artifact"
            )

    def _require_candidate_ir_artifact(
        self, *, attempt_id: str, candidate_ir_sha256: str,
    ) -> None:
        rows = self.connection.execute(
            """select metadata_json from project_repair_artifacts
               where attempt_id=? and kind='rust-project-ir-candidate'""",
            (attempt_id,),
        ).fetchall()
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            if metadata.get("ir_sha256") == candidate_ir_sha256:
                return
        raise LedgerError(
            "project repair candidate IR is not bound to an immutable artifact"
        )


def _event_projection(
    row: sqlite3.Row, prefix: str, max_attempts: int,
) -> ProjectRepairProjection:
    return ProjectRepairProjection(
        str(row[f"{prefix}_status"]), int(row[f"{prefix}_version"]),
        int(row[f"{prefix}_attempt_count"]), max_attempts,
        row[f"{prefix}_active_attempt_id"], row[f"{prefix}_candidate_ir_sha256"],
    )


def attempt_scope(row: sqlite3.Row) -> tuple[str, str, str]:
    return (
        str(row["run_id"]), str(row["project_repair_queue_sha256"]),
        str(row["repair_id"]),
    )


def require_identity(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256 or "\x00" in value:
        raise ValueError(f"{field} is invalid")
    assert_no_secrets(value, field)
    return value


__all__ = [
    "ProjectRepairCore", "ProjectRepairTransitionResult", "attempt_scope",
    "require_identity",
]
