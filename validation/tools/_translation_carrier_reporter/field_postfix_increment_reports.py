from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .field_postfix_increment_contract import behavior_fields
from .field_postfix_increment_model import mutated_outputs
from .source_binding import StaticContext


def build_negative_report(
    context: StaticContext, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    actual_runs = execution["partition_replay"]["case_runs"]
    detected_ids = [str(item["case_id"]) for item in actual_runs]
    expected_ids = [str(case["id"]) for case in context.cases]
    if detected_ids != expected_ids:
        raise ReporterError("postfix-increment negative replay case ids drifted")
    partition = execution["partition_replay"]
    if partition["observable_mismatch_case_ids"] != expected_ids:
        raise ReporterError("postfix-increment mutation did not reach every observable case")

    state_field = behavior_fields(context.contract)[1]
    mismatches: list[dict[str, Any]] = []
    for case in context.cases:
        expected = case["expected_outputs"]
        mutated = mutated_outputs(case, context.contract)
        if mutated[state_field] == expected[state_field]:
            raise ReporterError(f"postfix-increment mutation is not observable for {case['id']}")
        mismatches.append(
            {
                "case_id": case["id"],
                "field": state_field,
                "accepted_value": expected[state_field],
                "mutated_value": mutated[state_field],
            }
        )
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "wrapping_add changed to wrapping_sub",
        "detected_case_ids": detected_ids,
        "partition_detection": {
            "observable_mismatch_case_ids": partition["observable_mismatch_case_ids"]
        },
        "actual_mutation_execution": execution,
        "first_mismatch": mismatches[0],
        "mismatches": mismatches,
    }


def build_report_claim(context: StaticContext) -> dict[str, Any]:
    state = context.contract["state_output"]
    return {
        "scope": "source_fragment_only",
        "whole_function_semantics_verified": False,
        "external_callee_semantics_verified": False,
        "verified_behavior": (
            "The direct u32 field on one mutable record pointer is updated by a fixed "
            "wrapping increment of one; the declared constant bool result is observed."
        ),
        "external_callee": None,
        "field_update": {
            "operation": "wrapping_add",
            "increment": 1,
            "target_parameter": state["parameter"],
            "target_field_path": state["field_path"],
        },
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }
