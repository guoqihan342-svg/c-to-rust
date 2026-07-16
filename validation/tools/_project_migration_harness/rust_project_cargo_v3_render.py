from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes
from .rust_project_cargo_v3_projection_validation import (
    validate_rust_project_cargo_v3_projection,
)
from .rust_project_cargo_v3_toml import (
    checked_output_path, package_root, render_cargo_lock, render_package_toml,
    render_target_root, render_workspace_toml,
)
from .rust_project_ir import canonical_rust_project_ir_bytes
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


IR_FILE = "migration-rust-project-ir.json"
PROJECTION_FILE = "migration-cargo-workspace-v1.json"
EDITION = "2021"


def render_rust_project_cargo_v3_files(
    ir: Mapping[str, Any], projection: Mapping[str, Any],
    candidate_sources: Mapping[str, bytes],
) -> dict[str, bytes]:
    """Render one deterministic workspace from a ready, IR-bound projection."""
    _validate_inputs(ir, projection)
    packages = _index(projection["packages"], "package_id")
    targets = _index(projection["targets"], "target_id")
    modules = _index(projection["modules"], "module_id")
    _require_ir_binding(ir, projection, packages, targets, modules)
    sources = _candidate_sources(ir, modules, candidate_sources)
    files = _FileSet()
    workspace = projection["workspace"]
    projection_sha = str(projection["projection_sha256"])
    files.add("Cargo.toml", render_workspace_toml(
        workspace, packages, str(ir["ir_sha256"]), projection_sha,
    ))
    files.add("Cargo.lock", render_cargo_lock(list(packages.values())))
    files.add(IR_FILE, canonical_rust_project_ir_bytes(ir))
    files.add(PROJECTION_FILE, canonical_json_bytes(dict(projection)))
    by_package = _targets_by_package(targets)
    for package_id, package in sorted(packages.items()):
        files.add(str(package["manifest_path"]), render_package_toml(
            package, by_package[package_id], packages, EDITION,
        ))
    for module in sorted(modules.values(), key=lambda item: item["render_path"]):
        files.add(str(module["render_path"]), sources[str(module["unit_id"])])
    for target in sorted(targets.values(), key=lambda item: item["root_path"]):
        package = packages[str(target["package_id"])]
        owned = [modules[module_id] for module_id in target["module_ids"]]
        aliases = list(package["dependency_aliases"].values())
        files.add(
            str(target["root_path"]),
            render_target_root(target, owned, aliases),
        )
    return files.sorted()


