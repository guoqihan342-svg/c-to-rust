from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
)
from .ledger_project_repair_authority import ProjectRepairAuthority
from .ledger_project_repair_core import ProjectRepairTransitionResult
from .ledger_project_repair_registry import (
    ProjectRepairRegistration, ProjectRepairRegistry,
)
from .ledger_project_repair_intakes import (
    load_receipt_project_diagnostic_intakes,
)
from .ledger_project_repair_supersession import (
    cancel_superseded_items, receipt_repair_ids, resolve_revalidated_item,
)
from .ledger_schema import atomic
from .ledger_security import LedgerError
from .project_revalidation_authority import (
    validate_project_revalidation_authority,
)
from .project_verifier_receipt import (
    PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD,
)


@dataclass(frozen=True, slots=True)
class ProjectVerifierSettlement:
    registration: ProjectRepairRegistration
    terminal: ProjectRepairTransitionResult


def settle_project_verifier_pass(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    queue_sha256: str, repair_id: str, expected_version: int,
    revalidation_reference: Mapping[str, Any],
    successor_receipt: Mapping[str, Any], rust_project_ir: Mapping[str, Any],
) -> ProjectVerifierSettlement:
    reference = dict(revalidation_reference)
    require_content_addressed_reference(reference)
    with atomic(connection):
        registry = ProjectRepairRegistry(connection, database_path)
        source = registry.load_receipt(
            run_id=run_id, queue_sha256=queue_sha256,
        )
        _require_latest_source(connection, run_id, queue_sha256)
        _require_verifier_item(source, repair_id)
        wrappers = load_receipt_project_diagnostic_intakes(
            connection, database_path=database_path, run_id=run_id,
            receipt=source, rust_project_ir={
                "ir_sha256": source["rust_project_ir_sha256"],
                "interface_sha256": source["rust_project_interface_sha256"],
            },
        )
        revalidation = read_content_addressed_json(
            database_path, str(reference["path"]), str(reference["sha256"]),
        )
        if len(canonical_json_bytes(revalidation)) != reference["size_bytes"]:
            raise LedgerError("project revalidation receipt size binding drifted")
        validate_project_revalidation_authority(
            connection, database_path=database_path, run_id=run_id,
            source_receipt=source, candidate_ir=rust_project_ir,
            successor_receipt=successor_receipt, wrappers=wrappers,
            revalidation=revalidation,
        )
        registration = registry.register(
            run_id=run_id, receipt=successor_receipt,
            rust_project_ir=rust_project_ir,
        )
        authority = ProjectRepairAuthority(connection)
        receipt_sha = str(successor_receipt["coordinator_receipt_sha256"])
        terminal = resolve_revalidated_item(
            authority,
            run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
            expected_version=expected_version,
            successor_receipt_sha256=receipt_sha,
        )
        cancel_superseded_items(
            authority, run_id=run_id, queue_sha256=queue_sha256,
            repair_ids=receipt_repair_ids(source),
            successor_receipt_sha256=receipt_sha, excluded=[repair_id],
        )
    return ProjectVerifierSettlement(registration, terminal)


def settle_project_verifier_failure(
    connection: sqlite3.Connection, *, database_path: Path, run_id: str,
    queue_sha256: str, repair_id: str, expected_version: int,
    evidence_sha256: str, successor_receipt: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any],
) -> ProjectVerifierSettlement:
    with atomic(connection):
        registry = ProjectRepairRegistry(connection, database_path)
        source = registry.load_receipt(
            run_id=run_id, queue_sha256=queue_sha256,
        )
        _require_latest_source(connection, run_id, queue_sha256)
        _require_verifier_item(source, repair_id)
        registration = registry.register(
            run_id=run_id, receipt=successor_receipt,
            rust_project_ir=rust_project_ir,
        )
        authority = ProjectRepairAuthority(connection)
        rolled_back = authority.rollback_candidate(
            run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
            command_id=(
                "project-repair-verifier-failure-"
                f"{successor_receipt['coordinator_receipt_sha256'][:24]}"
            ),
            expected_version=expected_version,
            evidence_sha256=evidence_sha256,
        )
        receipt_sha = str(successor_receipt["coordinator_receipt_sha256"])
        cancelled = cancel_superseded_items(
            authority, run_id=run_id, queue_sha256=queue_sha256,
            repair_ids=receipt_repair_ids(source),
            successor_receipt_sha256=receipt_sha,
        )
        terminal = next(
            (item for item in cancelled if item.previous == rolled_back.current),
            rolled_back,
        )
    return ProjectVerifierSettlement(registration, terminal)


def _require_verifier_item(receipt: Mapping[str, Any], repair_id: str) -> None:
    if receipt.get("schema_version") != 2:
        raise LedgerError("project verifier settlement requires a v2 source receipt")
    item = next((
        value for value in receipt["project_repair_queue"]["items"]
        if value["repair_id"] == repair_id
    ), None)
    if (
        item is None or item["diagnostic_sha256"] not in receipt[
            PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD
        ]
    ):
        raise LedgerError("project verifier settlement target is not verifier-origin")


def _require_latest_source(
    connection: sqlite3.Connection, run_id: str, queue_sha256: str,
) -> None:
    latest = connection.execute(
        """select project_repair_queue_sha256
           from project_interface_receipts where run_id=?
           order by receipt_epoch desc limit 1""",
        (run_id,),
    ).fetchone()
    if latest is None or latest[0] != queue_sha256:
        raise LedgerError("project verifier settlement requires the latest receipt")


__all__ = [
    "ProjectVerifierSettlement", "settle_project_verifier_failure",
    "settle_project_verifier_pass",
]
