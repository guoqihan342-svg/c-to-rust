from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .controller_dispatch import dispatch_project_workers
from .controller_runtime import run_and_ingest_opencode_worker
from .ledger import LedgerError, ProjectLedger
from .project_completion_coordinator import resume_project_completion
from .project_preflight_runner import run_project_worker_preflight
from .project_worker_batch import (
    execute_project_worker_batch, safe_prelaunch_retry, worker_summary,
)


_TERMINAL_WORKER_FAILURES = {
    "blocked", "failed", "manual-reconcile", "rejected",
}
_MAX_CONSECUTIVE_PRELAUNCH_RETRIES = 2


def run_project_to_completion(
    portfolio: Mapping[str, Any], *, ledger: ProjectLedger,
    harness_root: Path, repo_root: Path, out_root: Path,
    out_root_rel: str, logical_model: str = "GLM-5.1",
    resolved_model: str = "zai/glm-5.1", timeout_seconds: int = 300,
    preflight_timeout_seconds: int = 60, lease_ttl_seconds: int = 900,
    max_cycles: int = 256,
) -> dict[str, Any]:
    if not 1 <= max_cycles <= 10_000:
        raise ValueError("run-to-completion max_cycles is invalid")
    if lease_ttl_seconds <= timeout_seconds + 30:
        raise ValueError("run-to-completion lease TTL is too short")
    run_id = portfolio.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run-to-completion portfolio run_id is invalid")
    preflight: Mapping[str, Any] | None = None
    preflight_reference: Mapping[str, Any] | None = None
    cycles: list[dict[str, Any]] = []
    consecutive_prelaunch_retries = 0
    for cycle_index in range(max_cycles):
        completion = resume_project_completion(
            ledger=ledger, run_id=run_id, harness_root=harness_root,
            repo_root=repo_root, timeout_seconds=timeout_seconds,
            preflight_timeout_seconds=preflight_timeout_seconds,
            logical_model=logical_model, resolved_model=resolved_model,
        )
        completion_summary = {
            "status": completion.get("status"),
            "stage": completion.get("stage"),
            "checkpoint_sha256": completion.get("checkpoint_sha256"),
        }
        if completion.get("status") == "completed":
            cycles.append({
                "cycle_index": cycle_index,
                "completion": completion_summary,
                "dispatch": None, "workers": [],
            })
            return _finish(
                out_root, run_id=run_id, status="completed",
                reason_code=None, preflight=preflight, cycles=cycles,
                completion=completion, semantic_gate=True,
            )
        if completion.get("status") != "waiting":
            return _finish(
                out_root, run_id=run_id,
                status=str(completion.get("status", "blocked")),
                reason_code=str(
                    completion.get("stage") or "project_completion_blocked"
                ),
                preflight=preflight, cycles=cycles,
                completion=completion, semantic_gate=False,
            )
        if preflight is None:
            try:
                preflight = run_project_worker_preflight(
                    harness_root=harness_root, out_root_rel=out_root_rel,
                    run_id=run_id, logical_model=logical_model,
                    resolved_model=resolved_model,
                    timeout_seconds=preflight_timeout_seconds,
                )
            except (OSError, TypeError, ValueError) as error:
                return _finish(
                    out_root, run_id=run_id, status="blocked",
                    reason_code="project_worker_preflight_invalid",
                    blockers=[str(error)[:160]], preflight=None,
                    cycles=cycles, completion=completion,
                    semantic_gate=False,
                )
            if preflight.get("status") != "passed":
                return _finish(
                    out_root, run_id=run_id, status="blocked",
                    reason_code="project_worker_preflight_blocked",
                    preflight=preflight, cycles=cycles,
                    completion=completion, semantic_gate=False,
                )
            candidate_reference = preflight.get("report")
            if not isinstance(candidate_reference, Mapping):
                return _finish(
                    out_root, run_id=run_id, status="blocked",
                    reason_code="project_worker_preflight_reference_missing",
                    preflight=preflight, cycles=cycles,
                    completion=completion, semantic_gate=False,
                )
            preflight_reference = candidate_reference
        try:
            dispatch = dispatch_project_workers(
                portfolio, ledger=ledger, harness_root=harness_root,
                out_root=out_root, out_root_rel=out_root_rel,
                lease_ttl_seconds=lease_ttl_seconds,
            )
        except (LedgerError, OSError, TypeError, ValueError) as error:
            return _finish(
                out_root, run_id=run_id, status="blocked",
                reason_code="project_worker_dispatch_blocked",
                blockers=[str(error)[:160]], preflight=preflight,
                cycles=cycles, completion=completion, semantic_gate=False,
            )
        launches = dispatch.get("launches")
        if not isinstance(launches, list) or not launches:
            cycles.append({
                "cycle_index": cycle_index,
                "completion": completion_summary,
                "dispatch": _dispatch_summary(dispatch), "workers": [],
            })
            return _finish(
                out_root, run_id=run_id, status="blocked",
                reason_code=(
                    "project_worker_attempt_limit_reached"
                    if _attempt_limit_reached(dispatch)
                    else "project_run_no_progress"
                ), preflight=preflight,
                cycles=cycles, completion=completion,
                dispatch=dispatch, semantic_gate=False,
            )
        executions = execute_project_worker_batch(
            launches, preflight_reference=preflight_reference,
            ledger=ledger, harness_root=harness_root,
            logical_model=logical_model, resolved_model=resolved_model,
            timeout_seconds=timeout_seconds,
            worker_runner=run_and_ingest_opencode_worker,
        )
        workers = [worker_summary(launch, worker) for launch, worker in executions]
        cycles.append({
            "cycle_index": cycle_index,
            "completion": completion_summary,
            "dispatch": _dispatch_summary(dispatch), "workers": workers,
        })
        terminal = next(
            (worker for _launch, worker in executions
             if worker.get("status") in _TERMINAL_WORKER_FAILURES),
            None,
        )
        if terminal is not None:
            return _finish(
                out_root, run_id=run_id,
                status=str(terminal.get("status", "blocked")),
                reason_code="project_worker_execution_blocked",
                preflight=preflight, cycles=cycles,
                completion=completion, worker=terminal,
                semantic_gate=False,
            )
        retryable = [
            worker for _launch, worker in executions
            if safe_prelaunch_retry(worker)
        ]
        if retryable and len(retryable) == len(executions):
            consecutive_prelaunch_retries += 1
            if consecutive_prelaunch_retries >= _MAX_CONSECUTIVE_PRELAUNCH_RETRIES:
                return _finish(
                    out_root, run_id=run_id, status="blocked",
                    reason_code="project_worker_prelaunch_retry_exhausted",
                    preflight=preflight, cycles=cycles,
                    completion=completion, workers=workers,
                    semantic_gate=False,
                )
        else:
            consecutive_prelaunch_retries = 0
    return _finish(
        out_root, run_id=run_id, status="blocked",
        reason_code="project_run_cycle_limit_reached", preflight=preflight,
        cycles=cycles, semantic_gate=False,
    )


