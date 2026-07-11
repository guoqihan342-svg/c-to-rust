from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .source_binding import StaticContext
from .stats_sequence_contract import behavior_fields
from .stats_sequence_model import mutated_outputs


def build_negative_report(
    context: StaticContext, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    actual_runs = execution["partition_replay"]["case_runs"]
    detected_ids = [str(item["case_id"]) for item in actual_runs]
    expected_ids = [str(case["id"]) for case in context.cases]
    if detected_ids != expected_ids:
        raise ReporterError("stats sequence negative replay case ids drifted")
    mutated_field = behavior_fields(context.contract)[3]
    observable_ids = [
        str(case["id"])
        for case in context.cases
        if mutated_outputs(case, context.contract)[mutated_field]
        != case["expected_outputs"][mutated_field]
    ]
    partition = execution["partition_replay"]
    if partition["observable_mismatch_case_ids"] != observable_ids:
        raise ReporterError("stats sequence second-add mutation partition drifted")
    equivalent_ids = [
        str(item["case_id"])
        for item in actual_runs
        if item.get("comparison_partition") == "mutation_equivalent"
    ]
    if equivalent_ids != [item for item in expected_ids if item not in observable_ids]:
        raise ReporterError("stats sequence equivalent mutation partition drifted")
    mismatches = []
    for case in context.cases:
        expected = case["expected_outputs"]
        mutated = mutated_outputs(case, context.contract)
        if mutated[mutated_field] == expected[mutated_field]:
            continue
        mismatches.append(
            {
                "case_id": case["id"],
                "field": mutated_field,
                "accepted_value": expected[mutated_field],
                "mutated_value": mutated[mutated_field],
            }
        )
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "second wrapping_add changed to wrapping_sub",
        "detected_case_ids": detected_ids,
        "partition_detection": {
            "observable_mismatch_case_ids": observable_ids,
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
            "One mutable owner record root performs one direct u32 postfix increment followed "
            "in order by two distinct direct LP64 usize wrapping additions from two distinct "
            "direct u32 fields reached through one pointer-typedef interior alias, then returns true."
        ),
        "external_callee": None,
        "ordered_updates": contract["updates"],
        "projection_path": contract["projection_path"],
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }
