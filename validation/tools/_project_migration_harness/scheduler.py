from __future__ import annotations

from typing import Any, Mapping, Sequence

from .schedule_facts import (
    dependencies_passed,
    planner_decision,
    repair_mode,
    sha_fact,
)
from .runtime_binding import compute_portfolio_binding
from .schedule_priority import scheduling_priority
from .project_knowledge import validate_knowledge_reference
from .schedule_graph import critical_path_weights
from .candidate_strategy import validate_candidate_strategy
from .project_interface_model_context import validate_model_coordinator_context
from .context_required_facts import context_retrieval_ready



def schedule_portfolio(
    portfolio: Mapping[str, Any],
    unit_states: Sequence[Mapping[str, Any]],
    gate_facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    if "plan_sha256" in portfolio:
        compute_portfolio_binding(portfolio)
    assignments = portfolio.get("assignments")
    limits = portfolio.get("limits")
    if not isinstance(assignments, list) or not isinstance(limits, Mapping):
        raise ValueError("portfolio assignments/limits contract is invalid")
    max_concurrency = limits.get("max_concurrency")
    if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int) or max_concurrency < 1:
        raise ValueError("portfolio max_concurrency is invalid")
    states = _unit_state_map(unit_states)
    critical_paths = critical_path_weights(
        assignments, known_group_ids=set(states),
    )
    ready: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise ValueError("portfolio assignment is invalid")
        group_id = _string(assignment, "group_id")
        if _string(assignment, "unit_id") != group_id:
            raise ValueError("assignment group_id must equal unit_id")
        role = _string(assignment, "role")
        facts = gate_facts.get(group_id, {})
        reasons = _deferred_reasons(assignment, states, facts)
        priority = scheduling_priority(
            facts, critical_path_weight=critical_paths[group_id],
        )
        if priority is not None and priority["stalled"] and not reasons:
            reasons = ["unchanged_failure_input_and_strategy"]
        record = {
            "worker_id": _string(assignment, "worker_id"),
            "group_id": group_id,
            "role": role,
            "wave_index": int(assignment.get("wave_index", -1)),
        }
        if role == "repairer" and not reasons:
            record["repair_mode"] = repair_mode(facts)
        if priority is not None:
            record["scheduling_priority"] = priority
        if reasons:
            deferred.append({**record, "reasons": reasons})
        else:
            ready.append({
                **record,
                "assignment": dict(assignment),
                "input_facts": _input_facts(role, facts),
            })
    role_order = {"planner": 0, "translator": 1, "reviewer": 2, "repairer": 3}
    ready.sort(key=lambda item: (
        -int(item.get("scheduling_priority", {}).get("score", 0)),
        item["wave_index"], role_order.get(item["role"], 99), item["worker_id"],
    ))
    selected = ready[:max_concurrency]
    for item in ready[max_concurrency:]:
        deferred.append({
            **{key: item[key] for key in ("worker_id", "group_id", "role", "wave_index")},
            "reasons": ["max_concurrency_reached"],
        })
    return {
        "schema_version": 1,
        "status": "ready" if selected else "waiting",
        "ready": selected,
        "deferred": sorted(deferred, key=lambda item: (
            item["wave_index"], item["role"], item["worker_id"],
        )),
        "limits": {"max_concurrency": max_concurrency},
        "authority": {
            "semantic_gate_owner": "external-verifier",
            "reviewer_can_accept_semantics": False,
            "repair_requires_failed_gate": True,
        },
    }


def _unit_state_map(values: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for value in values:
        if not isinstance(value, Mapping):
            raise ValueError("unit state must be an object")
        group_id = value.get("group_id")
        if not isinstance(group_id, str) or not group_id or group_id in result:
            raise ValueError("unit states require unique group_id values")
        result[group_id] = value
    return result


def _deferred_reasons(
    assignment: Mapping[str, Any],
    states: Mapping[str, Mapping[str, Any]],
    facts: Mapping[str, Any],
) -> list[str]:
    group_id = _string(assignment, "group_id")
    role = _string(assignment, "role")
    state = states.get(group_id)
    if state is None:
        return ["unit_state_missing"]
    context = assignment.get("context")
    if not isinstance(context, Mapping):
        raise ValueError("assignment context must be an object")
    if not context_retrieval_ready(context):
        return ["context_retrieval_pending"]
    dependencies = assignment.get("dependencies", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise ValueError("assignment dependencies must be strings")
    if role != "planner" and not dependencies_passed(dependencies, states):
        return ["dependency_gate_pending"]
    policy = assignment.get("launch_policy")
    requirements = policy.get("requires", []) if isinstance(policy, Mapping) else []
    if "generated_build_closure_verified" in requirements:
        return ["generated_build_closure_not_verified"]
    decision = planner_decision(assignment, facts)
    if role == "planner":
        if decision is not None:
            return ["planner_decision_already_recorded"]
        return [] if state.get("status") in {"pending", "retry-ready"} else ["planner_state_not_ready"]
    if role == "translator":
        needs_planner = "planner_decision_sha256" in assignment.get("launch_policy", {}).get("requires", [])
        if needs_planner and decision not in {"translate_with_context", "preserve_ffi_boundary"}:
            return ["planner_decision_not_translation"]
        if sha_fact(facts, "candidate_artifact_sha256") is not None:
            return ["candidate_already_recorded"]
        return [] if state.get("status") in {"pending", "candidate-ready"} else ["translator_state_not_ready"]
    if role == "reviewer":
        if sha_fact(facts, "candidate_artifact_sha256") is None:
            return ["candidate_artifact_missing"]
        if sha_fact(facts, "review_artifact_sha256") is not None:
            return ["review_already_recorded"]
        return [] if state.get("status") in {"candidate-ready", "gate-pending"} else ["reviewer_state_not_ready"]
    if role == "repairer":
        mode = repair_mode(facts)
        if mode is None:
            return ["failed_gate_result_missing"]
        return [] if state.get("status") == "retry-ready" else ["repairer_state_not_ready"]
    return ["unsupported_worker_role"]


def _string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{key} must be a non-empty string")
    return result


def _input_facts(role: str, facts: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "planner": (),
        "translator": ("planner_decision", "planner_decision_sha256"),
        "reviewer": (
            "candidate_artifact",
            "candidate_artifact_id",
            "candidate_artifact_sha256",
        ),
        "repairer": (
            "planner_decision",
            "planner_decision_sha256",
            "candidate_artifact",
            "candidate_artifact_id",
            "candidate_artifact_sha256",
            "failed_gate_result",
            "failed_gate_result_sha256",
            "last_good_artifact_id",
            "last_good_artifact",
            "last_good_artifact_sha256",
        ),
    }
    result = {key: facts[key] for key in allowed.get(role, ()) if key in facts}
    if role in {"translator", "repairer"} and "candidate_strategy" in facts:
        result["candidate_strategy"] = validate_candidate_strategy(
            facts["candidate_strategy"]
        )
    if "project_knowledge" in facts:
        result["project_knowledge"] = validate_knowledge_reference(
            facts["project_knowledge"]
        )
    if role in {"planner", "translator", "repairer"} and "coordinator_context" in facts:
        result["coordinator_context"] = validate_model_coordinator_context(
            facts["coordinator_context"]
        )
    return result


__all__ = ["schedule_portfolio"]
