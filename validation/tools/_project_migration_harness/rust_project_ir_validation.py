from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import checked_relative_path, content_sha256

RUST_PROJECT_IR_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TOP_KEYS = {
    "schema_version", "kind", "bindings", "crate", "modules", "public_api",
    "shared_types", "global_ownership", "initialization", "ffi_boundaries",
    "cfgs", "features", "unsafe_obligations", "interface_sha256",
    "claim_boundary", "ir_sha256",
}
_FIELDS = {
    "modules": {
        "module_id", "parent_module_id", "rust_path", "unit_id",
        "candidate_sha256", "visibility", "evidence",
    },
    "public_api": {
        "declaration_id", "module_id", "symbol", "kind", "signature",
        "visibility", "evidence",
    },
    "shared_types": {
        "declaration_id", "module_id", "name", "kind", "layout_sha256",
        "repr", "evidence",
    },
    "global_ownership": {
        "declaration_id", "module_id", "symbol", "access", "evidence",
    },
    "initialization": {
        "init_id", "module_id", "function", "phase", "after", "evidence",
    },
    "ffi_boundaries": {
        "declaration_id", "module_id", "symbol", "direction", "abi",
        "link_name", "evidence",
    },
    "cfgs": {"cfg_id", "expression", "module_ids", "evidence"},
    "features": {
        "feature_id", "name", "default", "enables", "module_ids", "evidence",
    },
    "unsafe_obligations": {
        "obligation_id", "module_id", "kind", "reason_code", "source_span",
        "evidence",
    },
}
_ID_FIELDS = {
    "modules": "module_id", "public_api": "declaration_id",
    "shared_types": "declaration_id", "global_ownership": "declaration_id",
    "initialization": "init_id", "ffi_boundaries": "declaration_id",
    "cfgs": "cfg_id", "features": "feature_id",
    "unsafe_obligations": "obligation_id",
}


class RustProjectIRError(ValueError):
    pass
def module_id_for_candidate(candidate_sha256: str) -> str:
    _sha(candidate_sha256, "candidate_sha256")
    return f"module-{candidate_sha256[:24]}"
def validate_rust_project_ir(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        _fail("RustProjectIR top-level schema is invalid")
    if value.get("schema_version") != RUST_PROJECT_IR_SCHEMA_VERSION:
        _fail("RustProjectIR schema version is unsupported")
    if value.get("kind") != "rust-project-ir":
        _fail("RustProjectIR kind is invalid")
    candidates, build_digests = _bindings(value.get("bindings"))
    module_units = _sections(value, candidates, build_digests)
    _crate(value.get("crate"), candidates, build_digests)
    _cross_references(value, candidates, module_units)
    boundary = value.get("claim_boundary")
    if boundary != {
        "artifact_role": "rust-project-ir-candidate", "semantic_gate": False,
        "semantic_pass": False, "translation_coverage_numerator": 0,
    }:
        _fail("RustProjectIR claim boundary is invalid")
    interface_sha = _sha(value.get("interface_sha256"), "interface_sha256")
    if content_sha256(interface_projection(value)) != interface_sha:
        _fail("RustProjectIR interface hash drifted")
    stored = _sha(value.get("ir_sha256"), "ir_sha256")
    payload = {key: item for key, item in value.items() if key != "ir_sha256"}
    if content_sha256(payload) != stored:
        _fail("RustProjectIR content hash drifted")
def interface_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    crate = {
        key: item for key, item in value["crate"].items()
        if key not in {"crate_id", "evidence"}
    }
    sections = {}
    for name in _FIELDS:
        sections[name] = [
            {key: item for key, item in record.items() if key != "evidence"}
            for record in value[name]
        ]
    for module in sections["modules"]:
        module.pop("unit_id", None)
    return {"schema_version": 1, "crate": crate, **sections}
def reopen_rust_project_ir_bindings(
    value: Mapping[str, Any], artifact_root: Path,
) -> dict[str, Any]:
    from .rust_project_ir_bindings import reopen_rust_project_ir_bindings as reopen
    return reopen(value, artifact_root)
def _bindings(value: Any) -> tuple[dict[str, dict[str, Any]], set[str]]:
    if not isinstance(value, Mapping) or set(value) != {
        "migration_dag", "build_ir", "candidates",
    }:
        _fail("RustProjectIR bindings are invalid")
    _artifact_ref(value["migration_dag"])
    build_refs = value["build_ir"]
    candidate_refs = value["candidates"]
    if not isinstance(build_refs, list) or not build_refs:
        _fail("RustProjectIR requires BuildIR references")
    for reference in build_refs:
        _artifact_ref(reference)
    if build_refs != sorted(build_refs, key=lambda item: (item["path"], item["sha256"])):
        _fail("BuildIR references are not canonical")
    if not isinstance(candidate_refs, list) or not candidate_refs:
        _fail("RustProjectIR requires candidate references")
    candidates: dict[str, dict[str, Any]] = {}
    for candidate in candidate_refs:
        if not isinstance(candidate, Mapping) or set(candidate) != {
            "unit_id", "artifact_id", "source",
        }:
            _fail("candidate reference schema is invalid")
        unit_id = _text(candidate.get("unit_id"), "candidate unit_id")
        _text(candidate.get("artifact_id"), "candidate artifact_id")
        _artifact_ref(candidate.get("source"))
        if unit_id in candidates:
            _fail("candidate units must be unique")
        candidates[unit_id] = dict(candidate)
    expected = sorted(candidate_refs, key=lambda item: (item["unit_id"], item["artifact_id"]))
    if candidate_refs != expected:
        _fail("candidate references are not canonical")
    return candidates, {reference["sha256"] for reference in build_refs}
def _sections(
    value: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]],
    build_digests: set[str],
) -> dict[str, str]:
    module_units: dict[str, str] = {}
    for section, fields in _FIELDS.items():
        records = value.get(section)
        if not isinstance(records, list):
            _fail(f"RustProjectIR {section} must be an array")
        id_field = _ID_FIELDS[section]
        seen: set[str] = set()
        for record in records:
            if not isinstance(record, Mapping) or set(record) != fields:
                _fail(f"RustProjectIR {section} entry schema is invalid")
            identity = _text(record.get(id_field), f"{section} identity")
            if identity in seen:
                _fail(f"RustProjectIR {section} identities must be unique")
            seen.add(identity)
            _record_shape(section, record)
            _evidence(record.get("evidence"), candidates, build_digests)
            if section == "modules":
                _module(record, candidates)
                module_units[identity] = str(record["unit_id"])
        if records != sorted(records, key=lambda item: item[id_field]):
            _fail(f"RustProjectIR {section} is not canonical")
    return module_units
