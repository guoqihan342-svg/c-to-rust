from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_security import LedgerError
from .ledger_transition_replay import audit_transition_projections


def completion_invariant(
    connection: Any, *, run_id: str, completion_epoch: int,
    cohort_sha256: str, generation_sha256: str,
    gate_bundle_sha256: str, phase: str,
) -> dict[str, Any]:
    if phase not in {"last-good", "completed"}:
        raise ValueError("completion invariant phase is invalid")
    audit_transition_projections(connection, run_id)
    units = connection.execute(
        """select unit_id,status,resumable_status,last_good_artifact_id
           from migration_units where run_id=? order by unit_id""",
        (run_id,),
    ).fetchall()
    expected_state = (
        ("resume-ready", "last_good")
        if phase == "last-good" else ("completed", "terminal")
    )
    if not units or any(
        (row["status"], row["resumable_status"]) != expected_state
        or not row["last_good_artifact_id"] for row in units
    ):
        raise LedgerError(f"project completion {phase} unit invariant failed")
    counts = {
        "running_attempt_count": _count(
            connection, "attempts", run_id, "status='running'",
        ),
        "active_lease_count": _count(
            connection, "leases", run_id, "status='active'",
        ),
        "running_repair_count": _count(
            connection, "project_repair_attempts", run_id, "status='running'",
        ),
        "unsettled_repair_count": _count(
            connection, "project_repair_items", run_id,
            "status not in ('resolved','cancelled')",
        ),
    }
    if any(counts.values()):
        raise LedgerError("project completion requires a quiescent repair/worker state")
    receipt = connection.execute(
        """select receipt_epoch,coordinator_receipt_sha256,
                  project_repair_queue_sha256,rust_project_ir_sha256,
                  rust_project_interface_sha256,status,queue_item_count
           from project_interface_receipts where run_id=?
           order by receipt_epoch desc limit 1""",
        (run_id,),
    ).fetchone()
    if (
        receipt is None or receipt["status"] != "candidate-ready"
        or int(receipt["queue_item_count"]) != 0
    ):
        raise LedgerError("project completion interface invariant failed")
    return {
        "schema_version": 1,
        "artifact_kind": "project-completion-invariant",
        "run_id": run_id,
        "completion_epoch": completion_epoch,
        "cohort_sha256": cohort_sha256,
        "generation_sha256": generation_sha256,
        "gate_bundle_sha256": gate_bundle_sha256,
        "unit_last_good": [
            {
                "unit_id": str(row["unit_id"]),
                "artifact_id": str(row["last_good_artifact_id"]),
            }
            for row in units
        ],
        "project_interface": {
            key: receipt[key] for key in (
                "receipt_epoch", "coordinator_receipt_sha256",
                "project_repair_queue_sha256", "rust_project_ir_sha256",
                "rust_project_interface_sha256",
            )
        },
        **counts,
    }


def invariant_reference(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"payload": dict(payload), "sha256": content_sha256(payload)}


def reopen_completed_invariant(
    connection: Any, *, expected: Mapping[str, Any], run_id: str,
    completion_epoch: int, cohort_sha256: str, generation_sha256: str,
    gate_bundle_sha256: str,
) -> None:
    binding = expected.get("invariant", expected)
    if not isinstance(binding, Mapping):
        raise LedgerError("project completion invariant receipt is invalid")
    payload = binding.get("payload")
    digest = binding.get("sha256")
    if not isinstance(payload, Mapping) or digest != content_sha256(payload):
        raise LedgerError("project completion invariant receipt is invalid")
    actual = completion_invariant(
        connection, run_id=run_id, completion_epoch=completion_epoch,
        cohort_sha256=cohort_sha256, generation_sha256=generation_sha256,
        gate_bundle_sha256=gate_bundle_sha256, phase="completed",
    )
    if actual != payload:
        raise LedgerError("project completion invariant drifted")


def _count(connection: Any, table: str, run_id: str, predicate: str) -> int:
    row = connection.execute(
        f"select count(*) from {table} where run_id=? and {predicate}",
        (run_id,),
    ).fetchone()
    return int(row[0]) if row is not None else -1


__all__ = [
    "completion_invariant", "invariant_reference",
    "reopen_completed_invariant",
]
