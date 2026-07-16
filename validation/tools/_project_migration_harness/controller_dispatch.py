from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import content_sha256, write_json_artifact
from .context_frontier import materialize_scheduled_contexts
from .context_frontier_overlay_runtime import resolve_schedule_context_overlays
from .ledger import LeaseConflict, ProjectLedger
from .ledger_security import AttemptLimitReached
from .model_safe_test_contract_bindings import portfolio_test_contract_references
from .orchestration_facts import build_gate_facts, read_artifact_reference
from .scheduler import schedule_portfolio
from .worker_requests import bind_attempt_request, materialize_worker_requests


def dispatch_project_workers(
    portfolio: Mapping[str, Any], *, ledger: ProjectLedger,
    harness_root: Path, out_root: Path, out_root_rel: str,
    lease_ttl_seconds: int = 900,
) -> dict[str, Any]:
    if lease_ttl_seconds < 30 or lease_ttl_seconds > 86_400:
        raise ValueError("lease_ttl_seconds must be between 30 and 86400")
    run_id = portfolio.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("portfolio run_id is invalid")
    portfolio_binding = ledger.require_portfolio_binding(portfolio)
    recovered = ledger.recover_expired_attempts(run_id=run_id)
    ledger.require_portfolio_binding(portfolio)
    states = ledger.unit_states(run_id)
    facts = build_gate_facts(ledger, run_id=run_id, harness_root=harness_root)
    for unit_id, reference in portfolio_test_contract_references(portfolio).items():
        if unit_id not in facts:
            raise ValueError("portfolio test contract references an unknown unit")
        facts[unit_id]["model_safe_test_contract"] = reference
    schedule = schedule_portfolio(portfolio, states, facts)
    schedule = resolve_schedule_context_overlays(
        schedule, harness_root=harness_root,
    )
    context_pages, context_materialization = materialize_scheduled_contexts(
        schedule,
        harness_root=harness_root,
        out_root=out_root,
        out_root_rel=out_root_rel,
    )
    context_binding = {
        **context_materialization,
        "path": f"{out_root_rel}/{context_materialization['path']}",
    }
    references = materialize_worker_requests(
        schedule, out_root=out_root, out_root_rel=out_root_rel,
        context_materialization=context_binding,
    )
    ready = {
        str(item["worker_id"]): item
        for item in schedule["ready"]
        if isinstance(item, Mapping)
    }
    launches: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for reference in references:
        worker_id = str(reference["worker_id"])
        scheduled = ready[worker_id]
        assignment = scheduled["assignment"]
        unit_id = str(assignment["unit_id"])
        role = str(assignment["role"])
        try:
            begun = ledger.begin_worker_attempt(
                run_id=run_id,
                assignment=assignment,
                ttl_seconds=lease_ttl_seconds,
                input_sha256=str(reference["effective_input_sha256"]),
                context_frontier=scheduled.get("context_frontier"),
                launch_claim=scheduled.get("launch_claim"),
                schedule_sha256=str(schedule["schedule_sha256"]),
                metadata={
                    "assignment_path": reference["assignment"]["path"],
                    "assignment_sha256": reference["assignment"]["sha256"],
                    "plan_sha256": portfolio_binding["plan_sha256"],
                    "dag_sha256": portfolio_binding["dag_sha256"],
                    "context_materialization_path": context_binding["path"],
                    "context_materialization_sha256": context_binding["sha256"],
                },
            )
        except LeaseConflict:
            skipped.append({"worker_id": worker_id, "reason": "lease_not_available"})
            continue
        except AttemptLimitReached:
            skipped.append({
                "worker_id": worker_id, "reason": "attempt_limit_reached",
            })
            continue
        attempt_id = str(begun["attempt_id"])
        token = int(begun["fencing_token"])
        try:
            base_request = json.loads(
                read_artifact_reference(harness_root, reference["request"]).decode("utf-8")
            )
            if not isinstance(base_request, Mapping):
                raise ValueError("materialized worker request must be an object")
            request = bind_attempt_request(
                base_request,
                attempt_id=attempt_id,
                fencing_token=token,
                lease_ttl_seconds=lease_ttl_seconds,
            )
            request_name = content_sha256({
                "attempt_id": attempt_id, "fencing_token": token,
                "request_sha256": content_sha256(request),
            })[:24]
            request_ref = write_json_artifact(
                out_root, f"harness/attempts/request-{request_name}.json", request
            )
            bound_ref = {
                **request_ref, "path": f"{out_root_rel}/{request_ref['path']}"
            }
            ledger.bind_attempt_request(
                attempt_id=attempt_id,
                owner=worker_id,
                fencing_token=token,
                request_path=bound_ref["path"],
                request_sha256=bound_ref["sha256"],
                effective_input_sha256=str(request["effective_input_sha256"]),
            )
        except BaseException:
            ledger.cancel_prelaunch_attempt(
                attempt_id=attempt_id, owner=worker_id, fencing_token=token,
            )
            raise
        launch = {
            "attempt_id": attempt_id,
            "run_id": run_id,
            "unit_id": unit_id,
            "group_id": assignment["group_id"],
            "worker_id": worker_id,
            "role": role,
            "fencing_token": token,
            "request": bound_ref,
            "assignment": reference["assignment"],
            "isolated_out_root": assignment["isolated_out_root"],
            "model_launched": False,
        }
        try:
            launch_name = content_sha256(launch)[:24]
            launch_ref = write_json_artifact(
                out_root, f"harness/launches/launch-{launch_name}.json", launch
            )
        except BaseException:
            ledger.cancel_prelaunch_attempt(
                attempt_id=attempt_id, owner=worker_id, fencing_token=token,
            )
            raise
        launches.append({**launch, "launch_artifact": {
            **launch_ref, "path": f"{out_root_rel}/{launch_ref['path']}"
        }})
    attempt_limit_reached = any(
        item["reason"] == "attempt_limit_reached" for item in skipped
    )
    report = {
        "schema_version": 1,
        "status": (
            "dispatched" if launches else "blocked" if attempt_limit_reached
            else schedule["status"]
        ),
        "run_id": run_id,
        "recovered_attempt_ids": recovered,
        "launches": launches,
        "skipped": skipped,
        "deferred": schedule["deferred"],
        "context_materialization": context_binding,
        "materialized_context_page_count": len(context_pages),
        "execution": {"model_launched": False, "cargo_executed": False},
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    report["dispatch_sha256"] = content_sha256(report)
    write_json_artifact(out_root, "harness/latest-dispatch.json", report)
    return report


__all__ = ["dispatch_project_workers"]
