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


NATIVE_LINK_ORDER_KIND = "native-link-order-evidence"


def build_native_link_order_evidence(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _validated_inputs(trace, context, candidate, actual_resolution)
    result = _build(*inputs)
    return validate_native_link_order_evidence(
        result, trace, context, candidate, actual_resolution,
    )


def validate_native_link_order_evidence(
    value: Any,
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _validated_inputs(trace, context, candidate, actual_resolution)
    expected = _build(*inputs)
    if not isinstance(value, Mapping) or canonical_json_bytes(value) != (
        canonical_json_bytes(expected)
    ):
        raise ValueError("native_link_order_evidence_invalid")
    return expected


def _validated_inputs(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any], dict[str, Any]]:
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    actual = validate_native_link_actual_resolution(
        actual_resolution, normalized_trace, context, candidate,
    )
    return normalized_trace, context, candidate, actual


def _build(
    trace: dict[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual: dict[str, Any],
) -> dict[str, Any]:
    candidate_order = [
        item["requirement_id"] for item in candidate["proposals"]
        if item["strategy"] == "rustc-link-lib"
    ]
    requirement_ordinals = {
        item["requirement_id"]: set(item["trace_ordinals"])
        for item in actual["requirements"]
    }
    diagnostics = []
    witness = []
    for diagnostic in range(trace["diagnostic_count"]):
        entries = [
            item for item in trace["entries"]
            if item["diagnostic_ordinal"] == diagnostic
        ]
        positions = [
            [
                item["link_ordinal"] for item in entries
                if item["ordinal"] in requirement_ordinals.get(identifier, set())
            ]
            for identifier in candidate_order
        ]
        if not any(positions):
            continue
        order_match = _has_ordered_witness(positions)
        diagnostics.append({
            "diagnostic_ordinal": diagnostic,
            "requirement_link_ordinals": positions,
            "order_match": order_match,
        })
        if order_match:
            witness.append(diagnostic)
    all_direct = len(candidate_order) == len(context["requirements"])
    passed = actual["status"] == "observed" and all_direct and bool(witness)
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_ORDER_KIND,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "trace_entry_set_sha256": trace["entry_set_sha256"],
        "actual_resolution_sha256": actual["artifact_sha256"],
        "candidate_order": candidate_order,
        "diagnostics": diagnostics,
        "witness_diagnostic_ordinals": witness,
        "status": "passed" if passed else "blocked",
        "order_gate": passed,
        "semantic_gate": False,
    }
    return {**core, "report_sha256": content_sha256(core)}


def _has_ordered_witness(positions: list[list[int]]) -> bool:
    previous = -1
    for options in positions:
        selected = next((item for item in options if item > previous), None)
        if selected is None:
            return False
        previous = selected
    return bool(positions)


__all__ = [
    "NATIVE_LINK_ORDER_KIND", "build_native_link_order_evidence",
    "validate_native_link_order_evidence",
]
