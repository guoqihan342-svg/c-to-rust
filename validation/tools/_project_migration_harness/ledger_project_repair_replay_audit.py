from __future__ import annotations

import json
import re
import sqlite3
from typing import Any

from .ledger_security import LedgerError


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def audit_project_repair_attempt_rows(
    connection: sqlite3.Connection, *, run_id: str, queue_sha256: str,
    repair_id: str, attempt_count: int, inherited_attempt_count: int,
    active_attempt_id: str | None, expected_status: dict[str, str],
) -> None:
    rows = connection.execute(
        """select attempt_id,ordinal,status,input_sha256,output_ir_sha256,
           lease_ttl_seconds,lease_expires_at,command_started,command_started_at
           from project_repair_attempts where run_id=?
           and project_repair_queue_sha256=? and repair_id=? order by ordinal""",
        (run_id, queue_sha256, repair_id),
    ).fetchall()
    if len(rows) != attempt_count - inherited_attempt_count:
        raise LedgerError("project repair attempt projection count drifted")
    expected_ordinals = list(range(
        inherited_attempt_count + 1, attempt_count + 1,
    ))
    if [int(row["ordinal"]) for row in rows] != expected_ordinals:
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
    expected_running = [] if active_attempt_id is None else [active_attempt_id]
    if running != expected_running:
        raise LedgerError("project repair active attempt projection drifted")


def audit_project_repair_event_evidence(
    connection: sqlite3.Connection, row: sqlite3.Row,
) -> None:
    kind = str(row["command_kind"])
    evidence = str(row["evidence_sha256"])
    attempt_id = None if row["attempt_id"] is None else str(row["attempt_id"])
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
        return
    if kind == "repair_cancelled" and attempt_id is None:
        receipt = connection.execute(
            """select 1 from project_interface_receipts
               where run_id=? and coordinator_receipt_sha256=?""",
            (row["run_id"], evidence),
        ).fetchone()
        if receipt is None:
            raise LedgerError("project repair supersession has no successor receipt")


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


__all__ = [
    "audit_project_repair_attempt_rows", "audit_project_repair_event_evidence",
]
