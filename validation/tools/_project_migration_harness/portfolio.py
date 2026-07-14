from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .ledger_security import assert_no_secrets
from .context_required_facts import required_fact_binding_ready
from .portfolio_integrity import (
    PortfolioIntegrityError,
    bind_context,
    canonical_dag,
    canonical_group,
    canonical_sha256,
    dependencies_by_group,
    groups_by_id,
    positive,
    relative_path,
    wave_layout,
)
from .portfolio_roles import boundary_required, roles_for_group, worker_descriptor


SCHEMA_VERSION = 1
PortfolioError = PortfolioIntegrityError
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def _explicitly_eligible(group: Mapping[str, Any]) -> bool:
    if "structurally_eligible" in group:
        return group.get("structurally_eligible") is True
    eligibility = group.get("eligibility")
    if isinstance(eligibility, Mapping) and eligibility.get("status") == "eligible":
        return True
    if group.get("structural_status") == "eligible":
        return True
    return group.get("classification") in {"independent", "context_group"}


def _retrieval_ready(context: Mapping[str, Any]) -> bool:
    if "retrieval" not in context:
        return True
    retrieval = context.get("retrieval")
    if not isinstance(retrieval, Mapping):
        return False
    receipt = retrieval.get("selection_receipt_sha256")
    blockers = retrieval.get("selection_blockers")
    return (
        retrieval.get("selection_status") == "ready"
        and isinstance(receipt, str)
        and len(receipt) == 64
        and all(character in _HEX_DIGITS for character in receipt)
        and isinstance(blockers, list)
        and not blockers
        and required_fact_binding_ready(retrieval)
    )


