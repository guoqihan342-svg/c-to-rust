from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_resolution_validation import (
    NATIVE_LINK_HOST_EVIDENCE_KIND,
    NATIVE_LINK_RESOLUTION_ISSUER,
    NATIVE_LINK_RESOLUTION_KIND,
    NATIVE_LINK_RESOLUTION_SCHEMA_VERSION,
    derived_resolution_status,
    validate_native_link_host_evidence,
    validate_native_link_resolution_receipt,
)


def build_native_link_resolution_receipt(
    context: Mapping[str, Any], candidate: Mapping[str, Any],
    host_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Issue a receipt whose status is derived only from host evidence."""
    return recompute_native_link_resolution_receipt(
        context, candidate, host_evidence,
    )


def recompute_native_link_resolution_receipt(
    context: Mapping[str, Any], candidate: Mapping[str, Any],
    host_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    evidence = validate_native_link_host_evidence(
        host_evidence, context, candidate,
    )
    resolutions = []
    for item in evidence["requirements"]:
        statuses = [evidence["cargo"]["status"]] + [
            item[field]["status"]
            for field in ("toolchain", "abi", "linker_trace", "actual_artifact")
        ]
        resolutions.append({
            **item, "status": derived_resolution_status(statuses),
        })
    payload = {
        "schema_version": NATIVE_LINK_RESOLUTION_SCHEMA_VERSION,
        "artifact_kind": NATIVE_LINK_RESOLUTION_KIND,
        "issuer": NATIVE_LINK_RESOLUTION_ISSUER,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "build_ir_semantic_sha256": context["build_ir_binding"]["semantic_sha256"],
        "toolchain_abi_sha256": context["build_ir_binding"]["toolchain_abi_sha256"],
        "project_input_sha256": evidence["project_input_sha256"],
        "host_evidence_sha256": content_sha256(evidence),
        "cargo": evidence["cargo"],
        "resolutions": resolutions,
        "requirement_count": len(resolutions),
        "status": derived_resolution_status([
            item["status"] for item in resolutions
        ]),
        "semantic_gate": False,
    }
    payload["receipt_sha256"] = native_link_resolution_receipt_sha256(payload)
    return validate_native_link_resolution_receipt(payload, context, candidate)


def reopen_native_link_resolution_receipt(
    value: Mapping[str, Any], context: Mapping[str, Any],
    candidate: Mapping[str, Any], host_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    receipt = validate_native_link_resolution_receipt(value, context, candidate)
    expected = recompute_native_link_resolution_receipt(
        context, candidate, host_evidence,
    )
    if canonical_json_bytes(receipt) != canonical_json_bytes(expected):
        raise ValueError("native_link_resolution_recompute_drift")
    return receipt


def native_link_resolution_receipt_sha256(value: Mapping[str, Any]) -> str:
    return content_sha256({
        key: item for key, item in value.items() if key != "receipt_sha256"
    })


canonical_native_link_resolution_receipt_sha256 = (
    native_link_resolution_receipt_sha256
)
reopen_and_validate_native_link_resolution_receipt = (
    reopen_native_link_resolution_receipt
)


__all__ = [
    "NATIVE_LINK_HOST_EVIDENCE_KIND", "NATIVE_LINK_RESOLUTION_ISSUER",
    "NATIVE_LINK_RESOLUTION_KIND", "NATIVE_LINK_RESOLUTION_SCHEMA_VERSION",
    "build_native_link_resolution_receipt",
    "canonical_native_link_resolution_receipt_sha256",
    "native_link_resolution_receipt_sha256",
    "recompute_native_link_resolution_receipt",
    "reopen_and_validate_native_link_resolution_receipt",
    "reopen_native_link_resolution_receipt",
    "validate_native_link_resolution_receipt",
]
