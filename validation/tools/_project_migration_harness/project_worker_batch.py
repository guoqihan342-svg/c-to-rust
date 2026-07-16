from __future__ import annotations

from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .ledger import LedgerError, ProjectLedger


def execute_project_worker_batch(
    launches: list[Any], *, preflight_reference: Mapping[str, Any] | None,
    ledger: ProjectLedger, harness_root: Path, logical_model: str,
    resolved_model: str, timeout_seconds: int,
    worker_runner: Callable[..., Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    if not isinstance(preflight_reference, Mapping):
        raise ValueError("project worker preflight reference is missing")
    normalized: list[Mapping[str, Any]] = []
    for launch in launches:
        if not isinstance(launch, Mapping):
            raise ValueError("project worker launch is invalid")
        normalized.append(launch)

    def execute(launch: Mapping[str, Any]) -> Mapping[str, Any]:
        request = launch.get("request")
        if not isinstance(request, Mapping):
            return _cancel_missing_worker_request(ledger, launch)
        try:
            return worker_runner(
                request, preflight_reference, ledger=ledger,
                harness_root=harness_root, logical_model=logical_model,
                resolved_model=resolved_model, opencode_command="opencode",
                timeout_seconds=timeout_seconds,
            )
        except Exception as error:
            return {
                "schema_version": 1, "status": "manual-reconcile",
                "reason_code": "project_worker_runtime_exception",
                "exception_type": type(error).__name__, "semantic_gate": False,
            }

    with ThreadPoolExecutor(
        max_workers=len(normalized), thread_name_prefix="c2r-project-worker",
    ) as pool:
        futures = [pool.submit(execute, launch) for launch in normalized]
        results = [future.result() for future in futures]
    return list(zip(normalized, results, strict=True))


def _cancel_missing_worker_request(
    ledger: ProjectLedger, launch: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        ledger.cancel_prelaunch_attempt(
            attempt_id=str(launch["attempt_id"]),
            owner=str(launch["worker_id"]),
            fencing_token=int(launch["fencing_token"]),
        )
    except (KeyError, LedgerError, TypeError, ValueError):
        return {
            "schema_version": 1, "status": "manual-reconcile",
            "reason_code": "project_worker_request_missing",
            "semantic_gate": False,
        }
    return {
        "schema_version": 1, "status": "prelaunch-blocked",
        "reason_code": "project_worker_request_missing",
        "attempt_consumed": False, "semantic_gate": False,
    }


def worker_summary(
    launch: Mapping[str, Any], worker: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "worker_id": launch.get("worker_id"),
        "unit_id": launch.get("unit_id"),
        "attempt_id": launch.get("attempt_id"),
        "status": worker.get("status"),
        "attempt_consumed": worker.get("attempt_consumed"),
    }


def safe_prelaunch_retry(value: Mapping[str, Any]) -> bool:
    return (
        value.get("status") == "prelaunch-blocked"
        and value.get("attempt_consumed") is False
    )


__all__ = [
    "execute_project_worker_batch", "safe_prelaunch_retry", "worker_summary",
]
