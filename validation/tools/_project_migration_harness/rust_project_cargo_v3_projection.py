from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .rust_project_cargo_v3_projection_analysis import (
    block, entry_module, link_order_unproven, public_namespaces, root_path,
    topology_blockers,
)
from .rust_project_cargo_v3_projection_validation import (
    ARTIFACT_KIND, SCHEMA_VERSION, cargo_alias, module_identifier,
    package_member_path, validate_rust_project_cargo_v3_projection,
)
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


_UNIT_KEYS = {
    "unit_id", "source_sha256", "size_bytes", "top_level_names",
    "binary_entry_count", "test_entry_count", "main_cfg_guarded",
    "unresolved_reasons",
}
import re

_SHA = re.compile(r"[0-9a-f]{64}\Z")


def derive_rust_project_cargo_v3_projection(
    ir: Mapping[str, Any], source_layout: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a ready RustProjectIR v3 into a fail-closed Cargo workspace."""
    if not isinstance(ir, Mapping) or ir.get("schema_version") != 3:
        raise ValueError("Cargo v3 projection requires RustProjectIR schema v3")
    validate_rust_project_ir_v3(ir)
    if ir.get("topology_status") != "ready":
        raise ValueError("Cargo v3 projection requires ready domain topology")
    units, layout_sha = _source_units(ir, source_layout)
    ir_packages = {str(item["package_id"]): item for item in ir["packages"]}
    ir_targets = {str(item["target_id"]): item for item in ir["targets"]}
    candidates = {
        str(item["unit_id"]): item["source"] for item in ir["bindings"]["candidates"]
    }
    blockers: set[tuple[str, str, str]] = set()
    modules = _project_modules(ir, units, candidates)
    module_map = {item["module_id"]: item for item in modules}
    packages = _project_packages(ir_packages)
    package_map = {item["package_id"]: item for item in packages}
    required, providers, namespace_hashes = public_namespaces(ir, module_map)
    targets = []
    for target_id in sorted(ir_targets):
        raw = ir_targets[target_id]
        owned = [module_map[key] for key in raw["module_ids"]]
        entry = entry_module(raw, owned, units, blockers)
        if link_order_unproven(raw):
            block(blockers, "link_occurrence_order_unproven", "target", target_id)
        targets.append({
            "target_id": target_id, "package_id": str(raw["package_id"]),
            "name": str(raw["name"]), "kind": str(raw["kind"]),
            "build_ir_target_id": str(raw["build_ir_target_id"]),
            "crate_types": sorted(raw["crate_types"]),
            "root_path": root_path(str(raw["package_id"]), str(raw["kind"])),
            "entry_module_id": entry, "module_ids": sorted(raw["module_ids"]),
            "input_occurrences": _clone(raw["input_occurrences"]),
            "ordered_link_arguments": list(raw["ordered_link_arguments"]),
            "export_namespace_sha256": namespace_hashes[target_id],
        })
    target_map = {item["target_id"]: item for item in targets}
    topology_blockers(
        ir, package_map, target_map, module_map, blockers,
        required=required, providers=providers,
    )
    workspace = {
        "workspace_id": str(ir["workspace"]["workspace_id"]),
        "resolver": str(ir["workspace"]["resolver"]),
        "member_paths": [package_member_path(key) for key in sorted(package_map)],
        "default_member_paths": sorted(
            package_member_path(str(key))
            for key in ir["workspace"]["default_package_ids"]
        ),
    }
    canonical_blockers = [
        {"code": code, "entity_kind": kind, "entity_id": entity_id}
        for code, kind, entity_id in sorted(blockers)
    ]
    payload = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": ARTIFACT_KIND,
        "rust_project_ir_sha256": str(ir["ir_sha256"]),
        "source_layout_sha256": layout_sha, "workspace": workspace,
        "packages": packages, "targets": targets, "modules": modules,
        "status": "blocked" if canonical_blockers else "ready",
        "blockers": canonical_blockers, "claim_boundary": False,
    }
    payload["projection_sha256"] = content_sha256(payload)
    validate_rust_project_cargo_v3_projection(payload)
    return payload


def _source_units(
    ir: Mapping[str, Any], layout: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], str]:
    if not isinstance(layout, Mapping) or layout.get("status") != "ready":
        raise ValueError("Cargo v3 projection requires ready source layout")
    digest = _source_layout_digest(layout)
    if "rust_project_ir_sha256" in layout and layout["rust_project_ir_sha256"] != ir["ir_sha256"]:
        raise ValueError("Cargo v3 source layout binds a different RustProjectIR")
    raw_units = layout.get("units")
    if not isinstance(raw_units, list):
        raise ValueError("Cargo v3 source layout units are invalid")
    result = {}
    for raw in raw_units:
        if not isinstance(raw, Mapping) or set(raw) != _UNIT_KEYS:
            raise ValueError("Cargo v3 source layout unit schema is invalid")
        unit_id = _text(raw.get("unit_id"), "source layout unit_id")
        if unit_id in result:
            raise ValueError("Cargo v3 source layout unit_ids must be unique")
        source_sha = _sha(raw.get("source_sha256"), "source layout source_sha256")
        size = _count(raw.get("size_bytes"), "source layout size_bytes")
        binary = _count(raw.get("binary_entry_count"), "binary_entry_count")
        tests = _count(raw.get("test_entry_count"), "test_entry_count")
        names = _string_array(raw.get("top_level_names"), "top_level_names")
        unresolved = _string_array(raw.get("unresolved_reasons"), "unresolved_reasons")
        if unresolved != sorted(set(unresolved)) or unresolved:
            raise ValueError("Cargo v3 ready source layout has unresolved reasons")
        if not isinstance(raw.get("main_cfg_guarded"), bool):
            raise ValueError("Cargo v3 source layout main_cfg_guarded is invalid")
        result[unit_id] = {
            "unit_id": unit_id, "source_sha256": source_sha, "size_bytes": size,
            "top_level_names": sorted(names), "binary_entry_count": binary,
            "test_entry_count": tests, "main_cfg_guarded": raw["main_cfg_guarded"],
            "unresolved_reasons": unresolved,
        }
    candidates = {
        str(item["unit_id"]): item["source"] for item in ir["bindings"]["candidates"]
    }
    module_units = {str(item["unit_id"]) for item in ir["modules"]}
    if set(result) != set(candidates) or set(result) != module_units:
        raise ValueError("Cargo v3 source layout unit closure drifted")
    for unit_id, unit in result.items():
        source = candidates[unit_id]
        if unit["source_sha256"] != source["sha256"] or unit["size_bytes"] != source["size_bytes"]:
            raise ValueError("Cargo v3 source layout candidate binding drifted")
    return result, digest


def _source_layout_digest(layout: Mapping[str, Any]) -> str:
    fields = [key for key in ("source_layout_sha256", "layout_sha256") if key in layout]
    if len(fields) > 1:
        raise ValueError("Cargo v3 source layout hash binding is ambiguous")
    clone = _clone(layout)
    if not fields:
        return content_sha256(clone)
    field = fields[0]
    digest = _sha(clone.pop(field), f"source layout {field}")
    if content_sha256(clone) != digest:
        raise ValueError("Cargo v3 source layout hash drifted")
    return digest


def _project_modules(ir, units, candidates):
    result = []
    for raw in ir["modules"]:
        module_id, unit_id = str(raw["module_id"]), str(raw["unit_id"])
        unit, source = units[unit_id], candidates[unit_id]
        identifier = module_identifier(module_id)
        package_id = str(raw["package_id"])
        result.append({
            "module_id": module_id, "package_id": package_id,
            "target_id": str(raw["target_id"]), "unit_id": unit_id,
            "identifier": identifier, "source_path": checked_relative_path(source["path"]),
            "render_path": (
                f"{package_member_path(package_id)}/src/modules/{identifier}.rs"
            ),
            "source_sha256": unit["source_sha256"],
            "top_level_names": list(unit["top_level_names"]),
            "binary_entry_count": unit["binary_entry_count"],
            "test_entry_count": unit["test_entry_count"],
        })
    return sorted(result, key=lambda item: item["module_id"])


def _project_packages(values):
    result = []
    for package_id in sorted(values):
        raw = values[package_id]
        dependencies = sorted(raw["dependency_package_ids"])
        result.append({
            "package_id": package_id, "name": str(raw["name"]),
            "manifest_path": f"{package_member_path(package_id)}/Cargo.toml",
            "build_ir_target_id": str(raw["build_ir_target_id"]),
            "product_kind": str(raw["product_kind"]),
            "dependency_package_ids": dependencies,
            "dependency_aliases": {
                key: cargo_alias(str(values[key]["name"])) for key in dependencies
            },
            "target_ids": sorted(raw["target_ids"]),
            "module_ids": sorted(raw["module_ids"]),
        })
    return result


def _clone(value):
    return json.loads(json.dumps(value, ensure_ascii=True))


def _string_array(value, label):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"Cargo v3 source layout {label} must be a string array")
    return list(value)


def _text(value, label):
    if not isinstance(value, str) or not value or len(value) > 1_024:
        raise ValueError(f"Cargo v3 {label} must be bounded text")
    return value


def _sha(value, label):
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise ValueError(f"Cargo v3 {label} is invalid")
    return value


def _count(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"Cargo v3 {label} is invalid")
    return value


__all__ = [
    "derive_rust_project_cargo_v3_projection",
    "validate_rust_project_cargo_v3_projection",
]
