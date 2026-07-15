from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .native_symbol_context import (
    model_native_symbol_context, validate_native_symbol_context,
)
from .runtime_security import assert_model_payload_safe


NATIVE_SYMBOL_RESPONSE_KIND = "native-symbol-model-response"
NATIVE_SYMBOL_CANDIDATE_KIND = "native-symbol-candidate"
MAX_NATIVE_SYMBOL_PROMPT_BYTES = 512 * 1024
_RESPONSE_KEYS = {
    "schema_version", "artifact_kind", "context_sha256", "assignments",
}
_ASSIGNMENT_KEYS = {"symbol_id", "provider_kind", "requirement_id"}
_CANDIDATE_KEYS = {
    "schema_version", "artifact_kind", "status", "context_sha256",
    "assignments", "native_assignment_count", "runtime_assignment_count",
    "defer_count", "claim_boundary", "candidate_sha256",
}
_CLAIM_BOUNDARY = {
    "artifact_role": "native-symbol-candidate",
    "symbol_assignments_resolved": False,
    "native_exports_verified": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}


def render_native_symbol_prompt(
    context: Mapping[str, Any], *,
    max_prompt_bytes: int = MAX_NATIVE_SYMBOL_PROMPT_BYTES,
) -> str:
    validate_native_symbol_context(context)
    if context["status"] != "planning-required":
        raise ValueError("native_symbol_context_not_required")
    if (
        isinstance(max_prompt_bytes, bool) or not isinstance(max_prompt_bytes, int)
        or not 4_096 <= max_prompt_bytes <= MAX_NATIVE_SYMBOL_PROMPT_BYTES
    ):
        raise ValueError("native_symbol_prompt_limit_invalid")
    payload = {
        "schema_version": 1,
        "task": "attribute every imported Rust FFI symbol to one provider class",
        "rules": [
            "Return exactly one assignment for every visible symbol_id.",
            "Use native-requirement only for a visible rustc-link-lib provider.",
            "Use runtime only for a platform runtime symbol; the host still verifies it.",
            "Use defer when evidence is insufficient.",
            "Do not invent symbols, paths, linker flags, or resolution claims.",
        ],
        "native_symbol_context": model_native_symbol_context(context),
        "output_schema": {
            "schema_version": 1,
            "artifact_kind": NATIVE_SYMBOL_RESPONSE_KIND,
            "context_sha256": context["context_sha256"],
            "assignments": [{
                "symbol_id": "one visible symbol_id",
                "provider_kind": "native-requirement | runtime | defer",
                "requirement_id": "visible requirement_id or null",
            }],
        },
    }
    assert_model_payload_safe(payload, "native_symbol_prompt")
    encoded = canonical_json_bytes(payload)
    if len(encoded) > max_prompt_bytes:
        raise ValueError("native_symbol_prompt_too_large")
    return encoded.decode("utf-8")


def build_native_symbol_candidate(
    context: Mapping[str, Any], response: Mapping[str, Any],
) -> dict[str, Any]:
    validate_native_symbol_context(context)
    if context["status"] != "planning-required":
        raise ValueError("native_symbol_context_not_required")
    assignments = validate_native_symbol_response(response, context)
    payload = {
        "schema_version": 1,
        "artifact_kind": NATIVE_SYMBOL_CANDIDATE_KIND,
        "status": "candidate",
        "context_sha256": context["context_sha256"],
        "assignments": assignments,
        "native_assignment_count": _count(assignments, "native-requirement"),
        "runtime_assignment_count": _count(assignments, "runtime"),
        "defer_count": _count(assignments, "defer"),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    payload["candidate_sha256"] = content_sha256(payload)
    validate_native_symbol_candidate(payload, context)
    return payload


def validate_native_symbol_response(
    value: Any, context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    validate_native_symbol_context(context)
    if not isinstance(value, Mapping) or set(value) != _RESPONSE_KEYS:
        raise ValueError("native_symbol_response_schema_invalid")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != NATIVE_SYMBOL_RESPONSE_KIND
        or value.get("context_sha256") != context["context_sha256"]
    ):
        raise ValueError("native_symbol_response_binding_invalid")
    assignments = value.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("native_symbol_response_assignments_invalid")
    normalized = [_validate_assignment(item, context) for item in assignments]
    expected = {item["symbol_id"] for item in context["symbols"]}
    identities = [item["symbol_id"] for item in normalized]
    if len(identities) != len(set(identities)) or set(identities) != expected:
        raise ValueError("native_symbol_response_coverage_invalid")
    return sorted(normalized, key=lambda item: item["symbol_id"])


def validate_native_symbol_candidate(
    value: Any, context: Mapping[str, Any],
) -> dict[str, Any]:
    validate_native_symbol_context(context)
    if not isinstance(value, Mapping) or set(value) != _CANDIDATE_KEYS:
        raise ValueError("native_symbol_candidate_schema_invalid")
    assignments = value.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("native_symbol_candidate_assignments_invalid")
    normalized = [_validate_assignment(item, context) for item in assignments]
    expected = [item["symbol_id"] for item in context["symbols"]]
    identities = [item["symbol_id"] for item in normalized]
    if (
        normalized != assignments
        or assignments != sorted(assignments, key=lambda item: item["symbol_id"])
        or identities != expected
    ):
        raise ValueError("native_symbol_candidate_coverage_invalid")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != NATIVE_SYMBOL_CANDIDATE_KIND
        or value.get("status") != "candidate"
        or value.get("context_sha256") != context["context_sha256"]
        or value.get("native_assignment_count")
        != _count(assignments, "native-requirement")
        or value.get("runtime_assignment_count") != _count(assignments, "runtime")
        or value.get("defer_count") != _count(assignments, "defer")
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
    ):
        raise ValueError("native_symbol_candidate_summary_invalid")
    claimed = value.get("candidate_sha256")
    projection = {key: item for key, item in value.items() if key != "candidate_sha256"}
    if not is_sha256(claimed) or claimed != content_sha256(projection):
        raise ValueError("native_symbol_candidate_sha256_drift")
    return {**dict(value), "assignments": normalized}


def _validate_assignment(
    value: Any, context: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ASSIGNMENT_KEYS:
        raise ValueError("native_symbol_assignment_schema_invalid")
    result = dict(value)
    symbol_ids = {item["symbol_id"] for item in context["symbols"]}
    provider_kind = result.get("provider_kind")
    requirement_id = result.get("requirement_id")
    if result.get("symbol_id") not in symbol_ids:
        raise ValueError("native_symbol_assignment_symbol_invalid")
    if provider_kind == "native-requirement":
        providers = {
            item["requirement_id"]: item for item in context["providers"]
        }
        provider = providers.get(requirement_id)
        if provider is None or provider["strategy"] != "rustc-link-lib":
            raise ValueError("native_symbol_assignment_provider_invalid")
    elif provider_kind in {"runtime", "defer"}:
        if requirement_id is not None:
            raise ValueError("native_symbol_assignment_provider_invalid")
    else:
        raise ValueError("native_symbol_assignment_provider_invalid")
    return result


def _count(values: list[dict[str, Any]], provider_kind: str) -> int:
    return sum(item["provider_kind"] == provider_kind for item in values)


__all__ = [
    "MAX_NATIVE_SYMBOL_PROMPT_BYTES", "NATIVE_SYMBOL_CANDIDATE_KIND",
    "NATIVE_SYMBOL_RESPONSE_KIND", "build_native_symbol_candidate",
    "render_native_symbol_prompt", "validate_native_symbol_candidate",
    "validate_native_symbol_response",
]
