from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes
from .build_ir import is_sha256
from .native_link_context import (
    native_link_requirements, validate_native_link_requirements,
)
from .native_link_model import validate_native_link_proposal


_BASE_VERIFIED_SECTIONS = [
    "candidate-module-binding", "ffi-boundary-name",
    "public-symbol-name", "unsafe-token-count",
]
_BASE_UNRESOLVED_SECTIONS = [
    "cfg-feature-extraction", "global-ownership",
    "initialization-destruction", "nested-module-multi-target",
    "public-signature", "shared-type-layout", "target-matrix",
]
DERIVED_INTERFACE_PRODUCER = "host-bound-rust-interface-topology-v3"
_CONSERVATIVE_INTERFACE_PRODUCER = "host-rust-source-and-build-facts-v2"
INTERFACE_SECTIONS = frozenset(
    _BASE_VERIFIED_SECTIONS + _BASE_UNRESOLVED_SECTIONS + ["native-link-config"]
)
_PLAN_KEYS = {
    "requirement_id", "strategy", "rustc_link_name", "rustc_link_kind",
    "candidate_sha256",
}


def host_interface_completeness(
    requirements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    unresolved = list(_BASE_UNRESOLVED_SECTIONS)
    verified = list(_BASE_VERIFIED_SECTIONS)
    if requirements:
        unresolved.append("native-link-config")
    else:
        verified.append("native-link-config")
    return {
        "status": "partial" if unresolved else "complete",
        "producer": _CONSERVATIVE_INTERFACE_PRODUCER,
        "verified_sections": sorted(verified),
        "unresolved_sections": sorted(unresolved),
        "semantic_gate": False,
    }


HOST_INTERFACE_COMPLETENESS = host_interface_completeness(())


def derived_interface_completeness(
    unresolved_sections: Sequence[str],
    requirements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    unresolved = set(unresolved_sections)
    if not unresolved <= INTERFACE_SECTIONS:
        raise ValueError("RustProjectIR interface section is unknown")
    if requirements:
        unresolved.add("native-link-config")
    else:
        unresolved.discard("native-link-config")
    return {
        "status": "partial" if unresolved else "complete",
        "producer": DERIVED_INTERFACE_PRODUCER,
        "verified_sections": sorted(INTERFACE_SECTIONS - unresolved),
        "unresolved_sections": sorted(unresolved),
        "semantic_gate": False,
    }


def refresh_native_link_completeness(
    completeness: Mapping[str, Any],
    requirements: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if completeness.get("producer") == DERIVED_INTERFACE_PRODUCER:
        unresolved = completeness.get("unresolved_sections")
        if not isinstance(unresolved, list):
            raise ValueError("RustProjectIR interface completeness boundary is invalid")
        return derived_interface_completeness(unresolved, requirements)
    return host_interface_completeness(requirements)


def validate_native_link_sections(value: Mapping[str, Any]) -> None:
    requirements = validate_native_link_requirements(
        value.get("native_link_requirements"),
    )
    plans = value.get("native_link_plans")
    if not isinstance(plans, list):
        raise ValueError("rust_project_ir_native_link_plans_invalid")
    normalized = [_validate_plan(item) for item in plans]
    if normalized != plans or plans != sorted(
        plans, key=lambda item: item["requirement_id"],
    ):
        raise ValueError("rust_project_ir_native_link_plans_noncanonical")
    plan_ids = [item["requirement_id"] for item in plans]
    if len(plan_ids) != len(set(plan_ids)):
        raise ValueError("rust_project_ir_native_link_plan_duplicate")
    requirement_ids = {item["requirement_id"] for item in requirements}
    if plans and set(plan_ids) != requirement_ids:
        raise ValueError("rust_project_ir_native_link_plan_coverage_invalid")
    if plans and len({item["candidate_sha256"] for item in plans}) != 1:
        raise ValueError("rust_project_ir_native_link_candidate_cohort_invalid")
    _validate_interface_completeness(value.get("interface_completeness"), requirements)


def _validate_interface_completeness(
    value: Any, requirements: Sequence[Mapping[str, Any]],
) -> None:
    if not isinstance(value, Mapping) or set(value) != {
        "status", "producer", "verified_sections", "unresolved_sections",
        "semantic_gate",
    }:
        raise ValueError("RustProjectIR interface completeness boundary is invalid")
    verified = value.get("verified_sections")
    unresolved = value.get("unresolved_sections")
    if (
        not _canonical_sections(verified)
        or not _canonical_sections(unresolved)
        or set(verified) & set(unresolved)
        or set(verified) | set(unresolved) != INTERFACE_SECTIONS
        or value.get("semantic_gate") is not False
        or value.get("status") != ("partial" if unresolved else "complete")
    ):
        raise ValueError("RustProjectIR interface completeness boundary is invalid")
    native_unresolved = "native-link-config" in unresolved
    if native_unresolved is not bool(requirements):
        raise ValueError("RustProjectIR interface completeness boundary is invalid")
    producer = value.get("producer")
    if producer == _CONSERVATIVE_INTERFACE_PRODUCER:
        if dict(value) != host_interface_completeness(requirements):
            raise ValueError("RustProjectIR interface completeness boundary is invalid")
    elif producer != DERIVED_INTERFACE_PRODUCER:
        raise ValueError("RustProjectIR interface completeness boundary is invalid")


def _canonical_sections(value: Any) -> bool:
    return (
        isinstance(value, list)
        and all(isinstance(item, str) and item in INTERFACE_SECTIONS for item in value)
        and value == sorted(set(value))
    )


def native_link_interface_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "native_link_requirements": [
            dict(item) for item in value["native_link_requirements"]
        ],
        "native_link_plans": [dict(item) for item in value["native_link_plans"]],
    }


def validate_bound_native_link_requirements(
    value: Mapping[str, Any], build_irs: Sequence[Mapping[str, Any]],
) -> None:
    expected = native_link_requirements(build_irs)
    if canonical_json_bytes(value["native_link_requirements"]) != canonical_json_bytes(
        expected
    ):
        raise ValueError("RustProjectIR native-link requirements drifted from BuildIR")


def plans_from_candidate(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    candidate_sha256 = candidate.get("candidate_sha256")
    if not is_sha256(candidate_sha256):
        raise ValueError("native_link_candidate_sha256_invalid")
    return [{
        **validate_native_link_proposal(item),
        "candidate_sha256": candidate_sha256,
    } for item in candidate["proposals"]]


def _validate_plan(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_KEYS:
        raise ValueError("rust_project_ir_native_link_plan_schema_invalid")
    result = dict(value)
    validate_native_link_proposal({
        key: result[key] for key in (
            "requirement_id", "strategy", "rustc_link_name", "rustc_link_kind",
        )
    })
    if not is_sha256(result.get("candidate_sha256")):
        raise ValueError("rust_project_ir_native_link_candidate_sha256_invalid")
    return result


__all__ = [
    "DERIVED_INTERFACE_PRODUCER", "HOST_INTERFACE_COMPLETENESS",
    "INTERFACE_SECTIONS", "derived_interface_completeness",
    "host_interface_completeness",
    "native_link_interface_projection", "plans_from_candidate",
    "refresh_native_link_completeness",
    "validate_bound_native_link_requirements", "validate_native_link_sections",
]
