from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_evidence import require_content_addressed_reference
from .sandbox_execution_schema import is_sha256


_KEYS = {
    "schema_version", "artifact_kind", "authority_id", "status", "run_id",
    "source", "candidate", "successor_coordinator_receipt_sha256",
    "gate_records", "claim_boundary",
}
_SOURCE_KEYS = {
    "coordinator_receipt_sha256", "project_repair_queue_sha256",
    "rust_project_ir_sha256", "rust_project_interface_sha256",
    "project_diagnostic_intake_set_sha256",
}
_CANDIDATE_KEYS = {
    "candidate_set_sha256", "rust_project_ir_sha256",
    "rust_project_interface_sha256",
}
_GATE_KEYS = {
    "gate_kind", "gate_status", "gate_epoch", "record_id",
    "candidate_set_sha256", "raw_observation", "evidence",
}


def project_revalidation_receipt(
    *, run_id: str, source_receipt: Mapping[str, Any],
    candidate_ir: Mapping[str, Any], successor_receipt: Mapping[str, Any],
    candidate_set_sha256: str, records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "artifact_kind": "host-project-repair-revalidation-receipt",
        "authority_id": "host.project-repair-revalidation.v1",
        "status": "passed", "run_id": run_id,
        "source": {
            "coordinator_receipt_sha256": source_receipt[
                "coordinator_receipt_sha256"
            ],
            "project_repair_queue_sha256": source_receipt[
                "project_repair_queue"
            ]["project_repair_queue_sha256"],
            "rust_project_ir_sha256": source_receipt["rust_project_ir_sha256"],
            "rust_project_interface_sha256": source_receipt[
                "rust_project_interface_sha256"
            ],
            "project_diagnostic_intake_set_sha256": source_receipt[
                "project_diagnostic_intake_set_sha256"
            ],
        },
        "candidate": {
            "candidate_set_sha256": candidate_set_sha256,
            "rust_project_ir_sha256": candidate_ir["ir_sha256"],
            "rust_project_interface_sha256": candidate_ir["interface_sha256"],
        },
        "successor_coordinator_receipt_sha256": successor_receipt[
            "coordinator_receipt_sha256"
        ],
        "gate_records": sorted(
            (_gate_record(record) for record in records),
            key=lambda item: item["gate_kind"],
        ),
        "claim_boundary": {
            "project_repair_revalidation": True,
            "project_final_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }
    return validate_project_revalidation_receipt(payload)


def validate_project_revalidation_receipt(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _KEYS:
        raise ValueError("project revalidation receipt fields are invalid")
    result = json.loads(canonical_json_bytes(value).decode("utf-8"))
    if (
        result["schema_version"] != 1
        or result["artifact_kind"]
        != "host-project-repair-revalidation-receipt"
        or result["authority_id"] != "host.project-repair-revalidation.v1"
        or result["status"] != "passed"
        or not isinstance(result["run_id"], str) or not result["run_id"]
        or result["claim_boundary"] != {
            "project_repair_revalidation": True,
            "project_final_gate": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        }
    ):
        raise ValueError("project revalidation receipt identity is invalid")
    _sha_object(result["source"], _SOURCE_KEYS, "source")
    _sha_object(result["candidate"], _CANDIDATE_KEYS, "candidate")
    if not is_sha256(result["successor_coordinator_receipt_sha256"]):
        raise ValueError("project revalidation successor receipt is invalid")
    gates = result["gate_records"]
    if not isinstance(gates, list) or not gates:
        raise ValueError("project revalidation gate records are invalid")
    normalized = [_gate_record(item) for item in gates]
    if gates != sorted(normalized, key=lambda item: item["gate_kind"]):
        raise ValueError("project revalidation gate records are not canonical")
    kinds = [item["gate_kind"] for item in gates]
    if len(kinds) != len(set(kinds)):
        raise ValueError("project revalidation gate records are duplicated")
    return result


def _gate_record(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not _GATE_KEYS <= set(value):
        raise ValueError("project revalidation gate record is invalid")
    result = {key: value[key] for key in _GATE_KEYS}
    if (
        not isinstance(result["gate_kind"], str) or not result["gate_kind"]
        or result["gate_status"] != "passed"
        or isinstance(result["gate_epoch"], bool)
        or not isinstance(result["gate_epoch"], int)
        or result["gate_epoch"] < 1
        or not isinstance(result["record_id"], str) or not result["record_id"]
        or not is_sha256(result["candidate_set_sha256"])
    ):
        raise ValueError("project revalidation gate identity is invalid")
    for field in ("raw_observation", "evidence"):
        reference = dict(result[field])
        require_content_addressed_reference(reference)
        result[field] = reference
    return result


def _sha_object(value: Any, keys: set[str], label: str) -> None:
    if (
        not isinstance(value, Mapping) or set(value) != keys
        or any(not is_sha256(item) for item in value.values())
    ):
        raise ValueError(f"project revalidation {label} binding is invalid")


__all__ = [
    "project_revalidation_receipt", "validate_project_revalidation_receipt",
]
