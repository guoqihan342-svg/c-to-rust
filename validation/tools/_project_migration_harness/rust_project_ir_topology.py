from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_native import derived_interface_completeness


def derive_project_interface_plan(
    *, build_irs: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    dependencies: Mapping[str, Sequence[str]],
    native_link_requirements: Sequence[Mapping[str, Any]],
    compilation_facts_complete: bool,
) -> dict[str, Any]:
    """Project the smallest topology justified by bound build and source facts."""
    ordered = [dict(item) for item in candidates]
    unit_ids = [str(item["unit_id"]) for item in ordered]
    if len(unit_ids) != len(set(unit_ids)) or set(unit_ids) != set(dependencies):
        raise ValueError("rust_project_ir_topology_candidate_domain_invalid")
    crate_id = "migrated-" + content_sha256({
        "build_ir": sorted(str(item.get("semantic_sha256")) for item in build_irs),
        "candidates": sorted(str(item["candidate_sha256"]) for item in ordered),
    })[:16]
    roles = {str(item["unit_id"]): _candidate_role(item["source_facts"])
             for item in ordered}
    topology, blockers = _verified_topology(
        build_irs, ordered, dependencies, roles, crate_id,
    )
    if not isinstance(compilation_facts_complete, bool):
        raise ValueError("rust_project_ir_compilation_facts_status_invalid")
    if not compilation_facts_complete:
        topology = None
        blockers = sorted(set([
            *blockers, "c_compilation_facts_incomplete",
        ]))
    unresolved = {
        section
        for item in ordered
        for section in item["source_facts"]["unresolved_sections"]
    }
    verified = topology is not None
    if not verified:
        unresolved.update({"nested-module-multi-target", "target-matrix"})
        topology = [_target(
            kind="library", name=crate_id.replace("-", "_"),
            root_path="src/lib.rs", root_unit_id=None,
            module_unit_ids=unit_ids, build_ir_target_ids=[],
        )]
    elif "nested-module-multi-target" in unresolved:
        verified = False
        blockers = sorted(set([*blockers, "candidate_module_topology_unresolved"]))
        unresolved.add("target-matrix")
    target_kinds = sorted({str(item["kind"]) for item in topology})
    crate_types = ["rlib", "staticlib"] if verified else ["rlib"]
    return {
        "crate_id": crate_id,
        "crate_types": crate_types,
        "targets": target_kinds,
        "target_topology": topology,
        "target_topology_sha256": content_sha256(topology),
        "topology_verified": verified,
        "topology_blockers": blockers,
        "interface_completeness": derived_interface_completeness(
            sorted(unresolved), native_link_requirements,
        ),
    }


def _candidate_role(facts: Mapping[str, Any]) -> str:
    binary = facts.get("binary_entry_count")
    tests = facts.get("test_entry_count")
    if binary == 0 and tests == 0:
        return "library"
    if binary == 1 and tests == 0:
        return "bin"
    if binary == 0 and isinstance(tests, int) and not isinstance(tests, bool) and tests > 0:
        return "test"
    return "ambiguous"


