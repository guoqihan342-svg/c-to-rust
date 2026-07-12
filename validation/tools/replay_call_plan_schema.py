from __future__ import annotations

import re
from typing import Any

from validation.tools.replay_call_plan_render_literal import (
    _encoded_literal,
    _plan_sha256,
    _source_literal,
)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RUST_TYPE_RE = re.compile(r"^[A-Za-z0-9_&'\[\]<>:(), ]+$")
ACTUAL_RE = re.compile(r"^return(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
ALLOWED_ENCODINGS = {
    "u32",
    "u64",
    "i32",
    "usize",
    "u16",
    "bool",
    "string",
    "string_vec",
    "hex_bytes",
    "u8_array",
}


def validate_replay_call_plan(plan: dict[str, Any]) -> None:
    if isinstance(plan, dict) and plan.get("schema_version") == 2:
        from validation.tools.replay_call_plan_v2 import validate_replay_call_plan_v2

        validate_replay_call_plan_v2(plan)
        return
    if (
        not isinstance(plan, dict)
        or plan.get("schema_version") != 1
        or plan.get("status") != "bound"
    ):
        raise ValueError("ReplayCallPlan must be a bound schema v1 object")
    _identifier(plan.get("source_function_name"), "source function")
    _identifier(plan.get("api_name"), "Rust API")
    if plan.get("visibility") not in {"pub", "pub(crate)", "private"}:
        raise ValueError("ReplayCallPlan visibility is invalid")
    if plan.get("abi") not in {"Rust", "C"} or not isinstance(
        plan.get("unsafe"), bool
    ):
        raise ValueError("ReplayCallPlan ABI or unsafe policy is invalid")
    _rust_type(plan.get("return_type"), "return type")
    parameters = plan.get("parameters")
    call_args = plan.get("call_args")
    if not isinstance(parameters, list) or not isinstance(call_args, list):
        raise ValueError("ReplayCallPlan parameters and call_args are required")
    if [item.get("position") for item in parameters if isinstance(item, dict)] != list(
        range(len(parameters))
    ):
        raise ValueError("ReplayCallPlan parameter order is invalid")
    normalized_parameters: list[dict[str, Any]] = []
    for item in parameters:
        if not isinstance(item, dict):
            raise ValueError("ReplayCallPlan parameter is invalid")
        normalized_parameters.append(
            {
                "position": item.get("position"),
                "name": _identifier(item.get("name"), "Rust parameter"),
                "rust_type": _rust_type(item.get("rust_type"), "parameter type"),
                "c_parameter": _identifier(
                    item.get("c_parameter"), "C parameter mapping"
                ),
                "length_retained": item.get("length_retained"),
                "source": _normalize_source(item.get("source")),
            }
        )
        if not isinstance(item.get("length_retained"), bool):
            raise ValueError("ReplayCallPlan length retention is invalid")
    if normalized_parameters != parameters:
        raise ValueError("ReplayCallPlan parameters are not canonical")
    names = [item["name"] for item in parameters]
    c_names = [item["c_parameter"] for item in parameters]
    if len(names) != len(set(names)) or len(c_names) != len(set(c_names)):
        raise ValueError("ReplayCallPlan parameter mappings are duplicated")
    c_parameter_mappings = plan.get("c_parameter_mappings")
    if not isinstance(c_parameter_mappings, list) or len(
        c_parameter_mappings
    ) != len(parameters):
        raise ValueError("ReplayCallPlan C parameter mappings are invalid")
    for parameter, mapping in zip(parameters, c_parameter_mappings, strict=True):
        if (
            not isinstance(mapping, dict)
            or mapping.get("position") != parameter["position"]
            or mapping.get("c_parameter") != parameter["c_parameter"]
            or mapping.get("rust_parameter") != parameter["name"]
            or mapping.get("rust_type") != parameter["rust_type"]
            or not isinstance(mapping.get("c_type"), str)
            or not isinstance(mapping.get("direction"), str)
        ):
            raise ValueError("ReplayCallPlan C parameter mappings drifted")
    if call_args != [
        {
            "position": item["position"],
            "parameter": item["name"],
            "source": item["source"],
        }
        for item in parameters
    ]:
        raise ValueError("ReplayCallPlan call arguments drifted")
    if _normalize_assertions(plan.get("assertions")) != plan.get("assertions"):
        raise ValueError("ReplayCallPlan assertions are not canonical")
    if "fixture_assertions" in plan and _normalize_fixture_assertions(
        plan.get("fixture_assertions")
    ) != plan.get("fixture_assertions"):
        raise ValueError("ReplayCallPlan fixture assertions are not canonical")
    if _normalize_supporting_types(plan.get("supporting_types")) != plan.get(
        "supporting_types"
    ):
        raise ValueError("ReplayCallPlan supporting types are not canonical")
    omitted = plan.get("omitted_c_parameters")
    if not isinstance(omitted, list) or any(
        not isinstance(item, str) for item in omitted
    ):
        raise ValueError("ReplayCallPlan omitted C parameters are invalid")
    omitted_names = [_identifier(item, "omitted C parameter") for item in omitted]
    if len(omitted_names) != len(set(omitted_names)) or set(omitted_names) & set(
        c_names
    ):
        raise ValueError("ReplayCallPlan omitted C parameters are duplicated")
    expected_lengths = [item["name"] for item in parameters if item["length_retained"]]
    if plan.get("length_parameters_retained") != expected_lengths:
        raise ValueError("ReplayCallPlan retained length fields drifted")
    if any(
        item["source"]["kind"] == "encoded_length" and not item["length_retained"]
        for item in parameters
    ):
        raise ValueError("ReplayCallPlan derived length must be retained")
    fixture = plan.get("fixture")
    if (
        not isinstance(fixture, dict)
        or not isinstance(fixture.get("path"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", str(fixture.get("sha256") or ""))
        or not isinstance(fixture.get("case_count"), int)
        or fixture["case_count"] < 1
    ):
        raise ValueError("ReplayCallPlan fixture binding is invalid")
    case_ids = fixture.get("case_ids")
    if (
        not isinstance(case_ids, list)
        or len(case_ids) != fixture["case_count"]
        or any(not isinstance(item, str) or not item for item in case_ids)
        or len(case_ids) != len(set(case_ids))
    ):
        raise ValueError("ReplayCallPlan fixture case identities are invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("plan_sha256") or "")):
        raise ValueError("ReplayCallPlan sha256 is invalid")
    if _plan_sha256(plan) != plan["plan_sha256"]:
        raise ValueError("ReplayCallPlan sha256 drifted")


def _normalize_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("call argument source must be an object")
    kind = value.get("kind")
    field = _identifier(value.get("field"), "fixture source field")
    if kind == "fixture_field":
        encoding = value.get("encoding")
        if encoding not in ALLOWED_ENCODINGS:
            raise ValueError("fixture field encoding is unsupported")
        result = {"kind": kind, "field": field, "encoding": encoding}
        if "null_default" in value:
            result["null_default"] = value["null_default"]
        return result
    if kind == "encoded_length" and value.get("encoding") == "hex":
        return {"kind": kind, "field": field, "encoding": "hex"}
    raise ValueError("call argument source kind is unsupported")


def _readonly_byte_slice_bool_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if contract.get("schema_version") != 1:
        raise ValueError("readonly byte-slice replay contract schema_version must be 1")
    input_contract = contract.get("input")
    output_contract = contract.get("output")
    if not isinstance(input_contract, dict) or not isinstance(output_contract, dict):
        raise ValueError("readonly byte-slice replay input and output are required")
    fixture_encoding = input_contract.get("fixture_encoding")
    if fixture_encoding not in {"hex", "hex_bytes", "u8_array"}:
        raise ValueError("readonly byte-slice replay encoding is unsupported")
    if (
        input_contract.get("fixture_scalar_type") != "u8"
        or output_contract.get("rust_type") != "bool"
    ):
        raise ValueError("readonly byte-slice replay encoding is unsupported")
    value_parameter = _identifier(
        input_contract.get("parameter"), "byte-slice parameter"
    )
    length_parameter = _identifier(
        input_contract.get("length_parameter"), "length parameter"
    )
    value_field = _identifier(
        input_contract.get("fixture_field"), "byte-slice fixture field"
    )
    length_field = _identifier(
        input_contract.get("length_field"), "length fixture field"
    )
    output_field = _identifier(
        output_contract.get("fixture_field"), "output fixture field"
    )
    return {
        "schema_version": 3,
        "kind": "declarative_call_plan",
        "rust_api": {
            "visibility": "pub",
            "abi": "Rust",
            "unsafe": False,
            "parameters": [
                {
                    "name": value_parameter,
                    "rust_type": "&[u8]",
                    "c_parameter": value_parameter,
                    "length_retained": False,
                    "source": {
                        "kind": "fixture_field",
                        "field": value_field,
                        "encoding": (
                            "u8_array"
                            if fixture_encoding == "u8_array"
                            else "hex_bytes"
                        ),
                    },
                },
                {
                    "name": length_parameter,
                    "rust_type": "usize",
                    "c_parameter": length_parameter,
                    "length_retained": True,
                    "source": {
                        "kind": "fixture_field",
                        "field": length_field,
                        "encoding": "usize",
                    },
                },
            ],
            "return_type": "bool",
            "supporting_types": [],
        },
        "omitted_c_parameters": [],
        "assertions": [
            {
                "actual": "return",
                "fixture_field": output_field,
                "rust_type": "bool",
                "encoding": "bool",
            }
        ],
    }


def _normalize_assertions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("replay assertions are required")
    result: list[dict[str, Any]] = []
    fields: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict) or not ACTUAL_RE.fullmatch(
            str(raw.get("actual") or "")
        ):
            raise ValueError("replay assertion actual path is invalid")
        field = _identifier(raw.get("fixture_field"), "assertion fixture field")
        if field in fields:
            raise ValueError("replay assertion fixture fields must be unique")
        encoding = raw.get("encoding")
        if encoding not in ALLOWED_ENCODINGS - {"hex_bytes"}:
            raise ValueError("replay assertion encoding is unsupported")
        result.append(
            {
                "actual": raw["actual"],
                "fixture_field": field,
                "rust_type": _rust_type(raw.get("rust_type"), "assertion type"),
                "encoding": encoding,
            }
        )
        fields.add(field)
    return result


def _normalize_fixture_assertions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("fixture assertions must be an array")
    result: list[dict[str, Any]] = []
    fields: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("fixture assertion must be an object")
        field = _identifier(raw.get("fixture_field"), "fixture assertion field")
        encoding = raw.get("encoding")
        if field in fields or encoding not in {
            "u32",
            "u64",
            "i32",
            "usize",
            "bool",
            "string",
            "string_vec",
        }:
            raise ValueError("fixture assertion field or encoding is invalid")
        _encoded_literal(raw.get("expected"), encoding)
        result.append(
            {
                "fixture_field": field,
                "encoding": encoding,
                "expected": raw.get("expected"),
            }
        )
        fields.add(field)
    return result


def _normalize_supporting_types(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("supporting_types must be an array")
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict) or raw.get("kind") != "struct":
            raise ValueError("only struct supporting types are supported")
        fields = raw.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError("supporting struct fields are required")
        visibility = raw.get("visibility")
        if visibility not in {"pub", "pub(crate)", "private"}:
            raise ValueError("supporting type visibility is unsupported")
        result.append(
            {
                "kind": "struct",
                "name": _identifier(raw.get("name"), "supporting type"),
                "visibility": visibility,
                "fields": [
                    {
                        "name": _identifier(field.get("name"), "supporting field"),
                        "rust_type": _rust_type(
                            field.get("rust_type"), "supporting field type"
                        ),
                    }
                    for field in fields
                    if isinstance(field, dict)
                ],
            }
        )
        if len(result[-1]["fields"]) != len(fields):
            raise ValueError("supporting struct field must be an object")
        field_names = [field["name"] for field in result[-1]["fields"]]
        if len(field_names) != len(set(field_names)):
            raise ValueError("supporting struct fields must be unique")
    type_names = [item["name"] for item in result]
    if len(type_names) != len(set(type_names)):
        raise ValueError("supporting types must be unique")
    return result


def _validate_case_values(
    cases: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    fixture_assertions: list[dict[str, Any]],
) -> None:
    for case in cases:
        for parameter in parameters:
            _source_literal(parameter["source"], case["inputs"])
        for assertion in assertions:
            field = assertion["fixture_field"]
            if field not in case["expected"]:
                raise ValueError(
                    f"fixture case {case['id']} is missing expected field {field}"
                )
            _encoded_literal(case["expected"][field], assertion["encoding"])
        for assertion in fixture_assertions:
            field = assertion["fixture_field"]
            if field not in case["expected"]:
                raise ValueError(
                    f"fixture case {case['id']} is missing metadata field {field}"
                )
            if case["expected"][field] != assertion["expected"]:
                raise ValueError(
                    f"fixture case {case['id']} metadata field {field} drifted"
                )
            _encoded_literal(case["expected"][field], assertion["encoding"])


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} identifier is invalid")
    return value


def _rust_type(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not RUST_TYPE_RE.fullmatch(value):
        raise ValueError(f"Rust {label} is invalid")
    return value
