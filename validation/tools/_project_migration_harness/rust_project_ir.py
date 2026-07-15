from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .rust_project_ir_validation import (
    RUST_PROJECT_IR_SCHEMA_VERSION,
    interface_projection,
    validate_rust_project_ir,
)
from .rust_project_ir_native import (
    host_interface_completeness, plans_from_candidate,
    refresh_native_link_completeness,
)
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate


CLAIM_BOUNDARY = {
    "artifact_role": "rust-project-ir-candidate",
    "semantic_gate": False,
    "semantic_pass": False,
    "translation_coverage_numerator": 0,
}
_SECTIONS = {
    "modules": "module_id",
    "public_api": "declaration_id",
    "shared_types": "declaration_id",
    "global_ownership": "declaration_id",
    "initialization": "init_id",
    "ffi_boundaries": "declaration_id",
    "cfgs": "cfg_id",
    "features": "feature_id",
    "unsafe_obligations": "obligation_id",
}


def build_rust_project_ir(
    *,
    migration_dag_ref: Mapping[str, Any],
    build_ir_refs: Sequence[Mapping[str, Any]],
    candidate_refs: Sequence[Mapping[str, Any]],
    crate: Mapping[str, Any],
    modules: Sequence[Mapping[str, Any]],
    public_api: Sequence[Mapping[str, Any]] = (),
    shared_types: Sequence[Mapping[str, Any]] = (),
    global_ownership: Sequence[Mapping[str, Any]] = (),
    initialization: Sequence[Mapping[str, Any]] = (),
    ffi_boundaries: Sequence[Mapping[str, Any]] = (),
    cfgs: Sequence[Mapping[str, Any]] = (),
    features: Sequence[Mapping[str, Any]] = (),
    unsafe_obligations: Sequence[Mapping[str, Any]] = (),
    native_link_requirements: Sequence[Mapping[str, Any]] = (),
    native_link_plans: Sequence[Mapping[str, Any]] = (),
    interface_completeness: Mapping[str, Any] | None = None,
    c_compilation_facts_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic candidate IR; this never grants semantic acceptance."""
    raw_sections = {
        "modules": modules,
        "public_api": public_api,
        "shared_types": shared_types,
        "global_ownership": global_ownership,
        "initialization": initialization,
        "ffi_boundaries": ffi_boundaries,
        "cfgs": cfgs,
        "features": features,
        "unsafe_obligations": unsafe_obligations,
    }
    normalized = {
        name: _normalized_records(values, key)
        for name, key in _SECTIONS.items()
        for values in (raw_sections[name],)
    }
    payload = {
        "schema_version": RUST_PROJECT_IR_SCHEMA_VERSION,
        "kind": "rust-project-ir",
        "bindings": {
            "migration_dag": _clone(migration_dag_ref),
            "build_ir": sorted(
                (_clone(value) for value in build_ir_refs),
                key=lambda value: (str(value.get("path")), str(value.get("sha256"))),
            ),
            "c_compilation_facts": (
                None
                if c_compilation_facts_ref is None
                else _clone(c_compilation_facts_ref)
            ),
            "candidates": sorted(
                (_normalized_candidate(value) for value in candidate_refs),
                key=lambda value: (
                    str(value.get("unit_id")), str(value.get("artifact_id")),
                ),
            ),
        },
        "crate": _normalized_crate(crate),
        "native_link_requirements": sorted(
            (_clone(value) for value in native_link_requirements),
            key=lambda value: str(value.get("requirement_id")),
        ),
        "native_link_plans": sorted(
            (_clone(value) for value in native_link_plans),
            key=lambda value: str(value.get("requirement_id")),
        ),
        **normalized,
    }
    payload["interface_completeness"] = _clone(
        interface_completeness
        if interface_completeness is not None
        else host_interface_completeness(payload["native_link_requirements"])
    )
    payload["interface_sha256"] = content_sha256(interface_projection(payload))
    payload["claim_boundary"] = dict(CLAIM_BOUNDARY)
    payload["ir_sha256"] = content_sha256(payload)
    validate_rust_project_ir(payload)
    return payload


def canonical_rust_project_ir_bytes(value: Mapping[str, Any]) -> bytes:
    validate_rust_project_ir(value)
    return canonical_json_bytes(value)


def rust_project_interface_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    validate_rust_project_ir(value)
    return _clone(interface_projection(value))


def bind_native_link_candidate(
    value: Mapping[str, Any], context: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Bind candidate-only native plans without granting resolution authority."""
    validate_rust_project_ir(value)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    build_reference = context["build_ir_binding"]["artifact"]
    if build_reference not in value["bindings"]["build_ir"]:
        raise ValueError("native_link_context_build_ir_binding_mismatch")
    if canonical_json_bytes(value["native_link_requirements"]) != canonical_json_bytes(
        context["requirements"]
    ):
        raise ValueError("native_link_context_requirement_mismatch")
    result = _clone(value)
    result["native_link_plans"] = plans_from_candidate(candidate)
    result["interface_completeness"] = refresh_native_link_completeness(
        result["interface_completeness"], result["native_link_requirements"],
    )
    result["interface_sha256"] = content_sha256(interface_projection(result))
    result["ir_sha256"] = content_sha256({
        key: item for key, item in result.items() if key != "ir_sha256"
    })
    validate_rust_project_ir(result)
    return result


def _normalized_records(values: Sequence[Mapping[str, Any]], key: str) -> list[dict[str, Any]]:
    records = [_clone(value) for value in values]
    for record in records:
        if isinstance(record.get("evidence"), dict):
            record["evidence"] = _normalized_evidence(record["evidence"])
        for field in ("after", "enables", "module_ids"):
            if isinstance(record.get(field), list):
                record[field] = sorted(record[field])
    return sorted(records, key=lambda value: str(value.get(key)))


def _normalized_candidate(value: Mapping[str, Any]) -> dict[str, Any]:
    return _clone(value)


def _normalized_crate(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _clone(value)
    for field in ("crate_types", "targets"):
        if isinstance(result.get(field), list):
            result[field] = sorted(result[field])
    if isinstance(result.get("evidence"), dict):
        result["evidence"] = _normalized_evidence(result["evidence"])
    return result


def _normalized_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _clone(value)
    for field in ("build_ir_sha256s", "dag_unit_ids", "candidate_sha256s"):
        if isinstance(result.get(field), list):
            result[field] = sorted(result[field])
    return result


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


__all__ = [
    "CLAIM_BOUNDARY",
    "RUST_PROJECT_IR_SCHEMA_VERSION",
    "bind_native_link_candidate",
    "build_rust_project_ir",
    "canonical_rust_project_ir_bytes",
    "rust_project_interface_projection",
]
