from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from .gate_authority import (
    derive_project_observation, project_authority, validate_project_summary,
)
from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
)
from .ledger_schema import _now_text
from .ledger_security import LedgerError
from .project_diagnostic_contract import validate_project_diagnostic_intake


def insert_project_diagnostic_intake(
    connection: sqlite3.Connection, *, database_path: Path,
    reference: Mapping[str, Any],
) -> dict[str, Any]:
    artifact = _reference(reference)
    payload = read_content_addressed_json(
        database_path, artifact["path"], artifact["sha256"],
    )
    intake = validate_project_diagnostic_intake(payload)
    record = connection.execute(
        "select * from project_gate_records where record_id=?",
        (intake["gate_record_id"],),
    ).fetchone()
    if record is None:
        raise LedgerError("project diagnostic intake gate record is missing")
    _assert_record_binding(record, intake)
    _assert_source_evidence(database_path, intake)
    connection.execute(
        """insert into project_diagnostic_intakes(
           intake_sha256,run_id,candidate_set_sha256,rust_project_ir_sha256,
           rust_project_interface_sha256,project_input_sha256,gate_record_id,
           gate_kind,gate_epoch,artifact_path,artifact_size_bytes,
           diagnostic_count,created_at) values (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            artifact["sha256"], intake["run_id"],
            intake["candidate_set_sha256"], intake["rust_project_ir_sha256"],
            intake["rust_project_interface_sha256"],
            intake["project_input_sha256"], intake["gate_record_id"],
            intake["gate_kind"], intake["gate_epoch"], artifact["path"],
            artifact["size_bytes"], len(intake["diagnostics"]), _now_text(),
        ),
    )
    return {"artifact": artifact, "intake": intake}


def load_bound_project_diagnostic_intakes(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    references: Sequence[Mapping[str, Any]],
    rust_project_ir_sha256: str | None = None,
) -> list[dict[str, Any]]:
    wrappers = []
    for raw in references:
        reference = _reference(raw)
        row = connection.execute(
            """select * from project_diagnostic_intakes
               where run_id=? and intake_sha256=? and artifact_path=?""",
            (run_id, reference["sha256"], reference["path"]),
        ).fetchone()
        if row is None or int(row["artifact_size_bytes"]) != reference["size_bytes"]:
            raise LedgerError("project diagnostic intake is absent from the ledger")
        wrapper = _load_row(connection, database_path, row)
        if (
            rust_project_ir_sha256 is not None
            and wrapper["intake"]["rust_project_ir_sha256"]
            != rust_project_ir_sha256
        ):
            raise LedgerError("project diagnostic intake changed RustProjectIR")
        wrappers.append(wrapper)
    if len({item["artifact"]["sha256"] for item in wrappers}) != len(wrappers):
        raise LedgerError("project diagnostic intake references are duplicated")
    return wrappers


def load_latest_project_diagnostic_intakes(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    candidate_set_sha256: str, rust_project_ir_sha256: str,
    project_input_sha256: str,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """select current.* from project_diagnostic_intakes current
           where current.run_id=? and current.candidate_set_sha256=?
             and current.rust_project_ir_sha256=?
             and current.project_input_sha256=?
             and current.gate_epoch=(
               select max(newer.gate_epoch) from project_diagnostic_intakes newer
               where newer.run_id=current.run_id
                 and newer.candidate_set_sha256=current.candidate_set_sha256
                 and newer.rust_project_ir_sha256=current.rust_project_ir_sha256
                 and newer.project_input_sha256=current.project_input_sha256
                 and newer.gate_kind=current.gate_kind)
           order by current.gate_kind,current.gate_epoch""",
        (
            run_id, candidate_set_sha256, rust_project_ir_sha256,
            project_input_sha256,
        ),
    ).fetchall()
    return [_load_row(connection, database_path, row) for row in rows]


class ProjectDiagnosticLedgerMixin:
    def bound_project_diagnostic_intakes(
        self, *, run_id: str, references: Sequence[Mapping[str, Any]],
        rust_project_ir_sha256: str | None = None,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return load_bound_project_diagnostic_intakes(
                connection, database_path=self.path, run_id=run_id,
                references=references,
                rust_project_ir_sha256=rust_project_ir_sha256,
            )

    def latest_project_diagnostic_intakes(
        self, *, run_id: str, candidate_set_sha256: str,
        rust_project_ir_sha256: str, project_input_sha256: str,
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return load_latest_project_diagnostic_intakes(
                connection, database_path=self.path, run_id=run_id,
                candidate_set_sha256=candidate_set_sha256,
                rust_project_ir_sha256=rust_project_ir_sha256,
                project_input_sha256=project_input_sha256,
            )


def _load_row(
    connection: sqlite3.Connection, database_path: Path, row: sqlite3.Row,
) -> dict[str, Any]:
    reference = {
        "path": str(row["artifact_path"]),
        "sha256": str(row["intake_sha256"]),
        "size_bytes": int(row["artifact_size_bytes"]),
    }
    payload = read_content_addressed_json(
        database_path, reference["path"], reference["sha256"],
    )
    intake = validate_project_diagnostic_intake(payload)
    record = connection.execute(
        "select * from project_gate_records where record_id=?",
        (row["gate_record_id"],),
    ).fetchone()
    if record is None:
        raise LedgerError("project diagnostic intake lost its gate record")
    _assert_record_binding(record, intake)
    if (
        intake["run_id"] != row["run_id"]
        or intake["candidate_set_sha256"] != row["candidate_set_sha256"]
        or intake["rust_project_ir_sha256"] != row["rust_project_ir_sha256"]
        or intake["rust_project_interface_sha256"]
        != row["rust_project_interface_sha256"]
        or intake["project_input_sha256"] != row["project_input_sha256"]
        or intake["gate_kind"] != row["gate_kind"]
        or intake["gate_epoch"] != int(row["gate_epoch"])
        or len(intake["diagnostics"]) != int(row["diagnostic_count"])
    ):
        raise LedgerError("project diagnostic intake ledger projection drifted")
    _assert_source_evidence(database_path, intake)
    return {"artifact": reference, "intake": intake}


def _assert_record_binding(record: sqlite3.Row, intake: Mapping[str, Any]) -> None:
    if (
        record["run_id"] != intake["run_id"]
        or record["candidate_set_sha256"] != intake["candidate_set_sha256"]
        or record["gate_kind"] != intake["gate_kind"]
        or int(record["gate_epoch"]) != intake["gate_epoch"]
        or record["status"] != "failed"
        or record["verifier_id"] != project_authority(intake["gate_kind"])
        or record["evidence_path"] != intake["verifier_receipt"]["path"]
        or record["evidence_sha256"] != intake["verifier_receipt"]["sha256"]
    ):
        raise LedgerError("project diagnostic intake changed its verifier receipt")


def _assert_source_evidence(database_path: Path, intake: Mapping[str, Any]) -> None:
    raw_ref = intake["raw_observation"]
    receipt_ref = intake["verifier_receipt"]
    raw = read_content_addressed_json(
        database_path, raw_ref["path"], raw_ref["sha256"],
    )
    receipt = read_content_addressed_json(
        database_path, receipt_ref["path"], receipt_ref["sha256"],
    )
    validate_project_summary(
        receipt, run_id=intake["run_id"], gate_kind=intake["gate_kind"],
        status="failed", candidate_set_sha256=intake["candidate_set_sha256"],
        verifier_id=intake["verifier_id"],
    )
    if receipt["source_evidence"] != [dict(raw_ref)]:
        raise LedgerError("project diagnostic verifier receipt changed its raw source")
    status = derive_project_observation(
        raw, run_id=intake["run_id"], gate_kind=intake["gate_kind"],
        candidate_set_sha256=intake["candidate_set_sha256"],
    )
    observation = raw.get("observation")
    observed_input = (
        observation.get("project_input_sha256")
        if isinstance(observation, Mapping) else None
    )
    if (
        status != "failed"
        or not isinstance(observation, Mapping)
        or observation.get("outcome") != "executed"
        or (
        observed_input is not None
        and observed_input != intake["project_input_sha256"]
        )
    ):
        raise LedgerError("project diagnostic intake is not a failed host observation")


def _reference(value: Mapping[str, Any]) -> dict[str, Any]:
    reference = dict(value)
    require_content_addressed_reference(reference)
    parts = list(PurePosixPath(str(reference["path"])).parts)
    if not any(
        parts[index:index + 2] == ["verification", "project-diagnostics"]
        for index in range(len(parts) - 1)
    ):
        raise LedgerError("project diagnostic intake artifact path is invalid")
    return reference


__all__ = [
    "ProjectDiagnosticLedgerMixin", "insert_project_diagnostic_intake",
    "load_bound_project_diagnostic_intakes",
    "load_latest_project_diagnostic_intakes",
]
