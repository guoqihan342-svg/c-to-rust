from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .owner_interior_usize_add_contract import initializer_fixture_paths, rust_initializer
from .record_contract import require_dict, require_nonempty_string, require_u32, require_usize, rust_string
from .stats_sequence_contract import behavior_fields


U32_MASK = (1 << 32) - 1
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
    output_types = {
        str(update["target"]["fixture_field"]): str(update["target"]["rust_type"])
        for update in contract["updates"]
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
        if expected[fields[0]] is not True:
            raise ReporterError(f"{case_id}.{fields[0]} must be true")
        for field, rust_type in output_types.items():
            (require_u32 if rust_type == "u32" else require_usize)(expected.get(field), f"{case_id}.{field}")
        if reference_outputs(case, contract) != expected:
            raise ReporterError(f"{case_id} expected outputs disagree with ordered stats sequence model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    outputs: dict[str, Any] = {
        str(contract["return"]["fixture_field"]): True,
    }
    for index, update in enumerate(contract["updates"]):
        target = update["target"]
        state = _field_value(inputs, contract, target["owner_field_path"])
        if index == 0:
            updated = (state + 1) & U32_MASK
        else:
            rhs = _field_value(inputs, contract, update["source"]["owner_field_path"])
            updated = (state + rhs) & USIZE_MASK
        outputs[str(target["fixture_field"])] = updated
    return outputs


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    outputs = reference_outputs(case, contract)
    inputs = case_inputs(case)
    update = contract["updates"][2]
    target = update["target"]
    state = _field_value(inputs, contract, target["owner_field_path"])
    rhs = _field_value(inputs, contract, update["source"]["owner_field_path"])
    outputs[str(target["fixture_field"])] = (state - rhs) & USIZE_MASK
    return outputs


def negative_partition_probe_source(context: Any) -> str:
    owner = context.contract["owner"]
    fields = behavior_fields(context.contract)
    tests: list[str] = []
    for index, case in enumerate(context.cases):
        local = f"actual_{index}_{owner['parameter']}"
        expected = case["expected_outputs"]
        assertions = []
        for update in context.contract["updates"]:
            target = update["target"]
            path = ".".join(target["owner_field_path"])
            suffix = "u32" if target["rust_type"] == "u32" else "usize"
            output = str(target["fixture_field"])
            assertions.append(
                f'    assert_eq!({local}.{path}, {expected[output]}{suffix}, "{rust_string(case["id"])} {rust_string(output)} drifted");\n'
            )
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    let mut {local} = {rust_initializer(owner['initializer'], case_inputs(case))};
    let actual_return = {context.spec['function_name']}(&mut {local});
{"".join(assertions)}    assert_eq!(actual_return, true, "{rust_string(case['id'])} return drifted");
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
