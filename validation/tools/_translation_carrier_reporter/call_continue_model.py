from __future__ import annotations

from typing import Any

from .call_continue_contract import behavior_fields
from .errors import ReporterError
from .record_contract import (
    initializer_fixture_paths,
    require_dict,
    require_nonempty_string,
    require_u32,
    require_usize,
    rust_initializer,
    rust_string,
)


U32_MASK = (1 << 32) - 1


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or len(cases) < 4:
        raise ReporterError("call-continue fixture requires at least four cases")
    ids: set[str] = set()
    partitions = {"hit": 0, "zero_miss": 0, "nonzero_miss": 0}
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
        return_field = contract["external_callee"]["return_fixture_field"]
        scripted = require_u32(inputs.get(return_field), f"{case_id}.{return_field}")
        sentinel = int(contract["comparison"]["sentinel"])
        partition = "hit" if scripted == sentinel else "zero_miss" if scripted == 0 else "nonzero_miss"
        partitions[partition] += 1
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != behavior_fields(contract) or expected != reference_outputs(case, contract):
            raise ReporterError(f"{case_id} expected outputs disagree with call-continue model")
        require_usize(expected[contract["external_callee"]["call_count_output"]], f"{case_id}.call_count")
    if partitions["hit"] < 2 or partitions["zero_miss"] < 1 or partitions["nonzero_miss"] < 1:
        raise ReporterError("fixture must cover two hits, zero miss, and nonzero miss")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    external = contract["external_callee"]
    scripted = int(inputs[external["return_fixture_field"]])
    hit = scripted == int(contract["comparison"]["sentinel"])
    owner = contract["owner_parameter"]
    add = contract["add_state"]
    rhs = add["rhs"]
    owner_before = field_value(inputs, contract, owner, add["owner_field_path"])
    rhs_value = field_value(inputs, contract, rhs["parameter"], rhs["field_path"])
    fields = behavior_fields(contract)
    snapshots = snapshot_values(inputs, contract)
    return {
        fields[0]: hit,
        fields[1]: 1,
        **{field: value for field, value in zip(fields[2:5], snapshots, strict=True)},
        fields[5]: 0 if hit else scripted,
        fields[6]: (owner_before + rhs_value) & U32_MASK if hit else owner_before,
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def comparison_mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    outputs = reference_outputs(case, contract)
    inputs = case_inputs(case)
    scripted = int(inputs[contract["external_callee"]["return_fixture_field"]])
    mutated_hit = scripted != int(contract["comparison"]["sentinel"])
    owner = contract["owner_parameter"]
    add = contract["add_state"]
    owner_before = field_value(inputs, contract, owner, add["owner_field_path"])
    rhs = add["rhs"]
    rhs_value = field_value(inputs, contract, rhs["parameter"], rhs["field_path"])
    fields = behavior_fields(contract)
    outputs[fields[0]] = mutated_hit
    outputs[fields[5]] = 0 if mutated_hit else scripted
    outputs[fields[6]] = (owner_before + rhs_value) & U32_MASK if mutated_hit else owner_before
    return outputs


def continue_mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    outputs = reference_outputs(case, contract)
    if outputs[behavior_fields(contract)[0]]:
        outputs[behavior_fields(contract)[0]] = False
    return outputs


def negative_partition_probe_source(context: Any, scenario: str) -> str:
    tests: list[str] = []
    scenario_ident = scenario.replace("-", "_")
    contract = context.contract
    fields = behavior_fields(contract)
    for index, case in enumerate(context.cases):
        inputs = case_inputs(case)
        expected = case["expected_outputs"]
        declarations: list[str] = []
        arguments: list[str] = []
        locals_by_parameter: dict[str, str] = {}
        for entry in contract["entry_arguments"]:
            local = f"actual_{index}_{entry['parameter']}"
            locals_by_parameter[entry["parameter"]] = local
            mutable = "mut " if entry["pass_mode"] == "mutable_ref" else ""
            declarations.append(f"    let {mutable}{local} = {rust_initializer(entry['initializer'], inputs)};")
            arguments.append(f"&mut {local}" if entry["pass_mode"] == "mutable_ref" else local)
        owner = locals_by_parameter[contract["owner_parameter"]]
        assigned = owner + "." + ".".join(contract["assigned_state"]["owner_field_path"])
        added = owner + "." + ".".join(contract["add_state"]["owner_field_path"])
        external = contract["external_callee"]
        snapshots = [expected[item["snapshot_output"]] for item in external["arguments"]]
        tests.append(
            f"""
#[test]
fn __c2r_negative_{scenario_ident}_case_{index}() {{
{chr(10).join(declarations)}
    __c2r_scripted_external_set_return({inputs[external['return_fixture_field']]}u32);
    __c2r_scripted_external_reset_calls();
    let actual_return = {context.spec['function_name']}({', '.join(arguments)});
    assert_eq!(__c2r_scripted_external_call_count(), {expected[fields[1]]}usize, "{rust_string(case['id'])} call count drifted");
    assert_eq!(__c2r_scripted_external_call_args(), ({snapshots[0]}u32, {snapshots[1]}u32, {snapshots[2]}u32), "{rust_string(case['id'])} call snapshots drifted");
    assert_eq!({assigned}, {expected[fields[5]]}u32, "{rust_string(case['id'])} assigned state drifted");
    assert_eq!({added}, {expected[fields[6]]}u32, "{rust_string(case['id'])} add state drifted");
    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} {scenario} mutation not detected");
}}
"""
        )
    return "".join(tests)


def snapshot_values(inputs: dict[str, Any], contract: dict[str, Any]) -> list[int]:
    values: list[int] = []
    projection = tuple(contract["projection"]["path"])
    for argument in contract["external_callee"]["arguments"]:
        path = tuple(argument["snapshot_field_path"])
        if argument["mode"] == "owner_interior_alias":
            path = projection + path
        values.append(field_value(inputs, contract, argument["entry_parameter"], path))
    return values


def field_value(
    inputs: dict[str, Any], contract: dict[str, Any], parameter: str, raw_path: Any
) -> int:
    entry = next(item for item in contract["entry_arguments"] if item["parameter"] == parameter)
    fixture_by_path = {path: field for field, path in initializer_fixture_paths(entry["initializer"])}
    return int(inputs[fixture_by_path[tuple(raw_path)]])


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    return require_dict(case.get("inputs", case), f"{case.get('id', 'case')}.inputs")
