from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .project_repair_context_native import (
    NATIVE_LINK_FIELD,
    context_allowed_output,
    native_link_planning,
    validate_native_link_planning,
)
from .project_repair_context_verifier import (
    diagnostic_keys,
    validate_verifier_diagnostic,
    verifier_model_detail,
)
from .project_interface_contract import validate_coordinator_receipt
from .project_interface_coordinator import (
    COORDINATOR_RECEIPT_SHA256_FIELD, PROJECT_REPAIR_QUEUE_SHA256_FIELD,
    coordinate_project_interfaces,
)
from .runtime_security import assert_model_payload_safe
from .rust_project_ir_validation import validate_rust_project_ir
from .project_verifier_receipt import verifier_diagnostic_detail


MAX_PROJECT_REPAIR_CONTEXT_BYTES = 131_072
MAX_PROJECT_REPAIR_RECORDS = 128
_SECTIONS = (
    "modules", "public_api", "shared_types", "global_ownership",
    "initialization", "ffi_boundaries", "cfgs", "features",
    "unsafe_obligations",
)
_IDENTITIES = {
    "modules": "module_id", "public_api": "declaration_id",
    "shared_types": "declaration_id", "global_ownership": "declaration_id",
    "initialization": "init_id", "ffi_boundaries": "declaration_id",
    "cfgs": "cfg_id", "features": "feature_id",
    "unsafe_obligations": "obligation_id",
}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_BASE_KEYS = {
    "schema_version", "authority", "receipt_epoch",
    "coordinator_receipt_sha256", "project_repair_queue_sha256", "repair_id",
    "base_rust_project_ir_sha256", "base_interface_sha256", "diagnostic",
    "repair_item", "crate", "interface_completeness", "visible_records",
    "withheld_record_counts", "allowed_output", "claim_boundary",
    "context_sha256",
}
_MODEL_FIELDS = {
    "modules": {"module_id", "parent_module_id", "rust_path", "unit_id",
                "candidate_sha256", "visibility"},
    "public_api": {"declaration_id", "module_id", "symbol", "kind", "signature",
                   "visibility"},
    "shared_types": {"declaration_id", "module_id", "name", "kind",
                     "layout_sha256", "repr"},
    "global_ownership": {"declaration_id", "module_id", "symbol", "access"},
    "initialization": {"init_id", "module_id", "function", "phase", "after"},
    "ffi_boundaries": {"declaration_id", "module_id", "symbol", "direction", "abi",
                       "link_name"},
    "cfgs": {"cfg_id", "expression", "module_ids"},
    "features": {"feature_id", "name", "default", "enables", "module_ids"},
    "unsafe_obligations": {"obligation_id", "module_id", "kind", "reason_code",
                           "source_span"},
}


def build_project_repair_context(
    rust_project_ir: Mapping[str, Any], receipt: Mapping[str, Any], *,
    receipt_epoch: int, repair_id: str,
    project_diagnostic_intakes: Sequence[Mapping[str, Any]] = (),
    native_link_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    validate_rust_project_ir(rust_project_ir)
    value = validate_coordinator_receipt(receipt)
    if isinstance(receipt_epoch, bool) or not isinstance(receipt_epoch, int) or receipt_epoch < 1:
        raise ValueError("project repair receipt_epoch is invalid")
    queue = value["project_repair_queue"]
    expected = coordinate_project_interfaces(
        rust_project_ir, max_repairs=queue["max_items"],
        max_attempts_per_item=queue["max_attempts_per_item"],
        project_diagnostic_intakes=project_diagnostic_intakes,
    )
    if expected != value:
        raise ValueError("project repair context receipt is not recomputable")
    item = next(
        (entry for entry in queue["items"] if entry["repair_id"] == repair_id),
        None,
    )
    if item is None:
        raise ValueError("project repair item is absent from its queue")
    diagnostic = next(
        entry for entry in value["diagnostics"]
        if entry["diagnostic_sha256"] == item["diagnostic_sha256"]
    )
    verifier_detail = verifier_diagnostic_detail(
        project_diagnostic_intakes, item["diagnostic_sha256"],
    )
    native_planning = native_link_planning(
        rust_project_ir, diagnostic, native_link_context,
    )
    if verifier_detail is not None and native_planning is not None:
        raise ValueError("native link planning cannot use verifier diagnostics")
    affected = set(item["affected_module_ids"])
    visible: dict[str, list[dict[str, Any]]] = {}
    withheld: dict[str, int] = {}
    record_count = 0
    for section in _SECTIONS:
        records = [
            _model_record(entry) for entry in rust_project_ir[section]
            if _record_relevant(entry, affected)
        ]
        record_count += len(records)
        visible[section] = records
        withheld[section] = len(rust_project_ir[section]) - len(records)
    if record_count > MAX_PROJECT_REPAIR_RECORDS:
        raise ValueError("project repair context record bound is exceeded")
    schema_version = (
        3 if native_planning is not None
        else 2 if verifier_detail is not None else 1
    )
    allowed_output = context_allowed_output(native_planning is not None)
    payload = {
        "schema_version": schema_version,
        "authority": "host-project-repair-context-builder",
        "receipt_epoch": receipt_epoch,
        "coordinator_receipt_sha256": value[COORDINATOR_RECEIPT_SHA256_FIELD],
        "project_repair_queue_sha256": queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD],
        "repair_id": repair_id,
        "base_rust_project_ir_sha256": rust_project_ir["ir_sha256"],
        "base_interface_sha256": rust_project_ir["interface_sha256"],
        "diagnostic": {
            "code": diagnostic["code"],
            "diagnostic_sha256": diagnostic["diagnostic_sha256"],
            "entity_ids": list(diagnostic["entity_ids"]),
            "affected_module_ids": list(diagnostic["affected_module_ids"]),
            **(verifier_model_detail(verifier_detail) if verifier_detail else {}),
        },
        "repair_item": dict(item),
        "crate": _model_record(rust_project_ir["crate"]),
        "interface_completeness": dict(rust_project_ir["interface_completeness"]),
        "visible_records": visible,
        "withheld_record_counts": withheld,
        "allowed_output": allowed_output,
        "claim_boundary": {
            "semantic_acceptance": False,
            "translation_coverage_numerator": 0,
        },
    }
    if native_planning is not None:
        payload[NATIVE_LINK_FIELD] = native_planning
    result = {**payload, "context_sha256": content_sha256(payload)}
    encoded = canonical_json_bytes(result)
    if len(encoded) > MAX_PROJECT_REPAIR_CONTEXT_BYTES:
        raise ValueError("project repair context byte bound is exceeded")
    assert_model_payload_safe(result, "project_repair_context")
    return result


