from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .gate_evidence import (
    read_content_addressed_json,
    write_content_addressed_json,
)
from .native_link_abi_evidence import build_native_link_abi_evidence
from .native_link_actual_evidence import (
    persist_native_link_actual_evidence,
    reopen_native_link_actual_evidence,
)
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_order import build_native_link_order_evidence
from .native_link_settlement import (
    build_native_link_settlement,
    validate_native_link_settlement,
)
from .native_link_symbol_evidence import build_native_link_symbol_evidence
from .native_link_symbol_reports import extract_native_link_symbol_reports
from .native_link_trace_evidence import reopen_native_link_trace_evidence
from .native_symbol_context import build_native_symbol_context
from .project_cargo_evidence import verify_project_cargo_raw_outputs
from .project_native_link_settlement_binding import (
    project_native_link_settlement_status,
    validate_project_native_link_settlement_binding,
)


def settle_project_native_links(
    *,
    ledger_path: Path,
    out_root: Path,
    native_state: Mapping[str, Any],
    rust_project_ir: Mapping[str, Any],
    execution: Mapping[str, Any],
    checks: Mapping[str, Mapping[str, Any]],
    observations: Mapping[str, Mapping[str, Any]],
    symbol_candidate: Mapping[str, Any] | None = None,
    guest_roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    context, candidate = _native_inputs(native_state)
    if not context["requirements"]:
        return project_native_link_settlement_status(
            "not-required", context=context,
        )
    if candidate is None:
        return project_native_link_settlement_status(
            "blocked", context=context,
            reason_code="native_link_candidate_missing",
        )
    cargo_test = observations.get("cargo-test")
    cargo_check = checks.get("test")
    sandbox = execution.get("sandbox")
    trace_binding = execution.get("native_link_trace")
    if not all(isinstance(value, Mapping) for value in (
        cargo_test, cargo_check, sandbox, trace_binding,
    )):
        raise ValueError("project_native_link_cargo_evidence_missing")
    verify_project_cargo_raw_outputs(
        Path(ledger_path), cargo_test, gate_kind="cargo-test",
    )
    trace = reopen_native_link_trace_evidence(
        Path(ledger_path), trace_binding, cargo_check, sandbox,
    )
    actual_binding = persist_native_link_actual_evidence(
        trace, context, candidate, out_root=Path(out_root),
        guest_roots=guest_roots,
    )
    actual = reopen_native_link_actual_evidence(
        Path(ledger_path), actual_binding, trace, context, candidate,
        guest_roots=guest_roots,
    )
    linker_contract = _linker_contract(sandbox)
    order = build_native_link_order_evidence(
        trace, context, candidate, actual,
    )
    abi = build_native_link_abi_evidence(
        linker_contract, trace, context, candidate, actual,
    )
    symbol_context = build_native_symbol_context(
        rust_project_ir, context, candidate,
    )
    symbol_reports = (
        extract_native_link_symbol_reports(
            trace, context, candidate, actual, guest_roots=guest_roots,
        )
        if symbol_context["status"] == "planning-required" else {}
    )
    symbols = build_native_link_symbol_evidence(
        trace, context, candidate, actual, symbol_context,
        symbol_candidate, symbol_reports,
    )
    settlement = build_native_link_settlement(
        cargo_test_observation=cargo_test,
        linker_contract=linker_contract,
        trace=trace,
        context=context,
        candidate=candidate,
        actual_resolution=actual,
        order_evidence=order,
        abi_evidence=abi,
        symbol_context=symbol_context,
        symbol_candidate=symbol_candidate,
        symbol_reports=symbol_reports,
        symbol_evidence=symbols,
    )
    artifacts = _persist_evidence(
        Path(out_root), trace_binding, actual_binding, order, abi,
        symbol_context, symbol_candidate, symbols, settlement,
    )
    reopened = read_content_addressed_json(
        Path(ledger_path), artifacts["settlement"]["path"],
        artifacts["settlement"]["sha256"],
    )
    validate_native_link_settlement(
        reopened,
        cargo_test_observation=cargo_test,
        linker_contract=linker_contract,
        trace=trace,
        context=context,
        candidate=candidate,
        actual_resolution=actual,
        order_evidence=order,
        abi_evidence=abi,
        symbol_context=symbol_context,
        symbol_candidate=symbol_candidate,
        symbol_reports=symbol_reports,
        symbol_evidence=symbols,
    )
    return project_native_link_settlement_status(
        str(settlement["status"]), context=context, candidate=candidate,
        reason_code=(
            None if settlement["resolution_gate"]
            else "native_link_settlement_gates_blocked"
        ),
        artifacts=artifacts,
        settlement_receipt_sha256=settlement["receipt_sha256"],
        resolution_gate=bool(settlement["resolution_gate"]),
    )


def _native_inputs(
    state: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if not isinstance(state, Mapping):
        raise ValueError("project_native_link_state_invalid")
    context = state.get("context")
    candidate = state.get("candidate")
    if not isinstance(context, Mapping):
        raise ValueError("project_native_link_state_invalid")
    validate_native_link_context(context)
    if candidate is not None:
        if not isinstance(candidate, Mapping):
            raise ValueError("project_native_link_state_invalid")
        validate_native_link_candidate(candidate, context)
    return dict(context), None if candidate is None else dict(candidate)


def _linker_contract(sandbox: Mapping[str, Any]) -> dict[str, Any]:
    contract = sandbox.get("contract")
    native = contract.get("native_linker") if isinstance(contract, Mapping) else None
    if not isinstance(native, Mapping):
        raise ValueError("project_native_linker_contract_missing")
    return dict(native)


def _persist_evidence(
    out_root: Path,
    trace_binding: Mapping[str, Any],
    actual_binding: Mapping[str, Any],
    order: Mapping[str, Any],
    abi: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbols: Mapping[str, Any],
    settlement: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "trace": dict(trace_binding["artifact"]),
        "actual_resolution": dict(actual_binding["artifact"]),
        "order_evidence": write_content_addressed_json(
            out_root, "native-link-order", order,
        ),
        "abi_evidence": write_content_addressed_json(
            out_root, "native-link-abi", abi,
        ),
        "symbol_context": write_content_addressed_json(
            out_root, "native-link-symbol-context", symbol_context,
        ),
        "symbol_candidate": (
            None if symbol_candidate is None else write_content_addressed_json(
                out_root, "native-link-symbol-candidate", symbol_candidate,
            )
        ),
        "symbol_evidence": write_content_addressed_json(
            out_root, "native-link-symbol", symbols,
        ),
        "settlement": write_content_addressed_json(
            out_root, "native-link-settlement", settlement,
        ),
    }


__all__ = [
    "project_native_link_settlement_status", "settle_project_native_links",
    "validate_project_native_link_settlement_binding",
]
