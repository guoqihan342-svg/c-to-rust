from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .record_contract import (
    initializer_fixture_paths,
    require_dict,
    require_nonempty_string,
    require_u32,
    rust_initializer,
    rust_string,
)
from .reset_add_while_continue_contract import behavior_fields


U32_MASK = (1 << 32) - 1


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ReporterError("fixture cases must be a non-empty list")
    ids: set[str] = set()
    fields = behavior_fields(contract)
    for index, raw in enumerate(cases):
        case = require_dict(raw, f"cases[{index}]")
        case_id = require_nonempty_string(case.get("id"), f"cases[{index}].id")
        if case_id in ids:
            raise ReporterError(f"duplicate fixture case id: {case_id}")
        ids.add(case_id)
        inputs = case_inputs(case)
        for entry in contract["entry_arguments"]:
            for fixture_field, _ in initializer_fixture_paths(entry["initializer"]):
                require_u32(inputs.get(fixture_field), f"{case_id}.{fixture_field}")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields or expected != reference_outputs(case, contract):
            raise ReporterError(f"{case_id} expected outputs disagree with reset-add model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    add = contract["add_state"]
    rhs = add["rhs"]
    owner_value = field_value(
        inputs, contract, contract["owner_parameter"], add["owner_field_path"]
    )
    rhs_value = field_value(inputs, contract, rhs["parameter"], rhs["field_path"])
    fields = behavior_fields(contract)
    return {fields[0]: True, fields[1]: 0, fields[2]: (owner_value + rhs_value) & U32_MASK}


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    output = reference_outputs(case, contract)
    output[behavior_fields(contract)[0]] = False
    return output


def negative_partition_probe_source(context: Any) -> str:
    contract = context.contract
    fields = behavior_fields(contract)
    tests: list[str] = []
    for index, case in enumerate(context.cases):
        inputs = case_inputs(case)
        expected = case["expected_outputs"]
        locals_by_parameter: dict[str, str] = {}
        declarations: list[str] = []
        arguments: list[str] = []
        for entry in contract["entry_arguments"]:
            parameter = entry["parameter"]
            local = f"actual_{index}_{parameter}"
            locals_by_parameter[parameter] = local
            mutable = "mut " if entry["direction"] == "inout" else ""
            declarations.append(
                f"    let {mutable}{local} = {rust_initializer(entry['initializer'], inputs)};"
            )
            arguments.append(f"&mut {local}" if entry["direction"] == "inout" else f"&{local}")
        owner = locals_by_parameter[contract["owner_parameter"]]
        reset_expr = owner + "." + ".".join(contract["reset_state"]["owner_field_path"])
        add_expr = owner + "." + ".".join(contract["add_state"]["owner_field_path"])
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
{chr(10).join(declarations)}
    let actual_return = {context.spec['function_name']}({', '.join(arguments)});
    assert_eq!({reset_expr}, {expected[fields[1]]}u32, "{rust_string(case['id'])} reset drifted");
    assert_eq!({add_expr}, {expected[fields[2]]}u32, "{rust_string(case['id'])} add drifted");
    assert_eq!(actual_return, true, "{rust_string(case['id'])} continue mutation not detected");
}}
"""
        )
    return "".join(tests)


def expected_fixture_state_model(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": contract["kind"],
        "scope": "fixture_only",
        "operations": ["alias_reset_zero", "owner_wrapping_add"],
        "projection_mode": "owner_interior_mutable",
        "pointer_root_count": 2,
        "noalias_required": [list(pair) for pair in contract["noalias_required"]],
        "continue_target": "current_while",
    }


def field_value(
    inputs: dict[str, Any], contract: dict[str, Any], parameter: str, raw_path: list[str]
) -> int:
    entry = next(item for item in contract["entry_arguments"] if item["parameter"] == parameter)
    fixtures = {path: field for field, path in initializer_fixture_paths(entry["initializer"])}
    return int(inputs[fixtures[tuple(raw_path)]])


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return require_dict(case.get("inputs", case), f"{case.get('id', 'case')}.inputs")
