from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .ledger import LedgerError, ProjectLedger
from .project_repair_worker_request import (
    materialize_project_repair_request, read_bound_rust_project_ir,
)


def resume_latest_project_repair(
    *, ledger: ProjectLedger, run_id: str,
    base_rust_project_ir: Mapping[str, Any], harness_root: Path,
    out_root: Path, out_root_rel: str, now_epoch: int | None = None,
) -> dict[str, Any]:
    clock = int(time.time()) if now_epoch is None else _require_epoch(now_epoch)
    latest = ledger.load_latest_project_interface_receipt(run_id=run_id)
    if latest is None:
        return _result(run_id, "blocked", "missing-project-interface-receipt")
    receipt_epoch, receipt = latest
    queue = receipt["project_repair_queue"]
    queue_sha256 = str(queue["project_repair_queue_sha256"])
    base_ir = read_bound_rust_project_ir(harness_root, base_rust_project_ir)
    if base_ir["ir_sha256"] != receipt["rust_project_ir_sha256"]:
        raise LedgerError("latest project repair receipt changed its base RustProjectIR")
    common = {
        "receipt_epoch": receipt_epoch,
        "coordinator_receipt_sha256": receipt["coordinator_receipt_sha256"],
        "project_repair_queue_sha256": queue_sha256,
        "base_rust_project_ir_sha256": base_ir["ir_sha256"],
    }
    if receipt["status"] == "candidate-ready":
        return _result(
            run_id, "ready-for-project-final", "project-interface-candidate-ready",
            **common,
        )
    recovered_attempts: list[str] = []
    for item in queue["items"]:
        repair_id = str(item["repair_id"])
        projection = ledger.project_repair_projection(
            run_id=run_id, queue_sha256=queue_sha256, repair_id=repair_id,
        )
        if projection.status == "resolved":
            continue
        if projection.status in {"queued", "retry-ready"}:
            return _dispatch(
                ledger=ledger, run_id=run_id, queue_sha256=queue_sha256,
                repair_id=repair_id, base_rust_project_ir=base_rust_project_ir,
                harness_root=harness_root, out_root=out_root,
                out_root_rel=out_root_rel, common=common,
                recovered_attempts=recovered_attempts,
            )
        if projection.status == "running":
            attempt = _load_running_attempt(
                ledger, projection.active_attempt_id, run_id, queue_sha256,
                repair_id,
            )
            if bool(attempt["command_started"]):
                return _item_result(
                    run_id, "blocked", "project-repair-manual-reconcile",
                    repair_id, projection, common,
                    blockers=["launched-command-outcome-is-unknown"],
                )
            if clock < int(attempt["lease_expires_at"]):
                return _item_result(
                    run_id, "waiting", "project-repair-attempt-active",
                    repair_id, projection, common,
                )
            evidence = content_sha256({
                "kind": "project-repair-expired-prelaunch-recovery",
                "attempt_id": attempt["attempt_id"],
                "lease_expires_at": int(attempt["lease_expires_at"]),
            })
            try:
                recovered = ledger.recover_project_repair_attempt(
                    attempt_id=str(attempt["attempt_id"]),
                    command_id=f"project-repair-coordinator-recover-{evidence[:24]}",
                    expected_version=projection.version,
                    evidence_sha256=evidence, recovered_at_epoch=clock,
                )
            except LedgerError:
                return _observe_dispatch_race(
                    ledger, run_id, queue_sha256, repair_id, common,
                )
            recovered_attempts.append(str(attempt["attempt_id"]))
            if recovered.current.status == "retry-ready":
                return _dispatch(
                    ledger=ledger, run_id=run_id, queue_sha256=queue_sha256,
                    repair_id=repair_id,
                    base_rust_project_ir=base_rust_project_ir,
                    harness_root=harness_root, out_root=out_root,
                    out_root_rel=out_root_rel, common=common,
                    recovered_attempts=recovered_attempts,
                )
            return _item_result(
                run_id, "blocked", "project-repair-attempts-exhausted",
                repair_id, recovered.current, common,
                blockers=["project-repair-attempt-budget-exhausted"],
                recovered_attempts=recovered_attempts,
            )
        if projection.status == "candidate-ready":
            return _item_result(
                run_id, "blocked", "project-repair-manual-reconcile",
                repair_id, projection, common,
                blockers=["candidate-lacks-atomic-host-recoordination"],
            )
        return _item_result(
            run_id, "blocked", "project-repair-terminal-blocker",
            repair_id, projection, common,
            blockers=[f"project-repair-item-{projection.status}"],
        )
    return _result(
        run_id, "blocked", "project-repair-receipt-state-drift",
        blockers=["repair-required-receipt-has-no-actionable-item"], **common,
    )


def _dispatch(
    *, ledger: ProjectLedger, run_id: str, queue_sha256: str,
    repair_id: str, base_rust_project_ir: Mapping[str, Any],
    harness_root: Path, out_root: Path, out_root_rel: str,
    common: Mapping[str, Any], recovered_attempts: list[str],
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
            out_root_rel=out_root_rel,
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
    if projection.status == "running":
        return _item_result(
            run_id, "waiting", "project-repair-attempt-active",
            repair_id, projection, common,
        )
    return _item_result(
        run_id, "waiting", "project-repair-state-advanced",
        repair_id, projection, common,
    )


def _load_running_attempt(
    ledger: ProjectLedger, attempt_id: str | None, run_id: str,
    queue_sha256: str, repair_id: str,
) -> dict[str, Any]:
    if attempt_id is None:
        raise LedgerError("running project repair item lacks an active attempt")
    with ledger.connect() as connection:
        row = connection.execute(
            """select attempt_id,run_id,project_repair_queue_sha256,repair_id,
               status,worker_id,lease_expires_at,command_started
               from project_repair_attempts where attempt_id=?""",
            (attempt_id,),
        ).fetchone()
    if (
        row is None or row["run_id"] != run_id
        or row["project_repair_queue_sha256"] != queue_sha256
        or row["repair_id"] != repair_id or row["status"] != "running"
    ):
        raise LedgerError("active project repair attempt changed scope")
    return dict(row)


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


def _require_epoch(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("project repair coordinator epoch is invalid")
    return value


__all__ = ["resume_latest_project_repair"]
