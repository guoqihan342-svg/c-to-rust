from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .project_test_completeness_schema import (
    CLAIM_BOUNDARY, COUNT_KEYS, MAPPING_KEYS, TOP_KEYS,
)
from .project_test_mapping import derive_project_test_mapping
from .rust_project_ir_v3_validation import validate_rust_project_ir_v3


def derive_project_test_completeness(
    inventory: Mapping[str, Any], mapping: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove exact test-case closure for the direct-executable adapter path."""
    try:
        validate_rust_project_ir_v3(rust_project_ir)
    except (TypeError, ValueError):
        return _blocked(
            inventory, mapping, rust_project_ir,
            "project_test_completeness_rust_project_ir_invalid",
        )
    try:
        canonical_mapping = derive_project_test_mapping(inventory, rust_project_ir)
    except (KeyError, TypeError, ValueError):
        return _blocked(
            inventory, mapping, rust_project_ir,
            "project_test_completeness_input_invalid",
        )
    if canonical_mapping.get("status") != "ready":
        return _blocked(
            inventory, mapping, rust_project_ir,
            "project_test_completeness_canonical_mapping_blocked",
        )
    try:
        result = _derive_closure(inventory, mapping, rust_project_ir)
    except (KeyError, TypeError, ValueError):
        return _blocked(
            inventory, mapping, rust_project_ir,
            "project_test_completeness_input_invalid",
        )
    if mapping != canonical_mapping:
        result["blockers"].append({
            "code": "project_test_mapping_derivation_drifted",
        })
    return _finish(result)


def validate_project_test_completeness(
    value: Mapping[str, Any], inventory: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> None:
    """Reopen the closure from persisted inventory and mapping artifacts."""
    if (
        not isinstance(value, Mapping) or set(value) != TOP_KEYS
        or value.get("schema_version") != 1
        or value.get("artifact_kind") != "project-test-completeness"
        or value.get("status") != "ready"
        or value.get("blockers") != []
        or value.get("claim_boundary") != CLAIM_BOUNDARY
        or value.get("completeness_sha256") != content_sha256({
            key: item for key, item in value.items()
            if key != "completeness_sha256"
        })
    ):
        raise ValueError("project_test_completeness_invalid")
    expected = _derive_closure(
        inventory, mapping,
        {"ir_sha256": value.get("rust_project_ir_sha256")},
    )
    expected = _finish(expected)
    if value != expected:
        raise ValueError("project_test_completeness_derivation_drifted")


def _derive_closure(
    inventory: Mapping[str, Any], mapping: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any],
) -> dict[str, Any]:
    tests = inventory.get("tests")
    mappings = mapping.get("mappings")
    if (
        inventory.get("status") != "ready" or not isinstance(tests, list)
        or not tests or mapping.get("status") != "ready"
        or not isinstance(mappings, list) or not mappings
        or mapping.get("inventory_sha256") != inventory.get("inventory_sha256")
        or mapping.get("rust_project_ir_sha256")
        != rust_project_ir.get("ir_sha256")
        or mapping.get("mapping_sha256") != content_sha256({
            key: item for key, item in mapping.items() if key != "mapping_sha256"
        })
    ):
        raise ValueError("project_test_completeness_input_invalid")

    expected_cases: list[str] = []
    expected_targets: list[str] = []
    expected_cases_by_target: dict[str, list[str]] = {}
    expected_paths_by_target: dict[str, set[str]] = {}
    for test in tests:
        if not isinstance(test, Mapping):
            raise ValueError("project_test_completeness_inventory_invalid")
        test_id, target_id = test.get("test_id"), test.get("source_target_id")
        executable = test.get("source_executable")
        executable_path = (
            executable.get("path") if isinstance(executable, Mapping) else None
        )
        if (
            not isinstance(test_id, str) or not test_id
            or not isinstance(target_id, str) or not target_id
            or not isinstance(executable_path, str) or not executable_path
        ):
            raise ValueError("project_test_completeness_inventory_invalid")
        expected_cases.append(test_id)
        expected_targets.append(target_id)
        expected_cases_by_target.setdefault(target_id, []).append(test_id)
        expected_paths_by_target.setdefault(target_id, set()).add(executable_path)
    if len(set(expected_cases)) != len(expected_cases):
        raise ValueError("project_test_completeness_inventory_invalid")

    mapped_cases: list[str] = []
    mapped_targets: list[str] = []
    rust_targets: list[str] = []
    mapped_cases_by_target: dict[str, list[str]] = {}
    mapped_paths_by_target: dict[str, set[str]] = {}
    zero_test_mappings = 0
    mapping_schema_invalid = False
    for item in mappings:
        if not isinstance(item, Mapping):
            mapping_schema_invalid = True
            continue
        if set(item) != MAPPING_KEYS:
            mapping_schema_invalid = True
        test_ids = item.get("test_ids")
        executable_paths = item.get("source_executable_paths")
        source_target_id = item.get("source_target_id")
        rust_target_id = item.get("rust_target_id")
        text_fields = (
            item.get("rust_package_id"), item.get("rust_package_name"),
            item.get("rust_target_name"),
        )
        if not isinstance(test_ids, list):
            mapping_schema_invalid = True
            continue
        if not test_ids:
            zero_test_mappings += 1
        if any(not isinstance(test_id, str) or not test_id for test_id in test_ids):
            mapping_schema_invalid = True
            continue
        if test_ids != sorted(test_ids):
            mapping_schema_invalid = True
        if (
            not isinstance(executable_paths, list) or not executable_paths
            or any(not isinstance(path, str) or not path for path in executable_paths)
            or executable_paths != sorted(set(executable_paths))
            or any(not isinstance(field, str) or not field for field in text_fields)
        ):
            mapping_schema_invalid = True
        if not isinstance(source_target_id, str) or not source_target_id:
            mapping_schema_invalid = True
            continue
        if not isinstance(rust_target_id, str) or not rust_target_id:
            mapping_schema_invalid = True
            continue
        mapped_cases.extend(test_ids)
        mapped_targets.append(source_target_id)
        rust_targets.append(rust_target_id)
        mapped_cases_by_target.setdefault(source_target_id, []).extend(test_ids)
        if isinstance(executable_paths, list) and all(
            isinstance(path, str) and path for path in executable_paths
        ):
            mapped_paths_by_target.setdefault(source_target_id, set()).update(
                executable_paths,
            )

    expected_case_set, mapped_case_set = set(expected_cases), set(mapped_cases)
    expected_target_set, mapped_target_set = set(expected_targets), set(mapped_targets)
    case_counts = Counter(mapped_cases)
    source_target_counts = Counter(mapped_targets)
    rust_target_counts = Counter(rust_targets)
    missing_cases = expected_case_set - mapped_case_set
    extra_cases = mapped_case_set - expected_case_set
    duplicate_cases = sum(count - 1 for count in case_counts.values() if count > 1)
    missing_targets = expected_target_set - mapped_target_set
    extra_targets = mapped_target_set - expected_target_set
    duplicate_rust_targets = sum(
        count - 1 for count in rust_target_counts.values() if count > 1
    )
    duplicate_source_targets = sum(
        count - 1 for count in source_target_counts.values() if count > 1
    )
    source_target_binding_drifts = sum(
        1 for target_id in expected_target_set | mapped_target_set
        if (
            sorted(expected_cases_by_target.get(target_id, []))
            != sorted(mapped_cases_by_target.get(target_id, []))
            or expected_paths_by_target.get(target_id, set())
            != mapped_paths_by_target.get(target_id, set())
        )
    )
    counts = {
        "inventory_case_count": len(expected_cases),
        "mapped_case_count": len(mapped_cases),
        "inventory_target_count": len(expected_target_set),
        "mapped_target_count": len(mapped_targets),
        "silent_skip_count": len(missing_cases),
        "zero_test_mapping_count": zero_test_mappings,
        "required_test_omission_count": len(missing_cases),
        "extra_mapped_test_count": len(extra_cases),
        "duplicate_mapped_test_count": duplicate_cases,
        "required_target_omission_count": len(missing_targets),
        "extra_mapped_target_count": len(extra_targets),
        "duplicate_source_target_binding_count": duplicate_source_targets,
        "source_target_binding_drift_count": source_target_binding_drifts,
        "duplicate_rust_target_binding_count": duplicate_rust_targets,
    }
    blockers = []
    checks = (
        (mapping_schema_invalid, "project_test_mapping_schema_invalid"),
        (bool(missing_cases), "project_test_required_case_omitted"),
        (bool(extra_cases), "project_test_extra_mapped_case"),
        (duplicate_cases > 0, "project_test_case_mapped_multiple_times"),
        (zero_test_mappings > 0, "project_test_zero_case_mapping"),
        (bool(missing_targets), "project_test_required_target_omitted"),
        (bool(extra_targets), "project_test_extra_mapped_target"),
        (
            duplicate_source_targets > 0,
            "project_test_source_target_bound_multiple_times",
        ),
        (
            source_target_binding_drifts > 0,
            "project_test_source_target_binding_drifted",
        ),
        (
            duplicate_rust_targets > 0,
            "project_test_rust_target_bound_multiple_times",
        ),
    )
    for failed, code in checks:
        if failed:
            blockers.append({"code": code})
    return {
        "schema_version": 1,
        "artifact_kind": "project-test-completeness",
        "status": "blocked" if blockers else "ready",
        "inventory_sha256": inventory.get("inventory_sha256"),
        "mapping_sha256": mapping.get("mapping_sha256"),
        "rust_project_ir_sha256": rust_project_ir.get("ir_sha256"),
        "case_ids": sorted(expected_case_set),
        "source_target_ids": sorted(expected_target_set),
        "counts": counts,
        "blockers": blockers,
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }


def _finish(value: dict[str, Any]) -> dict[str, Any]:
    blockers = {
        str(item.get("code")): {"code": str(item.get("code"))}
        for item in value.get("blockers", []) if isinstance(item, Mapping)
    }
    value["blockers"] = [blockers[key] for key in sorted(blockers)]
    value["status"] = "blocked" if value["blockers"] else "ready"
    value["completeness_sha256"] = content_sha256(value)
    return value


def _blocked(
    inventory: Mapping[str, Any], mapping: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any], code: str,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-completeness",
        "status": "blocked",
        "inventory_sha256": inventory.get("inventory_sha256"),
        "mapping_sha256": mapping.get("mapping_sha256"),
        "rust_project_ir_sha256": rust_project_ir.get("ir_sha256"),
        "case_ids": [], "source_target_ids": [],
        "counts": {key: 0 for key in sorted(COUNT_KEYS)},
        "blockers": [{"code": code}],
        "claim_boundary": dict(CLAIM_BOUNDARY),
    }
    payload["completeness_sha256"] = content_sha256(payload)
    return payload


__all__ = [
    "derive_project_test_completeness", "validate_project_test_completeness",
]
