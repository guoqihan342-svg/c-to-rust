from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


RUST_CARGO_TOPOLOGY_EXPECTATION_SCHEMA_VERSION = 1
_CLAIM_BOUNDARY = {
    "section_closure": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_TOP_KEYS = {
    "schema_version", "artifact_kind", "rust_project_ir_sha256", "facts",
    "claim_boundary", "expectation_sha256",
}
_FACT_KEYS = {
    "resolver", "packages", "default_members", "workspace_members",
}
_PACKAGE_KEYS = {"name", "version", "features", "targets"}
_TARGET_KEYS = {"name", "kind", "crate_types", "required_features"}
_IR_TARGET_KINDS = {"bin", "cdylib", "lib"}
_METADATA_TARGET_KINDS = {"bin", "cdylib", "lib", "rlib", "staticlib"}


def derive_rust_cargo_topology_expectation(
    rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(rust_project_ir, Mapping):
        raise ValueError("rust_cargo_topology_ir_v3_required")
    validate_rust_project_ir_v3(rust_project_ir)
    if (
        rust_project_ir.get("topology_status") != "ready"
        or rust_project_ir.get("topology_blockers") != []
    ):
        raise ValueError("rust_cargo_topology_ir_not_ready")
    packages = _index(rust_project_ir["packages"], "package_id")
    targets = _index(rust_project_ir["targets"], "target_id")
    projected = {
        package_id: _package(package, targets)
        for package_id, package in packages.items()
    }
    semantic_keys = [
        (item["name"], item["version"]) for item in projected.values()
    ]
    if len(semantic_keys) != len(set(semantic_keys)):
        raise ValueError("rust_cargo_topology_package_identity_collision")
    workspace = rust_project_ir["workspace"]
    facts = {
        "resolver": "no-deps",
        "packages": _ordered(list(projected.values())),
        "default_members": _ordered([
            projected[str(package_id)]
            for package_id in workspace["default_package_ids"]
        ]),
        "workspace_members": _ordered([
            projected[str(package_id)]
            for package_id in workspace["package_ids"]
        ]),
    }
    core = {
        "schema_version": RUST_CARGO_TOPOLOGY_EXPECTATION_SCHEMA_VERSION,
        "artifact_kind": "rust-project-ir-cargo-topology-expectation",
        "rust_project_ir_sha256": str(rust_project_ir["ir_sha256"]),
        "facts": facts,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return validate_rust_cargo_topology_expectation({
        **core, "expectation_sha256": content_sha256(core),
    })


def validate_rust_cargo_topology_expectation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rust_cargo_topology_expectation_schema_invalid")
    expectation = dict(value)
    facts = expectation.get("facts")
    if not isinstance(facts, Mapping) or set(facts) != _FACT_KEYS:
        raise ValueError("rust_cargo_topology_expectation_facts_invalid")
    packages = _packages(facts.get("packages"))
    workspace = _packages(facts.get("workspace_members"))
    defaults = _packages(facts.get("default_members"), allow_empty=True)
    if (
        expectation.get("schema_version")
        != RUST_CARGO_TOPOLOGY_EXPECTATION_SCHEMA_VERSION
        or expectation.get("artifact_kind")
        != "rust-project-ir-cargo-topology-expectation"
        or not is_sha256(expectation.get("rust_project_ir_sha256"))
        or facts.get("resolver") != "no-deps"
        or packages != workspace
        or not all(item in packages for item in defaults)
        or expectation.get("claim_boundary") != _CLAIM_BOUNDARY
    ):
        raise ValueError("rust_cargo_topology_expectation_invalid")
    core = {
        key: expectation[key] for key in expectation
        if key != "expectation_sha256"
    }
    if expectation.get("expectation_sha256") != content_sha256(core):
        raise ValueError("rust_cargo_topology_expectation_sha256_drifted")
    return expectation


def _package(
    package: Mapping[str, Any], targets: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    owned = []
    for target_id in package["target_ids"]:
        target = targets[str(target_id)]
        if target["package_id"] != package["package_id"]:
            raise ValueError("rust_cargo_topology_target_owner_drifted")
        ir_kind = str(target["kind"])
        if ir_kind not in _IR_TARGET_KINDS:
            raise ValueError("rust_cargo_topology_target_kind_unsupported")
        crate_types = sorted(target["crate_types"])
        kind = ["bin"] if ir_kind == "bin" else list(crate_types)
        owned.append({
            "name": str(target["name"]),
            "kind": list(kind),
            "crate_types": crate_types,
            "required_features": [],
        })
    return {
        "name": str(package["name"]),
        "version": "0.0.0",
        "features": [],
        "targets": _ordered(owned),
    }


def _packages(value: Any, *, allow_empty: bool = False) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise ValueError("rust_cargo_topology_expectation_packages_invalid")
    result = []
    for package in value:
        if not isinstance(package, Mapping) or set(package) != _PACKAGE_KEYS:
            raise ValueError("rust_cargo_topology_expectation_package_invalid")
        if (
            not isinstance(package.get("name"), str) or not package["name"]
            or package.get("version") != "0.0.0"
            or package.get("features") != []
        ):
            raise ValueError("rust_cargo_topology_expectation_package_invalid")
        raw_targets = package.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise ValueError("rust_cargo_topology_expectation_targets_invalid")
        for target in raw_targets:
            if not isinstance(target, Mapping) or set(target) != _TARGET_KEYS:
                raise ValueError("rust_cargo_topology_expectation_target_invalid")
            if (
                not isinstance(target.get("name"), str) or not target["name"]
                or target.get("required_features") != []
                or not isinstance(target.get("kind"), list)
                or not target["kind"]
                or target["kind"] != sorted(set(target["kind"]))
                or not set(target["kind"]) <= _METADATA_TARGET_KINDS
                or not isinstance(target.get("crate_types"), list)
                or not target["crate_types"]
            ):
                raise ValueError("rust_cargo_topology_expectation_target_invalid")
        normalized = {
            **dict(package), "targets": _ordered([dict(item) for item in raw_targets]),
        }
        result.append(normalized)
    ordered = _ordered(result)
    if value != ordered or len(ordered) != len({
        (item["name"], item["version"]) for item in ordered
    }):
        raise ValueError("rust_cargo_topology_expectation_packages_not_canonical")
    return ordered


def _index(values: Any, identity: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, list) or not values:
        raise ValueError("rust_cargo_topology_ir_collection_invalid")
    result = {}
    for item in values:
        key = item.get(identity) if isinstance(item, Mapping) else None
        if not isinstance(key, str) or not key or key in result:
            raise ValueError("rust_cargo_topology_ir_identity_invalid")
        result[key] = item
    return result


def _ordered(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(values, key=canonical_json_bytes)


__all__ = [
    "RUST_CARGO_TOPOLOGY_EXPECTATION_SCHEMA_VERSION",
    "derive_rust_cargo_topology_expectation",
    "validate_rust_cargo_topology_expectation",
]
