from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .interior_projection_contract import behavior_fields
from .interior_projection_model import mutated_outputs
from .source_binding import StaticContext


def build_negative_report(
    context: StaticContext, common: dict[str, Any], execution: dict[str, Any]
) -> dict[str, Any]:
    actual_runs = execution["partition_replay"]["case_runs"]
    detected_ids = [str(item["case_id"]) for item in actual_runs]
    expected_ids = [str(case["id"]) for case in context.cases]
    if detected_ids != expected_ids:
        raise ReporterError("interior projection negative replay case ids drifted")
    partition = execution["partition_replay"]
    if partition["observable_mismatch_case_ids"] != expected_ids:
        raise ReporterError("interior projection mutation did not reach every case")
    state_field = behavior_fields(context.contract)[1]
    mismatches = []
    for case in context.cases:
        expected = case["expected_outputs"]
        mutated = mutated_outputs(case, context.contract)
        if mutated[state_field] == expected[state_field]:
            raise ReporterError(f"projection mutation is not observable for {case['id']}")
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
        "mutation": "projected alias constant 0 changed to 1",
        "detected_case_ids": detected_ids,
        "partition_detection": {
            "observable_mismatch_case_ids": partition["observable_mismatch_case_ids"]
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
            "One proven mutable owner root is projected to an interior record by a local alias; "
            "the declared deeper u32 state is assigned zero through that alias and observed on owner."
        ),
        "external_callee": None,
        "interior_projection": {
            "owner_parameter": contract["owner"]["parameter"],
            "projection_path": contract["projection_path"],
            "alias_local": contract["alias"]["local"],
            "alias_rust_type": contract["alias"]["rust_type"],
            "state_owner_field_path": contract["state_output"]["owner_field_path"],
            "constant_assign": contract["constant_assign"],
            "pointer_root_count": 1,
            "noalias_required": [],
        },
        "excluded_semantics": list(context.claim_boundary["excluded_semantics"]),
    }
