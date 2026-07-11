from __future__ import annotations

from typing import Any

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
from .sequence_contract import behavior_fields


def validate_cases(cases: Any, contract: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(cases, list) or not cases:
        raise ReporterError("fixture cases must be a non-empty list")
    ids: set[str] = set()
    fields = behavior_fields(contract)
    external = contract["external_callee"]
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
        sequence = inputs.get(external["return_sequence_fixture_field"])
        if not isinstance(sequence, list) or not sequence:
            raise ReporterError(f"{case_id} return sequence must be non-empty")
        if len(sequence) > contract["loop"]["max_calls"]:
            raise ReporterError(f"{case_id} return sequence exceeds max_calls")
        for sequence_index, value in enumerate(sequence):
            require_u32(value, f"{case_id} return sequence[{sequence_index}]")
        sentinel = contract["loop"]["sentinel"]
        if sentinel not in sequence:
            raise ReporterError(f"{case_id} return sequence does not reach sentinel")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields:
            raise ReporterError(f"{case_id} expected output fields or order drifted")
        if not isinstance(expected[fields[0]], bool):
            raise ReporterError(f"{case_id}.{fields[0]} must be bool")
        require_u32(expected[fields[1]], f"{case_id}.{fields[1]}")
        require_usize(expected[fields[2]], f"{case_id}.{fields[2]}")
        rows = expected[fields[3]]
        if not isinstance(rows, list) or len(rows) != expected[fields[2]]:
            raise ReporterError(f"{case_id}.{fields[3]} row count drifted")
        for row_index, row in enumerate(rows):
            if not isinstance(row, list) or len(row) != len(external["arguments"]):
                raise ReporterError(f"{case_id}.{fields[3]}[{row_index}] width drifted")
            for column, value in enumerate(row):
                require_u32(value, f"{case_id}.{fields[3]}[{row_index}][{column}]")
        if reference_outputs(case, contract) != expected:
            raise ReporterError(f"{case_id} expected outputs disagree with the sequence model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    inputs = case_inputs(case)
    external = contract["external_callee"]
    sequence = inputs[external["return_sequence_fixture_field"]]
    sentinel = contract["loop"]["sentinel"]
    call_count = sequence.index(sentinel) + 1
    state = contract["state_output"]
    state_key = (str(state["parameter"]), tuple(str(item) for item in state["field_path"]))
    entries = {str(item["parameter"]): item for item in contract["entry_arguments"]}
    current_state = initial_value(inputs, state_key, entries)
    rows: list[list[int]] = []
    for scripted_value in sequence[:call_count]:
        row: list[int] = []
        for observation in external["arguments"]:
            key = observation_key(observation)
            row.append(current_state if key == state_key else initial_value(inputs, key, entries))
        rows.append(row)
        current_state = scripted_value
    fields = behavior_fields(contract)
    return {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: current_state,
        fields[2]: call_count,
        fields[3]: rows,
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutation_partition(case: dict[str, Any], contract: dict[str, Any]) -> str:
    sequence = case_inputs(case)[contract["external_callee"]["return_sequence_fixture_field"]]
    return "sequence_exhaustion" if sequence[0] == contract["loop"]["sentinel"] else "observable_mismatch"


def mutated_observable_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any] | None:
    if mutation_partition(case, contract) == "sequence_exhaustion":
        return None
    inputs = case_inputs(case)
    external = contract["external_callee"]
    sequence = inputs[external["return_sequence_fixture_field"]]
    first_only = dict(case)
    first_inputs = dict(inputs)
    first_inputs[external["return_sequence_fixture_field"]] = [sequence[0], contract["loop"]["sentinel"]]
    first_only["inputs"] = first_inputs
    output = reference_outputs(first_only, contract)
    fields = behavior_fields(contract)
    output[fields[1]] = sequence[0]
    output[fields[2]] = 1
    output[fields[3]] = output[fields[3]][:1]
    return output


def negative_partition_probe_source(context: Any) -> str:
    contract = context.contract
    external = contract["external_callee"]
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
            mutable = "mut " if entry["pass_mode"] == "mutable_ref" else ""
            declarations.append(f"    let {mutable}{local_name} = {rust_initializer(entry['initializer'], inputs)};")
            call_arguments.append(f"&mut {local_name}" if entry["pass_mode"] == "mutable_ref" else local_name)
        sequence = ", ".join(f"{value}u32" for value in inputs[external["return_sequence_fixture_field"]])
        rows = ", ".join(
            "[" + ", ".join(f"{value}u32" for value in row) + "]" for row in expected[fields[3]]
        )
        state_expression = f"{local_names[str(state['parameter'])]}." + ".".join(str(item) for item in state["field_path"])
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    __c2r_scripted_external_set_sequence(&[{sequence}]);
    __c2r_scripted_external_reset_calls();
{chr(10).join(declarations)}
    let actual_return = {context.spec['function_name']}({', '.join(call_arguments)});
    assert_eq!({state_expression}, {expected[fields[1]]}u32, "{rust_string(case['id'])} state drifted");
    assert_eq!(__c2r_scripted_external_call_count(), {expected[fields[2]]}usize, "{rust_string(case['id'])} call count drifted");
    assert_eq!(__c2r_scripted_external_call_args(), vec![{rows}], "{rust_string(case['id'])} call args drifted");
    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} return drifted");
}}
"""
        )
    return "".join(tests)


def case_inputs(case: dict[str, Any]) -> dict[str, Any]:
    value = case.get("inputs", case)
    return require_dict(value, f"{case.get('id', 'case')}.inputs")


def observation_key(observation: dict[str, Any]) -> tuple[str, tuple[str, ...]]:
    projection_path = (
        tuple(str(item) for item in observation["projection_path"])
        if observation["mode"] == "owner_interior_alias"
        else ()
    )
    field_path = tuple(str(item) for item in observation["field_path"])
    return str(observation["entry_parameter"]), (*projection_path, *field_path)


def initial_value(
    inputs: dict[str, Any],
    key: tuple[str, tuple[str, ...]],
    entries: dict[str, dict[str, Any]],
) -> int:
    fixture_by_path = {
        path: field for field, path in initializer_fixture_paths(entries[key[0]]["initializer"])
    }
    return int(inputs[fixture_by_path[key[1]]])
