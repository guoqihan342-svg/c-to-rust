from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .ledger_security import LedgerError
from .native_link_abi_evidence import validate_native_link_abi_evidence
from .native_link_actual_validation import (
    validate_native_link_actual_resolution,
)
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_order import validate_native_link_order_evidence
from .native_link_symbol_evidence import (
    validate_native_link_symbol_evidence,
)
from .native_link_trace import validate_cargo_linker_trace
from .native_symbol_context import validate_native_symbol_context
from .project_cargo_evidence import derive_project_cargo_status
from .sandbox_native_linker_contract import native_linker_contract_from_payload


NATIVE_LINK_SETTLEMENT_KIND = "native-link-settlement-receipt"
NATIVE_LINK_SETTLEMENT_ISSUER = "native-link-host-settlement-v1"


def build_native_link_settlement(
    *,
    cargo_test_observation: Mapping[str, Any],
    linker_contract: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    order_evidence: Mapping[str, Any],
    abi_evidence: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbol_reports: Mapping[str, Mapping[str, Any]],
    symbol_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _validated_inputs(
        cargo_test_observation, linker_contract, trace, context, candidate,
        actual_resolution, order_evidence, abi_evidence,
        symbol_context, symbol_candidate, symbol_reports, symbol_evidence,
    )
    return _build(*inputs)


def validate_native_link_settlement(
    value: Any,
    *,
    cargo_test_observation: Mapping[str, Any],
    linker_contract: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    order_evidence: Mapping[str, Any],
    abi_evidence: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbol_reports: Mapping[str, Mapping[str, Any]],
    symbol_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    expected = _build(*_validated_inputs(
        cargo_test_observation, linker_contract, trace, context, candidate,
        actual_resolution, order_evidence, abi_evidence,
        symbol_context, symbol_candidate, symbol_reports, symbol_evidence,
    ))
    if not isinstance(value, Mapping) or canonical_json_bytes(value) != (
        canonical_json_bytes(expected)
    ):
        raise ValueError("native_link_settlement_invalid")
    return expected


def _validated_inputs(
    cargo: Mapping[str, Any],
    linker_contract: Mapping[str, Any],
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    order_evidence: Mapping[str, Any],
    abi_evidence: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbol_reports: Mapping[str, Mapping[str, Any]],
    symbol_evidence: Mapping[str, Any],
) -> tuple[Any, dict[str, Any], Mapping[str, Any], Mapping[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = native_linker_contract_from_payload(linker_contract)
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    actual = validate_native_link_actual_resolution(
        actual_resolution, normalized_trace, context, candidate,
    )
    order = validate_native_link_order_evidence(
        order_evidence, normalized_trace, context, candidate, actual,
    )
    abi = validate_native_link_abi_evidence(
        abi_evidence, linker_contract, normalized_trace,
        context, candidate, actual,
    )
    symbols = validate_native_symbol_context(symbol_context)
    symbol_result = validate_native_link_symbol_evidence(
        symbol_evidence, normalized_trace, context, candidate, actual,
        symbols, symbol_candidate, symbol_reports,
    )
    try:
        cargo_status = derive_project_cargo_status("cargo-test", cargo)
    except LedgerError as error:
        raise ValueError("native_link_settlement_cargo_evidence_invalid") from error
    project_input = cargo.get("project_input_sha256")
    if not is_sha256(project_input):
        raise ValueError("native_link_settlement_project_input_invalid")
    cargo_binding = {
        "status": cargo_status,
        "project_input_sha256": project_input,
        "observation_sha256": content_sha256(cargo),
    }
    return contract, normalized_trace, context, candidate, actual, order, abi, {
        "symbols": symbol_result, "cargo": cargo_binding,
    }


def _build(
    contract: Any,
    trace: dict[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual: dict[str, Any],
    order: dict[str, Any],
    abi: dict[str, Any],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    symbols = evidence["symbols"]
    cargo = evidence["cargo"]
    gates = {
        "cargo-test": cargo["status"] == "passed",
        "actual-artifact": actual["status"] == "observed",
        "link-order": order["order_gate"] is True,
        "target-abi": abi["abi_gate"] is True,
        "symbols": symbols["symbol_gate"] is True,
    }
    blockers = sorted(name for name, passed in gates.items() if not passed)
    resolved = not blockers
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_SETTLEMENT_KIND,
        "issuer": NATIVE_LINK_SETTLEMENT_ISSUER,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "build_ir_semantic_sha256": context["build_ir_binding"]["semantic_sha256"],
        "toolchain_abi_sha256": context["build_ir_binding"]["toolchain_abi_sha256"],
        "project_input_sha256": cargo["project_input_sha256"],
        "cargo_test_observation_sha256": cargo["observation_sha256"],
        "native_linker_binding_sha256": contract.binding_sha256,
        "target_triple": contract.target_triple,
        "trace_source_sha256": trace["source_sha256"],
        "trace_entry_set_sha256": trace["entry_set_sha256"],
        "actual_resolution_sha256": actual["artifact_sha256"],
        "order_evidence_sha256": order["report_sha256"],
        "abi_evidence_sha256": abi["evidence_sha256"],
        "symbol_evidence_sha256": symbols["evidence_sha256"],
        "requirement_count": len(context["requirements"]),
        "gates": gates,
        "blockers": blockers,
        "status": "resolved" if resolved else "blocked",
        "resolution_gate": resolved,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "receipt_sha256": content_sha256(core)}


__all__ = [
    "NATIVE_LINK_SETTLEMENT_ISSUER", "NATIVE_LINK_SETTLEMENT_KIND",
    "build_native_link_settlement", "validate_native_link_settlement",
]
