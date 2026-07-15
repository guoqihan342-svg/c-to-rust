from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_native import (
    native_link_interface_projection, validate_native_link_sections,
)
from .rust_project_ir_v3_validation_sections import (
    module_id_for_target_candidate, validate_v3_sections,
)
from .rust_project_ir_validation import (
    RustProjectIRError as RustProjectIRV3Error,
    _artifact_ref, _sha, _text,
)

RUST_PROJECT_IR_V3_SCHEMA_VERSION = 3
_TOP_KEYS = {
    "schema_version", "kind", "bindings", "workspace", "packages", "targets",
    "modules", "public_api", "shared_types", "global_ownership", "initialization",
    "ffi_boundaries", "cfgs", "features", "unsafe_obligations",
    "native_link_requirements", "native_link_plans", "interface_completeness",
    "topology_status", "topology_blockers", "interface_sha256", "claim_boundary",
    "ir_sha256",
}
_BINDING_KEYS = {
    "migration_dag", "migration_graph", "build_ir", "c_compilation_facts", "candidates",
}
_SECTION_NAMES = (
    "public_api", "shared_types", "global_ownership", "initialization",
    "ffi_boundaries", "cfgs", "features", "unsafe_obligations",
)
_CLAIM_BOUNDARY = {
    "artifact_role": "rust-project-ir-candidate", "semantic_gate": False,
    "semantic_pass": False, "translation_coverage_numerator": 0,
}


def interface_projection_v3(value: Mapping[str, Any]) -> dict[str, Any]:
    def records(name: str) -> list[dict[str, Any]]:
        return [{key: item for key, item in record.items() if key != "evidence"}
                for record in value[name]]
    return {
        "schema_version": RUST_PROJECT_IR_V3_SCHEMA_VERSION,
        "workspace": {key: item for key, item in value["workspace"].items()
                      if key != "evidence"},
        "packages": records("packages"), "targets": records("targets"),
        "modules": records("modules"),
        **{name: records(name) for name in _SECTION_NAMES},
        **native_link_interface_projection(value),
        "interface_completeness": dict(value["interface_completeness"]),
        "topology_status": value["topology_status"],
        "topology_blockers": [dict(item) for item in value["topology_blockers"]],
    }


def validate_rust_project_ir_v3(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        _fail("RustProjectIR v3 top-level schema is invalid")
    if value.get("schema_version") != RUST_PROJECT_IR_V3_SCHEMA_VERSION:
        _fail("RustProjectIR v3 schema version is unsupported")
    if value.get("kind") != "rust-project-ir":
        _fail("RustProjectIR v3 kind is invalid")
    candidates, builds = _bindings(value.get("bindings"))
    validate_v3_sections(value, candidates, builds)
    try:
        validate_native_link_sections(value)
    except ValueError as error:
        _fail(str(error))
    if value.get("claim_boundary") != _CLAIM_BOUNDARY:
        _fail("RustProjectIR v3 claim boundary is invalid")
    if content_sha256(interface_projection_v3(value)) != _sha(
        value.get("interface_sha256"), "interface_sha256",
    ):
        _fail("RustProjectIR v3 interface hash drifted")
    payload = {key: item for key, item in value.items() if key != "ir_sha256"}
    if content_sha256(payload) != _sha(value.get("ir_sha256"), "ir_sha256"):
        _fail("RustProjectIR v3 content hash drifted")


def _bindings(value: Any) -> tuple[dict[str, Mapping[str, Any]], set[str]]:
    if not isinstance(value, Mapping) or set(value) != _BINDING_KEYS:
        _fail("RustProjectIR v3 bindings are invalid")
    _artifact_ref(value["migration_dag"])
    _artifact_ref(value["migration_graph"])
    if value["c_compilation_facts"] is not None:
        _artifact_ref(value["c_compilation_facts"])
    builds = value["build_ir"]
    if not isinstance(builds, list) or not builds:
        _fail("RustProjectIR v3 requires BuildIR references")
    for reference in builds:
        _artifact_ref(reference)
    build_keys = [(item["path"], item["sha256"]) for item in builds]
    if (
        build_keys != sorted(set(build_keys))
        or len({path for path, _ in build_keys}) != len(builds)
        or len({sha for _, sha in build_keys}) != len(builds)
    ):
        _fail("RustProjectIR v3 BuildIR references are not canonical")
    raw_candidates = value["candidates"]
    if not isinstance(raw_candidates, list) or not raw_candidates:
        _fail("RustProjectIR v3 requires candidate references")
    candidates: dict[str, Mapping[str, Any]] = {}
    for candidate in raw_candidates:
        if not isinstance(candidate, Mapping) or set(candidate) != {
            "unit_id", "artifact_id", "source",
        }:
            _fail("RustProjectIR v3 candidate reference schema is invalid")
        unit_id = _text(candidate.get("unit_id"), "candidate unit_id")
        _text(candidate.get("artifact_id"), "candidate artifact_id")
        _artifact_ref(candidate.get("source"))
        if unit_id in candidates:
            _fail("RustProjectIR v3 candidate unit_ids must be unique")
        candidates[unit_id] = candidate
    expected = sorted(raw_candidates, key=lambda item: (item["unit_id"], item["artifact_id"]))
    if raw_candidates != expected:
        _fail("RustProjectIR v3 candidate references are not canonical")
    return candidates, {item["sha256"] for item in builds}


def _fail(message: str) -> None:
    raise RustProjectIRV3Error(message)


__all__ = [
    "RUST_PROJECT_IR_V3_SCHEMA_VERSION", "module_id_for_target_candidate",
    "interface_projection_v3", "validate_rust_project_ir_v3",
]
