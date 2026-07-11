from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .field_postfix_increment_contract import behavior_fields, input_fixture_field
from .record_contract import (
    require_dict,
    require_nonempty_string,
    require_u32,
    rust_initializer,
    rust_string,
)


U32_MASK = (1 << 32) - 1


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ReporterError("fixture cases must be a non-empty list")
    ids: set[str] = set()
    fields = behavior_fields(contract)
    input_field = input_fixture_field(contract)
    for index, raw_case in enumerate(cases):
        case = require_dict(raw_case, f"cases[{index}]")
        case_id = require_nonempty_string(case.get("id"), f"cases[{index}].id")
        if case_id in ids:
            raise ReporterError(f"duplicate fixture case id: {case_id}")
        ids.add(case_id)
        inputs = case_inputs(case)
        if set(inputs) != {input_field}:
            raise ReporterError(f"{case_id} inputs must contain only the record initial field")
        require_u32(inputs.get(input_field), f"{case_id}.{input_field}")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields:
            raise ReporterError(f"{case_id} expected output fields or order drifted")
        if not isinstance(expected[fields[0]], bool):
            raise ReporterError(f"{case_id}.{fields[0]} must be bool")
        require_u32(expected[fields[1]], f"{case_id}.{fields[1]}")
        if reference_outputs(case, contract) != expected:
            raise ReporterError(f"{case_id} expected outputs disagree with postfix-increment model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    initial = int(case_inputs(case)[input_fixture_field(contract)])
    fields = behavior_fields(contract)
    return {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: (initial + 1) & U32_MASK,
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    initial = int(case_inputs(case)[input_fixture_field(contract)])
    fields = behavior_fields(contract)
    return {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: (initial - 1) & U32_MASK,
    }


def negative_partition_probe_source(context: Any) -> str:
    contract = context.contract
    entry = contract["entry_arguments"][0]
    state = contract["state_output"]
    fields = behavior_fields(contract)
    tests: list[str] = []
    for index, case in enumerate(context.cases):
        inputs = case_inputs(case)
        expected = case["expected_outputs"]
        local_name = f"actual_{index}_{entry['parameter']}"
        state_expression = f"{local_name}." + ".".join(str(item) for item in state["field_path"])
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    let mut {local_name} = {rust_initializer(entry['initializer'], inputs)};
    let actual_return = {context.spec['function_name']}(&mut {local_name});
    assert_eq!({state_expression}, {expected[fields[1]]}u32, "{rust_string(case['id'])} state drifted");
    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} return drifted");
}}
"""
        )
    return "".join(tests)


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return require_dict(case.get("inputs", case), f"{case.get('id', 'case')}.inputs")
