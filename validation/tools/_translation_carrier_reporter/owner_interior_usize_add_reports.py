from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .owner_interior_usize_add_contract import behavior_fields
from .owner_interior_usize_add_model import mutated_outputs
from .source_binding import StaticContext


def build_negative_report(
    context: StaticContext, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    actual_runs = execution["partition_replay"]["case_runs"]
    detected_ids = [str(item["case_id"]) for item in actual_runs]
    expected_ids = [str(case["id"]) for case in context.cases]
    if detected_ids != expected_ids:
        raise ReporterError("owner interior usize-add negative replay case ids drifted")
    partition = execution["partition_replay"]
    state_field = behavior_fields(context.contract)[1]
    observable_ids = [
        str(case["id"])
        for case in context.cases
        if mutated_outputs(case, context.contract)[state_field]
        != case["expected_outputs"][state_field]
    ]
    if partition["observable_mismatch_case_ids"] != observable_ids:
        raise ReporterError("owner interior usize-add mutation partition drifted")
    equivalent_ids = [
        str(item["case_id"])
        for item in actual_runs
        if item.get("comparison_partition") == "mutation_equivalent"
    ]
    if equivalent_ids != [item for item in expected_ids if item not in observable_ids]:
        raise ReporterError("owner interior usize-add equivalent mutation partition drifted")
    mismatches: list[dict[str, Any]] = []
    for case in context.cases:
        expected = case["expected_outputs"]
        mutated = mutated_outputs(case, context.contract)
        if mutated[state_field] == expected[state_field]:
            continue
        mismatches.append({
            "case_id": case["id"], "field": state_field,
            "accepted_value": expected[state_field], "mutated_value": mutated[state_field],
        })
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "wrapping_add changed to wrapping_sub",
        "detected_case_ids": detected_ids,
        "partition_detection": {
            "observable_mismatch_case_ids": partition["observable_mismatch_case_ids"],
            "mutation_equivalent_case_ids": equivalent_ids,
        },
        "actual_mutation_execution": execution,
        "first_mismatch": mismatches[0],
        "mismatches": mismatches,
    }


def build_report_claim(context: StaticContext) -> dict[str, Any]:
    contract = context.contract
    return {
        "scope": "source_fragment_only",
        "whole_function_semantics_verified": False,
        "external_callee_semantics_verified": False,
        "verified_behavior": (
            "One mutable owner record root exposes an interior mutable alias. Its direct u32 "
            "rhs is losslessly widened under the bound LP64 ABI and wrapping-added to a "
            "non-overlapping direct usize accumulator; the fixed bool result is observed."
        ),
        "external_callee": None,
        "field_update": {
            "operation": "wrapping_add",
            "target_owner_field_path": contract["state_output"]["owner_field_path"],
            "source_owner_field_path": contract["rhs"]["owner_field_path"],
            "projection_path": contract["projection_path"],
            "widening": contract["widening"],
        },
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }
