from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

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
    current = load_project_repair_projection(
        connection, run_id=run_id, queue_sha256=queue_sha256,
        repair_id=repair_id,
    )
    projected = ProjectRepairProjection(
        "queued", 0, 0, current.max_attempts, None, None,
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
        _audit_event_evidence(connection, row)
        _audit_event_attempt(row, previous, target, expected_attempt_status)
        projected = target
    if projected != current:
        raise LedgerError("project repair projection drifted from immutable events")
    _audit_attempt_rows(
        connection, run_id=run_id, queue_sha256=queue_sha256,
        repair_id=repair_id, projection=current,
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


def _audit_attempt_rows(
    connection: sqlite3.Connection, *, run_id: str, queue_sha256: str,
    repair_id: str, projection: ProjectRepairProjection,
    expected_status: dict[str, str],
) -> None:
    rows = connection.execute(
        """select attempt_id,ordinal,status,input_sha256,output_ir_sha256,
           lease_ttl_seconds,lease_expires_at,command_started,command_started_at
           from project_repair_attempts where run_id=?
           and project_repair_queue_sha256=? and repair_id=? order by ordinal""",
        (run_id, queue_sha256, repair_id),
    ).fetchall()
    if len(rows) != projection.attempt_count:
        raise LedgerError("project repair attempt projection count drifted")
    if [int(row["ordinal"]) for row in rows] != list(range(1, len(rows) + 1)):
        raise LedgerError("project repair attempt ordinals are not contiguous")
    for row in rows:
        attempt_id = str(row["attempt_id"])
        if expected_status.get(attempt_id) != str(row["status"]):
            raise LedgerError("project repair attempt status drifted from events")
        if _SHA256.fullmatch(str(row["input_sha256"])) is None:
            raise LedgerError("project repair attempt input SHA is invalid")
        output = row["output_ir_sha256"]
        if (output is not None) != (row["status"] == "completed"):
            raise LedgerError("project repair attempt output binding is invalid")
        if output is not None and _SHA256.fullmatch(str(output)) is None:
            raise LedgerError("project repair attempt output SHA is invalid")
        if (
            not 30 <= int(row["lease_ttl_seconds"]) <= 3_600
            or int(row["lease_expires_at"]) < 0
            or int(row["command_started"]) not in {0, 1}
            or (row["command_started_at"] is not None)
            != (int(row["command_started"]) == 1)
        ):
            raise LedgerError("project repair attempt lease/launch binding is invalid")
    running = [str(row["attempt_id"]) for row in rows if row["status"] == "running"]
    expected_running = [] if projection.active_attempt_id is None else [projection.active_attempt_id]
    if running != expected_running:
        raise LedgerError("project repair active attempt projection drifted")


def _audit_event_evidence(
    connection: sqlite3.Connection, row: sqlite3.Row,
) -> None:
    kind = str(row["command_kind"])
    evidence = str(row["evidence_sha256"])
    attempt_id = _optional_text(row["attempt_id"])
    if kind == "attempt_started":
        attempt = connection.execute(
            "select input_sha256 from project_repair_attempts where attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if attempt is None or attempt["input_sha256"] != evidence:
            raise LedgerError("project repair start evidence drifted from its input")
        return
    if kind in {"attempt_completed", "attempt_failed"} or (
        kind == "repair_cancelled" and attempt_id is not None
    ):
        if not _artifact_evidence_exists(connection, row, evidence, attempt_id):
            raise LedgerError("project repair finish evidence has no immutable artifact")
        if kind == "attempt_completed" and not _candidate_ir_artifact_exists(
            connection, attempt_id,
        ):
            raise LedgerError("project repair completed candidate has no IR artifact")
        return
    if kind == "attempt_recovered":
        attempt = connection.execute(
            "select command_started from project_repair_attempts where attempt_id=?",
            (attempt_id,),
        ).fetchone()
        known = row["reason"] == "project_repair_attempt_recovered_known"
        if attempt is None or bool(attempt["command_started"]) != known:
            raise LedgerError("project repair recovery launch/result binding drifted")
        if known and not _artifact_evidence_exists(
            connection, row, evidence, attempt_id,
        ):
            raise LedgerError("known project repair recovery has no immutable artifact")
        return
    if kind == "candidate_rolled_back":
        if not _artifact_evidence_exists(connection, row, evidence, None):
            raise LedgerError("project repair rollback evidence has no immutable artifact")
        return
    if kind == "candidate_recoordinated":
        receipt = connection.execute(
            """select 1 from project_interface_receipts
               where run_id=? and coordinator_receipt_sha256=?""",
            (row["run_id"], evidence),
        ).fetchone()
        if receipt is None:
            raise LedgerError("project repair resolution evidence has no receipt")


def _artifact_evidence_exists(
    connection: sqlite3.Connection, row: sqlite3.Row, evidence: str,
    attempt_id: str | None,
) -> bool:
    statement = (
        """select 1 from project_repair_artifacts where run_id=?
           and project_repair_queue_sha256=? and repair_id=?
           and content_sha256=?"""
    )
    parameters: tuple[Any, ...] = (
        row["run_id"], row["project_repair_queue_sha256"],
        row["repair_id"], evidence,
    )
    if attempt_id is not None:
        statement += " and attempt_id=?"
        parameters += (attempt_id,)
    return connection.execute(statement + " limit 1", parameters).fetchone() is not None


def _candidate_ir_artifact_exists(
    connection: sqlite3.Connection, attempt_id: str | None,
) -> bool:
    if attempt_id is None:
        return False
    attempt = connection.execute(
        "select output_ir_sha256 from project_repair_attempts where attempt_id=?",
        (attempt_id,),
    ).fetchone()
    if attempt is None or attempt["output_ir_sha256"] is None:
        return False
    rows = connection.execute(
        """select metadata_json from project_repair_artifacts
           where attempt_id=? and kind='rust-project-ir-candidate'""",
        (attempt_id,),
    ).fetchall()
    for row in rows:
        try:
            metadata = json.loads(row["metadata_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if metadata.get("ir_sha256") == attempt["output_ir_sha256"]:
            return True
    return False


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


__all__ = [
    "assert_project_repair_projection", "load_project_repair_projection",
]
