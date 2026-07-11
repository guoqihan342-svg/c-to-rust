from __future__ import annotations

import copy

from validation.tools._translation_carrier_reporter.call_continue_contract import (
    parse_contract,
)
from validation.tools.call_continue_test_support import renamed_zero_start_spec


EXPECTED_V2_PARTITIONS = {
    "ordinary_zero_start": {
        "external_call": "skipped",
        "external_call_count": 0,
        "case_requirement": "at_least_one",
        "u32_wrapping": False,
    },
    "wrapping_zero_start": {
        "external_call": "skipped",
        "external_call_count": 0,
        "case_requirement": "at_least_one",
        "u32_wrapping": True,
    },
    "sentinel_hit": {
        "external_call": "invoked",
        "external_call_count": 1,
        "case_requirement": "exactly_one",
        "traversed_u32_wrapping": True,
    },
    "zero_miss": {
        "external_call": "invoked",
        "external_call_count": 1,
        "case_requirement": "at_least_one",
    },
    "ordinary_miss": {
        "external_call": "invoked",
        "external_call_count": 1,
        "case_requirement": "at_least_one",
    },
}


def schema_v2_spec_with_five_partitions() -> tuple[
    dict[str, object], list[dict[str, object]]
]:
    spec, cases = renamed_zero_start_spec()
    if [case["id"] for case in cases] != [
        "zero-start-wrap",
        "zero-start-plain",
        "hit-wrap",
        "miss-zero-return",
        "miss-ordinary",
    ]:
        raise AssertionError("schema-v2 focused fixture partition set drifted")
    return spec, cases


def partition_reports(
    spec: dict[str, object], cases: list[dict[str, object]]
) -> tuple[dict[str, object], dict[str, object]]:
    parse_contract(spec)
    zero_start_ids = ["zero-start-wrap", "zero-start-plain"]
    hit_ids = ["hit-wrap"]
    all_ids = [str(case["id"]) for case in cases]
    nonzero_start_ids = [case_id for case_id in all_ids if case_id not in zero_start_ids]
    scenarios = [
        {
            "scenario_id": "comparison-equality-flip",
            "expected_detected_case_ids": nonzero_start_ids,
            "partition_replay": {
                "detected_case_ids": nonzero_start_ids,
                "passed_case_ids": zero_start_ids,
            },
        },
        {
            "scenario_id": "continue-noop",
            "expected_detected_case_ids": hit_ids,
            "partition_replay": {
                "detected_case_ids": hit_ids,
                "passed_case_ids": [case_id for case_id in all_ids if case_id not in hit_ids],
            },
        },
    ]
    declared = {
        scenario["scenario_id"]: copy.deepcopy(scenario["partition_replay"])
        for scenario in scenarios
    }
    return {"scenarios": scenarios}, {"partition_detection": declared}
