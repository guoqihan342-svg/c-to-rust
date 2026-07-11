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
    external_count_field = str(external["call_count_output"])
    external_args_field = str(external["call_args_output"])
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
        require_usize(expected[external_count_field], f"{case_id}.{external_count_field}")
        validate_observation_rows(
            expected[external_args_field],
            expected[external_count_field],
            external["arguments"],
            f"{case_id}.{external_args_field}",
        )
        body = contract.get("body_callee")
        if isinstance(body, dict):
            body_count = expected[str(body["call_count_output"])]
            require_usize(body_count, f"{case_id}.{body['call_count_output']}")
            validate_observation_rows(
                expected[str(body["call_args_output"])],
                body_count,
                body["arguments"],
                f"{case_id}.{body['call_args_output']}",
            )
            order = expected[str(body["call_order_output"])]
            if not isinstance(order, list) or len(order) != body_count + expected[external_count_field]:
                raise ReporterError(f"{case_id}.{body['call_order_output']} length drifted")
            for order_index, value in enumerate(order):
                require_u32(value, f"{case_id}.{body['call_order_output']}[{order_index}]")
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
    body = contract.get("body_callee")
    body_rows: list[list[int]] = []
    call_order: list[int] = []
    for scripted_value in sequence[:call_count]:
        if isinstance(body, dict):
            body_rows.append(observation_row(body["arguments"], current_state, state_key, inputs, entries))
            call_order.append(int(body["event_id"]))
        row: list[int] = []
        for observation in external["arguments"]:
            key = observation_key(observation)
            row.append(current_state if key == state_key else initial_value(inputs, key, entries))
        rows.append(row)
        if isinstance(body, dict):
            call_order.append(int(body["tail_event_id"]))
        current_state = scripted_value
    fields = behavior_fields(contract)
    outputs = {
        fields[0]: bool(contract["return"]["value"]),
        fields[1]: current_state,
    }
    if isinstance(body, dict):
        outputs.update(
            {
                str(body["call_count_output"]): call_count,
                str(body["call_args_output"]): body_rows,
            }
        )
    outputs.update(
        {
            str(external["call_count_output"]): call_count,
            str(external["call_args_output"]): rows,
        }
    )
    if isinstance(body, dict):
        outputs[str(body["call_order_output"])] = call_order
    return outputs


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def mutation_partition(case: dict[str, Any], contract: dict[str, Any]) -> str:
    if isinstance(contract.get("body_callee"), dict):
        return "body_call_observable_mismatch"
    sequence = case_inputs(case)[contract["external_callee"]["return_sequence_fixture_field"]]
    return "sequence_exhaustion" if sequence[0] == contract["loop"]["sentinel"] else "observable_mismatch"


def mutated_observable_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any] | None:
    body = contract.get("body_callee")
    if isinstance(body, dict):
        output = reference_outputs(case, contract)
        call_count = int(output[str(contract["external_callee"]["call_count_output"])])
        output[str(body["call_count_output"])] = 0
        output[str(body["call_args_output"])] = []
        output[str(body["call_order_output"])] = [int(body["tail_event_id"])] * call_count
        return output
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
    state_field = str(contract["state_output"]["fixture_field"])
    external_count_field = str(external["call_count_output"])
    external_args_field = str(external["call_args_output"])
    output[state_field] = sequence[0]
    output[external_count_field] = 1
    output[external_args_field] = output[external_args_field][:1]
    return output


def negative_partition_probe_source(context: Any) -> str:
    contract = context.contract
    external = contract["external_callee"]
    state = contract["state_output"]
    fields = behavior_fields(contract)
    external_count_field = str(external["call_count_output"])
    external_args_field = str(external["call_args_output"])
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
            "[" + ", ".join(f"{value}u32" for value in row) + "]"
            for row in expected[external_args_field]
        )
        body = contract.get("body_callee")
        body_assertions = ""
        if isinstance(body, dict):
            body_rows = ", ".join(
                "[" + ", ".join(f"{value}u32" for value in row) + "]"
                for row in expected[str(body["call_args_output"])]
            )
            order = ", ".join(
                f"{value}u32" for value in expected[str(body["call_order_output"])]
            )
            body_assertions = f'''    assert_eq!(__c2r_scripted_body_call_count(), {expected[str(body["call_count_output"])]}usize, "{rust_string(case['id'])} body call count drifted");
    assert_eq!(__c2r_scripted_body_call_args(), vec![{body_rows}], "{rust_string(case['id'])} body call args drifted");
    assert_eq!(__c2r_scripted_call_order(), vec![{order}], "{rust_string(case['id'])} call order drifted");
'''
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
    assert_eq!(__c2r_scripted_external_call_count(), {expected[external_count_field]}usize, "{rust_string(case['id'])} call count drifted");
    assert_eq!(__c2r_scripted_external_call_args(), vec![{rows}], "{rust_string(case['id'])} call args drifted");
{body_assertions}    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} return drifted");
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


def observation_row(
    observations: list[dict[str, Any]],
    current_state: int,
    state_key: tuple[str, tuple[str, ...]],
    inputs: dict[str, Any],
    entries: dict[str, dict[str, Any]],
) -> list[int]:
    return [
        current_state
        if observation_key(observation) == state_key
        else initial_value(inputs, observation_key(observation), entries)
        for observation in observations
    ]


def validate_observation_rows(
    rows: Any,
    call_count: int,
    observations: list[dict[str, Any]],
    label: str,
) -> None:
    if not isinstance(rows, list) or len(rows) != call_count:
        raise ReporterError(f"{label} row count drifted")
    for row_index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(observations):
            raise ReporterError(f"{label}[{row_index}] width drifted")
        for column, value in enumerate(row):
            require_u32(value, f"{label}[{row_index}][{column}]")


def initial_value(
    inputs: dict[str, Any],
    key: tuple[str, tuple[str, ...]],
    entries: dict[str, dict[str, Any]],
) -> int:
    fixture_by_path = {
        path: field for field, path in initializer_fixture_paths(entries[key[0]]["initializer"])
    }
    return int(inputs[fixture_by_path[key[1]]])
