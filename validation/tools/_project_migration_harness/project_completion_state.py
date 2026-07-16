from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import content_sha256, write_json_artifact
from .ledger import LedgerError, ProjectLedger
from .project_generation_context import managed_project_root
from .ledger_transition_authority import load_run_projection


def completion_paths(
    ledger: ProjectLedger, harness_root: Path,
) -> dict[str, Any]:
    root = harness_root.resolve(strict=True)
    database = ledger.path.resolve()
    try:
        database.relative_to(root)
    except ValueError as error:
        raise LedgerError(
            "completion ledger is outside the harness repository",
        ) from error
    if database.name != "project-migration.sqlite3" or database.parent.name != "state":
        raise LedgerError("completion requires the fixed project migration ledger path")
    out_root = database.parent.parent
    out_rel = out_root.relative_to(root).as_posix()
    return {
        "out_root": out_root,
        "out_root_rel": out_rel,
        "quarantine_root": out_root / "completion" / "quarantine",
        "runtime_root": out_root / "completion" / "runtime",
        "project_root": managed_project_root(out_root),
    }


def completion_result(
    paths: dict[str, Any], run_id: str, status: str, stage: str,
    blockers: list[str], candidate_set: str | None = None, **details: Any,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "status": status,
        "run_id": run_id,
        "stage": stage,
        "candidate_set_sha256": candidate_set,
        "blockers": blockers[:64],
        "semantic_gate": False,
        **details,
    }
    payload["checkpoint_sha256"] = content_sha256(payload)
    write_json_artifact(
        paths["out_root"], "completion/coordinator-state.json", payload,
    )
    return payload


def reopen_completed_result(
    ledger: ProjectLedger, paths: dict[str, Any], run_id: str,
) -> dict[str, Any] | None:
    with ledger.connect() as connection:
        projection = load_run_projection(connection, run_id)
    if projection.status == "finalizing":
        try:
            recovered = ledger.complete_project_run(
                run_id=run_id,
                candidate_set_sha256=str(projection.completion.cohort_sha256),
            )
        except LedgerError as error:
            message = str(error)[:160]
            waiting = "receipt is missing" in message
            return completion_result(
                paths, run_id, "waiting" if waiting else "blocked",
                "project-finalizing-recovery", [message],
                str(projection.completion.cohort_sha256),
                completion_epoch=projection.completion.epoch,
            )
        return {
            **recovered["receipt"],
            "stage": "project-finalizing-recovered", "blockers": [],
            "completion_receipt": recovered["reference"],
        }
    try:
        recovered = ledger.reopen_completed_project_run(run_id=run_id)
    except LedgerError as error:
        return completion_result(
            paths, run_id, "blocked", "project-completion-receipt-recovery",
            [str(error)[:160]],
        )
    if recovered is None:
        return None
    return {
        **recovered["receipt"],
        "stage": "project-completion-receipt-reopened", "blockers": [],
        "completion_receipt": recovered["reference"],
    }


__all__ = ["completion_paths", "completion_result", "reopen_completed_result"]
