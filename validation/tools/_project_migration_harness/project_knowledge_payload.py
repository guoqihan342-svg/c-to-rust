from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .ledger_security import assert_no_semantic_claims
from .runtime_security import assert_model_payload_safe


KINDS = {
    "abi-fact", "api-fact", "build-fact", "candidate-decision",
    "failure-class", "ownership-fact", "type-fact",
}
AUTHORITIES = {"external-verifier", "host-extractor", "transition-authority"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RAW_KEYS = {
    "complete_repository", "raw_repository", "raw_source", "repository_tree",
    "source_content", "source_text",
}
PAYLOAD_FIELDS = {
    "abi-fact": {
        "abi", "alignment_bytes", "calling_convention", "layout_sha256",
        "owner_unit_id", "size_bytes", "symbol",
    },
    "api-fact": {
        "abi", "arity", "declaration_sha256", "linkage", "owner_unit_id",
        "parameter_type_ids", "return_type_id", "symbol", "variadic", "visibility",
    },
    "build-fact": {
        "compile_args_sha256", "compiler_sha256", "dependency_ids", "language",
        "source_sha256", "status", "target_id", "target_kind",
    },
    "candidate-decision": {
        "candidate_sha256", "decision", "gate_family", "reason_code",
        "strategy_sha256", "verdict_sha256",
    },
    "failure-class": {
        "affected_subjects", "code", "environmental", "fingerprint_sha256",
        "gate_family", "stage",
    },
    "ownership-fact": {
        "lifetime_class", "mode", "mutable", "owner_unit_id", "symbol",
    },
    "type-fact": {
        "alignment_bytes", "field_layout_sha256", "kind", "layout_sha256",
        "name", "owner_unit_id", "repr", "size_bytes",
    },
}


def safe_knowledge_payload(kind: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("knowledge payload must be a non-empty object")
    _reject_raw_keys(value)
    unknown = set(value) - PAYLOAD_FIELDS[kind]
    if unknown:
        raise ValueError(f"knowledge {kind} payload fields are not allowlisted: {sorted(unknown)}")
    result = json.loads(json.dumps(dict(value), ensure_ascii=True, sort_keys=True))
    _validate_values(result)
    assert_no_semantic_claims(result, "project_knowledge.payload")
    assert_model_payload_safe(result, "project_knowledge.payload")
    return result


def knowledge_kind(value: Any) -> str:
    if value not in KINDS:
        raise ValueError("knowledge kind is not allowed")
    return str(value)


def knowledge_authority(value: Any) -> str:
    if value not in AUTHORITIES:
        raise ValueError("knowledge authority is not allowed")
    return str(value)


def _reject_raw_keys(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = re.sub(r"[^a-z0-9]+", "_", str(key).lower()).strip("_")
            if normalized in RAW_KEYS:
                raise ValueError(f"raw repository/source field is forbidden: {key}")
            _reject_raw_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_raw_keys(child)


def _validate_values(value: Mapping[str, Any]) -> None:
    for key, item in value.items():
        if key.endswith("sha256"):
            if not isinstance(item, str) or SHA256_RE.fullmatch(item) is None:
                raise ValueError(f"knowledge payload {key} must be a SHA-256")
        elif isinstance(item, bool):
            continue
        elif isinstance(item, int):
            if item < 0:
                raise ValueError(f"knowledge payload {key} must be non-negative")
        elif isinstance(item, str):
            if not item or len(item) > 512 or any(ord(char) < 32 for char in item):
                raise ValueError(f"knowledge payload {key} must be bounded text")
        elif isinstance(item, list):
            if (
                len(item) > 128
                or not all(isinstance(child, str) and child for child in item)
                or item != sorted(set(item))
            ):
                raise ValueError(f"knowledge payload {key} must be a canonical string array")
        else:
            raise ValueError(f"knowledge payload {key} has an unsupported value type")


__all__ = [
    "KINDS", "knowledge_authority", "knowledge_kind", "safe_knowledge_payload",
]