def plan_portfolio(
    dag: Mapping[str, Any], *, out_root: str, max_concurrency: int,
    max_attempts: int, context_byte_budget: int, context_token_budget: int,
    context_page_limit: int = 32,
    context_page_payloads: Mapping[str, Any] | None = None,
    context_page_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build hash-bound assignments; this function never materializes or launches them."""
    assert_no_secrets(dag, "migration_dag")
    max_concurrency = positive(max_concurrency, "max_concurrency")
    max_attempts = positive(max_attempts, "max_attempts")
    byte_budget = positive(context_byte_budget, "context_byte_budget")
    token_budget = positive(context_token_budget, "context_token_budget")
    page_limit = positive(context_page_limit, "context_page_limit")
    root = relative_path(out_root, "out_root")
    run_id = dag.get("run_id")
    project_key = dag.get("project_key", dag.get("project_id"))
    if not isinstance(run_id, str) or not run_id or not isinstance(project_key, str) or not project_key:
        raise PortfolioError("migration DAG requires run_id and project_key")

    groups = groups_by_id(dag)
    layout, membership = wave_layout(dag, groups)
    dependencies = dependencies_by_group(groups, membership)
    contexts: dict[str, dict[str, Any] | None] = {}
    canonical_groups: dict[str, dict[str, Any]] = {}
    group_hashes: dict[str, str] = {}
    for group_id, group in groups.items():
        raw_context = group.get("context_pack")
        if raw_context is None:
            context = None
        elif not isinstance(raw_context, Mapping):
            raise PortfolioError(f"group {group_id} context_pack must be an object")
        else:
            context = bind_context(
                raw_context,
                page_payloads=context_page_payloads,
                page_root=context_page_root,
                max_page_bytes=byte_budget,
            )
        contexts[group_id] = context
        payload, digest = canonical_group(group, dependencies[group_id], context)
        canonical_groups[group_id] = {**payload, "content_sha256": digest}
        group_hashes[group_id] = digest
    dag_sha256 = canonical_dag(
        dag, [canonical_groups[str(group["group_id"])] for group in dag["groups"]],
    )

    assignments: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    unavailable: set[str] = set()
    planned_waves: list[dict[str, Any]] = []
    for wave_index, group_ids in enumerate(layout):
        wave_workers: list[str] = []
        for slot, group_id in enumerate(group_ids, start=1):
            group = groups[group_id]
            needs_planner = boundary_required(group)
            reasons: list[str] = []
            if not _explicitly_eligible(group) and not needs_planner:
                reasons.append("structural_eligibility_not_proven")
            for dependency in dependencies[group_id]:
                if membership[dependency] >= wave_index:
                    reasons.append(f"dependency_not_in_earlier_wave:{dependency}")
                elif dependency in unavailable and not needs_planner:
                    reasons.append(f"dependency_blocked:{dependency}")
            context = contexts[group_id]
            if (_explicitly_eligible(group) or needs_planner) and context is None:
                reasons.append("routable_group_context_pack_missing")
            if context is not None and not _retrieval_ready(context):
                reasons.append("context_retrieval_not_ready")
            if context and context["byte_count"] > byte_budget:
                reasons.append("context_byte_budget_exceeded")
            if context and context["token_count"] > token_budget:
                reasons.append("context_token_budget_exceeded")
            if context and context["page_count"] > page_limit:
                reasons.append("context_page_limit_exceeded")
            if reasons:
                unavailable.add(group_id)
                blocked.append({
                    "group_id": group_id,
                    "wave_index": wave_index,
                    "reasons": sorted(set(reasons)),
                })
                continue
            for role in roles_for_group(group):
                descriptor = worker_descriptor(
                    run_id=run_id,
                    group_id=group_id,
                    group_sha256=group_hashes[group_id],
                    wave_index=wave_index,
                    slot=slot,
                    role=role,
                    dependencies=dependencies[group_id],
                    context=context or {},
                    out_root=root,
                    byte_budget=byte_budget,
                    token_budget=token_budget,
                    max_attempts=max_attempts,
                    needs_planner=needs_planner,
                )
                assignments.append(descriptor)
                wave_workers.append(descriptor["worker_id"])
        planned_waves.append({
            "wave_index": wave_index,
            "group_ids": list(group_ids),
            "worker_ids": wave_workers,
        })

    ready = [item for item in assignments if item["launch_policy"]["state"] == "ready"]
    role_order = {"planner": 0, "translator": 1, "reviewer": 2, "repairer": 3}
    ready.sort(key=lambda item: (
        item["wave_index"], role_order[item["role"]], item["worker_id"],
    ))
    units = ready[:max_concurrency]
    ledger_units = [
        {
            "unit_id": group_id,
            "group_id": group_id,
            "wave_index": membership[group_id],
            "status": "blocked" if group_id in unavailable else "pending",
            "resumable_status": "terminal" if group_id in unavailable else "ready",
            "content_sha256": group_hashes[group_id],
        }
        for group_id in groups
    ]
    plan = {
        "schema_version": SCHEMA_VERSION,
        "status": "planned" if assignments else "blocked",
        "run_id": run_id,
        "project_key": project_key,
        "dag_sha256": dag_sha256,
        "limits": {
            "max_concurrency": max_concurrency,
            "max_attempts": max_attempts,
            "context_byte_budget": byte_budget,
            "context_token_budget": token_budget,
            "context_page_limit": page_limit,
        },
        "waves": planned_waves,
        "assignments": assignments,
        "units": units,
        "ledger_units": ledger_units,
        "initial_ready": {
            "selected_worker_ids": [item["worker_id"] for item in units],
            "deferred_worker_ids": [item["worker_id"] for item in ready[max_concurrency:]],
        },
        "blocked_groups": blocked,
        "execution": {
            "launches_processes": False,
            "materialization_required": True,
            "direct_run_plan_safe": False,
            "reason": "portfolio requires its condition-aware ledger adapter; legacy run-plan is unsupported",
        },
    }
    plan["plan_sha256"] = canonical_sha256(plan)
    return plan


__all__ = ["PortfolioError", "plan_portfolio"]
