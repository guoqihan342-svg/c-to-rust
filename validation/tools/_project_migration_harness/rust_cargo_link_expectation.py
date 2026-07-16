from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


SCHEMA_VERSION = 1
ARTIFACT_KIND = "rust-cargo-link-order-expectation"
_CLAIM_BOUNDARY = {
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_TOP_KEYS = {
    "schema_version", "artifact_kind", "rust_project_ir_sha256", "targets",
    "claim_boundary", "expectation_sha256",
}
_TARGET_KEYS = {"package", "target", "dependencies"}
_OWNER_KEYS = {"name", "version"}
_RUST_TARGET_KEYS = {"name", "kind", "crate_types"}
_DEPENDENCY_KEYS = {"ordinal", "package", "target"}


def derive_rust_cargo_link_expectation(
    rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    validate_rust_project_ir_v3(rust_project_ir)
    if rust_project_ir.get("topology_status") != "ready" \
            or rust_project_ir.get("topology_blockers") != []:
        raise ValueError("rust_cargo_link_expectation_ir_not_ready")
    packages = _index(rust_project_ir["packages"], "package_id")
    targets = _index(rust_project_ir["targets"], "target_id")
    projected = []
    for target in targets.values():
        if target["kind"] not in {"bin", "cdylib"}:
            continue
        owner = packages[str(target["package_id"])]
        dependencies = []
        for occurrence in target["input_occurrences"]:
            dependency_id = occurrence["dependency_target_id"]
            if dependency_id is None:
                continue
            dependency = targets[str(dependency_id)]
            dependency_owner = packages[str(dependency["package_id"])]
            dependencies.append({
                "ordinal": len(dependencies),
                "package": _package(dependency_owner),
                "target": _target(dependency),
            })
        projected.append({
            "package": _package(owner), "target": _target(target),
            "dependencies": dependencies,
        })
    core = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": ARTIFACT_KIND,
        "rust_project_ir_sha256": str(rust_project_ir["ir_sha256"]),
        "targets": sorted(projected, key=canonical_json_bytes),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return validate_rust_cargo_link_expectation({
        **core, "expectation_sha256": content_sha256(core),
    })


def validate_rust_cargo_link_expectation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rust_cargo_link_expectation_schema_invalid")
    expectation = dict(value)
    targets = expectation.get("targets")
    if not isinstance(targets, list):
        raise ValueError("rust_cargo_link_expectation_targets_invalid")
    normalized = [_validate_target(item) for item in targets]
    identities = [_identity(item) for item in normalized]
    if normalized != sorted(normalized, key=canonical_json_bytes) \
            or len(identities) != len(set(identities)):
        raise ValueError("rust_cargo_link_expectation_targets_not_canonical")
    core = {key: expectation[key] for key in expectation
            if key != "expectation_sha256"}
    if (
        expectation.get("schema_version") != SCHEMA_VERSION
        or expectation.get("artifact_kind") != ARTIFACT_KIND
        or not is_sha256(expectation.get("rust_project_ir_sha256"))
        or expectation.get("claim_boundary") != _CLAIM_BOUNDARY
        or expectation.get("expectation_sha256") != content_sha256(core)
    ):
        raise ValueError("rust_cargo_link_expectation_invalid")
    return expectation


def _validate_target(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TARGET_KEYS:
        raise ValueError("rust_cargo_link_expectation_target_invalid")
    package = _validate_package(value.get("package"))
    target = _validate_rust_target(value.get("target"), linkable=True)
    dependencies = value.get("dependencies")
    if not isinstance(dependencies, list):
        raise ValueError("rust_cargo_link_expectation_dependencies_invalid")
    normalized = []
    identities = []
    for ordinal, dependency in enumerate(dependencies):
        if not isinstance(dependency, Mapping) \
                or set(dependency) != _DEPENDENCY_KEYS \
                or dependency.get("ordinal") != ordinal:
            raise ValueError("rust_cargo_link_expectation_dependency_invalid")
        item = {
            "ordinal": ordinal,
            "package": _validate_package(dependency.get("package")),
            "target": _validate_rust_target(dependency.get("target")),
        }
        normalized.append(item)
        identities.append(_dependency_identity(item))
    if len(identities) != len(set(identities)):
        raise ValueError("rust_cargo_link_expectation_dependency_duplicate")
    expected = {"package": package, "target": target,
                "dependencies": normalized}
    if dict(value) != expected:
        raise ValueError("rust_cargo_link_expectation_target_not_canonical")
    return expected


def _validate_package(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _OWNER_KEYS \
            or not _text(value.get("name")) or value.get("version") != "0.0.0":
        raise ValueError("rust_cargo_link_expectation_package_invalid")
    return {"name": str(value["name"]), "version": "0.0.0"}


def _validate_rust_target(
    value: Any, *, linkable: bool = False,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RUST_TARGET_KEYS:
        raise ValueError("rust_cargo_link_expectation_rust_target_invalid")
    crate_types = value.get("crate_types")
    if not _text(value.get("name")) or value.get("kind") not in {
        "bin", "cdylib", "lib",
    } or not isinstance(crate_types, list) or not crate_types \
            or crate_types != sorted(set(crate_types)) \
            or (linkable and value.get("kind") not in {"bin", "cdylib"}):
        raise ValueError("rust_cargo_link_expectation_rust_target_invalid")
    return {"name": str(value["name"]), "kind": str(value["kind"]),
            "crate_types": list(crate_types)}


def _package(value: Mapping[str, Any]) -> dict[str, str]:
    return {"name": str(value["name"]), "version": "0.0.0"}


def _target(value: Mapping[str, Any]) -> dict[str, Any]:
    return {"name": str(value["name"]), "kind": str(value["kind"]),
            "crate_types": sorted(value["crate_types"])}


def _index(values: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, list) or not values:
        raise ValueError("rust_cargo_link_expectation_ir_collection_invalid")
    return {str(item[key]): item for item in values}


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(value["package"]["name"]), str(value["package"]["version"]),
            str(value["target"]["name"]))


def _dependency_identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return _identity(value)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256


__all__ = [
    "ARTIFACT_KIND", "SCHEMA_VERSION", "derive_rust_cargo_link_expectation",
    "validate_rust_cargo_link_expectation",
]