def _record_shape(section: str, record: Mapping[str, Any]) -> None:
    for key, item in record.items():
        if key in {"evidence", "parent_module_id", "source_span", "default"}:
            continue
        if key in {"after", "enables", "module_ids"}:
            _string_list(item, f"{section}.{key}")
        elif key.endswith("sha256"):
            _sha(item, f"{section}.{key}")
        else:
            _text(item, f"{section}.{key}")
    if section == "features" and not isinstance(record.get("default"), bool):
        _fail("feature default must be boolean")
    if section == "modules":
        parent = record.get("parent_module_id")
        if parent is not None:
            _text(parent, "module parent_module_id")
        checked_relative_path(record.get("rust_path"))
    if section == "unsafe_obligations":
        _source_span(record.get("source_span"))
def _module(record: Mapping[str, Any], candidates: Mapping[str, Mapping[str, Any]]) -> None:
    unit_id = str(record["unit_id"])
    candidate = candidates.get(unit_id)
    if candidate is None or candidate["source"]["sha256"] != record["candidate_sha256"]:
        _fail("module does not bind its candidate source")
    if record["module_id"] != module_id_for_candidate(str(record["candidate_sha256"])):
        _fail("module identity is not candidate-content-derived")
def _crate(value: Any, candidates: Mapping[str, Any], build_digests: set[str]) -> None:
    fields = {"crate_id", "edition", "crate_types", "root_module_id", "targets", "evidence"}
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("RustProjectIR crate schema is invalid")
    for field in ("crate_id", "edition", "root_module_id"):
        _text(value.get(field), f"crate.{field}")
    _string_list(value.get("crate_types"), "crate.crate_types", nonempty=True)
    _string_list(value.get("targets"), "crate.targets", nonempty=True)
    _evidence(value.get("evidence"), candidates, build_digests)
def _cross_references(
    value: Mapping[str, Any], candidates: Mapping[str, Any], module_units: Mapping[str, str],
) -> None:
    for section in _FIELDS:
        for record in value[section]:
            evidence = record["evidence"]
            if not set(evidence["dag_unit_ids"]) <= set(candidates):
                _fail("declaration evidence references an unknown DAG unit")
            owner_ids = record.get("module_ids", [record.get("module_id")])
            for module_id in owner_ids:
                if module_id not in module_units:
                    continue
                unit_id = module_units[str(module_id)]
                candidate_sha = candidates[unit_id]["source"]["sha256"]
                if unit_id not in evidence["dag_unit_ids"] or candidate_sha not in evidence["candidate_sha256s"]:
                    _fail("declaration evidence does not bind its owning module")
def _evidence(value: Any, candidates: Mapping[str, Any], build_digests: set[str]) -> None:
    fields = {"build_ir_sha256s", "dag_unit_ids", "candidate_sha256s"}
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("declaration evidence schema is invalid")
    for field in fields:
        _string_list(value.get(field), f"evidence.{field}", nonempty=True)
    if not set(value["build_ir_sha256s"]) <= build_digests:
        _fail("declaration evidence references an unknown BuildIR")
    known_candidates = {item["source"]["sha256"] for item in candidates.values()}
    if not set(value["candidate_sha256s"]) <= known_candidates:
        _fail("declaration evidence references an unknown candidate")
def _artifact_ref(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}:
        _fail("artifact reference schema is invalid")
    checked_relative_path(value.get("path"))
    _sha(value.get("sha256"), "artifact sha256")
    size = value.get("size_bytes")
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        _fail("artifact size is invalid")
def _source_span(value: Any) -> None:
    if value is None:
        return
    fields = {"path", "start_line", "start_column", "end_line", "end_column"}
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("unsafe obligation source span is invalid")
    checked_relative_path(value.get("path"))
    numbers = [value[field] for field in fields if field != "path"]
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in numbers):
        _fail("unsafe obligation source span is invalid")
def _string_list(value: Any, label: str, *, nonempty: bool = False) -> None:
    if not isinstance(value, list) or (nonempty and not value):
        _fail(f"{label} must be a canonical string array")
    if any(not isinstance(item, str) or not item for item in value):
        _fail(f"{label} must be a canonical string array")
    if value != sorted(set(value)):
        _fail(f"{label} must be a canonical string array")
def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1_024 or any(ord(char) < 32 for char in value):
        _fail(f"{label} must be bounded text")
    return value
def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _fail(f"{label} is invalid")
    return value
def _fail(message: str) -> None:
    raise RustProjectIRError(message)
__all__ = [
    "RUST_PROJECT_IR_SCHEMA_VERSION", "RustProjectIRError",
    "interface_projection", "module_id_for_candidate", "reopen_rust_project_ir_bindings",
    "validate_rust_project_ir",
]
