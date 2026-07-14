from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .project_interface_coordinator import (
    COORDINATOR_ID,
    COORDINATOR_RECEIPT_SHA256_FIELD,
    MAX_DIAGNOSTICS,
    MAX_REPAIRS,
    PROJECT_REPAIR_QUEUE_SHA256_FIELD,
    coordinator_receipt_projection,
    project_repair_queue_projection,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECEIPT_KEYS = {
    "schema_version", "coordinator", "rust_project_ir_sha256",
    "rust_project_interface_sha256", "status", "diagnostics",
    "diagnostic_overflow_count", "project_repair_queue", "claim_boundary",
    COORDINATOR_RECEIPT_SHA256_FIELD,
}
_QUEUE_KEYS = {
    "schema_version", "scope", "rust_project_ir_sha256",
    "rust_project_interface_sha256", "max_items", "item_count",
    "overflow_count", "max_attempts_per_item", "items", "policy",
    PROJECT_REPAIR_QUEUE_SHA256_FIELD,
}
_DIAGNOSTIC_KEYS = {
    "code", "scope", "entity_ids", "affected_module_ids",
    "random_unit_attribution", "diagnostic_sha256",
}
_ITEM_KEYS = {
    "repair_id", "scope", "assigned_unit_id", "diagnostic_code",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "diagnostic_sha256", "affected_module_ids", "affected_unit_ids",
    "unresolved_module_ids", "max_attempts", "candidate_only",
}


def validate_coordinator_receipt(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("coordinator receipt must be an object")
    if value.get("schema_version") == 2:
        from .project_verifier_receipt_contract import (
            validate_verifier_coordinator_receipt,
        )
        return validate_verifier_coordinator_receipt(value)
    receipt = json.loads(canonical_json_bytes(value).decode("utf-8"))
    _exact_keys(receipt, _RECEIPT_KEYS, "coordinator receipt")
    if receipt["schema_version"] != 1 or receipt["coordinator"] != COORDINATOR_ID:
        raise ValueError("coordinator receipt identity is invalid")
    _sha(receipt["rust_project_ir_sha256"], "receipt RustProjectIR")
    _sha(receipt["rust_project_interface_sha256"], "receipt interface")
    diagnostics = receipt["diagnostics"]
    if not isinstance(diagnostics, list) or len(diagnostics) > MAX_DIAGNOSTICS:
        raise ValueError("coordinator diagnostics are invalid")
    diagnostic_hashes: set[str] = set()
    for diagnostic in diagnostics:
        digest = _validate_diagnostic(diagnostic)
        if digest in diagnostic_hashes:
            raise ValueError("coordinator diagnostics are duplicated")
        diagnostic_hashes.add(digest)
    overflow = _bounded_int(
        receipt["diagnostic_overflow_count"], 0, 1_000_000,
        "diagnostic overflow",
    )
    expected_status = "repair-required" if diagnostics or overflow else "candidate-ready"
    if receipt["status"] != expected_status:
        raise ValueError("coordinator receipt status does not match diagnostics")
    queue = _validate_queue(
        receipt["project_repair_queue"], receipt, diagnostic_hashes, overflow,
    )
    if receipt["claim_boundary"] != {
        "artifact_role": "project-interface-diagnostic",
        "semantic_gate": False,
        "semantic_pass": False,
        "translation_coverage_numerator": 0,
    }:
        raise ValueError("coordinator claim boundary is invalid")
    claimed = receipt[COORDINATOR_RECEIPT_SHA256_FIELD]
    _sha(claimed, "coordinator receipt")
    if content_sha256(coordinator_receipt_projection(receipt)) != claimed:
        raise ValueError("coordinator receipt SHA drifted")
    receipt["project_repair_queue"] = queue
    return receipt


def coordinator_receipt_accepts_repair_candidate(
    previous: Mapping[str, Any], candidate: Mapping[str, Any], *,
    diagnostic_sha256: str,
) -> bool:
    before = validate_coordinator_receipt(previous)
    after = validate_coordinator_receipt(candidate)
    _sha(diagnostic_sha256, "project repair target diagnostic")
    before_hashes = {
        item["diagnostic_sha256"] for item in before["diagnostics"]
    }
    if diagnostic_sha256 not in before_hashes:
        raise ValueError("project repair target diagnostic is absent from its receipt")
    if before.get("schema_version") == 2:
        from .project_verifier_receipt import (
            PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD,
        )
        if diagnostic_sha256 in before[PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD]:
            return False
    before_queue = before["project_repair_queue"]
    after_queue = after["project_repair_queue"]
    if (
        before_queue["max_items"] != after_queue["max_items"]
        or before_queue["max_attempts_per_item"]
        != after_queue["max_attempts_per_item"]
    ):
        return False
    after_hashes = {
        item["diagnostic_sha256"] for item in after["diagnostics"]
    }
    before_count = len(before_hashes) + before["diagnostic_overflow_count"]
    after_count = len(after_hashes) + after["diagnostic_overflow_count"]
    return (
        after["diagnostic_overflow_count"] == 0
        and diagnostic_sha256 not in after_hashes
        and after_hashes < before_hashes
        and after_count < before_count
    )


def _validate_queue(
    value: Any, receipt: Mapping[str, Any], diagnostic_hashes: set[str],
    diagnostic_overflow: int,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("project repair queue must be an object")
    _exact_keys(value, _QUEUE_KEYS, "project repair queue")
    if value["schema_version"] != 1 or value["scope"] != "project":
        raise ValueError("project repair queue identity is invalid")
    for field in ("rust_project_ir_sha256", "rust_project_interface_sha256"):
        _sha(value[field], f"queue {field}")
        if value[field] != receipt[field]:
            raise ValueError("project repair queue changed its receipt binding")
    max_items = _bounded_int(value["max_items"], 1, MAX_REPAIRS, "queue max_items")
    max_attempts = _bounded_int(
        value["max_attempts_per_item"], 1, 5, "queue max attempts",
    )
    items = value["items"]
    if not isinstance(items, list) or len(items) > max_items:
        raise ValueError("project repair queue items are invalid")
    if value["item_count"] != len(items):
        raise ValueError("project repair queue item count drifted")
    expected_overflow = max(0, len(diagnostic_hashes) - max_items) + diagnostic_overflow
    if value["overflow_count"] != expected_overflow:
        raise ValueError("project repair queue overflow count drifted")
    repair_ids: set[str] = set()
    queued_diagnostics: set[str] = set()
    for item in items:
        repair_id, diagnostic_sha = _validate_item(
            item, receipt, diagnostic_hashes, max_attempts,
        )
        if repair_id in repair_ids or diagnostic_sha in queued_diagnostics:
            raise ValueError("project repair queue items are duplicated")
        repair_ids.add(repair_id)
        queued_diagnostics.add(diagnostic_sha)
    if value["policy"] != {
        "assignment": "project-only",
        "allowed_output": "rust-project-ir-candidate",
        "generated_glue_allowed": False,
        "fixture_specific_shim_allowed": False,
    }:
        raise ValueError("project repair queue policy is invalid")
    claimed = value[PROJECT_REPAIR_QUEUE_SHA256_FIELD]
    _sha(claimed, "project repair queue")
    if content_sha256(project_repair_queue_projection(value)) != claimed:
        raise ValueError("project repair queue SHA drifted")
    return value


def _validate_diagnostic(value: Any) -> str:
    if not isinstance(value, dict):
        raise ValueError("project interface diagnostic must be an object")
    _exact_keys(value, _DIAGNOSTIC_KEYS, "project interface diagnostic")
    _text(value["code"], "diagnostic code")
    if value["scope"] != "project" or value["random_unit_attribution"] is not False:
        raise ValueError("project interface diagnostic scope is invalid")
    _sorted_texts(value["entity_ids"], "diagnostic entities")
    _sorted_texts(value["affected_module_ids"], "diagnostic modules")
    digest = value["diagnostic_sha256"]
    _sha(digest, "diagnostic")
    projection = {key: item for key, item in value.items() if key != "diagnostic_sha256"}
    if content_sha256(projection) != digest:
        raise ValueError("project interface diagnostic SHA drifted")
    return digest


def _validate_item(
    value: Any, receipt: Mapping[str, Any], diagnostic_hashes: set[str],
    max_attempts: int,
) -> tuple[str, str]:
    if not isinstance(value, dict):
        raise ValueError("project repair item must be an object")
    _exact_keys(value, _ITEM_KEYS, "project repair item")
    repair_id = _text(value["repair_id"], "repair id")
    diagnostic_code = _text(value["diagnostic_code"], "repair diagnostic code")
    if not repair_id.startswith("project-repair-") or value["scope"] != "project":
        raise ValueError("project repair item identity is invalid")
    if value["assigned_unit_id"] is not None or value["candidate_only"] is not True:
        raise ValueError("project repair item must remain project-only and candidate-only")
    for field in ("rust_project_ir_sha256", "rust_project_interface_sha256"):
        if value[field] != receipt[field]:
            raise ValueError("project repair item changed its receipt binding")
    diagnostic_sha = value["diagnostic_sha256"]
    if diagnostic_sha not in diagnostic_hashes:
        raise ValueError("project repair item references an unknown diagnostic")
    diagnostic = next(
        item for item in receipt["diagnostics"]
        if item["diagnostic_sha256"] == diagnostic_sha
    )
    if diagnostic_code != diagnostic["code"]:
        raise ValueError("project repair item changed its diagnostic code")
    affected_modules = _sorted_texts(value["affected_module_ids"], "repair modules")
    if affected_modules != diagnostic["affected_module_ids"]:
        raise ValueError("project repair item changed its affected modules")
    _sorted_texts(value["affected_unit_ids"], "repair units")
    _sorted_texts(value["unresolved_module_ids"], "repair unresolved modules")
    if value["max_attempts"] != max_attempts:
        raise ValueError("project repair item attempt cap drifted")
    return repair_id, diagnostic_sha


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields are invalid")


def _sha(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} SHA is invalid")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 512 or "\x00" in value:
        raise ValueError(f"{label} is invalid")
    return value


def _sorted_texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or len(value) > 512:
        raise ValueError(f"{label} are invalid")
    result = [_text(item, label) for item in value]
    if result != sorted(set(result)):
        raise ValueError(f"{label} must be sorted and unique")
    return result


def _bounded_int(value: Any, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} is invalid")
    return value


__all__ = [
    "coordinator_receipt_accepts_repair_candidate",
    "validate_coordinator_receipt",
]
