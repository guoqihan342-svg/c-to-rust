from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .owner_interior_usize_add_contract import (
    behavior_fields,
    initializer_fixture_paths,
    rust_initializer,
)
from .record_contract import require_dict, require_nonempty_string, require_u32, require_usize, rust_string


USIZE_MASK = (1 << 64) - 1


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ReporterError("fixture cases must be a non-empty list")
    ids: set[str] = set()
    fields = behavior_fields(contract)
    fixture_types = {
        field: rust_type
        for field, _, rust_type in initializer_fixture_paths(contract["owner"]["initializer"])
    }
    for index, raw_case in enumerate(cases):
        case = require_dict(raw_case, f"cases[{index}]")
        case_id = require_nonempty_string(case.get("id"), f"cases[{index}].id")
        if case_id in ids:
            raise ReporterError(f"duplicate fixture case id: {case_id}")
        ids.add(case_id)
        inputs = case_inputs(case)
        if set(inputs) != set(fixture_types):
            raise ReporterError(f"{case_id} input fields drifted")
        for name, rust_type in fixture_types.items():
            (require_u32 if rust_type == "u32" else require_usize)(inputs.get(name), f"{case_id}.{name}")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields:
            raise ReporterError(f"{case_id} expected output fields or order drifted")
        if not isinstance(expected[fields[0]], bool):
            raise ReporterError(f"{case_id}.{fields[0]} must be bool")
        require_usize(expected[fields[1]], f"{case_id}.{fields[1]}")
        if reference_outputs(case, contract) != expected:
            raise ReporterError(f"{case_id} expected outputs disagree with usize wrapping-add model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    state = _field_value(inputs, contract, contract["state_output"]["owner_field_path"])
    rhs = _field_value(inputs, contract, contract["rhs"]["owner_field_path"])
    fields = behavior_fields(contract)
    return {fields[0]: bool(contract["return"]["value"]), fields[1]: (state + rhs) & USIZE_MASK}


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    state = _field_value(inputs, contract, contract["state_output"]["owner_field_path"])
    rhs = _field_value(inputs, contract, contract["rhs"]["owner_field_path"])
    fields = behavior_fields(contract)
    return {fields[0]: bool(contract["return"]["value"]), fields[1]: (state - rhs) & USIZE_MASK}


def negative_partition_probe_source(context: Any) -> str:
    owner = context.contract["owner"]
    state_path = ".".join(context.contract["state_output"]["owner_field_path"])
    fields = behavior_fields(context.contract)
    tests: list[str] = []
    for index, case in enumerate(context.cases):
        local = f"actual_{index}_{owner['parameter']}"
        expected = case["expected_outputs"]
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    let mut {local} = {rust_initializer(owner['initializer'], case_inputs(case))};
    let actual_return = {context.spec['function_name']}(&mut {local});
    assert_eq!({local}.{state_path}, {expected[fields[1]]}usize, "{rust_string(case['id'])} state drifted");
    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} return drifted");
}}
"""
        )
    return "".join(tests)


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return require_dict(case.get("inputs", case), f"{case.get('id', 'case')}.inputs")


def _field_value(
    inputs: dict[str, Any], contract: dict[str, Any], path_value: list[str]
) -> int:
    fixtures = {
        path: field
        for field, path, _ in initializer_fixture_paths(contract["owner"]["initializer"])
    }
    return int(inputs[fixtures[tuple(path_value)]])