def _validate_inputs(ir: Mapping[str, Any], projection: Mapping[str, Any]) -> None:
    if not isinstance(ir, Mapping) or ir.get("schema_version") != 3:
        raise ValueError("rust_project_cargo_v3_ir_required")
    validate_rust_project_ir_v3(ir)
    if ir.get("topology_status") != "ready" or ir.get("topology_blockers") != []:
        raise ValueError("rust_project_cargo_v3_ir_not_ready")
    boundary = ir.get("claim_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("semantic_gate") is not False:
        raise ValueError("rust_project_cargo_v3_ir_claim_boundary_invalid")
    validate_rust_project_cargo_v3_projection(projection)
    if projection.get("status") != "ready" or projection.get("blockers") != []:
        raise ValueError("rust_project_cargo_v3_projection_not_ready")
    if projection.get("rust_project_ir_sha256") != ir.get("ir_sha256"):
        raise ValueError("rust_project_cargo_v3_projection_ir_drift")
    if ir.get("cfgs") or ir.get("features"):
        raise ValueError("rust_project_cargo_v3_configuration_unsupported")
    if any(ir.get(key) for key in ("native_link_requirements", "native_link_plans")):
        raise ValueError("rust_project_cargo_v3_native_link_unsupported")


def _require_ir_binding(ir, projection, packages, targets, modules) -> None:
    ir_packages = _index(ir["packages"], "package_id")
    ir_targets = _index(ir["targets"], "target_id")
    ir_modules = _index(ir["modules"], "module_id")
    if (
        set(packages) != set(ir_packages) or set(targets) != set(ir_targets)
        or set(modules) != set(ir_modules)
    ):
        raise ValueError("rust_project_cargo_v3_projection_closure_drift")
    package_fields = (
        "name", "build_ir_target_id", "product_kind",
        "dependency_package_ids", "target_ids", "module_ids",
    )
    target_fields = (
        "package_id", "name", "kind", "build_ir_target_id", "crate_types", "module_ids",
        "input_occurrences", "ordered_link_arguments",
    )
    module_fields = ("package_id", "target_id", "unit_id")
    _equal_fields(packages, ir_packages, package_fields)
    _equal_fields(targets, ir_targets, target_fields)
    _equal_fields(modules, ir_modules, module_fields)
    defaults = sorted(
        package_root(str(item))
        for item in ir["workspace"]["default_package_ids"]
    )
    workspace = projection["workspace"]
    if (
        workspace["workspace_id"] != ir["workspace"]["workspace_id"]
        or workspace["resolver"] != ir["workspace"]["resolver"]
        or workspace["default_member_paths"] != defaults
    ):
        raise ValueError("rust_project_cargo_v3_projection_workspace_drift")
    for module_id, module in modules.items():
        expected = ir_modules[module_id]
        if module["source_sha256"] != expected["candidate_sha256"]:
            raise ValueError("rust_project_cargo_v3_projection_module_drift")


def _equal_fields(current, expected, fields) -> None:
    for identity, record in current.items():
        if any(record.get(field) != expected[identity].get(field) for field in fields):
            raise ValueError("rust_project_cargo_v3_projection_ir_drift")


def _candidate_sources(ir, modules, values) -> dict[str, bytes]:
    if not isinstance(values, Mapping):
        raise ValueError("rust_project_cargo_v3_candidate_sources_invalid")
    expected_units = {str(item["unit_id"]) for item in modules.values()}
    references = {
        str(item["unit_id"]): item["source"]
        for item in ir["bindings"]["candidates"]
    }
    if set(values) != expected_units or set(references) != expected_units:
        raise ValueError("rust_project_cargo_v3_candidate_source_closure_drift")
    result = {}
    for unit_id in sorted(expected_units):
        source = values[unit_id]
        reference = references[unit_id]
        if (
            not isinstance(source, bytes)
            or len(source) != reference["size_bytes"]
            or hashlib.sha256(source).hexdigest() != reference["sha256"]
        ):
            raise ValueError("rust_project_cargo_v3_candidate_source_drift")
        result[unit_id] = source
    return result


def _targets_by_package(targets) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    for target in targets.values():
        result.setdefault(str(target["package_id"]), []).append(target)
    return result


def _index(values: Any, identity_field: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(values, list):
        raise ValueError("rust_project_cargo_v3_projection_invalid")
    result = {}
    for item in values:
        identity = item.get(identity_field) if isinstance(item, Mapping) else None
        if not isinstance(identity, str) or not identity or identity in result:
            raise ValueError("rust_project_cargo_v3_projection_invalid")
        result[identity] = item
    return result


class _FileSet:
    def __init__(self) -> None:
        self._files: dict[str, bytes] = {}
        self._paths: dict[str, tuple[str, ...]] = {}

    def add(self, path: str, content: bytes) -> None:
        canonical = checked_output_path(path)
        parts = tuple(part.casefold() for part in canonical.split("/"))
        for existing, other in self._paths.items():
            if parts == other or parts == other[:len(parts)] or other == parts[:len(other)]:
                raise ValueError(f"rust_project_cargo_v3_path_collision:{existing}")
        if not isinstance(content, bytes):
            raise ValueError("rust_project_cargo_v3_rendered_content_invalid")
        self._files[canonical] = content
        self._paths[canonical] = parts

    def sorted(self) -> dict[str, bytes]:
        return {path: self._files[path] for path in sorted(self._files)}


__all__ = ["IR_FILE", "PROJECTION_FILE", "render_rust_project_cargo_v3_files"]
