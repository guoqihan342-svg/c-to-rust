from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .native_link_actual_validation import (
    validate_native_link_actual_resolution,
)
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_trace import validate_cargo_linker_trace
from .native_target_abi import compare_native_target_abi
from .sandbox_native_linker_contract import native_linker_contract_from_payload


NATIVE_LINK_ABI_EVIDENCE_KIND = "native-link-abi-evidence"


def build_native_link_abi_evidence(
    linker_contract: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _validated_inputs(
        linker_contract, trace, context, candidate, actual_resolution,
    )
    return _build(*inputs)


def validate_native_link_abi_evidence(
    value: Any,
    linker_contract: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    expected = _build(*_validated_inputs(
        linker_contract, trace, context, candidate, actual_resolution,
    ))
    if not isinstance(value, Mapping) or canonical_json_bytes(value) != (
        canonical_json_bytes(expected)
    ):
        raise ValueError("native_link_abi_evidence_invalid")
    return expected


def _validated_inputs(
    linker_contract: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
) -> tuple[Any, dict[str, Any], Mapping[str, Any], Mapping[str, Any], dict[str, Any]]:
    contract = native_linker_contract_from_payload(linker_contract)
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    actual = validate_native_link_actual_resolution(
        actual_resolution, normalized_trace, context, candidate,
    )
    return contract, normalized_trace, context, candidate, actual


def _build(
    contract: Any,
    trace: dict[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual: dict[str, Any],
) -> dict[str, Any]:
    inspections = [
        item["inspection"] for item in actual["requirements"]
        if item["status"] == "passed" and item["inspection"] is not None
    ]
    report = None
    if actual["status"] == "observed" and len(inspections) == len(
        context["requirements"]
    ):
        unique = {
            item["inspection_sha256"]: item for item in inspections
        }
        report = compare_native_target_abi(
            contract.target_triple, list(unique.values()),
        )
    passed = report is not None and report["abi_gate"] is True
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_ABI_EVIDENCE_KIND,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "trace_entry_set_sha256": trace["entry_set_sha256"],
        "actual_resolution_sha256": actual["artifact_sha256"],
        "native_linker_binding_sha256": contract.binding_sha256,
        "target_triple": contract.target_triple,
        "abi_report": report,
        "status": "passed" if passed else "blocked",
        "abi_gate": passed,
        "semantic_gate": False,
    }
    return {**core, "evidence_sha256": content_sha256(core)}


__all__ = [
    "NATIVE_LINK_ABI_EVIDENCE_KIND", "build_native_link_abi_evidence",
    "validate_native_link_abi_evidence",
]
