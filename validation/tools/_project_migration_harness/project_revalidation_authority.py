from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_authority import (
    derive_project_observation, project_authority, validate_project_summary,
)
from .gate_candidate_sets import (
    assert_current_candidate_set, current_candidate_members,
)
from .gate_evidence import read_content_addressed_json
from .ledger_security import LedgerError
from .integration_generation import GenerationCommitError
from .project_generation_context import (
    load_managed_project_context, managed_project_root,
)
from .project_revalidation_receipt import (
    validate_project_revalidation_receipt,
)
from .sandbox_execution_schema import is_sha256


def validate_project_revalidation_authority(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    source_receipt: Mapping[str, Any], candidate_ir: Mapping[str, Any],
    successor_receipt: Mapping[str, Any],
    wrappers: Sequence[Mapping[str, Any]], revalidation: Mapping[str, Any],
) -> dict[str, Any]:
    value = validate_project_revalidation_receipt(revalidation)
    candidate_sets = {
        str(item["intake"]["candidate_set_sha256"]) for item in wrappers
    }
    if not wrappers or len(candidate_sets) != 1:
        raise LedgerError("project revalidation intake cohort is invalid")
    candidate_set = next(iter(candidate_sets))
    expected_source = {
        "coordinator_receipt_sha256": source_receipt[
            "coordinator_receipt_sha256"
        ],
        "project_repair_queue_sha256": source_receipt[
            "project_repair_queue"
        ]["project_repair_queue_sha256"],
        "rust_project_ir_sha256": source_receipt["rust_project_ir_sha256"],
        "rust_project_interface_sha256": source_receipt[
            "rust_project_interface_sha256"
        ],
        "project_diagnostic_intake_set_sha256": source_receipt[
            "project_diagnostic_intake_set_sha256"
        ],
    }
    expected_candidate = {
        "candidate_set_sha256": candidate_set,
        "rust_project_ir_sha256": candidate_ir["ir_sha256"],
        "rust_project_interface_sha256": candidate_ir["interface_sha256"],
    }
    if (
        value["run_id"] != run_id or value["source"] != expected_source
        or value["candidate"] != expected_candidate
        or value["successor_coordinator_receipt_sha256"]
        != successor_receipt["coordinator_receipt_sha256"]
        or candidate_ir["ir_sha256"] == source_receipt["rust_project_ir_sha256"]
    ):
        raise LedgerError("project revalidation receipt changed its binding")
    assert_current_candidate_set(
        connection, run_id, candidate_set, database_path=database_path,
    )
    by_kind = {item["gate_kind"]: item for item in value["gate_records"]}
    source_kinds = [item["intake"]["gate_kind"] for item in wrappers]
    if len(source_kinds) != len(set(source_kinds)) or set(by_kind) != set(source_kinds):
        raise LedgerError("project revalidation gate coverage is incomplete")
    project_inputs = set()
    for wrapper in wrappers:
        project_inputs.add(_validate_gate(
            connection, database_path=database_path, run_id=run_id,
            intake=wrapper["intake"], record=by_kind[wrapper["intake"]["gate_kind"]],
        ))
    members = current_candidate_members(connection, run_id)
    try:
        context = load_managed_project_context(
            managed_project_root(database_path.parent.parent), members,
        )
    except (GenerationCommitError, OSError, TypeError, ValueError) as error:
        raise LedgerError("project revalidation generation cannot be reopened") from error
    managed_ir = context["rust_project_ir"]
    if (
        project_inputs != {context["project_input_sha256"]}
        or managed_ir["ir_sha256"] != candidate_ir["ir_sha256"]
        or managed_ir["interface_sha256"] != candidate_ir["interface_sha256"]
    ):
        raise LedgerError("project revalidation generation binding drifted")
    return value


def _validate_gate(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    intake: Mapping[str, Any], record: Mapping[str, Any],
) -> str:
    gate_kind = str(intake["gate_kind"])
    if (
        record["gate_status"] != "passed"
        or record["candidate_set_sha256"] != intake["candidate_set_sha256"]
        or int(record["gate_epoch"]) <= int(intake["gate_epoch"])
    ):
        raise LedgerError("project verifier pass is stale or incomplete")
    row = connection.execute(
        """select gate_epoch,status,verifier_id,evidence_path,evidence_sha256
           from project_gate_records
           where record_id=? and run_id=? and gate_kind=?
             and candidate_set_sha256=?""",
        (
            record["record_id"], run_id, gate_kind,
            intake["candidate_set_sha256"],
        ),
    ).fetchone()
    evidence = record["evidence"]
    raw_ref = record["raw_observation"]
    if (
        row is None or row["status"] != "passed"
        or row["verifier_id"] != project_authority(gate_kind)
        or int(row["gate_epoch"]) != record["gate_epoch"]
        or row["evidence_path"] != evidence["path"]
        or row["evidence_sha256"] != evidence["sha256"]
    ):
        raise LedgerError("project verifier pass is not ledger authoritative")
    summary = read_content_addressed_json(
        database_path, str(evidence["path"]), str(evidence["sha256"]),
    )
    if len(canonical_json_bytes(summary)) != evidence["size_bytes"]:
        raise LedgerError("project verifier evidence size binding drifted")
    validate_project_summary(
        summary, run_id=run_id, gate_kind=gate_kind, status="passed",
        candidate_set_sha256=str(intake["candidate_set_sha256"]),
        verifier_id=project_authority(gate_kind),
    )
    if summary.get("source_evidence") != [dict(raw_ref)]:
        raise LedgerError("project verifier pass changed its raw observation")
    raw = read_content_addressed_json(
        database_path, str(raw_ref["path"]), str(raw_ref["sha256"]),
    )
    if len(canonical_json_bytes(raw)) != raw_ref["size_bytes"]:
        raise LedgerError("project verifier raw observation size binding drifted")
    status = derive_project_observation(
        raw, run_id=run_id, gate_kind=gate_kind,
        candidate_set_sha256=str(intake["candidate_set_sha256"]),
    )
    observation = raw.get("observation")
    project_input = (
        observation.get("project_input_sha256")
        if isinstance(observation, Mapping) else None
    )
    if (
        status != "passed" or not is_sha256(project_input)
        or project_input == intake["project_input_sha256"]
    ):
        raise LedgerError("project verifier pass did not bind a new generation")
    return str(project_input)


__all__ = ["validate_project_revalidation_authority"]
