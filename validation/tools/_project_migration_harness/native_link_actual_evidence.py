from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .gate_evidence import (
    read_content_addressed_json, require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError
from .native_link_actual_resolution import resolve_traced_native_artifacts
from .native_link_actual_validation import (
    validate_native_link_actual_resolution,
)
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_trace import validate_cargo_linker_trace


NATIVE_LINK_ACTUAL_BINDING_KEYS = {
    "schema_version", "status", "context_sha256", "candidate_sha256",
    "trace_entry_set_sha256", "artifact", "requirement_count",
    "unverified_gates", "semantic_gate", "resolution_gate",
}


def persist_native_link_actual_evidence(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    out_root: Path,
    guest_roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    result = resolve_traced_native_artifacts(
        trace, context, candidate, guest_roots=guest_roots,
    )
    reference = write_content_addressed_json(
        out_root, "native-link-actual", result,
    )
    binding = {
        "schema_version": 1,
        "status": result["status"],
        "context_sha256": result["context_sha256"],
        "candidate_sha256": result["candidate_sha256"],
        "trace_entry_set_sha256": result["trace_entry_set_sha256"],
        "artifact": reference,
        "requirement_count": len(result["requirements"]),
        "unverified_gates": list(result["unverified_gates"]),
        "semantic_gate": False,
        "resolution_gate": False,
    }
    return validate_native_link_actual_binding(
        binding, trace, context, candidate,
    )


def reopen_native_link_actual_evidence(
    ledger_path: Path,
    binding: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    guest_roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    normalized = validate_native_link_actual_binding(
        binding, trace, context, candidate,
    )
    reference = normalized["artifact"]
    payload = read_content_addressed_json(
        ledger_path, reference["path"], reference["sha256"],
    )
    if len(canonical_json_bytes(payload)) != reference["size_bytes"]:
        raise LedgerError("native link actual evidence size drifted")
    try:
        observed = validate_native_link_actual_resolution(
            payload, trace, context, candidate,
        )
        recomputed = resolve_traced_native_artifacts(
            trace, context, candidate, guest_roots=guest_roots,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise LedgerError("native link actual evidence is invalid") from error
    if (
        normalized["status"] != observed["status"]
        or normalized["requirement_count"] != len(observed["requirements"])
        or normalized["unverified_gates"] != observed["unverified_gates"]
    ):
        raise LedgerError("native link actual binding drifted")
    if canonical_json_bytes(observed) != canonical_json_bytes(recomputed):
        raise LedgerError("native link actual artifact recompute drifted")
    return observed


def validate_native_link_actual_binding(
    value: Any,
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    if not isinstance(value, Mapping) or set(value) != NATIVE_LINK_ACTUAL_BINDING_KEYS:
        raise ValueError("native_link_actual_binding_schema_invalid")
    result = dict(value)
    reference = result.get("artifact")
    if not isinstance(reference, Mapping):
        raise ValueError("native_link_actual_binding_reference_invalid")
    try:
        require_content_addressed_reference(reference)
    except LedgerError as error:
        raise ValueError("native_link_actual_binding_reference_invalid") from error
    if (
        result.get("schema_version") != 1
        or result.get("status") not in {"observed", "blocked"}
        or result.get("context_sha256") != context["context_sha256"]
        or result.get("candidate_sha256") != candidate["candidate_sha256"]
        or result.get("trace_entry_set_sha256")
        != normalized_trace["entry_set_sha256"]
        or type(result.get("requirement_count")) is not int
        or result["requirement_count"] != len(context["requirements"])
        or result.get("unverified_gates") != ["symbols", "target-triple"]
        or result.get("semantic_gate") is not False
        or result.get("resolution_gate") is not False
    ):
        raise ValueError("native_link_actual_binding_summary_invalid")
    result["artifact"] = dict(reference)
    return result


__all__ = [
    "NATIVE_LINK_ACTUAL_BINDING_KEYS", "persist_native_link_actual_evidence",
    "reopen_native_link_actual_evidence", "validate_native_link_actual_binding",
]
