from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .ledger import LedgerError, ProjectLedger
from .project_repair_dispatch_permit import (
    ProjectRepairDispatchPermit, project_repair_dispatch_binding,
)
from .project_repair_worker_request import materialize_project_repair_request


def dispatch_ready_project_repair_item(
    *, ledger: ProjectLedger, run_id: str, queue_sha256: str,
    repair_id: str, base_rust_project_ir: Mapping[str, Any],
    harness_root: Path, out_root: Path, out_root_rel: str,
    common: Mapping[str, Any], recovered_attempts: list[str],
    dispatch_permit: ProjectRepairDispatchPermit | None,
) -> dict[str, Any]:
    projection = ledger.project_repair_projection(
        run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
    )
    budget = ledger.project_repair_budget(run_id=run_id)
    budget_payload = {
        "max_provider_calls": budget.max_provider_calls,
        "provider_calls": budget.provider_calls,
        "remaining_provider_calls": budget.max_provider_calls - budget.provider_calls,
        "max_receipt_epochs": budget.max_receipt_epochs,
        "receipt_epochs": budget.receipt_epochs,
        "remaining_receipt_epochs": budget.max_receipt_epochs - budget.receipt_epochs,
    }
    if budget.receipt_epochs >= budget.max_receipt_epochs:
        return _item_result(
            run_id, "blocked", "project-repair-receipt-budget-exhausted",
            repair_id, projection, common,
            blockers=["project-repair-successor-receipt-budget-exhausted"],
            recovered_attempts=recovered_attempts,
            provider_budget=budget_payload,
        )
    if budget.provider_calls >= budget.max_provider_calls:
        return _item_result(
            run_id, "blocked", "project-repair-provider-budget-exhausted",
            repair_id, projection, common,
            blockers=["project-repair-provider-call-budget-exhausted"],
            recovered_attempts=recovered_attempts,
            provider_budget=budget_payload,
        )
    if dispatch_permit is None:
        return _item_result(
            run_id, "preflight-required", "project-repair-preflight-required",
            repair_id, projection, common,
            recovered_attempts=recovered_attempts,
            provider_budget=budget_payload,
        )
    permit = project_repair_dispatch_binding(dispatch_permit)
    expected = {
        "run_id": run_id,
        "receipt_epoch": common["receipt_epoch"],
        "coordinator_receipt_sha256": common["coordinator_receipt_sha256"],
        "project_repair_queue_sha256": queue_sha256,
        "repair_id": repair_id,
        "expected_status": projection.status,
        "expected_state_version": projection.version,
    }
    if any(permit.get(key) != value for key, value in expected.items()):
        return _item_result(
            run_id, "waiting", "project-repair-state-advanced",
            repair_id, projection, common,
            recovered_attempts=recovered_attempts,
            provider_budget=budget_payload,
        )
    recovered_attempts = list(dict.fromkeys([
        *permit.get("recovered_attempts", []), *recovered_attempts,
    ]))
    return _dispatch(
        ledger=ledger, run_id=run_id, queue_sha256=queue_sha256,
        repair_id=repair_id, base_rust_project_ir=base_rust_project_ir,
        harness_root=harness_root, out_root=out_root,
        out_root_rel=out_root_rel,
        common={**dict(common), "provider_budget": budget_payload},
        recovered_attempts=recovered_attempts,
        dispatch_permit=dispatch_permit,
    )


def _dispatch(
    *, ledger: ProjectLedger, run_id: str, queue_sha256: str,
    repair_id: str, base_rust_project_ir: Mapping[str, Any],
    harness_root: Path, out_root: Path, out_root_rel: str,
    common: Mapping[str, Any], recovered_attempts: list[str],
    dispatch_permit: ProjectRepairDispatchPermit,
) -> dict[str, Any]:
    worker_id = "project-repairer-" + content_sha256({
        "run_id": run_id, "queue_sha256": queue_sha256,
        "repair_id": repair_id,
    })[:20]
    try:
        request = materialize_project_repair_request(
            ledger=ledger, run_id=run_id, queue_sha256=queue_sha256,
            repair_id=repair_id, worker_id=worker_id,
            base_rust_project_ir=base_rust_project_ir,
            harness_root=harness_root, out_root=out_root,
            out_root_rel=out_root_rel, dispatch_permit=dispatch_permit,
        )
    except (LedgerError, ValueError):
        projection = ledger.project_repair_projection(
            run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
        )
        if projection.status in {"queued", "retry-ready"}:
            raise
        return _observe_dispatch_race(
            ledger, run_id, queue_sha256, repair_id, common,
        )
    if not request["attempt_applied"]:
        projection = ledger.project_repair_projection(
            run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
        )
        return _item_result(
            run_id, "waiting", "project-repair-attempt-active",
            repair_id, projection, common,
        )
    return _result(
        run_id, "repair-dispatched", "project-repair-request-materialized",
        repair_id=repair_id, attempt_id=request["attempt_id"],
        request=request["request"], context=request["context"],
        recovered_attempts=recovered_attempts, **dict(common),
    )


def _observe_dispatch_race(
    ledger: ProjectLedger, run_id: str, queue_sha256: str, repair_id: str,
    common: Mapping[str, Any],
) -> dict[str, Any]:
    projection = ledger.project_repair_projection(
        run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
    )
    return _item_result(
        run_id, "waiting", (
            "project-repair-attempt-active"
            if projection.status == "running" else "project-repair-state-advanced"
        ), repair_id, projection, common,
    )


def _item_result(
    run_id: str, status: str, stage: str, repair_id: str,
    projection: Any, common: Mapping[str, Any], **extra: Any,
) -> dict[str, Any]:
    return _result(
        run_id, status, stage, repair_id=repair_id,
        attempt_id=projection.active_attempt_id,
        item_status=projection.status, state_version=projection.version,
        **dict(common), **extra,
    )


def _result(run_id: str, status: str, stage: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": status, "stage": stage,
        "run_id": run_id, "semantic_gate": False, "model_launched": False,
        "blockers": [], "recovered_attempts": [], **extra,
    }


__all__ = ["dispatch_ready_project_repair_item"]