def _dispatch_summary(value: Mapping[str, Any]) -> dict[str, Any]:
    launches = value.get("launches")
    deferred = value.get("deferred")
    return {
        "status": value.get("status"),
        "dispatch_sha256": value.get("dispatch_sha256"),
        "launch_count": len(launches) if isinstance(launches, list) else None,
        "deferred_count": len(deferred) if isinstance(deferred, list) else None,
    }


def _attempt_limit_reached(value: Mapping[str, Any]) -> bool:
    skipped = value.get("skipped")
    return isinstance(skipped, list) and any(
        isinstance(item, Mapping)
        and item.get("reason") == "attempt_limit_reached"
        for item in skipped
    )


def _finish(
    out_root: Path, *, run_id: str, status: str, reason_code: str | None,
    preflight: Mapping[str, Any] | None, cycles: list[dict[str, Any]],
    semantic_gate: bool, **details: Any,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-run-to-completion",
        "status": status, "run_id": run_id,
        "reason_code": reason_code,
        "preflight": dict(preflight) if preflight is not None else None,
        "cycles": cycles,
        "semantic_gate": semantic_gate, **details,
    }
    reference = write_json_artifact(
        out_root, "completion/run-to-completion.json", payload,
    )
    return {**payload, "run_receipt": reference}


__all__ = ["run_project_to_completion"]
