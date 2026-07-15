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
from .native_object_symbols import validate_native_object_symbols
from .native_symbol_context import validate_native_symbol_context
from .native_symbol_model import validate_native_symbol_candidate


NATIVE_LINK_SYMBOL_EVIDENCE_KIND = "native-link-symbol-evidence"


def build_native_link_symbol_evidence(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbol_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    inputs = _validated_inputs(
        trace, context, candidate, actual_resolution,
        symbol_context, symbol_candidate, symbol_reports,
    )
    return _build(*inputs)


def validate_native_link_symbol_evidence(
    value: Any,
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbol_reports: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    expected = _build(*_validated_inputs(
        trace, context, candidate, actual_resolution,
        symbol_context, symbol_candidate, symbol_reports,
    ))
    if not isinstance(value, Mapping) or canonical_json_bytes(value) != (
        canonical_json_bytes(expected)
    ):
        raise ValueError("native_link_symbol_evidence_invalid")
    return expected


def _validated_inputs(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    symbol_context: Mapping[str, Any],
    symbol_candidate: Mapping[str, Any] | None,
    symbol_reports: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any], dict[str, Any], dict[str, Any], dict[str, Any] | None, dict[str, dict[str, Any]]]:
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    actual = validate_native_link_actual_resolution(
        actual_resolution, normalized_trace, context, candidate,
    )
    symbols = validate_native_symbol_context(symbol_context)
    bindings = symbols["bindings"]
    if (
        bindings["native_link_context_sha256"] != context["context_sha256"]
        or bindings["native_link_candidate_sha256"] != candidate["candidate_sha256"]
    ):
        raise ValueError("native_link_symbol_context_binding_invalid")
    if symbols["status"] == "planning-required":
        assignment = (
            None if symbol_candidate is None
            else validate_native_symbol_candidate(symbol_candidate, symbols)
        )
    else:
        if symbol_candidate is not None:
            raise ValueError("native_link_symbol_candidate_unexpected")
        assignment = None
    if not isinstance(symbol_reports, Mapping):
        raise ValueError("native_link_symbol_reports_invalid")
    expected_report_ids = {
        item["requirement_id"] for item in actual["requirements"]
        if item["status"] == "passed"
    } if symbols["status"] == "planning-required" else set()
    if set(symbol_reports) != expected_report_ids:
        raise ValueError("native_link_symbol_report_coverage_invalid")
    inspections = {
        item["requirement_id"]: item["inspection"]
        for item in actual["requirements"]
    }
    reports = {}
    for identifier, raw in symbol_reports.items():
        report = validate_native_object_symbols(raw)
        inspection = inspections[identifier]
        if inspection is None or any(
            report[field] != inspection[field] for field in (
                "object_format", "object_kind", "member_count",
                "file_sha256", "size_bytes",
            )
        ):
            raise ValueError("native_link_symbol_report_object_drift")
        reports[identifier] = report
    return (
        normalized_trace, context, candidate, actual,
        symbols, assignment, reports,
    )


def _build(
    trace: dict[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual: dict[str, Any],
    symbol_context: dict[str, Any],
    symbol_candidate: dict[str, Any] | None,
    reports: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    report_bindings = [{
        "requirement_id": identifier,
        "report_sha256": report["report_sha256"],
        "file_sha256": report["file_sha256"],
        "symbol_set_sha256": report["symbol_set_sha256"],
    } for identifier, report in sorted(reports.items())]
    checks = []
    if symbol_context["status"] == "planning-required" and symbol_candidate is None:
        checks = [{
            "symbol_id": item["symbol_id"],
            "provider_kind": None,
            "requirement_id": None,
            "status": "blocked",
            "reason_code": "native_symbol_candidate_missing",
        } for item in symbol_context["symbols"]]
    elif symbol_candidate is not None:
        symbols = {
            item["symbol_id"]: item for item in symbol_context["symbols"]
        }
        for assignment in symbol_candidate["assignments"]:
            provider = assignment["provider_kind"]
            requirement_id = assignment["requirement_id"]
            if provider == "native-requirement":
                report = reports.get(requirement_id)
                passed = (
                    report is not None
                    and symbols[assignment["symbol_id"]]["link_name"]
                    in report["symbols"]
                )
                reason = (
                    "native_symbol_export_observed"
                    if passed else "native_symbol_export_missing"
                )
            elif provider == "runtime":
                passed = False
                reason = "native_symbol_runtime_provider_unverified"
            else:
                passed = False
                reason = "native_symbol_assignment_deferred"
            checks.append({
                "symbol_id": assignment["symbol_id"],
                "provider_kind": provider,
                "requirement_id": requirement_id,
                "status": "passed" if passed else "blocked",
                "reason_code": reason,
            })
    not_required = symbol_context["status"] == "not-required"
    passed = (
        not_required
        or (
            actual["status"] == "observed" and bool(checks)
            and all(item["status"] == "passed" for item in checks)
        )
    )
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_SYMBOL_EVIDENCE_KIND,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "trace_entry_set_sha256": trace["entry_set_sha256"],
        "actual_resolution_sha256": actual["artifact_sha256"],
        "native_symbol_context_sha256": symbol_context["context_sha256"],
        "native_symbol_candidate_sha256": (
            None if symbol_candidate is None
            else symbol_candidate["candidate_sha256"]
        ),
        "report_bindings": report_bindings,
        "checks": checks,
        "status": (
            "not-required" if not_required
            else ("passed" if passed else "blocked")
        ),
        "symbol_gate": passed,
        "semantic_gate": False,
    }
    return {**core, "evidence_sha256": content_sha256(core)}


__all__ = [
    "NATIVE_LINK_SYMBOL_EVIDENCE_KIND", "build_native_link_symbol_evidence",
    "validate_native_link_symbol_evidence",
]
