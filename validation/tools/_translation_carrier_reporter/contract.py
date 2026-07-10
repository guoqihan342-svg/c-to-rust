from __future__ import annotations

import re
from typing import Any


KIND = "scripted_external_u32_call_bool_out"
U32_MAX = (1 << 32) - 1


class ReporterError(ValueError):
    pass


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("replay_contract.schema_version must be 1")

    external = require_dict(contract.get("external_callee"), "external_callee")
    inputs = contract.get("inputs")
    output_pointer = require_dict(contract.get("output_pointer"), "output_pointer")
    return_contract = require_dict(contract.get("return"), "return")
    if not isinstance(inputs, list) or len(inputs) != 3:
        raise ReporterError("scripted u32 reporter requires three declared inputs")

    expected_types = ("u32", "u32", "usize")
    for index, (item, expected_type) in enumerate(zip(inputs, expected_types, strict=True)):
        mapping = require_dict(item, f"inputs[{index}]")
        require_identifier(mapping.get("parameter"), f"inputs[{index}].parameter")
        require_identifier(mapping.get("fixture_field"), f"inputs[{index}].fixture_field")
        if mapping.get("rust_type") != expected_type:
            raise ReporterError(f"inputs[{index}].rust_type must be {expected_type}")

    required_external = (
        "name",
        "return_fixture_field",
        "call_count_output",
        "call_args_output",
    )
    for key in required_external:
        require_identifier(external.get(key), f"external_callee.{key}")
    require_identifier(output_pointer.get("parameter"), "output_pointer.parameter")
    require_identifier(output_pointer.get("fixture_field"), "output_pointer.fixture_field")
    require_identifier(return_contract.get("fixture_field"), "return.fixture_field")
    if output_pointer.get("rust_type") != "u32":
        raise ReporterError("output_pointer.rust_type must be u32")
    if return_contract.get("rust_type") != "bool":
        raise ReporterError("return.rust_type must be bool")

    fixture_fields = [
        *(str(item["fixture_field"]) for item in inputs),
        str(external["return_fixture_field"]),
        str(return_contract["fixture_field"]),
        str(output_pointer["fixture_field"]),
        str(external["call_count_output"]),
        str(external["call_args_output"]),
    ]
    if len(fixture_fields) != len(set(fixture_fields)):
        raise ReporterError("replay contract fixture and output fields must be unique")
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    external = contract["external_callee"]
    return [
        str(contract["return"]["fixture_field"]),
        str(contract["output_pointer"]["fixture_field"]),
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
        for input_index, item in enumerate(contract["inputs"]):
            value = case.get(item["fixture_field"])
            if item["rust_type"] == "u32":
                require_u32(value, f"{case_id} input {input_index}")
            else:
                require_usize(value, f"{case_id} input {input_index}")
        require_u32(case.get(external["return_fixture_field"]), f"{case_id} scripted return")
        expected = require_dict(case.get("expected_outputs"), f"{case_id}.expected_outputs")
        if list(expected) != fields:
            raise ReporterError(f"{case_id} expected output fields or order drifted")
        if not isinstance(expected[fields[0]], bool):
            raise ReporterError(f"{case_id} {fields[0]} must be bool")
        require_u32(expected[fields[1]], f"{case_id} {fields[1]}")
        require_usize(expected[fields[2]], f"{case_id} {fields[2]}")
        args = expected[fields[3]]
        if not isinstance(args, list) or len(args) != 3:
            raise ReporterError(f"{case_id} {fields[3]} must contain three arguments")
        require_u32(args[0], f"{case_id} {fields[3]}[0]")
        require_u32(args[1], f"{case_id} {fields[3]}[1]")
        require_usize(args[2], f"{case_id} {fields[3]}[2]")
    return cases


def reference_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    external = contract["external_callee"]
    args = [case[item["fixture_field"]] for item in contract["inputs"]]
    assigned_value = 0
    assigned_value = case[external["return_fixture_field"]]
    fields = behavior_fields(contract)
    return {
        fields[0]: assigned_value == U32_MAX,
        fields[1]: assigned_value,
        fields[2]: 1,
        fields[3]: args,
    }


def replay_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    external = contract["external_callee"]
    external_return = case[external["return_fixture_field"]]
    forwarded = [case[item["fixture_field"]] for item in contract["inputs"]]
    fields = behavior_fields(contract)
    return {
        fields[0]: external_return == U32_MAX,
        fields[1]: external_return,
        fields[2]: len([forwarded]),
        fields[3]: forwarded,
    }


def mutated_outputs(case: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    output = replay_outputs(case, contract)
    return_field = behavior_fields(contract)[0]
    output[return_field] = not output[return_field]
    return output


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
