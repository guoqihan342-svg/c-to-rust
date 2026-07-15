from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_validation import VIRTUAL_CRATE_ROOT_MODULE_ID


_CONFLICT_SPECS = (
    (
        "public_api", "symbol", ("kind", "signature", "visibility"),
        "duplicate_public_symbol", "conflicting_public_api",
    ),
    (
        "shared_types", "name", ("kind", "layout_sha256", "repr"),
        "duplicate_shared_type_definition", "conflicting_shared_type",
    ),
    (
        "global_ownership", "symbol", ("module_id", "access"),
        "duplicate_global_owner", "conflicting_global_ownership",
    ),
    (
        "ffi_boundaries", "link_name", ("direction", "abi", "symbol"),
        "duplicate_ffi_boundary", "conflicting_ffi_boundary",
    ),
    (
        "features", "name", ("default", "enables", "module_ids"),
        "duplicate_feature", "conflicting_feature",
    ),
    (
        "cfgs", "expression", ("module_ids",),
        "duplicate_cfg", "conflicting_cfg",
    ),
    (
        "initialization", "function", ("module_id", "phase", "after"),
        "duplicate_initialization", "conflicting_initialization",
    ),
)
_REFERENCE_KINDS = {
    "public_api": "public_api",
    "shared_types": "shared_type",
    "global_ownership": "global_ownership",
    "initialization": "initialization",
    "ffi_boundaries": "ffi_boundary",
    "cfgs": "cfg",
    "features": "feature",
    "unsafe_obligations": "unsafe_obligation",
}


def collect_project_interface_diagnostics(
    ir: Mapping[str, Any],
) -> list[dict[str, Any]]:
    modules = {str(item["module_id"]): item for item in ir["modules"]}
    result = _module_diagnostics(ir, modules)
    result.extend(_native_link_diagnostics(ir))
    for section, group_key, shape_keys, duplicate_code, conflict_code in _CONFLICT_SPECS:
        result.extend(_group_conflicts(
            ir[section], group_key, shape_keys, duplicate_code, conflict_code,
        ))
    result.extend(_section_reference_diagnostics(ir, modules))
    result.extend(_feature_dependency_diagnostics(ir["features"]))
    result.extend(_initialization_dependency_diagnostics(ir["initialization"]))
    return result


def _native_link_diagnostics(
    ir: Mapping[str, Any],
) -> list[dict[str, Any]]:
    requirements = ir["native_link_requirements"]
    if not requirements or ir["native_link_plans"]:
        return []
    requirement_ids = [str(item["requirement_id"]) for item in requirements]
    plan_set_id = "native-link-plan-set-" + content_sha256(
        requirement_ids,
    )[:24]
    return [_diagnostic(
        "rust_project_ir_native_link_plan_missing", [plan_set_id], [],
    )]


