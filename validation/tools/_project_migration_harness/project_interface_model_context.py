from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .project_interface_contract import validate_coordinator_receipt
from .project_interface_coordinator import (
    COORDINATOR_RECEIPT_SHA256_FIELD, PROJECT_REPAIR_QUEUE_SHA256_FIELD,
)
from .runtime_security import assert_model_payload_safe


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT_KEYS = {
    "schema_version", "authority", "receipt_epoch",
    "coordinator_receipt_sha256", "project_repair_queue_sha256",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "receipt_status", "visibility", "subject_unit_ids",
    "diagnostic_total_count", "visible_diagnostic_count", "queue_item_count",
    "diagnostics", "repair_policy", "claim_boundary", "context_sha256",
}
_DIAGNOSTIC_KEYS = {
    "code", "diagnostic_sha256", "affected_module_ids",
    "affected_unit_ids", "unresolved_module_ids",
}


def build_model_coordinator_context(
    receipt: Mapping[str, Any], *, receipt_epoch: int,
    subject_unit_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    value = validate_coordinator_receipt(receipt)
    epoch = _positive_int(receipt_epoch, "receipt_epoch")
    subjects = _canonical_texts(subject_unit_ids or [], "subject_unit_ids")
    queue = value["project_repair_queue"]
    item_by_diagnostic = {
        item["diagnostic_sha256"]: item for item in queue["items"]
    }
    visible = []
    for diagnostic in value["diagnostics"]:
        item = item_by_diagnostic.get(diagnostic["diagnostic_sha256"])
        affected_units = [] if item is None else list(item["affected_unit_ids"])
        if subjects and not set(subjects).intersection(affected_units):
            continue
        visible.append({
            "code": diagnostic["code"],
            "diagnostic_sha256": diagnostic["diagnostic_sha256"],
            "affected_module_ids": list(diagnostic["affected_module_ids"]),
            "affected_unit_ids": affected_units,
            "unresolved_module_ids": (
                [] if item is None else list(item["unresolved_module_ids"])
            ),
        })
    payload = {
        "schema_version": 1,
        "authority": "host-project-interface-coordinator",
        "receipt_epoch": epoch,
        "coordinator_receipt_sha256": value[COORDINATOR_RECEIPT_SHA256_FIELD],
        "project_repair_queue_sha256": queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD],
        "rust_project_ir_sha256": value["rust_project_ir_sha256"],
        "rust_project_interface_sha256": value["rust_project_interface_sha256"],
        "receipt_status": value["status"],
        "visibility": "subject-filtered" if subjects else "project",
        "subject_unit_ids": subjects,
        "diagnostic_total_count": (
            len(value["diagnostics"]) + value["diagnostic_overflow_count"]
        ),
        "visible_diagnostic_count": len(visible),
        "queue_item_count": queue["item_count"],
        "diagnostics": visible,
        "repair_policy": dict(queue["policy"]),
        "claim_boundary": {
            "model_opinion_is_gate": False,
            "semantic_acceptance": False,
            "translation_coverage_numerator": 0,
        },
    }
    result = {**payload, "context_sha256": content_sha256(payload)}
    return validate_model_coordinator_context(result)


def validate_model_coordinator_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _CONTEXT_KEYS:
        raise ValueError("model coordinator context fields are invalid")
    result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    if result["schema_version"] != 1 or result["authority"] != "host-project-interface-coordinator":
        raise ValueError("model coordinator context identity is invalid")
    _positive_int(result["receipt_epoch"], "receipt_epoch")
    for field in (
        "coordinator_receipt_sha256", "project_repair_queue_sha256",
        "rust_project_ir_sha256", "rust_project_interface_sha256",
    ):
        _sha(result[field], field)
    if result["receipt_status"] not in {"candidate-ready", "repair-required"}:
        raise ValueError("model coordinator context status is invalid")
    if result["visibility"] not in {"project", "subject-filtered"}:
        raise ValueError("model coordinator context visibility is invalid")
    subjects = _canonical_texts(result["subject_unit_ids"], "subject_unit_ids")
    if (result["visibility"] == "subject-filtered") != bool(subjects):
        raise ValueError("model coordinator context subject visibility drifted")
    totals = [
        _nonnegative_int(result[field], field)
        for field in (
            "diagnostic_total_count", "visible_diagnostic_count", "queue_item_count",
        )
    ]
    diagnostics = result["diagnostics"]
    if not isinstance(diagnostics, list) or len(diagnostics) != totals[1] or totals[1] > totals[0]:
        raise ValueError("model coordinator diagnostic counts are invalid")
    seen: set[str] = set()
    for item in diagnostics:
        if not isinstance(item, dict) or set(item) != _DIAGNOSTIC_KEYS:
            raise ValueError("model coordinator diagnostic fields are invalid")
        _text(item["code"], "diagnostic code")
        digest = _sha(item["diagnostic_sha256"], "diagnostic_sha256")
        if digest in seen:
            raise ValueError("model coordinator diagnostics are duplicated")
        seen.add(digest)
        for field in (
            "affected_module_ids", "affected_unit_ids", "unresolved_module_ids",
        ):
            _canonical_texts(item[field], field)
        if subjects and not set(subjects).intersection(item["affected_unit_ids"]):
            raise ValueError("model coordinator diagnostic is irrelevant to its subjects")
    if result["repair_policy"] != {
        "assignment": "project-only",
        "allowed_output": "rust-project-ir-candidate",
        "generated_glue_allowed": False,
        "fixture_specific_shim_allowed": False,
    }:
        raise ValueError("model coordinator repair policy is invalid")
    if result["claim_boundary"] != {
        "model_opinion_is_gate": False,
        "semantic_acceptance": False,
        "translation_coverage_numerator": 0,
    }:
        raise ValueError("model coordinator claim boundary is invalid")
    claimed = _sha(result["context_sha256"], "context_sha256")
    projection = {key: item for key, item in result.items() if key != "context_sha256"}
    if content_sha256(projection) != claimed:
        raise ValueError("model coordinator context SHA drifted")
    assert_model_payload_safe(result, "coordinator_context")
    return result


def _canonical_texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or len(value) > 512:
        raise ValueError(f"{label} must be a bounded string array")
    result = [_text(item, label) for item in value]
    if result != sorted(set(result)):
        raise ValueError(f"{label} must be sorted and unique")
    return result


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
        raise ValueError(f"{label} is invalid")
    return value


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} is not a SHA-256")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


__all__ = [
    "build_model_coordinator_context", "validate_model_coordinator_context",
]
