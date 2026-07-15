from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .ledger_security import assert_no_semantic_claims
from .project_repair_context import (
    validate_project_repair_context, visible_record_ids,
)
from .runtime_security import assert_model_payload_safe
from .rust_project_ir import build_rust_project_ir
from .rust_project_ir_validation import validate_rust_project_ir


MAX_PROJECT_REPAIR_OPERATIONS = 32
_COMMON = {
    "schema_version", "run_id", "role", "project_repair_queue_sha256",
    "repair_id", "attempt_id", "effective_input_sha256",
    "base_rust_project_ir_sha256", "context_sha256", "operations",
}
_IDENTITIES = {
    "modules": "module_id", "public_api": "declaration_id",
    "shared_types": "declaration_id", "global_ownership": "declaration_id",
    "initialization": "init_id", "ffi_boundaries": "declaration_id",
    "cfgs": "cfg_id", "features": "feature_id",
    "unsafe_obligations": "obligation_id",
}
_MUTABLE = {
    "modules": {"parent_module_id", "rust_path", "visibility"},
    "public_api": {"module_id", "symbol", "kind", "signature", "visibility"},
    "shared_types": {"module_id", "name", "kind", "layout_sha256", "repr"},
    "global_ownership": {"module_id", "symbol", "access"},
    "initialization": {"module_id", "function", "phase", "after"},
    "ffi_boundaries": {"module_id", "symbol", "direction", "abi", "link_name"},
    "cfgs": {"expression", "module_ids"},
    "features": {"name", "default", "enables", "module_ids"},
    "unsafe_obligations": {"module_id", "kind", "reason_code"},
}


def normalize_project_repair_response(
    request: Mapping[str, Any], response: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(response, Mapping) or set(response) != _COMMON:
        raise ValueError("project repair response fields are invalid")
    expected = {
        "schema_version": 1, "run_id": request.get("run_id"),
        "role": "project-repairer",
        "project_repair_queue_sha256": request.get("project_repair_queue_sha256"),
        "repair_id": request.get("repair_id"),
        "attempt_id": request.get("execution_binding", {}).get("attempt_id"),
        "effective_input_sha256": request.get("effective_input_sha256"),
        "base_rust_project_ir_sha256": request.get("base_rust_project_ir", {}).get(
            "ir_sha256"
        ),
        "context_sha256": request.get("project_repair_context", {}).get(
            "context_sha256"
        ),
    }
    if any(response.get(key) != value for key, value in expected.items()):
        raise ValueError("project repair response changed its request binding")
    operations = response.get("operations")
    if (
        not isinstance(operations, list) or not operations
        or len(operations) > MAX_PROJECT_REPAIR_OPERATIONS
    ):
        raise ValueError("project repair operations are outside their bound")
    normalized = [_normalize_operation(item) for item in operations]
    identities = [(item["section"], item["record_id"]) for item in normalized]
    if len(set(identities)) != len(identities):
        raise ValueError("project repair operations target one record more than once")
    result = {**expected, "operations": normalized}
    assert_no_semantic_claims(result, "project_repair_response")
    assert_model_payload_safe(result, "project_repair_response")
    return result


def apply_project_repair_operations(
    base_ir: Mapping[str, Any], context: Mapping[str, Any],
    normalized_response: Mapping[str, Any],
) -> dict[str, Any]:
    validate_rust_project_ir(base_ir)
    safe_context = validate_project_repair_context(context)
    if (
        normalized_response.get("base_rust_project_ir_sha256") != base_ir["ir_sha256"]
        or safe_context["base_rust_project_ir_sha256"] != base_ir["ir_sha256"]
        or normalized_response.get("context_sha256") != safe_context["context_sha256"]
    ):
        raise ValueError("project repair patch changed its base IR/context binding")
    visible = visible_record_ids(safe_context)
    affected_modules = set(safe_context["diagnostic"]["affected_module_ids"])
    diagnostic_entities = set(safe_context["diagnostic"]["entity_ids"])
    sections = {
        name: json.loads(json.dumps(base_ir[name], ensure_ascii=True))
        for name in _IDENTITIES
    }
    for operation in normalized_response["operations"]:
        section = operation["section"]
        record_id = operation["record_id"]
        if record_id not in visible[section]:
            raise ValueError("project repair operation targets a withheld record")
        if record_id not in diagnostic_entities:
            raise ValueError("project repair operation targets an unrelated record")
        identity = _IDENTITIES[section]
        index = next(
            (offset for offset, item in enumerate(sections[section])
             if item[identity] == record_id),
            None,
        )
        if index is None:
            raise ValueError("project repair operation target is absent from base IR")
        _assert_record_scope(sections[section][index], affected_modules)
        if operation["action"] == "remove":
            sections[section].pop(index)
            continue
        changes = operation["changes"]
        _assert_module_scope(changes, affected_modules)
        sections[section][index].update(changes)
    candidate = build_rust_project_ir(
        migration_dag_ref=base_ir["bindings"]["migration_dag"],
        build_ir_refs=base_ir["bindings"]["build_ir"],
        candidate_refs=base_ir["bindings"]["candidates"],
        crate=base_ir["crate"],
        native_link_requirements=base_ir["native_link_requirements"],
        native_link_plans=base_ir["native_link_plans"],
        **sections,
    )
    if candidate["ir_sha256"] == base_ir["ir_sha256"]:
        raise ValueError("project repair operations produced no IR change")
    return candidate


def _normalize_operation(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "section", "action", "record_id", "changes",
    }:
        raise ValueError("project repair operation fields are invalid")
    section = value.get("section")
    action = value.get("action")
    record_id = value.get("record_id")
    changes = value.get("changes")
    if section not in _IDENTITIES or action not in {"replace", "remove"}:
        raise ValueError("project repair operation kind is invalid")
    if not isinstance(record_id, str) or not record_id or len(record_id) > 512:
        raise ValueError("project repair operation record_id is invalid")
    if not isinstance(changes, Mapping):
        raise ValueError("project repair operation changes must be an object")
    if action == "remove" and changes:
        raise ValueError("project repair remove operation cannot carry changes")
    if action == "replace" and (not changes or set(changes) - _MUTABLE[str(section)]):
        raise ValueError("project repair replace fields are not allowlisted")
    normalized = json.loads(json.dumps(dict(changes), ensure_ascii=True, sort_keys=True))
    return {
        "section": str(section), "action": str(action),
        "record_id": record_id, "changes": normalized,
    }


def _assert_module_scope(changes: Mapping[str, Any], affected: set[str]) -> None:
    module_id = changes.get("module_id")
    if module_id is not None and module_id not in affected:
        raise ValueError("project repair operation moved a record outside affected modules")
    module_ids = changes.get("module_ids")
    if module_ids is not None and (
        not isinstance(module_ids, list) or not set(module_ids) <= affected
    ):
        raise ValueError("project repair operation changed unrelated module bindings")


def _assert_record_scope(record: Mapping[str, Any], affected: set[str]) -> None:
    module_id = record.get("module_id")
    if module_id is not None and module_id not in affected:
        raise ValueError("project repair operation targets an unrelated module")
    module_ids = record.get("module_ids")
    if module_ids is not None and (
        not isinstance(module_ids, list) or not set(module_ids) <= affected
    ):
        raise ValueError("project repair operation targets unrelated module bindings")


__all__ = [
    "MAX_PROJECT_REPAIR_OPERATIONS", "apply_project_repair_operations",
    "normalize_project_repair_response",
]
