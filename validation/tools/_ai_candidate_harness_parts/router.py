from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Any


MAX_CANDIDATES = 4
MAX_CANDIDATE_ID_BYTES = 128
DEFAULT_PROVIDER_INVOCATION_BUDGET = 1
HARD_MAX_PROVIDER_INVOCATIONS = 2
SOURCE_ORDER = (
    "opencode-ai",
    "typed-ir",
    "c2rust-repair",
    "c2rust-baseline",
)
ALLOWED_SOURCES = frozenset(SOURCE_ORDER)
FORBIDDEN_SOURCE_CLASSES = (
    "legacy",
    "handwritten",
    "accepted-evidence",
)
REQUIRED_GATES = (
    "compile",
    "oracle",
    "replay",
    "schema_diff",
    "negative_diff",
    "unsafe",
    "alias_abi",
    "final_verification",
)
IGNORED_RANKING_FIELDS = (
    "target",
    "project",
    "function",
    "slice",
    "model",
    "self_score",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def build_selection_policy(*, provider_invocation_budget: int = DEFAULT_PROVIDER_INVOCATION_BUDGET) -> dict[str, Any]:
    budget = _bounded_invocation_count(provider_invocation_budget, field="provider_invocation_budget")
    return {
        "schema_version": 1,
        "stage": "p0_ai_primary_pure_candidate_router",
        "full_router": True,
        "max_candidates": MAX_CANDIDATES,
        "source_order": list(SOURCE_ORDER),
        "forbidden_source_classes": list(FORBIDDEN_SOURCE_CLASSES),
        "deduplication_key": "artifact_sha256",
        "tie_breakers": ["source_order", "artifact_sha256", "candidate_id"],
        "ignored_ranking_fields": list(IGNORED_RANKING_FIELDS),
        "required_gates": list(REQUIRED_GATES),
        "selection_rule": "first_fixed_order_candidate_passing_all_sha_bound_gates",
        "provider_invocation_budget": {
            "default": DEFAULT_PROVIDER_INVOCATION_BUDGET,
            "hard_max": HARD_MAX_PROVIDER_INVOCATIONS,
            "effective": budget,
        },
    }


def selection_policy_sha256(policy: dict[str, Any]) -> str:
    encoded = json.dumps(policy, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def route_candidates(
    candidates: list[dict[str, Any]],
    *,
    provider_invocation_budget: int = DEFAULT_PROVIDER_INVOCATION_BUDGET,
    provider_invocations: int = 0,
) -> dict[str, Any]:
    if not isinstance(candidates, list):
        raise ValueError("candidates must be an array")
    if len(candidates) > MAX_CANDIDATES:
        raise ValueError(f"candidate input exceeds hard maximum of {MAX_CANDIDATES}")
    observed_invocations = _bounded_invocation_count(provider_invocations, field="provider_invocations")
    policy = build_selection_policy(provider_invocation_budget=provider_invocation_budget)
    budget = policy["provider_invocation_budget"]["effective"]
    if observed_invocations > budget:
        raise ValueError("provider_invocations exceeds the effective invocation budget")

    normalized = [_normalize_candidate(item) for item in candidates]
    candidate_ids = [item["candidate_id"] for item in normalized]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("candidate_id values must be unique")
    normalized.sort(key=_schedule_key)

    candidate_set: list[dict[str, Any]] = []
    deduplicated_candidates: list[dict[str, Any]] = []
    by_sha: dict[str, str] = {}
    for candidate in normalized:
        artifact_sha = candidate["artifact_sha256"]
        if _valid_sha256(artifact_sha) and artifact_sha in by_sha:
            deduplicated_candidates.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "source": candidate["source"],
                    "artifact_sha256": artifact_sha,
                    "duplicate_of": by_sha[artifact_sha],
                    "rejection_facts": [
                        {
                            "gate": "deduplication",
                            "reason": "duplicate_artifact_sha256",
                            "artifact_sha256": artifact_sha,
                        }
                    ],
                }
            )
            continue
        if _valid_sha256(artifact_sha):
            by_sha[artifact_sha] = candidate["candidate_id"]
        candidate_set.append(candidate)

    selected_id: str | None = None
    for schedule_index, candidate in enumerate(candidate_set):
        candidate["schedule_index"] = schedule_index
        gate_facts, accepted_gates = _evaluate_gates(candidate)
        candidate["rejection_facts"].extend(gate_facts)
        candidate["accepted_gates"] = accepted_gates
        if selected_id is None and not candidate["rejection_facts"]:
            selected_id = candidate["candidate_id"]
            candidate["decision"] = "selected"
        elif candidate["rejection_facts"]:
            candidate["decision"] = "rejected"
        else:
            candidate["decision"] = "eligible_not_selected"
        candidate.pop("gate_results", None)

    result = {
        "schema_version": 1,
        "selection_policy": policy,
        "selection_policy_sha256": selection_policy_sha256(policy),
        "provider_invocations": observed_invocations,
        "selected_candidate_id": selected_id,
        "candidate_set": candidate_set,
        "deduplicated_candidates": deduplicated_candidates,
    }
    result["metrics"] = recompute_router_metrics(result)
    return result


