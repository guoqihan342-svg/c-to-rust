from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .rust_occurrence_manifest import occurrence_manifest_bytes
from .rust_project_cargo_v3_projection_analysis import root_path
from .rust_project_cargo_v3_projection_validation import (
    module_identifier, package_member_path,
)
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3
from .sandbox_execution_schema import is_sha256


SCHEMA_VERSION = 1
ARTIFACT_KIND = "rust-cargo-object-occurrence-expectation"
_CLAIM_BOUNDARY = {
    "section_closure": False, "semantic_gate": False,
    "translation_coverage_numerator": 0,
}
_TOP_KEYS = {
    "schema_version", "artifact_kind", "rust_project_ir_sha256", "status",
    "targets", "blockers", "claim_boundary", "expectation_sha256",
}
_TARGET_KEYS = {
    "package", "target", "root_guest_path_sha256", "occurrence_count",
    "occurrence_order_sha256", "module_order", "expected_sources",
    "source_order_sha256", "manifest_sha256",
}
_OWNER_KEYS = {"name", "version"}
_RUST_TARGET_KEYS = {"name", "kind", "crate_types"}
_MODULE_KEYS = {"ordinal", "module_id_sha256", "source_guest_path_sha256"}
_SOURCE_KEYS = {"ordinal", "guest_path_sha256"}
_EXTENDED_OCCURRENCE_KEYS = {
    "occurrence_id", "object_target_id", "source_unit_id", "module_id",
}


def derive_rust_cargo_occurrence_expectation(
    rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    validate_rust_project_ir_v3(rust_project_ir)
    packages = _index(rust_project_ir["packages"], "package_id")
    modules = _index(rust_project_ir["modules"], "module_id")
    blockers = []
    targets = []
    for target in rust_project_ir["targets"]:
        identity = content_sha256({
            "package_id": target["package_id"], "target_id": target["target_id"],
        })
        try:
            targets.append(_target_expectation(target, packages, modules))
        except (KeyError, TypeError, ValueError):
            blockers.append({
                "code": "rust_cargo_object_occurrence_mapping_unavailable",
                "detail": identity,
            })
    blockers = sorted(blockers, key=canonical_json_bytes)
    core = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": ARTIFACT_KIND,
        "rust_project_ir_sha256": str(rust_project_ir["ir_sha256"]),
        "status": "blocked" if blockers else "ready",
        "targets": sorted(targets, key=canonical_json_bytes),
        "blockers": blockers, "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    return validate_rust_cargo_occurrence_expectation({
        **core, "expectation_sha256": content_sha256(core),
    })


def validate_rust_cargo_occurrence_expectation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rust_cargo_occurrence_expectation_schema_invalid")
    targets, blockers = value.get("targets"), value.get("blockers")
    if not isinstance(targets, list) or not isinstance(blockers, list):
        raise ValueError("rust_cargo_occurrence_expectation_collections_invalid")
    normalized = [_validate_target(item) for item in targets]
    identities = [_identity(item) for item in normalized]
    if normalized != sorted(normalized, key=canonical_json_bytes) \
            or len(identities) != len(set(identities)):
        raise ValueError("rust_cargo_occurrence_expectation_targets_invalid")
    if blockers != sorted(blockers, key=canonical_json_bytes) \
            or any(not _blocker(item) for item in blockers):
        raise ValueError("rust_cargo_occurrence_expectation_blockers_invalid")
    core = {key: value[key] for key in value if key != "expectation_sha256"}
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("artifact_kind") != ARTIFACT_KIND
        or not is_sha256(value.get("rust_project_ir_sha256"))
        or value.get("status") not in {"ready", "blocked"}
        or (value["status"] == "ready") != (not blockers)
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
        or value.get("expectation_sha256") != content_sha256(core)
    ):
        raise ValueError("rust_cargo_occurrence_expectation_invalid")
    return dict(value)


