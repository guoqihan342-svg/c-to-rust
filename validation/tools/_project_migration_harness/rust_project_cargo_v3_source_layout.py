from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .rust_project_cargo_v3_source_scan import scan_source_unit
from .rust_project_ir_source_lexer import identifier
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


RUST_PROJECT_CARGO_V3_SOURCE_LAYOUT_SCHEMA_VERSION = 1
_TOP_KEYS = {
    "schema_version", "artifact_kind", "rust_project_ir_sha256", "units",
    "status", "blockers", "claim_boundary", "layout_sha256",
}
_UNIT_KEYS = {
    "unit_id", "source_sha256", "size_bytes", "top_level_names",
    "binary_entry_count", "test_entry_count", "main_cfg_guarded",
    "unresolved_reasons",
}
_BLOCKER_KEYS = {"code", "unit_id", "detail_sha256"}
_CLAIM_BOUNDARY = {
    "semantic_gate": False,
    "semantic_pass": False,
    "translation_coverage_numerator": 0,
}
_REASONS = {
    "rust_project_cargo_main_cfg_unresolved",
    "rust_project_cargo_main_signature_unresolved",
    "rust_project_cargo_main_test_entries_mixed",
    "rust_project_cargo_multiple_main_entries",
    "rust_project_cargo_test_signature_unresolved",
    "rust_project_cargo_top_level_name_collision",
    "rust_source_cfg_attr_unresolved",
    "rust_source_external_module_unresolved",
    "rust_source_invalid_utf8",
    "rust_source_macro_expansion_required",
    "rust_source_parse_ambiguity",
    "rust_source_parse_failed",
    "rust_source_unsupported_attribute",
}


