from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .guarded_stats_sequence_contract import behavior_fields
from .guarded_stats_sequence_model import mutated_outputs
from .source_binding import StaticContext


def build_negative_report(
    context: StaticContext, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    actual_runs = execution["partition_replay"]["case_runs"]
    detected_ids = [str(item["case_id"]) for item in actual_runs]
    expected_ids = [str(case["id"]) for case in context.cases]
    if detected_ids != expected_ids:
        raise ReporterError("guarded stats negative replay case ids drifted")
    observable_ids = [
        str(case["id"])
        for case in context.cases
        if mutated_outputs(case, context.contract) != case["expected_outputs"]
    ]
    partition = execution["partition_replay"]
    if partition["observable_mismatch_case_ids"] != observable_ids:
        raise ReporterError("guarded stats second-equality mutation partition drifted")
    equivalent_ids = [
        str(item["case_id"])
        for item in actual_runs
        if item.get("comparison_partition") == "mutation_equivalent"
    ]
    if equivalent_ids != [item for item in expected_ids if item not in observable_ids]:
        raise ReporterError("guarded stats equivalent mutation partition drifted")
    mismatches: list[dict[str, Any]] = []
    for case in context.cases:
        expected = case["expected_outputs"]
        mutated = mutated_outputs(case, context.contract)
        for field in behavior_fields(context.contract):
            if mutated[field] != expected[field]:
                mismatches.append(
                    {
                        "case_id": case["id"],
                        "field": field,
                        "accepted_value": expected[field],
                        "mutated_value": mutated[field],
                    }
                )
    if not mismatches:
        raise ReporterError("guarded stats mutation produced no observable mismatch")
    return {
        **common,
        "status": "expected_failed",
        "expected_failure": True,
        "mutation_detected": True,
        "mutation": "second guard equality == changed to !=",
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
            "One mutable owner record root evaluates two ordered equality predicates through "
            "one pointer-typedef interior alias using short-circuit &&. A true guard performs "
            "three ordered wrapping statistics updates and returns true; a false guard leaves "
            "the owner unchanged and returns false."
        ),
        "external_callee": None,
        "guard": contract["guard"],
        "ordered_updates": contract["updates"],
        "projection_path": contract["projection_path"],
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }
