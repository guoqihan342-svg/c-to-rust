from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .native_link_context import (
    model_native_link_context, validate_native_link_context,
)
from .runtime_security import assert_model_payload_safe


NATIVE_LINK_RESPONSE_KIND = "native-link-model-response"
NATIVE_LINK_CANDIDATE_KIND = "native-link-candidate"
MAX_NATIVE_LINK_PROMPT_BYTES = 512 * 1024
_PORTABLE_LINK_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}\Z")
_RESPONSE_KEYS = {
    "schema_version", "artifact_kind", "context_sha256", "proposals",
}
_PROPOSAL_KEYS = {
    "requirement_id", "strategy", "rustc_link_name", "rustc_link_kind",
}
_CANDIDATE_KEYS = {
    "schema_version", "artifact_kind", "status", "context_sha256",
    "build_ir_semantic_sha256", "proposals", "cargo_directive_count",
    "claim_boundary", "candidate_sha256",
}
_CLAIM_BOUNDARY = {
    "artifact_role": "native-link-candidate",
    "native_link_config_resolved": False,
    "cargo_executed": False,
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}


def render_native_link_prompt(
    context: Mapping[str, Any], *,
    max_prompt_bytes: int = MAX_NATIVE_LINK_PROMPT_BYTES,
) -> str:
    validate_native_link_context(context)
    if context["status"] != "planning-required":
        raise ValueError("native_link_context_not_required")
    if (
        isinstance(max_prompt_bytes, bool) or not isinstance(max_prompt_bytes, int)
        or not 4_096 <= max_prompt_bytes <= MAX_NATIVE_LINK_PROMPT_BYTES
    ):
        raise ValueError("native_link_prompt_limit_invalid")
    payload = {
        "schema_version": 1,
        "task": "select generic native-link strategies for a Rust project",
        "rules": [
            "Use only grouped portable library identities from the host context.",
            "Return exactly one proposal for every requirement_id.",
            "Never emit absolute paths, search paths, shell flags, or project-specific shims.",
            "A proposal is only a candidate; the host and Cargo decide resolution.",
            "Use defer when the visible evidence is insufficient.",
        ],
        "native_link_context": model_native_link_context(context),
        "output_schema": {
            "schema_version": 1,
            "artifact_kind": NATIVE_LINK_RESPONSE_KIND,
            "context_sha256": context["context_sha256"],
            "proposals": [{
                "requirement_id": "one visible requirement_id",
                "strategy": "rustc-link-lib | ffi-boundary | defer",
                "rustc_link_name": "portable name or null",
                "rustc_link_kind": "dylib | static | null",
            }],
        },
    }
    assert_model_payload_safe(payload, "native_link_prompt")
    encoded = canonical_json_bytes(payload)
    if len(encoded) > max_prompt_bytes:
        raise ValueError("native_link_prompt_too_large")
    return encoded.decode("utf-8")


def build_native_link_candidate(
    context: Mapping[str, Any], response: Mapping[str, Any],
) -> dict[str, Any]:
    validate_native_link_context(context)
    if context["status"] != "planning-required":
        raise ValueError("native_link_context_not_required")
    proposals = validate_native_link_response(response, context)
    payload = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_CANDIDATE_KIND,
        "status": "candidate",
        "context_sha256": context["context_sha256"],
        "build_ir_semantic_sha256": context["build_ir_binding"][
            "semantic_sha256"
        ],
        "proposals": proposals,
        "cargo_directive_count": sum(
            item["strategy"] == "rustc-link-lib" for item in proposals
        ),
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }
    payload["candidate_sha256"] = content_sha256(payload)
    validate_native_link_candidate(payload, context)
    return payload


def validate_native_link_response(
    response: Mapping[str, Any], context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    validate_native_link_context(context)
    if not isinstance(response, Mapping) or set(response) != _RESPONSE_KEYS:
        raise ValueError("native_link_response_schema_invalid")
    if (
        response.get("schema_version") != 1
        or response.get("artifact_kind") != NATIVE_LINK_RESPONSE_KIND
        or response.get("context_sha256") != context["context_sha256"]
    ):
        raise ValueError("native_link_response_binding_invalid")
    proposals = response.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("native_link_response_proposals_invalid")
    normalized = [validate_native_link_proposal(item) for item in proposals]
    expected_ids = {item["requirement_id"] for item in context["requirements"]}
    actual_ids = [item["requirement_id"] for item in normalized]
    if (
        len(actual_ids) != len(set(actual_ids))
        or set(actual_ids) != expected_ids
    ):
        raise ValueError("native_link_response_coverage_invalid")
    return sorted(normalized, key=lambda item: item["requirement_id"])


def validate_native_link_candidate(
    value: Mapping[str, Any], context: Mapping[str, Any],
) -> None:
    validate_native_link_context(context)
    if not isinstance(value, Mapping) or set(value) != _CANDIDATE_KEYS:
        raise ValueError("native_link_candidate_schema_invalid")
    proposals = value.get("proposals")
    if not isinstance(proposals, list):
        raise ValueError("native_link_candidate_proposals_invalid")
    normalized = [validate_native_link_proposal(item) for item in proposals]
    expected_ids = {item["requirement_id"] for item in context["requirements"]}
    actual_ids = [item["requirement_id"] for item in normalized]
    if (
        normalized != proposals
        or proposals != sorted(proposals, key=lambda item: item["requirement_id"])
        or len(actual_ids) != len(set(actual_ids))
        or set(actual_ids) != expected_ids
    ):
        raise ValueError("native_link_candidate_coverage_invalid")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != NATIVE_LINK_CANDIDATE_KIND
        or value.get("status") != "candidate"
        or value.get("context_sha256") != context["context_sha256"]
        or value.get("build_ir_semantic_sha256")
        != context["build_ir_binding"]["semantic_sha256"]
        or value.get("cargo_directive_count")
        != sum(item["strategy"] == "rustc-link-lib" for item in proposals)
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
    ):
        raise ValueError("native_link_candidate_summary_invalid")
    claimed = value.get("candidate_sha256")
    projection = {key: item for key, item in value.items() if key != "candidate_sha256"}
    if not is_sha256(claimed) or content_sha256(projection) != claimed:
        raise ValueError("native_link_candidate_sha256_drift")


def validate_native_link_proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PROPOSAL_KEYS:
        raise ValueError("native_link_proposal_schema_invalid")
    result = dict(value)
    requirement_id = result.get("requirement_id")
    strategy = result.get("strategy")
    name = result.get("rustc_link_name")
    kind = result.get("rustc_link_kind")
    if not isinstance(requirement_id, str) or not requirement_id.startswith(
        "native-link-requirement-"
    ):
        raise ValueError("native_link_proposal_identity_invalid")
    if strategy == "rustc-link-lib":
        if (
            not isinstance(name, str)
            or _PORTABLE_LINK_NAME.fullmatch(name) is None
            or name.startswith(("-", "."))
            or ".." in name
            or kind not in {"dylib", "static"}
        ):
            raise ValueError("native_link_proposal_directive_invalid")
    elif strategy in {"ffi-boundary", "defer"}:
        if name is not None or kind is not None:
            raise ValueError("native_link_proposal_non_directive_invalid")
    else:
        raise ValueError("native_link_proposal_strategy_invalid")
    return result


__all__ = [
    "MAX_NATIVE_LINK_PROMPT_BYTES", "NATIVE_LINK_CANDIDATE_KIND",
    "NATIVE_LINK_RESPONSE_KIND", "build_native_link_candidate",
    "render_native_link_prompt", "validate_native_link_candidate",
    "validate_native_link_proposal", "validate_native_link_response",
]
