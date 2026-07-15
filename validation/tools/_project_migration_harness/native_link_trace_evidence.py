from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .cargo_raw_output_evidence import read_cargo_raw_output
from .gate_evidence import (
    read_content_addressed_json,
    require_content_addressed_reference,
    write_content_addressed_json,
)
from .ledger_security import LedgerError
from .native_link_trace import (
    CargoLinkerTraceError,
    parse_cargo_linker_trace,
    validate_cargo_linker_trace,
)
from .sandbox_native_linker_contract import (
    NativeLinkerContract, native_linker_contract_from_payload,
)


TRACE_BINDING_KEYS = {
    "schema_version", "status", "cargo_gate", "source_stdout_sha256",
    "native_linker_binding_sha256", "artifact", "entry_count", "semantic_gate",
}


def persist_captured_native_link_trace(
    execution: Mapping[str, Any], *, out_root: Path, required: bool,
) -> dict[str, Any]:
    if type(required) is not bool:
        raise ValueError("native linker trace requirement must be a boolean")
    result = deepcopy(dict(execution))
    checks = result.get("checks")
    requested = [
        item for item in checks if _trace_requested(item)
    ] if isinstance(checks, list) else []
    if not requested:
        if required:
            return _blocked(result, "native_link_trace_request_missing")
        result["native_link_trace"] = _binding("not-required")
        return result
    if len(requested) != 1:
        return _blocked(result, "native_link_trace_request_invalid")
    check = requested[0]
    source = check.get("_captured_stdout")
    if check.get("status") != "passed" or not isinstance(source, bytes):
        return _blocked(result, "native_link_trace_source_unavailable")
    try:
        linker_contract = _native_linker_contract(result.get("sandbox"))
        trace = parse_cargo_linker_trace(source)
        reference = write_content_addressed_json(
            out_root, "native-link-trace", trace,
        )
    except (CargoLinkerTraceError, OSError, TypeError, ValueError):
        return _blocked(result, "native_link_trace_invalid")
    result["native_link_trace"] = {
        "schema_version": 1,
        "status": "passed",
        "cargo_gate": "cargo-test",
        "source_stdout_sha256": trace["source_sha256"],
        "native_linker_binding_sha256": linker_contract.binding_sha256,
        "artifact": reference,
        "entry_count": len(trace["entries"]),
        "semantic_gate": False,
    }
    return result


def reopen_native_link_trace_evidence(
    ledger_path: Path, binding: Mapping[str, Any],
    cargo_test_check: Mapping[str, Any], sandbox: Mapping[str, Any],
) -> dict[str, Any]:
    normalized = validate_native_link_trace_binding(binding, required=True)
    expected_source = str(cargo_test_check.get("stdout_sha256"))
    if normalized["source_stdout_sha256"] != expected_source:
        raise LedgerError("native linker trace source binding drifted")
    try:
        linker_contract = _native_linker_contract(sandbox)
    except (TypeError, ValueError) as error:
        raise LedgerError("native linker sandbox contract is invalid") from error
    if normalized["native_linker_binding_sha256"] != linker_contract.binding_sha256:
        raise LedgerError("native linker trace toolchain binding drifted")
    source = read_cargo_raw_output(
        ledger_path, cargo_test_check.get("stdout_ref"),
        gate_kind="cargo-test", stream="stdout",
        expected_sha256=expected_source,
    )
    reference = normalized["artifact"]
    payload = read_content_addressed_json(
        ledger_path, reference["path"], reference["sha256"],
    )
    if len(canonical_json_bytes(payload)) != reference["size_bytes"]:
        raise LedgerError("native linker trace artifact size drifted")
    try:
        trace = validate_cargo_linker_trace(payload, source)
    except (CargoLinkerTraceError, TypeError, ValueError) as error:
        raise LedgerError("native linker trace evidence is invalid") from error
    if len(trace["entries"]) != normalized["entry_count"]:
        raise LedgerError("native linker trace entry count drifted")
    return trace


def validate_native_link_trace_binding(
    value: Mapping[str, Any], *, required: bool,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != TRACE_BINDING_KEYS:
        raise ValueError("native_link_trace_binding_schema_invalid")
    result = dict(value)
    status = result.get("status")
    if result.get("schema_version") != 1 or result.get("semantic_gate") is not False:
        raise ValueError("native_link_trace_binding_schema_invalid")
    if status == "not-required" and not required:
        if any(result.get(key) is not None for key in (
            "cargo_gate", "source_stdout_sha256",
            "native_linker_binding_sha256", "artifact",
        )) or result.get("entry_count") != 0:
            raise ValueError("native_link_trace_not_required_claim_invalid")
        return result
    if status != "passed" or result.get("cargo_gate") != "cargo-test":
        raise ValueError("native_link_trace_required_evidence_missing")
    reference = result.get("artifact")
    if not isinstance(reference, Mapping):
        raise ValueError("native_link_trace_artifact_reference_invalid")
    require_content_addressed_reference(reference)
    count = result.get("entry_count")
    source = result.get("source_stdout_sha256")
    linker = result.get("native_linker_binding_sha256")
    if (
        type(count) is not int or count <= 0
        or not isinstance(source, str) or len(source) != 64
        or any(character not in "0123456789abcdef" for character in source)
        or not isinstance(linker, str) or len(linker) != 64
        or any(character not in "0123456789abcdef" for character in linker)
    ):
        raise ValueError("native_link_trace_binding_summary_invalid")
    result["artifact"] = dict(reference)
    return result


def _trace_requested(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    plan = value.get("sandbox_verification_plan")
    return isinstance(plan, Mapping) and plan.get("native_link_trace") is True


def _binding(status: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": status,
        "cargo_gate": None,
        "source_stdout_sha256": None,
        "native_linker_binding_sha256": None,
        "artifact": None,
        "entry_count": 0,
        "semantic_gate": False,
    }


def _blocked(result: dict[str, Any], code: str) -> dict[str, Any]:
    result["native_link_trace"] = _binding("blocked")
    result["status"] = "blocked"
    diagnostics = result.get("diagnostics")
    result["diagnostics"] = [*(diagnostics if isinstance(diagnostics, list) else []), {
        "code": code,
        "stage": "native-link-trace",
        "message": "Native linker trace evidence could not be produced",
    }]
    return result


def _native_linker_contract(sandbox: Any) -> NativeLinkerContract:
    contract = sandbox.get("contract") if isinstance(sandbox, Mapping) else None
    native = contract.get("native_linker") if isinstance(contract, Mapping) else None
    return native_linker_contract_from_payload(native)


__all__ = [
    "TRACE_BINDING_KEYS", "persist_captured_native_link_trace",
    "reopen_native_link_trace_evidence", "validate_native_link_trace_binding",
]
