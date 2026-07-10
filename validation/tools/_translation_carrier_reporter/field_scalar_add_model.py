from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .field_scalar_add_contract import behavior_fields
from .record_contract import (
    initializer_fixture_paths,
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
    for index, raw_case in enumerate(cases):
        case = require_dict(raw_case, f"cases[{index}]")
        case_id = require_nonempty_string(case.get("id"), f"cases[{index}].id")
        if case_id in ids:
            raise ReporterError(f"duplicate fixture case id: {case_id}")
        ids.add(case_id)
        inputs = case_inputs(case)
        for entry in contract["entry_arguments"]:
            if "initializer" in entry:
                for fixture_field, _ in initializer_fixture_paths(entry["initializer"]):
                    require_u32(inputs.get(fixture_field), f"{case_id}.{fixture_field}")
            else:
                require_u32(inputs.get(entry["fixture_field"]), f"{case_id}.{entry['fixture_field']}")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields:
            raise ReporterError(f"{case_id} expected output fields or order drifted")
        if not isinstance(expected[fields[0]], bool):
            raise ReporterError(f"{case_id}.{fields[0]} must be bool")
        require_u32(expected[fields[1]], f"{case_id}.{fields[1]}")
        if reference_outputs(case, contract) != expected:
            raise ReporterError(f"{case_id} expected outputs disagree with field-scalar add model")
        if mutated_outputs(case, contract)[fields[1]] == expected[fields[1]]:
            raise ReporterError(f"{case_id} does not observe the add-to-sub mutation")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    source = record_field_value(inputs, contract)
    scalar = int(inputs[contract["state_update"]["scalar"]["fixture_field"]])
    fields = behavior_fields(contract)
    return {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: (source + scalar) & U32_MASK,
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    source = record_field_value(inputs, contract)
    scalar = int(inputs[contract["state_update"]["scalar"]["fixture_field"]])
    fields = behavior_fields(contract)
    return {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: (source - scalar) & U32_MASK,
    }


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
            if "initializer" in entry:
                mutable = "mut " if entry["pass_mode"] == "mutable_ref" else ""
                declarations.append(
                    f"    let {mutable}{local_name} = {rust_initializer(entry['initializer'], inputs)};"
                )
                call_arguments.append(
                    f"&mut {local_name}" if entry["pass_mode"] == "mutable_ref" else local_name
                )
            else:
                declarations.append(
                    f"    let {local_name} = {inputs[entry['fixture_field']]}u32;"
                )
                call_arguments.append(local_name)
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


def record_field_value(inputs: dict[str, Any], contract: dict[str, Any]) -> int:
    binding = contract["state_update"]["record_field"]
    entries = {str(item["parameter"]): item for item in contract["entry_arguments"]}
    entry = entries[str(binding["parameter"])]
    fixture_by_path = {
        path: fixture_field
        for fixture_field, path in initializer_fixture_paths(entry["initializer"])
    }
    return int(inputs[fixture_by_path[tuple(binding["field_path"])]] )
