from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_validation import validate_rust_project_ir


COORDINATOR_ID = "deterministic-project-interface-coordinator-v1"
DEFAULT_MAX_REPAIRS = 32
MAX_REPAIRS = 64
MAX_DIAGNOSTICS = 256


def coordinate_project_interfaces(
    rust_project_ir: Mapping[str, Any], *, max_repairs: int = DEFAULT_MAX_REPAIRS,
    max_attempts_per_item: int = 3,
) -> dict[str, Any]:
    """Diagnose project assembly conflicts without generating or accepting Rust."""
    validate_rust_project_ir(rust_project_ir)
    if (
        isinstance(max_repairs, bool) or not isinstance(max_repairs, int)
        or not 1 <= max_repairs <= MAX_REPAIRS
        or isinstance(max_attempts_per_item, bool)
        or not isinstance(max_attempts_per_item, int)
        or not 1 <= max_attempts_per_item <= 5
    ):
        raise ValueError("project repair bounds are invalid")
    diagnostics = _collect_diagnostics(rust_project_ir)
    diagnostics.sort(key=lambda item: (
        item["code"], item["entity_ids"], item["affected_module_ids"],
    ))
    diagnostic_overflow = max(0, len(diagnostics) - MAX_DIAGNOSTICS)
    published = diagnostics[:MAX_DIAGNOSTICS]
    repairs = [
        _repair_item(item, rust_project_ir, max_attempts_per_item)
        for item in published[:max_repairs]
    ]
    return {
        "schema_version": 1,
        "coordinator": COORDINATOR_ID,
        "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
        "status": "repair-required" if diagnostics else "candidate-ready",
        "diagnostics": published,
        "diagnostic_overflow_count": diagnostic_overflow,
        "project_repair_queue": {
            "schema_version": 1,
            "scope": "project",
            "max_items": max_repairs,
            "item_count": len(repairs),
            "overflow_count": max(0, len(published) - max_repairs) + diagnostic_overflow,
            "max_attempts_per_item": max_attempts_per_item,
            "items": repairs,
            "policy": {
                "assignment": "project-only",
                "allowed_output": "rust-project-ir-candidate",
                "generated_glue_allowed": False,
                "fixture_specific_shim_allowed": False,
            },
        },
        "claim_boundary": {
            "artifact_role": "project-interface-diagnostic",
            "semantic_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }


def _collect_diagnostics(ir: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    modules = {item["module_id"]: item for item in ir["modules"]}
    result.extend(_module_diagnostics(ir, modules))
    result.extend(_group_conflicts(
        ir["public_api"], "symbol",
        ("kind", "signature", "visibility"),
        "duplicate_public_symbol", "conflicting_public_api",
    ))
    result.extend(_group_conflicts(
        ir["shared_types"], "name", ("kind", "layout_sha256", "repr"),
        "duplicate_shared_type_definition", "conflicting_shared_type",
    ))
    result.extend(_group_conflicts(
        ir["global_ownership"], "symbol", ("module_id", "access"),
        "duplicate_global_owner", "conflicting_global_ownership",
    ))
    result.extend(_group_conflicts(
        ir["ffi_boundaries"], "symbol", ("direction", "abi", "link_name"),
        "duplicate_ffi_boundary", "conflicting_ffi_boundary",
    ))
    result.extend(_feature_diagnostics(ir["features"], modules))
    result.extend(_module_reference_diagnostics(ir["cfgs"], modules, "cfg"))
    result.extend(_initialization_diagnostics(ir["initialization"], modules))
    return result


def _module_diagnostics(
    ir: Mapping[str, Any], modules: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = _group_conflicts(
        ir["modules"], "rust_path", ("candidate_sha256",),
        "duplicate_module_path", "conflicting_module_path",
    )
    root = ir["crate"]["root_module_id"]
    reachable: set[str] = set()
    if root in modules:
        pending = [root]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(sorted(
                module_id for module_id, module in modules.items()
                if module.get("parent_module_id") == current
            ))
    else:
        result.append(_diagnostic("missing_root_module", [root], []))
    for module_id in sorted(set(modules) - reachable):
        result.append(_diagnostic(
            "orphan_module", [module_id], [module_id],
        ))
    return result


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
        shapes = {tuple(str(entry[field]) for field in shape_keys) for entry in entries}
        modules = sorted({
            str(module_id)
            for entry in entries
            for module_id in entry.get("module_ids", [entry.get("module_id")])
            if module_id
        })
        identities = sorted({_identity(entry) for entry in entries})
        result.append(_diagnostic(
            conflict_code if len(shapes) > 1 else duplicate_code,
            [key, *identities], modules,
        ))
    return result


def _feature_diagnostics(
    features: list[Mapping[str, Any]], modules: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result = _group_conflicts(
        features, "name", ("default", "enables", "module_ids"),
        "duplicate_feature", "conflicting_feature",
    )
    known = {str(item["feature_id"]) for item in features}
    for feature in features:
        unknown_features = sorted(set(feature["enables"]) - known)
        unknown_modules = sorted(set(feature["module_ids"]) - set(modules))
        if unknown_features:
            result.append(_diagnostic(
                "unknown_feature_dependency",
                [str(feature["feature_id"]), *unknown_features],
                list(feature["module_ids"]),
            ))
        if unknown_modules:
            result.append(_diagnostic(
                "feature_references_orphan_module",
                [str(feature["feature_id"]), *unknown_modules], unknown_modules,
            ))
    return result


def _module_reference_diagnostics(
    records: list[Mapping[str, Any]], modules: Mapping[str, Any], kind: str,
) -> list[dict[str, Any]]:
    result = []
    for record in records:
        unknown = sorted(set(record["module_ids"]) - set(modules))
        if unknown:
            result.append(_diagnostic(
                f"{kind}_references_orphan_module",
                [_identity(record), *unknown], unknown,
            ))
    return result


def _initialization_diagnostics(
    records: list[Mapping[str, Any]], modules: Mapping[str, Any],
) -> list[dict[str, Any]]:
    result = []
    by_id = {str(item["init_id"]): item for item in records}
    for record in records:
        missing = sorted(set(record["after"]) - set(by_id))
        if missing:
            result.append(_diagnostic(
                "unknown_initialization_dependency",
                [str(record["init_id"]), *missing], [str(record["module_id"])],
            ))
        if record["module_id"] not in modules:
            result.append(_diagnostic(
                "initialization_references_orphan_module",
                [str(record["init_id"]), str(record["module_id"])],
                [str(record["module_id"])],
            ))
    cyclic = _cyclic_initializers(by_id)
    if cyclic:
        result.append(_diagnostic(
            "cyclic_initialization", cyclic,
            sorted({str(by_id[item]["module_id"]) for item in cyclic}),
        ))
    return result


def _cyclic_initializers(by_id: Mapping[str, Mapping[str, Any]]) -> list[str]:
    cyclic = []
    for root in sorted(by_id):
        pending = list(by_id[root]["after"])
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == root:
                cyclic.append(root)
                break
            if current in by_id and current not in visited:
                visited.add(current)
                pending.extend(by_id[current]["after"])
    return cyclic


def _diagnostic(code: str, entity_ids: list[str], module_ids: list[str]) -> dict[str, Any]:
    payload = {
        "code": code,
        "scope": "project",
        "entity_ids": sorted(set(entity_ids)),
        "affected_module_ids": sorted(set(module_ids)),
        "random_unit_attribution": False,
    }
    return {**payload, "diagnostic_sha256": content_sha256(payload)}


def _repair_item(
    diagnostic: Mapping[str, Any], ir: Mapping[str, Any], max_attempts: int,
) -> dict[str, Any]:
    unit_by_module = {item["module_id"]: item["unit_id"] for item in ir["modules"]}
    units = sorted({
        unit_by_module[module_id]
        for module_id in diagnostic["affected_module_ids"]
        if module_id in unit_by_module
    })
    return {
        "repair_id": f"project-repair-{diagnostic['diagnostic_sha256'][:24]}",
        "scope": "project",
        "assigned_unit_id": None,
        "diagnostic_code": diagnostic["code"],
        "diagnostic_sha256": diagnostic["diagnostic_sha256"],
        "affected_module_ids": list(diagnostic["affected_module_ids"]),
        "affected_unit_ids": units,
        "max_attempts": max_attempts,
        "candidate_only": True,
    }


def _identity(record: Mapping[str, Any]) -> str:
    for key in ("declaration_id", "module_id", "feature_id", "cfg_id", "init_id"):
        if key in record:
            return str(record[key])
    return content_sha256(record)[:24]


__all__ = [
    "COORDINATOR_ID", "DEFAULT_MAX_REPAIRS", "MAX_REPAIRS",
    "coordinate_project_interfaces",
]
