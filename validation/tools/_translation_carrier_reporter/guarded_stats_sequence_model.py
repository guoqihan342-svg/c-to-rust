from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .guarded_stats_sequence_contract import behavior_fields
from .owner_interior_usize_add_contract import initializer_fixture_paths, rust_initializer
from .record_contract import (
    require_dict,
    require_nonempty_string,
    require_u32,
    require_usize,
    rust_string,
)


U32_MASK = (1 << 32) - 1
USIZE_MASK = (1 << 64) - 1


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ReporterError("fixture cases must be a non-empty list")
    ids: set[str] = set()
    fields = behavior_fields(contract)
    fixture_types = {
        field: rust_type
        for field, _, rust_type in initializer_fixture_paths(
            contract["owner"]["initializer"]
        )
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
            value = inputs.get(name)
            if rust_type == "bool":
                if type(value) is not bool:
                    raise ReporterError(f"{case_id}.{name} must be bool")
            else:
                (require_u32 if rust_type == "u32" else require_usize)(
                    value, f"{case_id}.{name}"
                )
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if set(expected) != set(fields):
            raise ReporterError(f"{case_id} expected output fields drifted")
        if type(expected[fields[0]]) is not bool:
            raise ReporterError(f"{case_id}.{fields[0]} must be bool")
        for field, rust_type in output_types.items():
            (require_u32 if rust_type == "u32" else require_usize)(
                expected.get(field), f"{case_id}.{field}"
            )
        if reference_outputs(case, contract) != expected:
            raise ReporterError(
                f"{case_id} expected outputs disagree with guarded stats sequence model"
            )
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return _outputs(case, contract, mutate_second_equality=False)


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return _outputs(case, contract, mutate_second_equality=True)


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
        expected_return = str(expected[fields[0]]).lower()
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    let mut {local} = {rust_initializer(owner['initializer'], case_inputs(case))};
    let actual_return = {context.spec['function_name']}(&mut {local});
{"".join(assertions)}    assert_eq!(actual_return, {expected_return}, "{rust_string(case['id'])} return drifted");
}}
"""
        )
    return "".join(tests)


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return require_dict(case.get("inputs", case), f"{case.get('id', 'case')}.inputs")


def guard_matches(
    case: dict[str, Any], contract: dict[str, Any], *, mutate_second_equality: bool
) -> bool:
    inputs = case_inputs(case)
    results: list[bool] = []
    for index, predicate in enumerate(contract["guard"]["predicates"]):
        lhs = _field_value(inputs, contract, predicate["lhs"]["owner_field_path"])
        result = lhs == predicate["rhs"]["value"]
        results.append(not result if mutate_second_equality and index == 1 else result)
    return results[0] and results[1]


def _outputs(
    case: dict[str, Any], contract: dict[str, Any], *, mutate_second_equality: bool
) -> dict[str, Any]:
    inputs = case_inputs(case)
    guarded = guard_matches(
        case, contract, mutate_second_equality=mutate_second_equality
    )
    outputs: dict[str, Any] = {
        str(contract["return"]["fixture_field"]): guarded,
    }
    for index, update in enumerate(contract["updates"]):
        target = update["target"]
        state = _field_value(inputs, contract, target["owner_field_path"])
        if not guarded:
            updated = state
        elif index == 0:
            updated = (int(state) + 1) & U32_MASK
        else:
            rhs = _field_value(inputs, contract, update["source"]["owner_field_path"])
            updated = (int(state) + int(rhs)) & USIZE_MASK
        outputs[str(target["fixture_field"])] = updated
    return outputs


def _field_value(
    inputs: dict[str, Any], contract: dict[str, Any], path_value: list[str]
) -> Any:
    fixtures = {
        path: field
        for field, path, _ in initializer_fixture_paths(
            contract["owner"]["initializer"]
        )
    }
    return inputs[fixtures[tuple(path_value)]]