def _target_expectation(target, packages, modules) -> dict[str, Any]:
    occurrences = target["input_occurrences"]
    if not occurrences or any(
        not isinstance(item, Mapping)
        or not _EXTENDED_OCCURRENCE_KEYS <= set(item)
        for item in occurrences
    ):
        raise ValueError("occurrence_mapping_missing")
    object_rows = [item for item in occurrences
                   if item["dependency_target_id"] is None]
    if not object_rows or any(
        not all(_text(item.get(key)) for key in _EXTENDED_OCCURRENCE_KEYS)
        for item in object_rows
    ) or any(
        any(item.get(key) is not None for key in (
            "object_target_id", "source_unit_id", "module_id",
        ))
        for item in occurrences if item["dependency_target_id"] is not None
    ):
        raise ValueError("occurrence_mapping_invalid")
    owned = {str(item): modules[str(item)] for item in target["module_ids"]}
    expected_pairs = {
        (module_id, str(source_unit))
        for module_id, module in owned.items()
        for source_unit in module["source_unit_ids"]
    }
    actual_pairs = {(str(item["module_id"]), str(item["source_unit_id"]))
                    for item in object_rows}
    if actual_pairs != expected_pairs \
            or len({item["object_target_id"] for item in object_rows}) != len(object_rows):
        raise ValueError("occurrence_mapping_closure_invalid")
    module_order = []
    for item in object_rows:
        module_id = str(item["module_id"])
        if not module_order or module_order[-1] != module_id:
            if module_id in module_order:
                raise ValueError("occurrence_module_not_contiguous")
            module_order.append(module_id)
    for module_id in module_order:
        actual = [str(item["source_unit_id"]) for item in object_rows
                  if item["module_id"] == module_id]
        if actual != list(owned[module_id]["source_unit_ids"]):
            raise ValueError("occurrence_module_source_order_invalid")
    package = packages[str(target["package_id"])]
    root = f"/workspace/{root_path(str(target['package_id']), str(target['kind']))}"
    module_paths = [
        f"/workspace/{package_member_path(str(target['package_id']))}"
        f"/src/modules/{module_identifier(module_id)}.rs"
        for module_id in module_order
    ]
    module_rows = [{
        "ordinal": ordinal,
        "module_id_sha256": _hash(module_id),
        "source_guest_path_sha256": _hash(module_paths[ordinal]),
    } for ordinal, module_id in enumerate(module_order)]
    sources = [{"ordinal": ordinal, "guest_path_sha256": _hash(path)}
               for ordinal, path in enumerate([root, *module_paths])]
    return {
        "package": {"name": str(package["name"]), "version": "0.0.0"},
        "target": {"name": str(target["name"]), "kind": str(target["kind"]),
                   "crate_types": sorted(target["crate_types"])},
        "root_guest_path_sha256": _hash(root),
        "occurrence_count": len(occurrences),
        "occurrence_order_sha256": content_sha256(occurrences),
        "module_order": module_rows, "expected_sources": sources,
        "source_order_sha256": content_sha256(sources),
        "manifest_sha256": hashlib.sha256(
            occurrence_manifest_bytes(target),
        ).hexdigest(),
    }


def _validate_target(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TARGET_KEYS:
        raise ValueError("rust_cargo_occurrence_expectation_target_invalid")
    package, target = value.get("package"), value.get("target")
    modules, sources = value.get("module_order"), value.get("expected_sources")
    if not isinstance(package, Mapping) or set(package) != _OWNER_KEYS \
            or not _text(package.get("name")) or package.get("version") != "0.0.0" \
            or not isinstance(target, Mapping) or set(target) != _RUST_TARGET_KEYS \
            or not _text(target.get("name")) or target.get("kind") not in {"bin", "cdylib", "lib"} \
            or not _texts(target.get("crate_types")):
        raise ValueError("rust_cargo_occurrence_expectation_identity_invalid")
    _ordered_hash_rows(modules, _MODULE_KEYS)
    _ordered_hash_rows(sources, _SOURCE_KEYS)
    if not sources or len(sources) != len(modules) + 1 \
            or sources[0]["guest_path_sha256"] != value.get("root_guest_path_sha256") \
            or value.get("source_order_sha256") != content_sha256(sources) \
            or type(value.get("occurrence_count")) is not int \
            or value["occurrence_count"] < len(modules) \
            or not is_sha256(value.get("occurrence_order_sha256")) \
            or not is_sha256(value.get("manifest_sha256")):
        raise ValueError("rust_cargo_occurrence_expectation_target_invalid")
    return dict(value)


def _ordered_hash_rows(value: Any, keys: set[str]) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) or set(item) != keys
        or item.get("ordinal") != ordinal
        or any(not is_sha256(item.get(key)) for key in keys - {"ordinal"})
        for ordinal, item in enumerate(value)
    ):
        raise ValueError("rust_cargo_occurrence_expectation_order_invalid")


def _index(values: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, list) or not values:
        raise ValueError("rust_cargo_occurrence_expectation_ir_invalid")
    return {str(item[key]): item for item in values}


def _identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    return (str(value["package"]["name"]), str(value["package"]["version"]),
            str(value["target"]["name"]))


def _blocker(value: Any) -> bool:
    return isinstance(value, Mapping) and set(value) == {"code", "detail"} \
        and _text(value.get("code")) and is_sha256(value.get("detail"))


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 256


def _texts(value: Any) -> bool:
    return isinstance(value, list) and bool(value) \
        and value == sorted(set(value)) and all(_text(item) for item in value)


__all__ = [
    "derive_rust_cargo_occurrence_expectation",
    "validate_rust_cargo_occurrence_expectation",
]