def recompute_router_metrics(result: dict[str, Any]) -> dict[str, int | str | None]:
    policy = result.get("selection_policy")
    if not isinstance(policy, dict):
        raise ValueError("router result requires selection_policy")
    candidate_set = result.get("candidate_set")
    duplicates = result.get("deduplicated_candidates")
    if not isinstance(candidate_set, list) or not isinstance(duplicates, list):
        raise ValueError("router result requires candidate_set and deduplicated_candidates arrays")
    observed = _bounded_invocation_count(result.get("provider_invocations"), field="provider_invocations")
    budget_record = policy.get("provider_invocation_budget")
    if not isinstance(budget_record, dict):
        raise ValueError("selection policy requires provider_invocation_budget")
    budget = _bounded_invocation_count(budget_record.get("effective"), field="effective budget")
    if observed > budget:
        raise ValueError("provider_invocations exceeds the effective invocation budget")

    selected_id = result.get("selected_candidate_id")
    selected_index = next(
        (index for index, item in enumerate(candidate_set) if item.get("candidate_id") == selected_id),
        None,
    )
    rejected = [item for item in candidate_set if item.get("decision") == "rejected"]
    eligible = [item for item in candidate_set if item.get("decision") in {"selected", "eligible_not_selected"}]
    source_rejected = sum(
        any(fact.get("gate") == "candidate_source" for fact in item.get("rejection_facts", []))
        for item in rejected
    )
    return {
        "candidate_inputs": len(candidate_set) + len(duplicates),
        "unique_candidates": len(candidate_set),
        "deduplicated_candidates": len(duplicates),
        "eligible_candidates": len(eligible),
        "rejected_candidates": len(rejected),
        "source_rejected_candidates": source_rejected,
        "fallbacks_attempted": selected_index if selected_index is not None else len(candidate_set),
        "selected_candidate_id": selected_id,
        "provider_invocation_budget": budget,
        "provider_invocations": observed,
        "provider_invocations_remaining": budget - observed,
        "selection_policy_sha256": selection_policy_sha256(policy),
    }


def _normalize_candidate(candidate: Any) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ValueError("each candidate must be an object")
    candidate_id = candidate.get("candidate_id")
    if (
        not isinstance(candidate_id, str)
        or not candidate_id
        or candidate_id != candidate_id.strip()
        or len(candidate_id.encode("utf-8")) > MAX_CANDIDATE_ID_BYTES
    ):
        raise ValueError("each candidate requires a non-empty candidate_id")
    source = candidate.get("source", candidate.get("kind"))
    rejection_facts: list[dict[str, Any]] = []
    if not isinstance(source, str) or not source:
        source = "invalid"
        rejection_facts.append({"gate": "candidate_source", "reason": "missing_candidate_source"})
    elif candidate.get("source") is not None and candidate.get("kind") not in {None, source}:
        rejection_facts.append({"gate": "candidate_source", "reason": "conflicting_source_and_kind"})
    elif source not in ALLOWED_SOURCES:
        rejection_facts.append({"gate": "candidate_source", "reason": "forbidden_or_unsupported_source"})

    artifact = candidate.get("artifact")
    nested_sha = artifact.get("sha256") if isinstance(artifact, dict) else None
    direct_sha = candidate.get("artifact_sha256")
    artifact_sha = direct_sha if direct_sha is not None else nested_sha
    if direct_sha is not None and nested_sha is not None and direct_sha != nested_sha:
        rejection_facts.append({"gate": "artifact_binding", "reason": "conflicting_artifact_sha256"})
    artifact_sha_valid = _valid_sha256(artifact_sha)
    if not artifact_sha_valid:
        rejection_facts.append({"gate": "artifact_binding", "reason": "invalid_artifact_sha256"})

    gate_results = candidate.get("gate_results")
    if not isinstance(gate_results, dict):
        gate_results = {}
    normalized_source = source if source in ALLOWED_SOURCES else "rejected"
    return {
        "candidate_id": candidate_id,
        "source": normalized_source,
        "artifact_sha256": artifact_sha if artifact_sha_valid else None,
        "gate_results": gate_results,
        "rejection_facts": rejection_facts,
    }


def _evaluate_gates(candidate: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    artifact_sha = candidate["artifact_sha256"]
    gate_results = candidate["gate_results"]
    facts: list[dict[str, Any]] = []
    accepted: list[str] = []
    for gate in REQUIRED_GATES:
        result = gate_results.get(gate)
        if not isinstance(result, dict):
            facts.append({"gate": gate, "reason": "missing_or_invalid_gate_result"})
            continue
        status = result.get("status")
        bound_sha = result.get("candidate_sha256")
        if status != "passed":
            actual_status = status if status in {"failed", "blocked", "skipped", "refused", "not_run"} else "invalid"
            facts.append({"gate": gate, "reason": "gate_not_passed", "actual": actual_status})
        if not _valid_sha256(bound_sha):
            facts.append({"gate": gate, "reason": "invalid_gate_candidate_sha256"})
        elif bound_sha != artifact_sha:
            facts.append(
                {
                    "gate": gate,
                    "reason": "gate_candidate_sha256_mismatch",
                    "expected": artifact_sha,
                    "actual": bound_sha,
                }
            )
        if status == "passed" and bound_sha == artifact_sha:
            accepted.append(gate)
    return facts, accepted


def _schedule_key(candidate: dict[str, Any]) -> tuple[int, str, str]:
    try:
        source_rank = SOURCE_ORDER.index(candidate["source"])
    except ValueError:
        source_rank = len(SOURCE_ORDER)
    artifact_sha = candidate["artifact_sha256"] if _valid_sha256(candidate["artifact_sha256"]) else "~"
    return source_rank, artifact_sha, candidate["candidate_id"]


def _valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _bounded_invocation_count(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    if value > HARD_MAX_PROVIDER_INVOCATIONS:
        raise ValueError(f"{field} exceeds hard maximum of {HARD_MAX_PROVIDER_INVOCATIONS}")
    return value
