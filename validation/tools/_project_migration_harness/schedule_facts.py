from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .portfolio_roles import PLANNER_DECISIONS


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha_fact(facts: Mapping[str, Any], key: str) -> str | None:
    value = facts.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"gate fact {key} must be a lowercase SHA-256")
    return value


def planner_decision(
    assignment: Mapping[str, Any], facts: Mapping[str, Any]
) -> str | None:
    raw = facts.get("planner_decision")
    claimed = facts.get("planner_decision_sha256")
    if raw is None and claimed is None:
        return None
    if not isinstance(raw, Mapping) or not isinstance(claimed, str):
        raise ValueError("planner decision payload and SHA must be provided together")
    context = assignment.get("context")
    if not isinstance(context, Mapping):
        raise ValueError("planner assignment context is invalid")
    expected = {
        "run_id": assignment.get("run_id"),
        "group_id": assignment.get("group_id"),
        "group_sha256": assignment.get("group_sha256"),
        "context_pack_sha256": context.get("sha256"),
        "decision": raw.get("decision"),
    }
    if dict(raw) != expected or content_sha256(expected) != claimed:
        raise ValueError("planner decision binding does not match the assignment")
    decision = expected["decision"]
    if decision not in PLANNER_DECISIONS:
        raise ValueError("planner decision is not allowed")
    return str(decision)


def dependencies_passed(
    dependencies: Any, states: Mapping[str, Mapping[str, Any]]
) -> bool:
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) and item for item in dependencies
    ):
        raise ValueError("assignment dependencies must be non-empty strings")
    for dependency in dependencies:
        state = states.get(dependency)
        if not state:
            return False
        if state.get("status") == "completed":
            continue
        if (
            state.get("resumable_status") != "last_good"
            or not isinstance(state.get("last_good_artifact_id"), str)
            or not state["last_good_artifact_id"]
        ):
            return False
    return True


def repair_mode(facts: Mapping[str, Any]) -> str | None:
    candidate = sha_fact(facts, "candidate_artifact_sha256")
    failed = sha_fact(facts, "failed_gate_result_sha256")
    if candidate is None or failed is None:
        return None
    last_good_sha = sha_fact(facts, "last_good_artifact_sha256")
    last_good_id = facts.get("last_good_artifact_id")
    if last_good_sha is None and last_good_id is None:
        return "candidate_repair"
    if (
        last_good_sha is not None
        and isinstance(last_good_id, str)
        and bool(last_good_id)
    ):
        return "post_last_good_regression_repair"
    raise ValueError("last-good repair facts must be complete")


__all__ = [
    "dependencies_passed",
    "planner_decision",
    "repair_mode",
    "sha_fact",
]
