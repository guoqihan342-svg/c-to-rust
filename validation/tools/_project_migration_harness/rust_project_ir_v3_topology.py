from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .migration_target_scope import validate_scc_target_scope
from .rust_project_ir_v3_topology_products import (
    derive_product_topology, project_input_occurrences, stable_topology_id,
)
from .rust_project_ir_v3_validation import module_id_for_target_candidate

def derive_rust_project_ir_v3_topology(
    build_irs: Sequence[Mapping[str, Any]], target_scopes: Mapping[str, Mapping[str, Any]],
    candidate_refs: Sequence[Mapping[str, Any]], *,
    build_ir_binding_sha256s: Mapping[str, str],
) -> dict[str, Any]:
    """Derive only topology fields from reopened BuildIR and target scopes."""
    builds = _builds(build_irs)
    build_bindings = _build_bindings(builds, build_ir_binding_sha256s)
    candidates = _candidates(candidate_refs)
    scopes = _scopes(target_scopes)
    workspace_id = stable_topology_id("workspace", {
        "build_irs": [{"semantic_sha256": semantic, "artifact_sha256": artifact}
                      for semantic, artifact in sorted(build_bindings.items())],
        "target_scopes": {key: scopes[key]["scope_sha256"] for key in sorted(scopes)},
        "candidates": [[key, candidates[key]["artifact_id"],
                        candidates[key]["source"]["sha256"]]
                       for key in sorted(candidates)],
    })
    blockers: set[tuple[str, str, str]] = set()
    targets, units, collisions = _index_builds(builds, build_bindings)
    for _ in collisions:
        _block(blockers, "build_ir_target_namespace_collision", workspace_id)
    products, product_blockers = derive_product_topology(targets)
    for code in product_blockers:
        _block(blockers, code, workspace_id)

    modules: dict[str, dict[str, Any]] = {}
    modules_by_target = {item["target_id"]: [] for item in products.values()}
    all_target_ids = set(targets)
    for unit_id in sorted(candidates):
        candidate = candidates[unit_id]
        scope = scopes.get(unit_id)
        if scope is None:
            _block(blockers, "candidate_target_scope_missing", workspace_id)
            continue
        source_ids = list(scope["source_unit_ids"])
        if any(source_id not in units for source_id in source_ids):
            _block(blockers, "candidate_source_unit_unknown", workspace_id)
            continue
        if _mixed_source_variants(source_ids, units):
            _block(blockers, "candidate_same_source_variants_mixed", workspace_id)
            continue
        reachable = set(scope["reachable_target_ids"])
        shared = set(scope["shared_reachable_target_ids"])
        if not reachable <= all_target_ids or not shared <= reachable:
            _block(blockers, "candidate_target_scope_unknown_target", workspace_id)
            continue
        common_products = shared & set(products)
        minimal = [
            raw_id for raw_id in sorted(common_products)
            if not (_ancestors(raw_id, targets) & common_products)
        ]
        if not minimal:
            _block(blockers, "candidate_common_consumer_missing", workspace_id)
            continue
        candidate_sha = str(candidate["source"]["sha256"])
        for raw_id in minimal:
            product = products[raw_id]
            module_id = module_id_for_target_candidate(
                product["namespace_id"], unit_id, candidate_sha, source_ids,
            )
            record = {
                "module_id": module_id, "package_id": product["package_id"],
                "target_id": product["target_id"],
                "target_namespace_id": product["namespace_id"],
                "rust_path": f"packages/{product['package_id']}/src/{module_id}.rs",
                "unit_id": unit_id, "source_unit_ids": source_ids,
                "candidate_sha256": candidate_sha, "visibility": "crate",
                "evidence": _evidence([product["evidence_sha256"]], [unit_id],
                                      [candidate_sha]),
            }
            previous = modules.get(module_id)
            if previous is not None and previous != record:
                _block(blockers, "candidate_module_namespace_collision", module_id,
                       entity_kind="module")
                continue
            modules[module_id] = record
            modules_by_target[product["target_id"]].append(module_id)
    for unit_id in sorted(set(scopes) - set(candidates)):
        _block(blockers, "candidate_reference_missing", workspace_id)

    global_units = sorted(candidates)
    global_shas = sorted({str(item["source"]["sha256"])
                          for item in candidates.values()})
    packages = []
    rust_targets = []
    for raw_id in sorted(products):
        product = products[raw_id]
        module_ids = sorted(set(modules_by_target[product["target_id"]]))
        if not module_ids:
            _block(blockers, "product_candidate_modules_missing",
                   product["package_id"], entity_kind="package")
        owner_units = sorted({modules[key]["unit_id"] for key in module_ids})
        owner_shas = sorted({modules[key]["candidate_sha256"] for key in module_ids})
        evidence = _evidence([product["evidence_sha256"]], owner_units or global_units,
                             owner_shas or global_shas)
        dependencies = sorted({
            products[dependency]["package_id"]
            for dependency in product["raw"].get("dependency_target_ids", [])
            if dependency in products
        })
        suffix = content_sha256({"build_ir_target_id": raw_id})[:16]
        packages.append({
            "package_id": product["package_id"], "name": f"package_{suffix}",
            "build_ir_target_id": raw_id, "product_kind": product["product_kind"],
            "dependency_package_ids": dependencies,
            "target_ids": [product["target_id"]], "module_ids": module_ids,
            "evidence": evidence,
        })
        rust_targets.append({
            "target_id": product["target_id"], "package_id": product["package_id"],
            "name": f"target_{suffix}", "kind": product["rust_kind"],
            "crate_types": list(product["crate_types"]),
            "build_ir_target_id": raw_id, "module_ids": module_ids,
            "input_occurrences": project_input_occurrences(
                product["raw"], products,
            ),
            "ordered_link_arguments": list(product["raw"].get(
                "ordered_link_arguments", [])),
            "evidence": evidence,
        })
    package_ids = sorted(item["package_id"] for item in packages)
    build_shas = sorted(build_bindings.values())
    workspace = {
        "workspace_id": workspace_id, "resolver": "2",
        "package_ids": package_ids, "default_package_ids": package_ids,
        "evidence": _evidence(build_shas, global_units, global_shas),
    }
    canonical_blockers = [
        {"code": code, "entity_kind": kind, "entity_id": entity_id}
        for code, kind, entity_id in sorted(blockers)
    ]
    return {
        "workspace": workspace,
        "packages": sorted(packages, key=lambda item: item["package_id"]),
        "targets": sorted(rust_targets, key=lambda item: item["target_id"]),
        "modules": sorted(modules.values(), key=lambda item: item["module_id"]),
        "topology_status": "blocked" if canonical_blockers else "ready",
        "topology_blockers": canonical_blockers,
    }