def _verified_topology(
    build_irs: Sequence[Mapping[str, Any]],
    candidates: list[dict[str, Any]],
    dependencies: Mapping[str, Sequence[str]],
    roles: Mapping[str, str],
    crate_id: str,
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    blockers: list[str] = []
    if len(build_irs) != 1:
        blockers.append("build_ir_target_domain_ambiguous")
        return None, blockers
    build_ir = build_irs[0]
    if build_ir.get("status") != "ready" or build_ir.get("boundaries") != []:
        blockers.append("build_ir_target_domain_incomplete")
    targets = build_ir.get("targets")
    if not isinstance(targets, list) or not targets:
        blockers.append("build_ir_target_facts_missing")
        return None, sorted(set(blockers))
    by_kind = {
        kind: [item for item in targets if isinstance(item, Mapping) and item.get("kind") == kind]
        for kind in ("object", "archive", "link")
    }
    if len(by_kind["archive"]) != 1:
        blockers.append("build_ir_library_target_ambiguous")
    if not by_kind["object"]:
        blockers.append("build_ir_object_targets_missing")
    if len(by_kind["link"]) > 1:
        blockers.append("build_ir_binary_target_ambiguous")
    if len(by_kind["object"]) + len(by_kind["archive"]) + len(by_kind["link"]) != len(targets):
        blockers.append("build_ir_target_kind_unsupported")
    library_units = [unit for unit in roles if roles[unit] == "library"]
    binary_units = [unit for unit in roles if roles[unit] == "bin"]
    test_units = [unit for unit in roles if roles[unit] == "test"]
    if not library_units:
        blockers.append("candidate_library_modules_missing")
    if len(binary_units) != len(by_kind["link"]) or len(binary_units) > 1:
        blockers.append("candidate_binary_target_cardinality_mismatch")
    if len(test_units) > 1:
        blockers.append("candidate_test_target_ambiguous")
    if any(role == "ambiguous" for role in roles.values()):
        blockers.append("candidate_target_role_ambiguous")
    if not _candidate_dependencies_supported(dependencies, roles):
        blockers.append("candidate_target_dependency_unsupported")
    if not blockers and not _build_graph_supported(targets):
        blockers.append("build_ir_target_graph_unsupported")
    if blockers:
        return None, sorted(set(blockers))
    archive = by_kind["archive"][0]
    result = [_target(
        kind="library", name=crate_id.replace("-", "_"),
        root_path="src/lib.rs", root_unit_id=None,
        module_unit_ids=library_units,
        build_ir_target_ids=[str(archive["target_id"])],
    )]
    if binary_units:
        link = by_kind["link"][0]
        name = "bin_" + content_sha256({
            "build_ir_target_id": str(link["target_id"]),
        })[:24]
        result.append(_target(
            kind="bin", name=name, root_path=f"src/bin/{name}.rs",
            root_unit_id=binary_units[0],
            module_unit_ids=[*library_units, binary_units[0]],
            build_ir_target_ids=[str(link["target_id"])],
        ))
    if test_units:
        root = next(item for item in candidates if item["unit_id"] == test_units[0])
        name = "test_" + str(root["candidate_sha256"])[:24]
        result.append(_target(
            kind="test", name=name, root_path=f"tests/{name}.rs",
            root_unit_id=test_units[0],
            module_unit_ids=[*library_units, test_units[0]],
            build_ir_target_ids=[],
        ))
    return result, []


def _candidate_dependencies_supported(
    dependencies: Mapping[str, Sequence[str]], roles: Mapping[str, str],
) -> bool:
    for unit_id, required in dependencies.items():
        role = roles.get(unit_id)
        allowed = {item for item, candidate_role in roles.items() if candidate_role == "library"}
        if role not in {"library", "bin", "test"} or not set(required) <= allowed:
            return False
    return True


def _build_graph_supported(targets: Sequence[Mapping[str, Any]]) -> bool:
    by_id = {str(item["target_id"]): item for item in targets}
    archives = [str(item["target_id"]) for item in targets if item["kind"] == "archive"]
    links = [str(item["target_id"]) for item in targets if item["kind"] == "link"]
    objects = {str(item["target_id"]) for item in targets if item["kind"] == "object"}
    archive_ancestors = _ancestors(archives[0], by_id)
    if not objects & archive_ancestors:
        return False
    covered = set(archive_ancestors)
    for link in links:
        ancestors = _ancestors(link, by_id)
        if archives[0] not in ancestors:
            return False
        covered.update(ancestors)
    return objects <= covered


def _ancestors(target_id: str, targets: Mapping[str, Mapping[str, Any]]) -> set[str]:
    pending = list(targets[target_id].get("dependency_target_ids", []))
    result: set[str] = set()
    while pending:
        current = str(pending.pop())
        if current in result:
            continue
        result.add(current)
        pending.extend(targets[current].get("dependency_target_ids", []))
    return result


def _target(
    *, kind: str, name: str, root_path: str, root_unit_id: str | None,
    module_unit_ids: Sequence[str], build_ir_target_ids: Sequence[str],
) -> dict[str, Any]:
    core = {
        "kind": kind,
        "name": name,
        "root_path": root_path,
        "root_unit_id": root_unit_id,
        "module_unit_ids": list(module_unit_ids),
        "build_ir_target_ids": sorted(build_ir_target_ids),
    }
    return {"target_id": "cargo-target-" + content_sha256(core)[:24], **core}


__all__ = ["derive_project_interface_plan"]
