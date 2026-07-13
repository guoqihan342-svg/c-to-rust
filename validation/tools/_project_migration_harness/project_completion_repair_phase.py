from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger import LedgerError, ProjectLedger
from .project_integration import integrate_verified_project_repair
from .project_preflight_runner import run_project_worker_preflight
from .project_repair_dispatch_permit import issue_project_repair_dispatch_permit
from .project_repair_result_recovery import ingest_recorded_project_repair_result
from .project_repair_runtime import run_and_ingest_opencode_project_repair


def execute_project_repair_completion_step(
    migration_manifest: Mapping[str, Any], *, initial_integration: Mapping[str, Any],
    ledger: ProjectLedger, run_id: str, harness_root: Path, out_root: Path,
    out_root_rel: str, project_root: Path, logical_model: str,
    resolved_model: str, timeout_seconds: int,
    preflight_timeout_seconds: int,
) -> dict[str, Any]:
    repair = initial_integration.get("project_repair")
    if (
        initial_integration.get("stage") == "project-interface-repair"
        and isinstance(repair, Mapping)
        and repair.get("status") == "ingest-required"
    ):
        recovered = ingest_recorded_project_repair_result(
            repair["request"], repair["response"], ledger=ledger,
            harness_root=harness_root, out_root=out_root,
            out_root_rel=out_root_rel,
        )
        return _from_runtime(
            recovered, dispatched=repair,
            preflight={"status": "reopened-from-bound-request"},
        )
    if (
        initial_integration.get("stage") != "project-interface-repair"
        or not isinstance(repair, Mapping)
        or repair.get("status") != "preflight-required"
    ):
        return _from_integration(initial_integration)
    try:
        preflight = run_project_worker_preflight(
            harness_root=harness_root, out_root_rel=out_root_rel,
            run_id=run_id, logical_model=logical_model,
            resolved_model=resolved_model,
            timeout_seconds=preflight_timeout_seconds,
        )
    except (LedgerError, OSError, ValueError):
        return _result(
            "blocked", "project-repair-preflight-invariant-failed",
            ["project-repair-preflight-invariant-failed"],
            provider_invocations=0, model_launched=False,
        )
    if preflight.get("status") != "passed":
        return _result(
            "blocked", "project-repair-preflight-blocked",
            ["project-repair-model-or-agent-unavailable"],
            preflight=preflight, provider_invocations=0,
            model_launched=False,
        )
    try:
        permit = issue_project_repair_dispatch_permit(
            repair, preflight["report"], harness_root=harness_root,
            run_id=run_id, logical_model=logical_model,
            resolved_model=resolved_model,
        )
    except (KeyError, OSError, TypeError, ValueError):
        return _result(
            "blocked", "project-repair-preflight-invariant-failed",
            ["project-repair-preflight-evidence-invalid"],
            preflight=preflight, provider_invocations=0,
            model_launched=False,
        )
    integration = integrate_verified_project_repair(
        migration_manifest, ledger=ledger, run_id=run_id,
        candidate_root=out_root, candidate_root_rel=out_root_rel,
        project_root=project_root, repair_dispatch_permit=permit,
    )
    if integration.get("status") == "integrated":
        return _result(
            "integrated", "project-repair-state-advanced", [],
            integration=integration, preflight=preflight,
            provider_invocations=0, model_launched=False,
        )
    dispatched = integration.get("project_repair")
    if (
        integration.get("stage") != "project-interface-repair"
        or not isinstance(dispatched, Mapping)
        or dispatched.get("status") != "repair-dispatched"
    ):
        value = _from_integration(integration)
        value["preflight"] = preflight
        return value
    runtime = run_and_ingest_opencode_project_repair(
        dispatched["request"], preflight["report"], ledger=ledger,
        harness_root=harness_root, out_root=out_root,
        out_root_rel=out_root_rel, logical_model=logical_model,
        resolved_model=resolved_model, timeout_seconds=timeout_seconds,
    )
    return _from_runtime(runtime, dispatched=dispatched, preflight=preflight)


def _from_integration(value: Mapping[str, Any]) -> dict[str, Any]:
    repair = value.get("project_repair")
    blockers = repair.get("blockers", []) if isinstance(repair, Mapping) else []
    return _result(
        str(value.get("status", "blocked")),
        str(value.get("stage", "project-interface-repair")),
        list(blockers) if isinstance(blockers, list) else [],
        integration=dict(value), provider_invocations=0,
        model_launched=False,
    )


def _from_runtime(
    runtime: Mapping[str, Any], *, dispatched: Mapping[str, Any],
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    status = str(runtime.get("status", "blocked"))
    if status in {
        "resolved", "retry-ready", "waiting", "ingest-required",
        "terminal-replay",
    }:
        coordinator_status = "waiting"
    else:
        coordinator_status = "blocked"
    if status == "resolved":
        stage = "project-repair-candidate-recoordinated"
    elif status == "retry-ready":
        stage = "project-repair-attempt-retry-ready"
    elif status == "waiting":
        stage = str(runtime.get("stage", "project-repair-attempt-active"))
    elif status == "ingest-required":
        stage = "project-repair-provider-result-recorded"
    elif status == "terminal-replay":
        stage = "project-repair-state-advanced"
    elif status == "exhausted":
        stage = "project-repair-attempts-exhausted"
    elif status == "manual-reconcile":
        stage = "project-repair-manual-reconcile"
    else:
        stage = "project-repair-attempt-blocked"
    blockers = [] if coordinator_status == "waiting" else [
        f"project-repair-runtime-{status}"
    ]
    generation = runtime.get("generation")
    model_launched = bool(runtime.get("model_launched"))
    if isinstance(generation, Mapping):
        model_launched = bool(generation.get("model_launched", model_launched))
    return _result(
        coordinator_status, stage, blockers, runtime=dict(runtime),
        dispatch=dict(dispatched), preflight=dict(preflight),
        provider_invocations=1 if model_launched else 0,
        model_launched=model_launched,
    )


def _result(
    status: str, stage: str, blockers: list[str], **details: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": status, "stage": stage,
        "blockers": blockers, "semantic_gate": False, **details,
    }


__all__ = ["execute_project_repair_completion_step"]
