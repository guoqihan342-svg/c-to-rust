from __future__ import annotations

from typing import Any

from .constant_state_contract import behavior_fields
from .errors import ReporterError
from .record_contract import (
    initializer_fixture_paths,
    require_dict,
    require_nonempty_string,
    require_u32,
    rust_initializer,
    rust_string,
)


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ReporterError("fixture cases must be a non-empty list")
    ids: set[str] = set()
    fields = behavior_fields(contract)
    expected_model = reference_outputs({}, contract)
    for index, raw_case in enumerate(cases):
        case = require_dict(raw_case, f"cases[{index}]")
        case_id = require_nonempty_string(case.get("id"), f"cases[{index}].id")
        if case_id in ids:
            raise ReporterError(f"duplicate fixture case id: {case_id}")
        ids.add(case_id)
        inputs = case_inputs(case)
        for entry in contract["entry_arguments"]:
            for fixture_field, _ in initializer_fixture_paths(entry["initializer"]):
                require_u32(inputs.get(fixture_field), f"{case_id}.{fixture_field}")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if set(expected) != set(fields):
            raise ReporterError(f"{case_id} expected output fields drifted")
        if expected != expected_model:
            raise ReporterError(f"{case_id} expected outputs disagree with constant-state model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    fields = behavior_fields(contract)
    return {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: int(contract["state_update"]["value"]),
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    output = reference_outputs(case, contract)
    output[behavior_fields(contract)[1]] = 1
    return output


def negative_partition_probe_source(context: Any) -> str:
    contract = context.contract
    state = contract["state_output"]
    fields = behavior_fields(contract)
    tests: list[str] = []
    for index, case in enumerate(context.cases):
        inputs = case_inputs(case)
        expected = case["expected_outputs"]
        local_names: dict[str, str] = {}
        declarations: list[str] = []
        call_arguments: list[str] = []
        for entry in contract["entry_arguments"]:
            parameter = str(entry["parameter"])
            local_name = f"actual_{index}_{parameter}"
            local_names[parameter] = local_name
            declarations.append(
                f"    let mut {local_name} = {rust_initializer(entry['initializer'], inputs)};"
            )
            call_arguments.append(f"&mut {local_name}")
        state_expression = (
            f"{local_names[str(state['parameter'])]}."
            + ".".join(str(item) for item in state["field_path"])
        )
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
{chr(10).join(declarations)}
    let actual_return = {context.spec['function_name']}({', '.join(call_arguments)});
    assert_eq!({state_expression}, {expected[fields[1]]}u32, "{rust_string(case['id'])} state drifted");
    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} return drifted");
}}
"""
        )
    return "".join(tests)


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return require_dict(case.get("inputs", case), f"{case.get('id', 'case')}.inputs")
