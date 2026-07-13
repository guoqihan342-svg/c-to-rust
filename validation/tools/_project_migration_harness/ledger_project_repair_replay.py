from __future__ import annotations

import re
import sqlite3
from typing import Any

from .ledger_project_repair_replay_audit import (
    audit_project_repair_attempt_rows, audit_project_repair_event_evidence,
)
from .ledger_security import LedgerError
from .project_repair_policy import (
    ProjectRepairProjection, assert_project_repair_transition,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EVENT_REASONS = {
    "attempt_started": {"project_repair_attempt_started"},
    "attempt_completed": {"project_repair_attempt_completed"},
    "attempt_failed": {
        "project_repair_attempt_failed", "project_repair_attempt_result_unknown",
    },
    "attempt_recovered": {
        "project_repair_attempt_recovered",
        "project_repair_attempt_recovered_known",
    },
    "repair_cancelled": {"project_repair_attempt_cancelled"},
    "candidate_rolled_back": {"project_repair_candidate_rolled_back"},
    "candidate_recoordinated": {"project_repair_candidate_recoordinated"},
}


def load_project_repair_projection(
    connection: sqlite3.Connection, *, run_id: str, queue_sha256: str,
    repair_id: str,
) -> ProjectRepairProjection:
    row = connection.execute(
        """select status,state_version,attempt_count,max_attempts,
           active_attempt_id,candidate_ir_sha256 from project_repair_items
           where run_id=? and project_repair_queue_sha256=? and repair_id=?""",
        (run_id, queue_sha256, repair_id),
    ).fetchone()
    if row is None:
        raise LedgerError("project repair item does not exist")
    return _projection(row, "")


def assert_project_repair_projection(
    connection: sqlite3.Connection, *, run_id: str, queue_sha256: str,
    repair_id: str,
) -> ProjectRepairProjection:
    item = connection.execute(
        """select * from project_repair_items where run_id=?
           and project_repair_queue_sha256=? and repair_id=?""",
        (run_id, queue_sha256, repair_id),
    ).fetchone()
    if item is None:
        raise LedgerError("project repair item does not exist")
    current = _projection(item, "")
    projected = ProjectRepairProjection(
        str(item["initial_status"]), 0,
        int(item["inherited_attempt_count"]),
        current.max_attempts, None, None,
    )
    expected_attempt_status: dict[str, str] = {}
    rows = connection.execute(
        """select * from project_repair_events where run_id=?
           and project_repair_queue_sha256=? and repair_id=? order by event_id""",
        (run_id, queue_sha256, repair_id),
    ).fetchall()
    for row in rows:
        previous = _event_projection(row, "from", current.max_attempts)
        target = _event_projection(row, "to", current.max_attempts)
        if previous != projected:
            raise LedgerError("project repair event history is not contiguous")
        if _SHA256.fullmatch(str(row["evidence_sha256"])) is None:
            raise LedgerError("project repair event evidence SHA is invalid")
        kind = str(row["command_kind"])
        if str(row["reason"]) not in _EVENT_REASONS.get(kind, set()):
            raise LedgerError("project repair event reason is invalid")
        assert_project_repair_transition(previous, target, command_kind=kind)
        audit_project_repair_event_evidence(connection, row)
        _audit_event_attempt(row, previous, target, expected_attempt_status)
        projected = target
    if projected != current:
        raise LedgerError("project repair projection drifted from immutable events")
    audit_project_repair_attempt_rows(
        connection, run_id=run_id, queue_sha256=queue_sha256,
        repair_id=repair_id, attempt_count=current.attempt_count,
        inherited_attempt_count=int(item["inherited_attempt_count"]),
        active_attempt_id=current.active_attempt_id,
        expected_status=expected_attempt_status,
    )
    return current


def _event_projection(
    row: sqlite3.Row, prefix: str, max_attempts: int,
) -> ProjectRepairProjection:
    candidate = row[f"{prefix}_candidate_ir_sha256"]
    if candidate is not None and _SHA256.fullmatch(str(candidate)) is None:
        raise LedgerError("project repair event candidate SHA is invalid")
    return ProjectRepairProjection(
        str(row[f"{prefix}_status"]),
        int(row[f"{prefix}_version"]),
        int(row[f"{prefix}_attempt_count"]),
        max_attempts,
        _optional_text(row[f"{prefix}_active_attempt_id"]),
        _optional_text(candidate),
    )


def _projection(row: sqlite3.Row, prefix: str) -> ProjectRepairProjection:
    candidate = row[f"{prefix}candidate_ir_sha256"]
    if candidate is not None and _SHA256.fullmatch(str(candidate)) is None:
        raise LedgerError("project repair candidate SHA is invalid")
    return ProjectRepairProjection(
        str(row[f"{prefix}status"]),
        int(row[f"{prefix}state_version"]),
        int(row[f"{prefix}attempt_count"]),
        int(row[f"{prefix}max_attempts"]),
        _optional_text(row[f"{prefix}active_attempt_id"]),
        _optional_text(candidate),
    )


def _audit_event_attempt(
    row: sqlite3.Row, previous: ProjectRepairProjection,
    current: ProjectRepairProjection, expected: dict[str, str],
) -> None:
    kind = str(row["command_kind"])
    attempt_id = _optional_text(row["attempt_id"])
    if kind == "attempt_started":
        if attempt_id is None or current.active_attempt_id != attempt_id:
            raise LedgerError("project repair start event lost its attempt binding")
        if attempt_id in expected:
            raise LedgerError("project repair attempt was started more than once")
        expected[attempt_id] = "running"
        return
    if kind in {"attempt_completed", "attempt_failed", "attempt_recovered"}:
        if attempt_id is None or previous.active_attempt_id != attempt_id:
            raise LedgerError("project repair finish event lost its attempt binding")
        statuses = {
            "attempt_completed": "completed",
            "attempt_failed": "failed",
            "attempt_recovered": "recovered",
        }
        if expected.get(attempt_id) != "running":
            raise LedgerError("project repair attempt finish has no matching start")
        expected[attempt_id] = statuses[kind]
        return
    if kind == "repair_cancelled" and previous.status == "running":
        if attempt_id is None or previous.active_attempt_id != attempt_id:
            raise LedgerError("project repair cancellation lost its attempt binding")
        if expected.get(attempt_id) != "running":
            raise LedgerError("project repair cancellation has no matching start")
        expected[attempt_id] = "cancelled"
        return
    if attempt_id is not None:
        raise LedgerError("project repair event has an unexpected attempt binding")


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "assert_project_repair_projection", "load_project_repair_projection",
]
