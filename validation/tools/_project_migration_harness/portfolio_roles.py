from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .portfolio_integrity import canonical_sha256


PLANNER_DECISIONS = (
    "translate_with_context",
    "preserve_ffi_boundary",
    "refuse_with_reason",
)
STANDARD_ROLES = ("translator", "reviewer", "repairer")
BOUNDARY_ROLES = ("planner", *STANDARD_ROLES)


def boundary_required(group: Mapping[str, Any]) -> bool:
    if group.get("classification") == "boundary_required":
        return True
    if group.get("structural_status") == "boundary_required":
        return True
    eligibility = group.get("eligibility")
    return isinstance(eligibility, Mapping) and eligibility.get("status") == "boundary_required"


def roles_for_group(group: Mapping[str, Any]) -> tuple[str, ...]:
    return BOUNDARY_ROLES if boundary_required(group) else STANDARD_ROLES


def worker_descriptor(
    *, run_id: str, group_id: str, group_sha256: str, wave_index: int, slot: int,
    role: str, dependencies: list[str], context: Mapping[str, Any], out_root: str,
    byte_budget: int, token_budget: int, max_attempts: int, needs_planner: bool,
) -> dict[str, Any]:
    identity = hashlib.sha256(group_id.encode("utf-8")).hexdigest()[:10]
    worker_id = f"w{wave_index:03d}-{slot:03d}-{identity}-{role}"
    worker_root = f"{out_root}/workers/{worker_id}"
    roots = {
        name: f"{worker_root}/{name}"
        for name in ("config", "data", "state", "cache", "tmp", "out")
    }
    ledger_binding = {
        "run_id": run_id,
        "unit_id": group_id,
        "group_id": group_id,
        "role": role,
        "worker_id": worker_id,
        "lease_owner": worker_id,
        "isolated_out_root": roots["out"],
    }
    ledger_binding["binding_sha256"] = canonical_sha256(ledger_binding)
    result = {
        "worker_id": worker_id,
        "worker_identity": worker_id,
        "run_id": run_id,
        "role": role,
        "group_id": group_id,
        "unit_id": group_id,
        "slice_id": group_id,
        "wave_index": wave_index,
        "group_sha256": group_sha256,
        "dependencies": dependencies,
        "out_root": roots["out"],
        "isolated_out_root": roots["out"],
        "runtime_roots": roots,
        "assignment_path": f"{out_root}/harness/assignments/{worker_id}.json",
        "request_path": f"{out_root}/harness/assignments/{worker_id}-request.json",
        "ledger_binding": ledger_binding,
        "context": {
            **dict(context),
            "byte_budget": byte_budget,
            "token_budget": token_budget,
        },
        "max_attempts": max_attempts,
        "launch_policy": launch_policy(
            role,
            wave_index=wave_index,
            dependencies=dependencies,
            needs_planner=needs_planner,
        ),
        "authority": authority(role),
    }
    if role == "planner":
        result["planner_decision_contract"] = planner_decision_contract()
    return result


def launch_policy(
    role: str, *, wave_index: int, dependencies: list[str], needs_planner: bool,
) -> dict[str, Any]:
    dependency_requirements = [f"group_gate:{item}" for item in dependencies]
    if role == "planner":
        return {
            "state": "ready",
            "condition": "boundary_route_decision_required",
            "requires": [],
            "gate_triggered": False,
        }
    if role == "translator":
        requirements = list(dependency_requirements)
        if wave_index > 0:
            requirements.append(f"wave_gate:{wave_index - 1}")
        if needs_planner:
            requirements.append("planner_decision_sha256")
            return {
                "state": "deferred",
                "condition": "hash_bound_planner_decision_allows_translation",
                "requires": requirements,
                "gate_triggered": True,
                "planner_decision": {
                    "sha256_field": "planner_decision_sha256",
                    "decision_field": "decision",
                    "hash_algorithm": "sha256",
                    "canonicalization": "canonical_json_bytes",
                    "required_bindings": [
                        "run_id", "group_id", "group_sha256", "context_pack_sha256",
                    ],
                    "allowed_decisions": list(PLANNER_DECISIONS),
                    "translate_when": "translate_with_context",
                    "terminal_decisions": ["preserve_ffi_boundary", "refuse_with_reason"],
                },
            }
        ready = wave_index == 0 and not dependencies
        return {
            "state": "ready" if ready else "deferred",
            "condition": "wave_dependencies_gate_passed",
            "requires": requirements,
            "gate_triggered": not ready,
        }
    if role == "reviewer":
        return {
            "state": "deferred",
            "condition": "translator_candidate_recorded",
            "requires": ["candidate_artifact_sha256"],
            "gate_triggered": False,
        }
    if role == "repairer":
        return _repair_policy()
    raise ValueError(f"unsupported portfolio role: {role}")


def planner_decision_contract() -> dict[str, Any]:
    return {
        "artifact_kind": "planner-decision",
        "sha256_required": True,
        "hash_algorithm": "sha256",
        "canonicalization": "canonical_json_bytes",
        "hash_payload_fields": [
            "run_id", "group_id", "group_sha256", "context_pack_sha256", "decision",
        ],
        "allowed_decisions": list(PLANNER_DECISIONS),
        "decision_requirements": {
            "translate_with_context": ["context_pack_sha256"],
            "preserve_ffi_boundary": ["boundary_reason"],
            "refuse_with_reason": ["refusal_reason"],
        },
        "semantic_acceptance": False,
    }


def authority(role: str) -> dict[str, Any]:
    result = {
        "semantic_acceptance": False,
        "semantic_gate_owner": "external-verifier",
        "review_scope": "structural-and-diagnostic-only" if role == "reviewer" else "not-applicable",
    }
    if role == "planner":
        result.update({
            "planning_scope": "structural-route-only",
            "allowed_decisions": list(PLANNER_DECISIONS),
        })
    return result


def _repair_policy() -> dict[str, Any]:
    return {
        "state": "gate-deferred",
        "condition": "candidate_gate_failed",
        "requires": ["candidate_artifact_sha256", "failed_gate_result_sha256"],
        "gate_triggered": True,
        "repair_modes": [
            {
                "mode": "candidate_repair",
                "condition": "candidate_failed_before_last_good",
                "requires": ["candidate_artifact_sha256", "failed_gate_result_sha256"],
                "last_good_required": False,
            },
            {
                "mode": "post_last_good_regression_repair",
                "condition": "candidate_regressed_after_last_good",
                "requires": [
                    "candidate_artifact_sha256",
                    "failed_gate_result_sha256",
                    "last_good_artifact_id",
                    "last_good_artifact_sha256",
                ],
                "last_good_required": True,
            },
        ],
        "allowed_gate_families": [
            "compile", "link", "test", "oracle-replay-diff", "negative",
            "unsafe-alias", "abi-layout", "integration",
        ],
    }


__all__ = [
    "PLANNER_DECISIONS", "authority", "boundary_required", "launch_policy",
    "planner_decision_contract", "roles_for_group", "worker_descriptor",
]
