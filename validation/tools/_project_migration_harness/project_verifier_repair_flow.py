from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .gate_evidence import write_content_addressed_json
from .ledger import LedgerError, ProjectLedger
from .project_interface_coordinator import coordinate_project_interfaces
from .project_revalidation_receipt import project_revalidation_receipt
from .project_verifier_receipt import receipt_project_diagnostic_references


def register_project_diagnostic_repairs(
    *, ledger: ProjectLedger, run_id: str, rust_project_ir: Mapping[str, Any],
    intake_references: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    wrappers = ledger.bound_project_diagnostic_intakes(
        run_id=run_id, references=intake_references,
        rust_project_ir_sha256=str(rust_project_ir["ir_sha256"]),
    )
    receipt = coordinate_project_interfaces(
        rust_project_ir, project_diagnostic_intakes=wrappers,
    )
    registration = ledger.register_project_interface_receipt(
        run_id=run_id, receipt=receipt, rust_project_ir=rust_project_ir,
    )
    return {
        "schema_version": 1, "status": "registered",
        "receipt_epoch": registration.receipt_epoch,
        "coordinator_receipt_sha256": registration.coordinator_receipt_sha256,
        "project_repair_queue_sha256": registration.project_repair_queue_sha256,
        "item_count": registration.item_count, "semantic_gate": False,
    }


def settle_pending_project_verifier_repair(
    *, ledger: ProjectLedger, run_id: str, rust_project_ir: Mapping[str, Any],
    pending: Mapping[str, Any], cargo_result: Mapping[str, Any],
) -> dict[str, Any]:
    latest = ledger.load_latest_project_interface_receipt(run_id=run_id)
    if latest is None:
        raise LedgerError("project verifier settlement lost its source receipt")
    _epoch, receipt = latest
    queue = receipt["project_repair_queue"]
    queue_sha = str(queue["project_repair_queue_sha256"])
    repair_id = str(pending.get("repair_id", ""))
    if (
        receipt.get("schema_version") != 2
        or pending.get("project_repair_queue_sha256") != queue_sha
        or pending.get("candidate_ir_sha256") != rust_project_ir.get("ir_sha256")
    ):
        raise LedgerError("project verifier settlement binding drifted")
    projection = ledger.project_repair_projection(
        run_id=run_id, queue_sha256=queue_sha, repair_id=repair_id,
    )
    if (
        projection.status != "candidate-ready"
        or projection.candidate_ir_sha256 != rust_project_ir.get("ir_sha256")
    ):
        raise LedgerError("project verifier candidate is not awaiting verification")
    source_wrappers = ledger.bound_project_diagnostic_intakes(
        run_id=run_id,
        references=receipt_project_diagnostic_references(receipt),
        rust_project_ir_sha256=str(receipt["rust_project_ir_sha256"]),
    )
    if cargo_result.get("status") == "passed":
        source_gate_kinds = {
            wrapper["intake"]["gate_kind"] for wrapper in source_wrappers
        }
        raw_records = cargo_result.get("records")
        records = [
            record for record in raw_records
            if isinstance(record, Mapping)
            and record.get("gate_kind") in source_gate_kinds
        ] if isinstance(raw_records, list) else []
        successor = coordinate_project_interfaces(rust_project_ir)
        revalidation = project_revalidation_receipt(
            run_id=run_id, source_receipt=receipt,
            candidate_ir=rust_project_ir, successor_receipt=successor,
            candidate_set_sha256=str(cargo_result.get("candidate_set_sha256")),
            records=records,
        )
        revalidation_ref = write_content_addressed_json(
            ledger.path.parent.parent, "project-repair-revalidation",
            revalidation,
        )
        settled = ledger.settle_project_verifier_pass(
            run_id=run_id, queue_sha256=queue_sha, repair_id=repair_id,
            expected_version=projection.version,
            revalidation_reference=revalidation_ref,
            successor_receipt=successor,
            rust_project_ir=rust_project_ir,
        )
        result = _settlement("verified", settled, successor)
        result["revalidation_receipt"] = revalidation_ref
        return result
    references = cargo_result.get("project_diagnostic_intakes")
    if not isinstance(references, list) or not references:
        return {
            "schema_version": 1, "status": "blocked",
            "stage": "project-repair-verifier-did-not-produce-candidate-failure",
            "semantic_gate": False,
        }
    wrappers = ledger.bound_project_diagnostic_intakes(
        run_id=run_id, references=references,
        rust_project_ir_sha256=str(rust_project_ir["ir_sha256"]),
    )
    successor = coordinate_project_interfaces(
        rust_project_ir, project_diagnostic_intakes=wrappers,
    )
    evidence = _candidate_receipt_artifact(
        ledger, run_id=run_id, queue_sha256=queue_sha,
        repair_id=repair_id, candidate_ir_sha256=str(rust_project_ir["ir_sha256"]),
    )
    settled = ledger.settle_project_verifier_failure(
        run_id=run_id, queue_sha256=queue_sha, repair_id=repair_id,
        expected_version=projection.version, evidence_sha256=evidence,
        successor_receipt=successor, rust_project_ir=rust_project_ir,
    )
    return _settlement("repair-required", settled, successor)


def _candidate_receipt_artifact(
    ledger: ProjectLedger, *, run_id: str, queue_sha256: str,
    repair_id: str, candidate_ir_sha256: str,
) -> str:
    with ledger.connect() as connection:
        row = connection.execute(
            """select artifacts.content_sha256 from project_repair_artifacts artifacts
               join project_repair_attempts attempts
                 on attempts.attempt_id=artifacts.attempt_id
               where artifacts.run_id=? and artifacts.project_repair_queue_sha256=?
                 and artifacts.repair_id=? and artifacts.kind='project-interface-receipt'
                 and attempts.output_ir_sha256=? and attempts.status='completed'
               order by attempts.ordinal desc limit 1""",
            (run_id, queue_sha256, repair_id, candidate_ir_sha256),
        ).fetchone()
    if row is None:
        raise LedgerError("project verifier candidate lost coordinator evidence")
    return str(row[0])


def _settlement(status: str, settled: Any, receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": status,
        "receipt_epoch": settled.registration.receipt_epoch,
        "coordinator_receipt_sha256": receipt["coordinator_receipt_sha256"],
        "item_status": settled.terminal.current.status,
        "semantic_gate": False,
    }


__all__ = [
    "register_project_diagnostic_repairs",
    "settle_pending_project_verifier_repair",
]
