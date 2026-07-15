from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .rust_project_ir import CLAIM_BOUNDARY
from .rust_project_ir_native import host_interface_completeness
from .rust_project_ir_v3_validation import (
    RUST_PROJECT_IR_V3_SCHEMA_VERSION,
    interface_projection_v3,
    validate_rust_project_ir_v3,
)


_SECTIONS = {
    "public_api": "declaration_id",
    "shared_types": "declaration_id",
    "global_ownership": "declaration_id",
    "initialization": "init_id",
    "ffi_boundaries": "declaration_id",
    "cfgs": "cfg_id",
    "features": "feature_id",
    "unsafe_obligations": "obligation_id",
}


def build_rust_project_ir_v3(
    *,
    migration_dag_ref: Mapping[str, Any],
    migration_graph_ref: Mapping[str, Any],
    build_ir_refs: Sequence[Mapping[str, Any]],
    candidate_refs: Sequence[Mapping[str, Any]],
    workspace: Mapping[str, Any],
    packages: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
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
    topology_blockers: Sequence[Mapping[str, Any]] = (),
    c_compilation_facts_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical v3 topology without granting semantic acceptance."""
    raw_sections = {
        "public_api": public_api,
        "shared_types": shared_types,
        "global_ownership": global_ownership,
        "initialization": initialization,
        "ffi_boundaries": ffi_boundaries,
        "cfgs": cfgs,
        "features": features,
        "unsafe_obligations": unsafe_obligations,
    }
    sections = {
        name: _records(raw_sections[name], identity)
        for name, identity in _SECTIONS.items()
    }
    blockers = sorted(
        (_clone(item) for item in topology_blockers),
        key=lambda item: (
            str(item.get("code")), str(item.get("entity_kind")),
            str(item.get("entity_id")),
        ),
    )
    payload = {
        "schema_version": RUST_PROJECT_IR_V3_SCHEMA_VERSION,
        "kind": "rust-project-ir",
        "bindings": {
            "migration_dag": _clone(migration_dag_ref),
            "migration_graph": _clone(migration_graph_ref),
            "build_ir": sorted(
                (_clone(item) for item in build_ir_refs),
                key=lambda item: (str(item.get("path")), str(item.get("sha256"))),
            ),
            "c_compilation_facts": (
                None if c_compilation_facts_ref is None
                else _clone(c_compilation_facts_ref)
            ),
            "candidates": sorted(
                (_clone(item) for item in candidate_refs),
                key=lambda item: (
                    str(item.get("unit_id")), str(item.get("artifact_id")),
                ),
            ),
        },
        "workspace": _workspace(workspace),
        "packages": _packages(packages),
        "targets": _targets(targets),
        "modules": _modules(modules),
        "native_link_requirements": sorted(
            (_clone(item) for item in native_link_requirements),
            key=lambda item: str(item.get("requirement_id")),
        ),
        "native_link_plans": sorted(
            (_clone(item) for item in native_link_plans),
            key=lambda item: str(item.get("requirement_id")),
        ),
        **sections,
        "topology_status": "blocked" if blockers else "ready",
        "topology_blockers": blockers,
    }
    payload["interface_completeness"] = _clone(
        interface_completeness
        if interface_completeness is not None
        else host_interface_completeness(payload["native_link_requirements"])
    )
    payload["interface_sha256"] = content_sha256(interface_projection_v3(payload))
    payload["claim_boundary"] = dict(CLAIM_BOUNDARY)
    payload["ir_sha256"] = content_sha256(payload)
    validate_rust_project_ir_v3(payload)
    return payload


def canonical_rust_project_ir_v3_bytes(value: Mapping[str, Any]) -> bytes:
    validate_rust_project_ir_v3(value)
    return canonical_json_bytes(value)


def _workspace(value: Mapping[str, Any]) -> dict[str, Any]:
    result = _clone(value)
    for name in ("package_ids", "default_package_ids"):
        if isinstance(result.get(name), list):
            result[name] = sorted(result[name])
    _normalize_evidence(result)
    return result


def _packages(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [_clone(item) for item in values]
    for record in records:
        for name in ("dependency_package_ids", "target_ids", "module_ids"):
            if isinstance(record.get(name), list):
                record[name] = sorted(record[name])
        _normalize_evidence(record)
    return sorted(records, key=lambda item: str(item.get("package_id")))


def _targets(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [_clone(item) for item in values]
    for record in records:
        for name in ("crate_types", "module_ids"):
            if isinstance(record.get(name), list):
                record[name] = sorted(record[name])
        _normalize_evidence(record)
    return sorted(records, key=lambda item: str(item.get("target_id")))


def _modules(values: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = [_clone(item) for item in values]
    for record in records:
        if isinstance(record.get("source_unit_ids"), list):
            record["source_unit_ids"] = sorted(record["source_unit_ids"])
        _normalize_evidence(record)
    return sorted(records, key=lambda item: str(item.get("module_id")))


def _records(
    values: Sequence[Mapping[str, Any]], identity: str,
) -> list[dict[str, Any]]:
    records = [_clone(item) for item in values]
    for record in records:
        for name in ("after", "enables", "module_ids"):
            if isinstance(record.get(name), list):
                record[name] = sorted(record[name])
        _normalize_evidence(record)
    return sorted(records, key=lambda item: str(item.get(identity)))


def _normalize_evidence(value: dict[str, Any]) -> None:
    evidence = value.get("evidence")
    if not isinstance(evidence, dict):
        return
    for name in ("build_ir_sha256s", "dag_unit_ids", "candidate_sha256s"):
        if isinstance(evidence.get(name), list):
            evidence[name] = sorted(evidence[name])


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=True))


__all__ = [
    "build_rust_project_ir_v3", "canonical_rust_project_ir_v3_bytes",
]