def _module_diagnostics(
    ir: Mapping[str, Any], modules: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = _group_conflicts(
        ir["modules"], "rust_path", ("candidate_sha256",),
        "duplicate_module_path", "conflicting_module_path",
    )
    known = set(modules)
    for module_id, module in sorted(modules.items()):
        parent = module.get("parent_module_id")
        if parent is not None and parent not in known:
            result.append(_diagnostic(
                "unknown_parent_module", [module_id, str(parent)], [module_id],
            ))
    for cycle in _parent_cycles(modules):
        result.append(_diagnostic("cyclic_module_parent", list(cycle), list(cycle)))

    root = str(ir["crate"]["root_module_id"])
    if root == VIRTUAL_CRATE_ROOT_MODULE_ID:
        pending = sorted(
            module_id for module_id, module in modules.items()
            if module.get("parent_module_id") is None
        )
    elif root in modules:
        pending = [root]
    else:
        pending = []
        result.append(_diagnostic("missing_root_module", [root], []))
    reachable: set[str] = set()
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(sorted(
            module_id for module_id, module in modules.items()
            if module.get("parent_module_id") == current
        ))
    for module_id in sorted(known - reachable):
        result.append(_diagnostic("orphan_module", [module_id], [module_id]))
    return result


def _parent_cycles(
    modules: Mapping[str, Mapping[str, Any]],
) -> list[tuple[str, ...]]:
    resolved: set[str] = set()
    cycles: set[tuple[str, ...]] = set()
    for start in sorted(modules):
        if start in resolved:
            continue
        path: list[str] = []
        positions: dict[str, int] = {}
        current: str | None = start
        while current in modules and current not in resolved:
            if current in positions:
                cycles.add(tuple(sorted(path[positions[current]:])))
                break
            positions[current] = len(path)
            path.append(current)
            parent = modules[current].get("parent_module_id")
            current = str(parent) if parent is not None else None
        resolved.update(path)
    return sorted(cycles)


def _group_conflicts(
    records: list[Mapping[str, Any]], group_key: str, shape_keys: tuple[str, ...],
    duplicate_code: str, conflict_code: str,
) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        groups[str(record[group_key])].append(record)
    result = []
    for key, entries in sorted(groups.items()):
        if len(entries) < 2:
            continue
        by_shape: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for entry in entries:
            shape = content_sha256({field: entry[field] for field in shape_keys})
            by_shape[shape].append(entry)
        duplicates = [
            entry for shape_entries in by_shape.values() if len(shape_entries) > 1
            for entry in shape_entries
        ]
        if duplicates:
            result.append(_group_diagnostic(duplicate_code, key, duplicates))
        if len(by_shape) > 1:
            result.append(_group_diagnostic(conflict_code, key, entries))
    return result


def _group_diagnostic(
    code: str, key: str, entries: list[Mapping[str, Any]],
) -> dict[str, Any]:
    modules = sorted({
        str(module_id)
        for entry in entries
        for module_id in entry.get("module_ids", [entry.get("module_id")])
        if module_id
    })
    identities = sorted({_identity(entry) for entry in entries})
    return _diagnostic(code, [key, *identities], modules)


def _section_reference_diagnostics(
    ir: Mapping[str, Any], modules: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result = []
    known = set(modules)
    for section, kind in _REFERENCE_KINDS.items():
        for record in ir[section]:
            owner_ids = record.get("module_ids", [record.get("module_id")])
            unknown = sorted(str(item) for item in set(owner_ids) - known)
            if unknown:
                result.append(_diagnostic(
                    f"{kind}_references_unknown_module",
                    [_identity(record), *unknown], unknown,
                ))
    return result


def _feature_dependency_diagnostics(
    features: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    known = {str(item["feature_id"]) for item in features}
    for feature in features:
        unknown = sorted(set(feature["enables"]) - known)
        if unknown:
            result.append(_diagnostic(
                "unknown_feature_dependency",
                [str(feature["feature_id"]), *unknown], list(feature["module_ids"]),
            ))
    return result


def _initialization_dependency_diagnostics(
    records: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    by_id = {str(item["init_id"]): item for item in records}
    for record in records:
        unknown = sorted(set(record["after"]) - set(by_id))
        if unknown:
            result.append(_diagnostic(
                "unknown_initialization_dependency",
                [str(record["init_id"]), *unknown], [str(record["module_id"])],
            ))
    cyclic = _cyclic_dependency_nodes({
        identity: list(record["after"]) for identity, record in by_id.items()
    })
    if cyclic:
        result.append(_diagnostic(
            "cyclic_initialization", cyclic,
            sorted({str(by_id[item]["module_id"]) for item in cyclic}),
        ))
    return result


def _cyclic_dependency_nodes(edges: Mapping[str, list[str]]) -> list[str]:
    cyclic = []
    for root in sorted(edges):
        pending = list(edges[root])
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == root:
                cyclic.append(root)
                break
            if current in edges and current not in visited:
                visited.add(current)
                pending.extend(edges[current])
    return cyclic


def _diagnostic(
    code: str, entity_ids: list[str], module_ids: list[str],
) -> dict[str, Any]:
    payload = {
        "code": code,
        "scope": "project",
        "entity_ids": sorted(set(entity_ids)),
        "affected_module_ids": sorted(set(module_ids)),
        "random_unit_attribution": False,
    }
    return {**payload, "diagnostic_sha256": content_sha256(payload)}


def _identity(record: Mapping[str, Any]) -> str:
    for key in ("declaration_id", "module_id", "feature_id", "cfg_id", "init_id"):
        if key in record:
            return str(record[key])
    return content_sha256(record)[:24]


__all__ = ["collect_project_interface_diagnostics"]