def _builds(values: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
        raise ValueError("rust_project_ir_v3_topology_build_irs_invalid")
    result = []
    for value in values:
        if not isinstance(value, Mapping) or not _sha(value.get("semantic_sha256")):
            raise ValueError("rust_project_ir_v3_topology_build_ir_invalid")
        if (not isinstance(value.get("targets"), list)
                or not isinstance(value.get("translation_units"), list)):
            raise ValueError("rust_project_ir_v3_topology_build_ir_invalid")
        result.append(value)
    result.sort(key=lambda item: str(item["semantic_sha256"]))
    if len(result) != len({item["semantic_sha256"] for item in result}):
        raise ValueError("rust_project_ir_v3_topology_build_irs_invalid")
    return result

def _build_bindings(
    builds: Sequence[Mapping[str, Any]], values: Mapping[str, str],
) -> dict[str, str]:
    semantics = {str(item["semantic_sha256"]) for item in builds}
    if (
        not isinstance(values, Mapping) or set(values) != semantics
        or any(not _sha(item) for item in values.values())
        or len(set(values.values())) != len(values)
    ):
        raise ValueError("rust_project_ir_v3_topology_build_binding_sha256s_invalid")
    return dict(values)

def _candidates(values: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for value in values:
        source = value.get("source") if isinstance(value, Mapping) else None
        unit_id = value.get("unit_id") if isinstance(value, Mapping) else None
        if (
            not isinstance(unit_id, str) or not unit_id or unit_id in result
            or not isinstance(value.get("artifact_id"), str)
            or not isinstance(source, Mapping) or not _sha(source.get("sha256"))
        ):
            raise ValueError("rust_project_ir_v3_topology_candidate_refs_invalid")
        result[unit_id] = value
    if not result:
        raise ValueError("rust_project_ir_v3_topology_candidate_refs_invalid")
    return result

def _scopes(values: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if not isinstance(values, Mapping):
        raise ValueError("rust_project_ir_v3_topology_target_scopes_invalid")
    result = {}
    for unit_id in sorted(values):
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError("rust_project_ir_v3_topology_target_scopes_invalid")
        try:
            result[unit_id] = validate_scc_target_scope(values[unit_id])
        except ValueError as error:
            raise ValueError("rust_project_ir_v3_topology_target_scope_invalid") from error
    return result

def _index_builds(builds: Sequence[Mapping[str, Any]], bindings: Mapping[str, str]):
    targets: dict[str, dict[str, Any]] = {}
    units: dict[str, Mapping[str, Any]] = {}
    collisions: set[str] = set()
    for build in builds:
        semantic_sha = str(build["semantic_sha256"])
        for target in build["targets"]:
            target_id = target.get("target_id") if isinstance(target, Mapping) else None
            if not isinstance(target_id, str) or not target_id:
                raise ValueError("rust_project_ir_v3_topology_build_target_invalid")
            if target_id in targets or target_id in collisions:
                targets.pop(target_id, None)
                collisions.add(target_id)
            else:
                targets[target_id] = {
                    "target": target, "build": build,
                    "semantic_sha256": semantic_sha,
                    "evidence_sha256": bindings[semantic_sha],
                }
        for unit in build["translation_units"]:
            unit_id = unit.get("unit_id") if isinstance(unit, Mapping) else None
            if not isinstance(unit_id, str) or not unit_id or unit_id in units:
                raise ValueError("rust_project_ir_v3_topology_build_unit_collision")
            units[unit_id] = unit
    return targets, units, collisions

def _ancestors(target_id: str, targets: Mapping[str, Any]) -> set[str]:
    pending = list(targets[target_id]["target"].get("dependency_target_ids", []))
    result = set()
    while pending:
        current = str(pending.pop())
        if current in result or current not in targets:
            continue
        result.add(current)
        pending.extend(targets[current]["target"].get("dependency_target_ids", []))
    return result

def _mixed_source_variants(source_ids: Sequence[str], units: Mapping[str, Any]) -> bool:
    identities = []
    for source_id in source_ids:
        source = units[source_id].get("source")
        if not isinstance(source, Mapping) or not isinstance(source.get("path"), str):
            raise ValueError("rust_project_ir_v3_topology_source_binding_invalid")
        identities.append((str(source["path"]), source.get("sha256")))
    return len(identities) != len(set(identities))

def _evidence(build_shas, unit_ids, candidate_shas) -> dict[str, list[str]]:
    return {"build_ir_sha256s": sorted(set(build_shas)),
            "dag_unit_ids": sorted(set(unit_ids)),
            "candidate_sha256s": sorted(set(candidate_shas))}

def _block(
    blockers: set[tuple[str, str, str]], code: str, entity_id: str, *,
    entity_kind: str = "workspace",
) -> None:
    blockers.add((code, entity_kind, entity_id))

def _sha(value: Any) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))

__all__ = ["derive_rust_project_ir_v3_topology"]