def derive_rust_project_cargo_v3_source_layout(
    ir: Mapping[str, Any], candidate_sources: Mapping[str, bytes],
) -> dict[str, Any]:
    """Derive source-only Cargo layout facts without granting semantic credit."""
    validate_rust_project_ir_v3(ir)
    bindings = ir["bindings"]["candidates"]
    expected_ids = {item["unit_id"] for item in bindings}
    if not isinstance(candidate_sources, Mapping) or set(candidate_sources) != expected_ids:
        raise ValueError("rust_project_cargo_v3_candidate_source_set_invalid")
    units: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for binding in bindings:
        unit_id = binding["unit_id"]
        source = candidate_sources[unit_id]
        if type(source) is not bytes:
            raise ValueError("rust_project_cargo_v3_candidate_source_bytes_invalid")
        reference = binding["source"]
        digest = hashlib.sha256(source).hexdigest()
        if digest != reference["sha256"] or len(source) != reference["size_bytes"]:
            raise ValueError("rust_project_cargo_v3_candidate_source_artifact_drifted")
        unit, unit_blockers = scan_source_unit(unit_id, digest, source)
        units.append(unit)
        blockers.extend(unit_blockers)
    units.sort(key=lambda item: item["unit_id"])
    blockers.sort(key=canonical_json_bytes)
    core = {
        "schema_version": RUST_PROJECT_CARGO_V3_SOURCE_LAYOUT_SCHEMA_VERSION,
        "artifact_kind": "rust-project-cargo-v3-source-layout",
        "rust_project_ir_sha256": ir["ir_sha256"],
        "units": units,
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    result = {**core, "layout_sha256": content_sha256(core)}
    return validate_rust_project_cargo_v3_source_layout(result)


def validate_rust_project_cargo_v3_source_layout(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        _fail("rust_project_cargo_v3_source_layout_schema_invalid")
    result = dict(value)
    if (
        result.get("schema_version")
        != RUST_PROJECT_CARGO_V3_SOURCE_LAYOUT_SCHEMA_VERSION
        or result.get("artifact_kind") != "rust-project-cargo-v3-source-layout"
        or not is_sha256(result.get("rust_project_ir_sha256"))
        or result.get("claim_boundary") != _CLAIM_BOUNDARY
    ):
        _fail("rust_project_cargo_v3_source_layout_identity_invalid")
    units = result.get("units")
    if not isinstance(units, list) or not units:
        _fail("rust_project_cargo_v3_source_layout_units_invalid")
    unit_ids: list[str] = []
    reason_pairs: set[tuple[str, str]] = set()
    for unit in units:
        if not isinstance(unit, Mapping) or set(unit) != _UNIT_KEYS:
            _fail("rust_project_cargo_v3_source_layout_unit_schema_invalid")
        unit_id = unit.get("unit_id")
        names = unit.get("top_level_names")
        reasons = unit.get("unresolved_reasons")
        if (
            not isinstance(unit_id, str) or not unit_id
            or not is_sha256(unit.get("source_sha256"))
            or type(unit.get("size_bytes")) is not int or unit["size_bytes"] < 0
            or not _canonical_strings(names, identifiers=True)
            or not _canonical_strings(reasons)
            or any(reason not in _REASONS for reason in reasons)
            or type(unit.get("binary_entry_count")) is not int
            or unit["binary_entry_count"] < 0
            or type(unit.get("test_entry_count")) is not int
            or unit["test_entry_count"] < 0
            or type(unit.get("main_cfg_guarded")) is not bool
        ):
            _fail("rust_project_cargo_v3_source_layout_unit_invalid")
        if unit["main_cfg_guarded"] and "rust_project_cargo_main_cfg_unresolved" not in reasons:
            _fail("rust_project_cargo_v3_source_layout_main_cfg_invalid")
        if unit["binary_entry_count"] and unit["test_entry_count"] and (
            "rust_project_cargo_main_test_entries_mixed" not in reasons
        ):
            _fail("rust_project_cargo_v3_source_layout_entry_mix_invalid")
        unit_ids.append(unit_id)
        reason_pairs.update((unit_id, reason) for reason in reasons)
    if unit_ids != sorted(set(unit_ids)):
        _fail("rust_project_cargo_v3_source_layout_units_noncanonical")
    blockers = result.get("blockers")
    if not isinstance(blockers, list):
        _fail("rust_project_cargo_v3_source_layout_blockers_invalid")
    blocker_pairs: set[tuple[str, str]] = set()
    identities: set[tuple[str, str, str | None]] = set()
    for blocker in blockers:
        if not isinstance(blocker, Mapping) or set(blocker) != _BLOCKER_KEYS:
            _fail("rust_project_cargo_v3_source_layout_blocker_schema_invalid")
        code, unit_id, detail = (
            blocker.get("code"), blocker.get("unit_id"),
            blocker.get("detail_sha256"),
        )
        if (
            code not in _REASONS or unit_id not in unit_ids
            or (detail is not None and not is_sha256(detail))
            or (unit_id, code) in blocker_pairs
            or (code, unit_id, detail) in identities
        ):
            _fail("rust_project_cargo_v3_source_layout_blocker_invalid")
        blocker_pairs.add((unit_id, code))
        identities.add((code, unit_id, detail))
    if blockers != sorted(blockers, key=canonical_json_bytes):
        _fail("rust_project_cargo_v3_source_layout_blockers_noncanonical")
    if blocker_pairs != reason_pairs:
        _fail("rust_project_cargo_v3_source_layout_reasons_drifted")
    expected_status = "blocked" if blockers else "ready"
    if result.get("status") != expected_status:
        _fail("rust_project_cargo_v3_source_layout_status_invalid")
    core = {key: result[key] for key in result if key != "layout_sha256"}
    if result.get("layout_sha256") != content_sha256(core):
        _fail("rust_project_cargo_v3_source_layout_hash_drifted")
    return result


def _canonical_strings(value: Any, *, identifiers: bool = False) -> bool:
    return (isinstance(value, list) and value == sorted(set(value))
            and all(isinstance(item, str) and item
                    and (not identifiers or (item != "_" and identifier(item)))
                    for item in value))


def _fail(code: str) -> None:
    raise ValueError(code)


__all__ = [
    "RUST_PROJECT_CARGO_V3_SOURCE_LAYOUT_SCHEMA_VERSION",
    "derive_rust_project_cargo_v3_source_layout",
    "validate_rust_project_cargo_v3_source_layout",
]