def validate_project_repair_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("project repair context must be an object")
    result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    schema_version = result.get("schema_version")
    expected_keys = _CONTEXT_BASE_KEYS | (
        {NATIVE_LINK_FIELD} if schema_version == 3 else set()
    )
    if set(result) != expected_keys:
        raise ValueError("project repair context fields are invalid")
    claimed = result.get("context_sha256")
    projection = {key: item for key, item in result.items() if key != "context_sha256"}
    if not isinstance(claimed, str) or content_sha256(projection) != claimed:
        raise ValueError("project repair context SHA drifted")
    expected_output = context_allowed_output(schema_version == 3)
    if (
        schema_version not in {1, 2, 3}
        or result.get("authority") != "host-project-repair-context-builder"
        or set(result.get("visible_records", {})) != set(_SECTIONS)
        or set(result.get("withheld_record_counts", {})) != set(_SECTIONS)
        or result.get("allowed_output") != expected_output
        or result.get("claim_boundary") != {
            "semantic_acceptance": False,
            "translation_coverage_numerator": 0,
        }
    ):
        raise ValueError("project repair context contract is invalid")
    if schema_version == 3:
        validate_native_link_planning(result)
    records = result["visible_records"]
    if not all(isinstance(records[name], list) for name in _SECTIONS):
        raise ValueError("project repair context records are invalid")
    for section in _SECTIONS:
        if any(
            not isinstance(item, dict) or set(item) != _MODEL_FIELDS[section]
            for item in records[section]
        ):
            raise ValueError("project repair context record fields are invalid")
    if any(
        isinstance(result["withheld_record_counts"][name], bool)
        or not isinstance(result["withheld_record_counts"][name], int)
        or result["withheld_record_counts"][name] < 0
        for name in _SECTIONS
    ):
        raise ValueError("project repair withheld counts are invalid")
    for field in (
        "coordinator_receipt_sha256", "project_repair_queue_sha256",
        "base_rust_project_ir_sha256", "base_interface_sha256",
    ):
        if not isinstance(result.get(field), str) or _SHA256.fullmatch(result[field]) is None:
            raise ValueError("project repair context SHA binding is invalid")
    if (
        isinstance(result.get("receipt_epoch"), bool)
        or not isinstance(result.get("receipt_epoch"), int)
        or result["receipt_epoch"] < 1
        or not isinstance(result.get("repair_id"), str)
        or not result["repair_id"].startswith("project-repair-")
        or not isinstance(result.get("diagnostic"), dict)
        or set(result["diagnostic"]) != diagnostic_keys(result["schema_version"])
        or not isinstance(result.get("repair_item"), dict)
        or result["repair_item"].get("repair_id") != result["repair_id"]
        or result["repair_item"].get("assigned_unit_id") is not None
        or result["repair_item"].get("candidate_only") is not True
        or not isinstance(result.get("crate"), dict)
        or set(result["crate"]) != {
            "crate_id", "edition", "crate_types", "root_module_id", "targets",
        }
    ):
        raise ValueError("project repair context identity binding is invalid")
    validate_verifier_diagnostic(result["diagnostic"], result["schema_version"])
    if sum(len(records[name]) for name in _SECTIONS) > MAX_PROJECT_REPAIR_RECORDS:
        raise ValueError("project repair context record bound is exceeded")
    if len(canonical_json_bytes(result)) > MAX_PROJECT_REPAIR_CONTEXT_BYTES:
        raise ValueError("project repair context byte bound is exceeded")
    assert_model_payload_safe(result, "project_repair_context")
    return result


def visible_record_ids(context: Mapping[str, Any]) -> dict[str, set[str]]:
    value = validate_project_repair_context(context)
    return {
        section: {str(item[_IDENTITIES[section]]) for item in value["visible_records"][section]}
        for section in _SECTIONS
    }


def _record_relevant(record: Mapping[str, Any], affected: set[str]) -> bool:
    module_ids = record.get("module_ids")
    if isinstance(module_ids, list):
        return bool(affected.intersection(str(item) for item in module_ids))
    module_id = record.get("module_id")
    return isinstance(module_id, str) and module_id in affected


def _model_record(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: json.loads(json.dumps(item, ensure_ascii=True))
        for key, item in value.items() if key != "evidence"
    }


__all__ = [
    "MAX_PROJECT_REPAIR_CONTEXT_BYTES", "build_project_repair_context",
    "validate_project_repair_context", "visible_record_ids",
]
