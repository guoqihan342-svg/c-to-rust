from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .portfolio_integrity import canonical_sha256


CANDIDATE_ONLY_SCOPE = "candidate-only"
SEMANTIC_ELIGIBLE_SCOPE = "semantic-eligible"
GENERATED_CLOSURE_REQUIREMENT = "generated_build_closure_verified"
ADMISSION_FIELDS = frozenset({
    "admission_scope", "admission_binding_sha256",
    "quarantine_required", "promotion_requires",
})
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def admission_evidence(
    *, build_ir: Mapping[str, Any], generated_build_closure: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = {
        "build_ir": dict(build_ir),
        "generated_build_closure": dict(generated_build_closure),
    }
    _admission_scope(evidence)
    return evidence


def candidate_admission_from_evidence(
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = admission_evidence(
        build_ir=_mapping(evidence, "build_ir"),
        generated_build_closure=_mapping(evidence, "generated_build_closure"),
    )
    scope = _admission_scope(normalized)
    binding = {
        "schema_version": 1,
        "admission_scope": scope,
        **normalized,
    }
    return {
        "admission_scope": scope,
        "admission_binding_sha256": content_sha256(binding),
        "quarantine_required": True,
        "promotion_requires": (
            [GENERATED_CLOSURE_REQUIREMENT]
            if scope == CANDIDATE_ONLY_SCOPE else []
        ),
    }


def candidate_admission_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    return candidate_admission_from_evidence({
        "build_ir": _mapping(manifest, "build_ir"),
        "generated_build_closure": _mapping(
            manifest, "generated_build_closure",
        ),
    })


def candidate_admission_metadata(
    value: Any, *, required: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        if value is None and not required:
            return {}
        raise ValueError("candidate admission policy must be an object")
    present = ADMISSION_FIELDS.intersection(value)
    if not present and not required:
        return {}
    if present != ADMISSION_FIELDS:
        raise ValueError("candidate admission policy is incomplete")
    scope = value.get("admission_scope")
    digest = value.get("admission_binding_sha256")
    expected_requires = (
        [GENERATED_CLOSURE_REQUIREMENT]
        if scope == CANDIDATE_ONLY_SCOPE else []
    )
    if (
        scope not in {CANDIDATE_ONLY_SCOPE, SEMANTIC_ELIGIBLE_SCOPE}
        or not isinstance(digest, str) or SHA256.fullmatch(digest) is None
        or value.get("quarantine_required") is not True
        or value.get("promotion_requires") != expected_requires
    ):
        raise ValueError("candidate admission policy is invalid")
    return {key: value[key] for key in sorted(ADMISSION_FIELDS)}


def apply_candidate_admission(
    portfolio: dict[str, Any], evidence: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_evidence = admission_evidence(
        build_ir=_mapping(evidence, "build_ir"),
        generated_build_closure=_mapping(
            evidence, "generated_build_closure",
        ),
    )
    admission = candidate_admission_from_evidence(normalized_evidence)
    for assignment in portfolio.get("assignments", []):
        if not isinstance(assignment, dict):
            continue
        policy = assignment.get("launch_policy")
        if isinstance(policy, dict):
            policy.update(admission)
    execution = portfolio.get("execution")
    if isinstance(execution, dict):
        execution.update({
            "build_closure_admission": admission["admission_scope"],
            "candidate_generation_allowed": True,
            "promotion_allowed": (
                admission["admission_scope"] == SEMANTIC_ELIGIBLE_SCOPE
            ),
            "admission_binding": {
                "schema_version": 1,
                **normalized_evidence,
                **admission,
            },
        })
    payload = {key: value for key, value in portfolio.items() if key != "plan_sha256"}
    portfolio["plan_sha256"] = canonical_sha256(payload)
    return portfolio


def _admission_scope(evidence: Mapping[str, Any]) -> str:
    build_ir = _mapping(evidence, "build_ir")
    closure = _mapping(evidence, "generated_build_closure")
    if set(build_ir) != {"status", "artifact", "verification", "worker_admission"}:
        raise ValueError("candidate admission BuildIR evidence is invalid")
    if set(closure) != {"status", "closure", "verification"}:
        raise ValueError("candidate admission closure evidence is invalid")
    for reference in (
        build_ir["artifact"], build_ir["verification"],
        build_ir["worker_admission"], closure["closure"], closure["verification"],
    ):
        if not isinstance(reference, Mapping) or set(reference) != {
            "path", "sha256", "size_bytes",
        }:
            raise ValueError("candidate admission artifact reference is invalid")
    if build_ir.get("status") != "bound":
        raise ValueError("candidate admission requires verified BuildIR")
    if closure.get("status") == "bound":
        return SEMANTIC_ELIGIBLE_SCOPE
    if closure.get("status") == "blocked":
        return CANDIDATE_ONLY_SCOPE
    raise ValueError("candidate admission closure status is invalid")


def _mapping(value: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    item = value.get(key)
    if not isinstance(item, Mapping):
        raise ValueError(f"candidate admission {key} evidence is invalid")
    return item


__all__ = [
    "CANDIDATE_ONLY_SCOPE", "SEMANTIC_ELIGIBLE_SCOPE",
    "admission_evidence", "apply_candidate_admission",
    "candidate_admission_from_evidence", "candidate_admission_from_manifest",
    "candidate_admission_metadata",
]
