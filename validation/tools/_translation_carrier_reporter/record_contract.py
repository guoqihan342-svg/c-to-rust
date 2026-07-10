from __future__ import annotations

import re
from typing import Any

from .errors import ReporterError


KIND = "scripted_external_record_u32_call_bool_state"
U32_MAX = (1 << 32) - 1


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("replay_contract.schema_version must be 1")
    if set(contract) != {
        "schema_version",
        "kind",
        "external_callee",
        "entry_arguments",
        "state_output",
        "return",
        "noalias_required",
    }:
        raise ReporterError("scripted record replay contract shape drifted")

    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or not entries:
        raise ReporterError("scripted record replay entry arguments are missing")
    entry_by_name: dict[str, dict[str, Any]] = {}
    fixture_fields: list[str] = []
    for index, entry in enumerate(entries):
        entry = require_dict(entry, f"entry_arguments[{index}]")
        if set(entry) != {
            "parameter",
            "c_type",
            "rust_type",
            "pass_mode",
            "direction",
            "initializer",
        }:
            raise ReporterError(f"entry_arguments[{index}] shape drifted")
        parameter = require_identifier(entry.get("parameter"), f"entry_arguments[{index}].parameter")
        rust_type = require_identifier(entry.get("rust_type"), f"entry_arguments[{index}].rust_type")
        if entry.get("pass_mode") not in {"mutable_ref", "value"}:
            raise ReporterError(f"entry_arguments[{index}].pass_mode is unsupported")
        expected_c_type = (
            f"struct {rust_type} *"
            if entry["pass_mode"] == "mutable_ref"
            else f"struct {rust_type}"
        )
        if normalize_c_type(entry.get("c_type")) != normalize_c_type(expected_c_type):
            raise ReporterError(f"entry_arguments[{index}].c_type drifted")
        if parameter in entry_by_name:
            raise ReporterError("entry argument parameters must be unique")
        validate_initializer(entry.get("initializer"), f"entry_arguments[{index}].initializer")
        if entry["initializer"]["record_type"] != rust_type:
            raise ReporterError(f"entry_arguments[{index}] initializer type drifted")
        fixture_fields.extend(field for field, _ in initializer_fixture_paths(entry["initializer"]))
        entry_by_name[parameter] = entry

    external = require_dict(contract.get("external_callee"), "external_callee")
    if set(external) != {
        "name",
        "return_fixture_field",
        "call_count_output",
        "call_args_output",
        "arguments",
    }:
        raise ReporterError("external_callee shape drifted")
    for key in ("name", "return_fixture_field", "call_count_output", "call_args_output"):
        require_identifier(external.get(key), f"external_callee.{key}")
    observations = external.get("arguments")
    if not isinstance(observations, list) or not observations:
        raise ReporterError("external_callee.arguments are missing")
    external_names: set[str] = set()
    for index, observation in enumerate(observations):
        observation = require_dict(observation, f"external_callee.arguments[{index}]")
        if set(observation) != {"parameter", "entry_parameter", "field_path"}:
            raise ReporterError(f"external_callee.arguments[{index}] shape drifted")
        external_name = require_identifier(
            observation.get("parameter"), f"external_callee.arguments[{index}].parameter"
        )
        entry_name = require_identifier(
            observation.get("entry_parameter"),
            f"external_callee.arguments[{index}].entry_parameter",
        )
        if external_name in external_names:
            raise ReporterError("external parameter names must be unique")
        external_names.add(external_name)
        entry = entry_by_name.get(entry_name)
        if entry is None:
            raise ReporterError(f"external_callee.arguments[{index}] entry mapping is missing")
        path = field_path(
            observation.get("field_path"), f"external_callee.arguments[{index}].field_path"
        )
        if path not in dict(initializer_fixture_paths(entry["initializer"])).values():
            raise ReporterError(f"external_callee.arguments[{index}] field path is not initialized")

    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {"parameter", "field_path", "fixture_field", "rust_type"}:
        raise ReporterError("state_output shape drifted")
    state_parameter = require_identifier(state.get("parameter"), "state_output.parameter")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    if state.get("rust_type") != "u32":
        raise ReporterError("state_output.rust_type must be u32")
    state_entry = entry_by_name.get(state_parameter)
    state_path = field_path(state.get("field_path"), "state_output.field_path")
    if state_entry is None or state_entry.get("pass_mode") != "mutable_ref":
        raise ReporterError("state_output must bind a mutable entry argument")
    if state_path not in dict(initializer_fixture_paths(state_entry["initializer"])).values():
        raise ReporterError("state_output.field_path is not initialized")

    return_contract = require_dict(contract.get("return"), "return")
    if set(return_contract) != {"fixture_field", "rust_type"}:
        raise ReporterError("return shape drifted")
    require_identifier(return_contract.get("fixture_field"), "return.fixture_field")
    if return_contract.get("rust_type") != "bool":
        raise ReporterError("return.rust_type must be bool")

    noalias = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    pointer_contract = require_dict(
        spec.get("c_boundary", {}).get("pointer_contract"), "c_boundary.pointer_contract"
    )
    if pointer_contract.get("aliasing_proven") is not True:
        raise ReporterError("pointer aliasing metadata is not proven")
    if noalias != noalias_pairs(pointer_contract.get("noalias_required"), "pointer noalias_required"):
        raise ReporterError("noalias contract drifted")
    forwarded_mutable = sorted(
        {
            str(observation["entry_parameter"])
            for observation in observations
            if entry_by_name[str(observation["entry_parameter"])]["pass_mode"] == "mutable_ref"
        }
    )
    required_noalias = {
        (forwarded_mutable[left], forwarded_mutable[right])
        for left in range(len(forwarded_mutable))
        for right in range(left + 1, len(forwarded_mutable))
    }
    if noalias != required_noalias:
        raise ReporterError("noalias contract must cover all forwarded mutable record pairs")

    output_fields = behavior_fields(contract)
    all_fields = [
        *fixture_fields,
        str(external["return_fixture_field"]),
        *output_fields,
    ]
    if len(all_fields) != len(set(all_fields)):
        raise ReporterError("fixture and output fields must be unique")
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    declared_fields = fixture.get("observable_outputs") or fixture.get("behavior_fields")
    if declared_fields != output_fields:
        raise ReporterError("observable output mapping drifted")
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    external = contract["external_callee"]
    return [
        str(contract["return"]["fixture_field"]),
        str(contract["state_output"]["fixture_field"]),
        str(external["call_count_output"]),
        str(external["call_args_output"]),
    ]


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
        for entry in contract["entry_arguments"]:
            for fixture_field, _ in initializer_fixture_paths(entry["initializer"]):
                require_u32(case.get(fixture_field), f"{case_id}.{fixture_field}")
        require_u32(case.get(external["return_fixture_field"]), f"{case_id} scripted return")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields:
            raise ReporterError(f"{case_id} expected output fields or order drifted")
        if not isinstance(expected[fields[0]], bool):
            raise ReporterError(f"{case_id}.{fields[0]} must be bool")
        require_u32(expected[fields[1]], f"{case_id}.{fields[1]}")
        require_usize(expected[fields[2]], f"{case_id}.{fields[2]}")
        args = expected[fields[3]]
        if not isinstance(args, list) or len(args) != len(external["arguments"]):
            raise ReporterError(f"{case_id}.{fields[3]} argument count drifted")
        for arg_index, arg in enumerate(args):
            require_u32(arg, f"{case_id}.{fields[3]}[{arg_index}]")
        if reference_outputs(case, contract) != expected:
            raise ReporterError(f"{case_id} expected outputs disagree with the record model")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    external = contract["external_callee"]
    assigned = case[external["return_fixture_field"]]
    fields = behavior_fields(contract)
    return {
        fields[0]: assigned == U32_MAX,
        fields[1]: assigned,
        fields[2]: 1,
        fields[3]: observation_values(case, contract),
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    return reference_outputs(case, contract)


def observation_values(case: dict[str, Any], contract: dict[str, Any]) -> list[int]:
    entry_by_name = {
        str(entry["parameter"]): entry for entry in contract["entry_arguments"]
    }
    result: list[int] = []
    for observation in contract["external_callee"]["arguments"]:
        entry = entry_by_name[str(observation["entry_parameter"])]
        fixture_by_path = {
            path: fixture_field
            for fixture_field, path in initializer_fixture_paths(entry["initializer"])
        }
        result.append(int(case[fixture_by_path[tuple(observation["field_path"])]]))
    return result


def negative_partition_probe_source(context: Any) -> str:
    contract = context.contract
    function_name = context.spec["function_name"]
    external = contract["external_callee"]
    fields = behavior_fields(contract)
    tests: list[str] = []
    for index, case in enumerate(context.cases):
        expected = case["expected_outputs"]
        local_names: dict[str, str] = {}
        declarations: list[str] = []
        call_arguments: list[str] = []
        for entry in contract["entry_arguments"]:
            parameter = str(entry["parameter"])
            local_name = f"actual_{index}_{parameter}"
            local_names[parameter] = local_name
            mutable = "mut " if entry["pass_mode"] == "mutable_ref" else ""
            declarations.append(
                f"    let {mutable}{local_name} = {rust_initializer(entry['initializer'], case)};"
            )
            call_arguments.append(
                f"&mut {local_name}" if entry["pass_mode"] == "mutable_ref" else local_name
            )
        state = contract["state_output"]
        state_expression = (
            f"{local_names[str(state['parameter'])]}."
            + ".".join(str(field) for field in state["field_path"])
        )
        args = ", ".join(f"{value}u32" for value in expected[fields[3]])
        tests.append(
            f"""
#[test]
fn __c2r_negative_partition_case_{index}() {{
    __c2r_scripted_external_set_return({case[external['return_fixture_field']]}u32);
    __c2r_scripted_external_reset_calls();
{chr(10).join(declarations)}
    let actual_return = {function_name}({', '.join(call_arguments)});
    assert_eq!({state_expression}, {expected[fields[1]]}u32, "{rust_string(case['id'])} state drifted");
    assert_eq!(__c2r_scripted_external_call_count(), {expected[fields[2]]}usize, "{rust_string(case['id'])} call count drifted");
    assert_eq!(__c2r_scripted_external_call_args(), [{args}], "{rust_string(case['id'])} call args drifted");
    assert_eq!(actual_return, {str(expected[fields[0]]).lower()}, "{rust_string(case['id'])} comparison mutation not detected");
}}
"""
        )
    return "".join(tests)


def validate_initializer(value: Any, label: str) -> None:
    initializer = require_dict(value, label)
    if set(initializer) != {"record_type", "fields"}:
        raise ReporterError(f"{label} shape drifted")
    require_identifier(initializer.get("record_type"), f"{label}.record_type")
    fields = initializer.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ReporterError(f"{label}.fields are missing")
    names: set[str] = set()
    for index, raw_field in enumerate(fields):
        field = require_dict(raw_field, f"{label}.fields[{index}]")
        name = require_identifier(field.get("name"), f"{label}.fields[{index}].name")
        if name in names:
            raise ReporterError(f"{label} field names must be unique")
        names.add(name)
        if set(field) == {"name", "fixture_field", "rust_type"}:
            require_identifier(field.get("fixture_field"), f"{label}.fields[{index}].fixture_field")
            if field.get("rust_type") != "u32":
                raise ReporterError(f"{label}.fields[{index}].rust_type must be u32")
        elif set(field) == {"name", "record"}:
            validate_initializer(field.get("record"), f"{label}.fields[{index}].record")
        else:
            raise ReporterError(f"{label}.fields[{index}] shape drifted")


def initializer_fixture_paths(
    initializer: dict[str, Any], prefix: tuple[str, ...] = ()
) -> list[tuple[str, tuple[str, ...]]]:
    result: list[tuple[str, tuple[str, ...]]] = []
    for field in initializer["fields"]:
        path = (*prefix, str(field["name"]))
        if "fixture_field" in field:
            result.append((str(field["fixture_field"]), path))
        else:
            result.extend(initializer_fixture_paths(field["record"], path))
    return result


def rust_initializer(initializer: dict[str, Any], case: dict[str, Any]) -> str:
    fields: list[str] = []
    for field in initializer["fields"]:
        value = (
            f"{case[field['fixture_field']]}u32"
            if "fixture_field" in field
            else rust_initializer(field["record"], case)
        )
        fields.append(f"{field['name']}: {value}")
    return f"{initializer['record_type']} {{ " + ", ".join(fields) + " }"


def field_path(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ReporterError(f"{label} must be a non-empty list")
    return tuple(require_identifier(item, f"{label}[{index}]") for index, item in enumerate(value))


def noalias_pairs(value: Any, label: str) -> set[tuple[str, str]]:
    if not isinstance(value, list):
        raise ReporterError(f"{label} must be a list")
    result: set[tuple[str, str]] = set()
    for index, pair in enumerate(value):
        if not isinstance(pair, list) or len(pair) != 2:
            raise ReporterError(f"{label}[{index}] must contain two names")
        left = require_identifier(pair[0], f"{label}[{index}][0]")
        right = require_identifier(pair[1], f"{label}[{index}][1]")
        if left == right:
            raise ReporterError(f"{label}[{index}] must bind distinct names")
        canonical = tuple(sorted((left, right)))
        if canonical in result:
            raise ReporterError(f"{label} contains duplicate pairs")
        result.add(canonical)
    return result


def normalize_c_type(value: Any) -> str:
    return " ".join(str(value or "").replace("*", " * ").split())


def require_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReporterError(f"{label} must be an object")
    return value


def require_identifier(value: Any, label: str) -> str:
    text = require_nonempty_string(value, label)
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", text) is None:
        raise ReporterError(f"{label} must be a portable identifier")
    return text


def require_nonempty_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ReporterError(f"{label} must be a non-empty string")
    return value


def require_u32(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= U32_MAX:
        raise ReporterError(f"{label} must be a u32 integer")
    return value


def require_usize(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < (1 << 64):
        raise ReporterError(f"{label} must be a non-negative 64-bit usize fixture integer")
    return value


def rust_string(value: Any) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
