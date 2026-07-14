from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .gate_evidence import require_content_addressed_reference
from .project_diagnostic_contract import MAX_PROJECT_DIAGNOSTIC_INTAKES
from .project_interface_coordinator import (
    COORDINATOR_ID, COORDINATOR_RECEIPT_SHA256_FIELD,
    PROJECT_REPAIR_QUEUE_SHA256_FIELD, coordinator_receipt_projection,
    project_repair_queue_projection,
)
from .project_verifier_receipt import (
    PROJECT_DIAGNOSTIC_INTAKES_FIELD,
    PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD,
    PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_RECEIPT_EXTRA = {
    PROJECT_DIAGNOSTIC_INTAKES_FIELD,
    PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD,
    PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD,
}
_QUEUE_EXTRA = {PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD}


def validate_verifier_coordinator_receipt(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    from .project_interface_contract import validate_coordinator_receipt

    receipt = json.loads(canonical_json_bytes(value).decode("utf-8"))
    base_receipt_keys = {
        "schema_version", "coordinator", "rust_project_ir_sha256",
        "rust_project_interface_sha256", "status", "diagnostics",
        "diagnostic_overflow_count", "project_repair_queue", "claim_boundary",
        COORDINATOR_RECEIPT_SHA256_FIELD,
    }
    if set(receipt) != base_receipt_keys | _RECEIPT_EXTRA:
        raise ValueError("verifier coordinator receipt fields are invalid")
    if receipt["schema_version"] != 2 or receipt["coordinator"] != COORDINATOR_ID:
        raise ValueError("verifier coordinator receipt identity is invalid")
    references = _references(receipt[PROJECT_DIAGNOSTIC_INTAKES_FIELD])
    intake_set = receipt[PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD]
    if not _is_sha(intake_set) or content_sha256(references) != intake_set:
        raise ValueError("project diagnostic intake set SHA drifted")
    verifier_hashes = receipt[PROJECT_VERIFIER_DIAGNOSTIC_SHA256S_FIELD]
    all_hashes = {
        item.get("diagnostic_sha256") for item in receipt.get("diagnostics", [])
        if isinstance(item, Mapping)
    }
    if (
        not isinstance(verifier_hashes, list) or not verifier_hashes
        or verifier_hashes != sorted(set(verifier_hashes))
        or any(not _is_sha(item) for item in verifier_hashes)
        or not set(verifier_hashes) <= all_hashes
    ):
        raise ValueError("project verifier diagnostic identities are invalid")
    queue = receipt.get("project_repair_queue")
    base_queue_keys = {
        "schema_version", "scope", "rust_project_ir_sha256",
        "rust_project_interface_sha256", "max_items", "item_count",
        "overflow_count", "max_attempts_per_item", "items", "policy",
        PROJECT_REPAIR_QUEUE_SHA256_FIELD,
    }
    if not isinstance(queue, dict) or set(queue) != base_queue_keys | _QUEUE_EXTRA:
        raise ValueError("verifier project repair queue fields are invalid")
    if (
        queue["schema_version"] != 2
        or queue[PROJECT_DIAGNOSTIC_INTAKE_SET_SHA256_FIELD] != intake_set
        or content_sha256(project_repair_queue_projection(queue))
        != queue.get(PROJECT_REPAIR_QUEUE_SHA256_FIELD)
    ):
        raise ValueError("verifier project repair queue binding drifted")
    if receipt.get("claim_boundary") != {
        "artifact_role": "project-interface-and-verifier-diagnostic",
        "semantic_gate": False,
        "semantic_pass": False,
        "translation_coverage_numerator": 0,
    }:
        raise ValueError("verifier coordinator claim boundary is invalid")
    if (
        not _is_sha(receipt.get(COORDINATOR_RECEIPT_SHA256_FIELD))
        or content_sha256(coordinator_receipt_projection(receipt))
        != receipt[COORDINATOR_RECEIPT_SHA256_FIELD]
    ):
        raise ValueError("verifier coordinator receipt SHA drifted")
    validate_coordinator_receipt(_schema_one_projection(receipt, queue))
    return receipt


def _schema_one_projection(
    receipt: Mapping[str, Any], queue: Mapping[str, Any],
) -> dict[str, Any]:
    projected_queue = {
        key: item for key, item in queue.items()
        if key not in _QUEUE_EXTRA | {PROJECT_REPAIR_QUEUE_SHA256_FIELD}
    }
    projected_queue["schema_version"] = 1
    projected_queue[PROJECT_REPAIR_QUEUE_SHA256_FIELD] = content_sha256(
        project_repair_queue_projection(projected_queue),
    )
    projected = {
        key: item for key, item in receipt.items()
        if key not in _RECEIPT_EXTRA | {COORDINATOR_RECEIPT_SHA256_FIELD}
    }
    projected["schema_version"] = 1
    projected["project_repair_queue"] = projected_queue
    projected["claim_boundary"] = {
        "artifact_role": "project-interface-diagnostic",
        "semantic_gate": False,
        "semantic_pass": False,
        "translation_coverage_numerator": 0,
    }
    projected[COORDINATOR_RECEIPT_SHA256_FIELD] = content_sha256(
        coordinator_receipt_projection(projected),
    )
    return projected


def _references(value: Any) -> list[dict[str, Any]]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_PROJECT_DIAGNOSTIC_INTAKES
    ):
        raise ValueError("project diagnostic intake references are invalid")
    result = []
    for raw in value:
        reference = dict(raw)
        require_content_addressed_reference(reference)
        parts = PurePosixPath(str(reference["path"])).parts
        if not any(
            tuple(parts[index:index + 2]) == ("verification", "project-diagnostics")
            for index in range(len(parts) - 1)
        ):
            raise ValueError("project diagnostic intake reference path is invalid")
        result.append(reference)
    expected = sorted(result, key=lambda item: (item["path"], item["sha256"]))
    if result != expected or len({(item["path"], item["sha256"]) for item in result}) != len(result):
        raise ValueError("project diagnostic intake references are not canonical")
    return result


def _is_sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


__all__ = ["validate_verifier_coordinator_receipt"]
