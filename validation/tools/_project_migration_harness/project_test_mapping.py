from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


_CLAIM_BOUNDARY = {
    "semantic_gate": False, "translation_coverage_numerator": 0,
}


def derive_project_test_mapping(
    inventory: Mapping[str, Any], rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    try:
        validate_rust_project_ir_v3(rust_project_ir)
    except (TypeError, ValueError):
        return _blocked(
            inventory, rust_project_ir, "project_test_rust_project_ir_v3_invalid",
        )
    if rust_project_ir.get("topology_status") != "ready":
        return _blocked(
            inventory, rust_project_ir, "project_test_rust_topology_blocked",
        )
    tests = inventory.get("tests")
    if inventory.get("status") != "ready" or not isinstance(tests, list) or not tests:
        return _blocked(
            inventory, rust_project_ir, "project_test_inventory_not_ready",
        )
    packages = _index(rust_project_ir.get("packages"), "package_id")
    targets = _targets_by_build_id(rust_project_ir.get("targets"))
    binary_name_counts: dict[str, int] = {}
    for target in rust_project_ir["targets"]:
        if target.get("kind") == "bin":
            name = str(target.get("name"))
            binary_name_counts[name] = binary_name_counts.get(name, 0) + 1
    grouped = _tests_by_source_target(tests)
    used_rust_targets: set[str] = set()
    processed_groups = 0
    for source_target_id, source_tests in sorted(grouped.items()):
        processed_groups += 1
        matches = targets.get(source_target_id, [])
        if len(matches) != 1:
            blockers.append({
                "code": "project_test_rust_target_missing_or_ambiguous",
                "source_target_id": source_target_id,
            })
            continue
        target = matches[0]
        package = packages.get(str(target.get("package_id")))
        target_id = str(target.get("target_id"))
        if (
            target.get("kind") != "bin" or target.get("crate_types") != ["bin"]
            or package is None or package.get("product_kind") != "executable"
            or package.get("build_ir_target_id") != source_target_id
            or binary_name_counts.get(str(target.get("name"))) != 1
            or target_id in used_rust_targets
        ):
            blockers.append({
                "code": "project_test_rust_executable_binding_invalid",
                "source_target_id": source_target_id,
            })
            continue
        used_rust_targets.add(target_id)
        mappings.append({
            "source_target_id": source_target_id,
            "source_executable_paths": sorted({
                str(item["source_executable"]["path"]) for item in source_tests
            }),
            "test_ids": sorted(str(item["test_id"]) for item in source_tests),
            "rust_package_id": str(package["package_id"]),
            "rust_package_name": str(package["name"]),
            "rust_target_id": target_id,
            "rust_target_name": str(target["name"]),
        })
    if processed_groups != len(grouped):
        blockers.append({"code": "project_test_mapping_closure_drifted"})
    covered_source_targets = set(grouped)
    executable_source_targets = {
        str(package["build_ir_target_id"])
        for package in packages.values()
        if package.get("product_kind") == "executable"
    }
    for source_target_id in sorted(
        executable_source_targets - covered_source_targets
    ):
        blockers.append({
            "code": "project_test_executable_target_uncovered",
            "source_target_id": source_target_id,
        })
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-mapping",
        "status": "blocked" if blockers else "ready",
        "inventory_sha256": inventory.get("inventory_sha256"),
        "rust_project_ir_sha256": rust_project_ir.get("ir_sha256"),
        "mappings": mappings,
        "blockers": blockers,
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    payload["mapping_sha256"] = content_sha256(payload)
    return payload


def _index(value: Any, key: str) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("project_test_mapping_ir_collection_invalid")
    result = {}
    for item in value:
        identity = item.get(key) if isinstance(item, Mapping) else None
        if not isinstance(identity, str) or not identity or identity in result:
            raise ValueError("project_test_mapping_ir_collection_invalid")
        result[identity] = item
    return result


def _targets_by_build_id(value: Any) -> dict[str, list[Mapping[str, Any]]]:
    if not isinstance(value, list):
        raise ValueError("project_test_mapping_ir_collection_invalid")
    result: dict[str, list[Mapping[str, Any]]] = {}
    for item in value:
        identity = item.get("build_ir_target_id") if isinstance(item, Mapping) else None
        if not isinstance(identity, str) or not identity:
            raise ValueError("project_test_mapping_ir_collection_invalid")
        result.setdefault(identity, []).append(item)
    return result


def _tests_by_source_target(
    tests: list[Any],
) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    seen: set[str] = set()
    for test in tests:
        test_id = test.get("test_id") if isinstance(test, Mapping) else None
        target_id = test.get("source_target_id") if isinstance(test, Mapping) else None
        executable = test.get("source_executable") if isinstance(test, Mapping) else None
        if (
            not isinstance(test_id, str) or not test_id or test_id in seen
            or not isinstance(target_id, str) or not target_id
            or not isinstance(executable, Mapping)
            or not isinstance(executable.get("path"), str)
        ):
            raise ValueError("project_test_inventory_record_invalid")
        seen.add(test_id)
        result.setdefault(target_id, []).append(test)
    return result


def _blocked(
    inventory: Mapping[str, Any], rust_project_ir: Mapping[str, Any], code: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1, "artifact_kind": "project-test-mapping",
        "status": "blocked",
        "inventory_sha256": inventory.get("inventory_sha256"),
        "rust_project_ir_sha256": rust_project_ir.get("ir_sha256"),
        "mappings": [], "blockers": [{"code": code}],
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    payload["mapping_sha256"] = content_sha256(payload)
    return payload


__all__ = ["derive_project_test_mapping"]
