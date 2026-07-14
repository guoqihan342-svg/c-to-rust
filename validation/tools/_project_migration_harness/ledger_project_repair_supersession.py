from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .ledger_project_repair_authority import ProjectRepairAuthority
from .ledger_project_repair_core import ProjectRepairTransitionResult
from .ledger_project_repair_replay import assert_project_repair_projection
from .ledger_schema import _now_text
from .ledger_security import LedgerError
from .project_repair_policy import ProjectRepairProjection


def resolve_revalidated_item(
    authority: ProjectRepairAuthority, *, run_id: str, queue_sha256: str,
    repair_id: str, expected_version: int, successor_receipt_sha256: str,
) -> ProjectRepairTransitionResult:
    previous = authority._expected(
        run_id, queue_sha256, repair_id, "candidate-ready", expected_version,
    )
    current = ProjectRepairProjection(
        "resolved", previous.version + 1, previous.attempt_count,
        previous.max_attempts, None, previous.candidate_ir_sha256,
    )
    return authority._append_and_project(
        run_id, queue_sha256, repair_id,
        f"project-repair-verifier-pass-{successor_receipt_sha256[:24]}",
        "candidate_recoordinated", "project_repair_candidate_recoordinated",
        successor_receipt_sha256, None, previous, current, _now_text(),
    )


def cancel_superseded_items(
    authority: ProjectRepairAuthority, *, run_id: str, queue_sha256: str,
    repair_ids: Iterable[str], successor_receipt_sha256: str,
    excluded: Iterable[str] = (),
) -> list[ProjectRepairTransitionResult]:
    excluded_set = set(excluded)
    results = []
    for repair_id in sorted(set(repair_ids) - excluded_set):
        previous = assert_project_repair_projection(
            authority.connection, run_id=run_id, queue_sha256=queue_sha256,
            repair_id=repair_id,
        )
        if previous.status in {"resolved", "cancelled", "failed", "exhausted"}:
            continue
        if previous.status not in {"queued", "retry-ready", "candidate-ready"}:
            raise LedgerError("superseded project repair item is not quiescent")
        current = ProjectRepairProjection(
            "cancelled", previous.version + 1, previous.attempt_count,
            previous.max_attempts, None, None,
        )
        results.append(authority._append_and_project(
            run_id, queue_sha256, repair_id,
            "project-repair-supersede-" + successor_receipt_sha256[:16]
            + "-" + repair_id,
            "repair_cancelled", "project_repair_attempt_cancelled",
            successor_receipt_sha256, None, previous, current, _now_text(),
        ))
    return results


def receipt_repair_ids(receipt: dict[str, Any]) -> list[str]:
    return [
        str(item["repair_id"])
        for item in receipt["project_repair_queue"]["items"]
    ]


__all__ = [
    "cancel_superseded_items", "receipt_repair_ids",
    "resolve_revalidated_item",
]
