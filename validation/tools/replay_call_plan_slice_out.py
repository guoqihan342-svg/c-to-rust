from __future__ import annotations

import re
from typing import Any

from validation.tools.replay_call_plan_v2 import (
    _plan_sha256,
    validate_replay_call_plan_v2,
)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_I32_SLICE_ITEMS = 4096


def supports_implicit_i32_slice_output_plan(spec: dict[str, Any]) -> bool:
    try:
        function_name = _identifier(spec.get("function_name"), "source function")
        signature = _matching_signature(spec, function_name)
        parameters = _slice_parameters(signature)
        observable = spec.get("fixture_contract", {}).get("observable_outputs")
        required = {
            "return_code",
            "status",
            _identifier(parameters["input"].get("name"), "input buffer"),
            _identifier(parameters["length"].get("name"), "length parameter"),
        }
    except ValueError:
        return False
    return (
        _normalize_c_type(signature.get("return_type")) == "int"
        and isinstance(observable, list)
        and len(observable) == 10
        and len(set(observable)) == len(observable)
        and required.issubset(observable)
    )


def build_implicit_i32_slice_output_plan(
    spec: dict[str, Any], fixture: dict[str, Any]
) -> dict[str, Any]:
    if not supports_implicit_i32_slice_output_plan(spec):
        raise ValueError("implicit i32 slice-output replay shape is unsupported")
    function_name = _identifier(spec.get("function_name"), "source function")
    signature = _matching_signature(spec, function_name)
    components = _slice_parameters(signature)
    input_name = _identifier(components["input"].get("name"), "input buffer")
    length_name = _identifier(components["length"].get("name"), "length parameter")
    output_name = _identifier(components["output"].get("name"), "output buffer")
    shape = _validate_fixture_cases(spec, fixture, input_name, length_name)
    parameters, mappings = _parameter_contracts(
        signature, components, input_name, length_name, output_name
    )
    plan: dict[str, Any] = {
        "schema_version": 2,
        "status": "bound",
        "source_function_name": function_name,
        "api_name": _public_api_name(spec, function_name),
        "visibility": "pub",
        "abi": "Rust",
        "unsafe": False,
        "parameters": parameters,
        "c_parameter_mappings": mappings,
        "omitted_c_parameters": [],
        "length_parameters_retained": [length_name],
        "return_type": "i32",
        "supporting_types": [],
        "bindings": [_output_binding(output_name, length_name, shape["maximum_length"])],
        "distinct_mutable_bindings": [],
        "call_args": [
            {"position": item["position"], "parameter": item["name"], "source": item["source"]}
            for item in parameters
        ],
        "assertions": [
            {
                "actual": "return",
                "fixture_field": "return_code",
                "rust_type": "i32",
                "encoding": "i32",
            },
            {
                "actual": f"binding.{output_name}",
                "fixture_field": shape["output_field"],
                "rust_type": "Vec<i32>",
                "encoding": "i32_vec",
            },
        ],
        "fixture_assertions": [
            {
                "fixture_field": field,
                "encoding": "string",
                "expected": shape["metadata_values"][field],
            }
            for field in shape["metadata_fields"]
        ],
        "fixture_relations": _fixture_relations(
            input_name,
            length_name,
            shape["output_field"],
            shape["write_count_field"],
        ),
        "fixture": {
            "path": fixture["path"],
            "sha256": fixture["sha256"],
            "case_count": len(fixture["cases"]),
            "case_ids": [item["id"] for item in fixture["cases"]],
        },
    }
    plan["plan_sha256"] = _plan_sha256(plan)
    validate_replay_call_plan_v2(plan)
    return plan


def _parameter_contracts(
    signature: dict[str, Any],
    components: dict[str, dict[str, Any]],
    input_name: str,
    length_name: str,
    output_name: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parameters = []
    mappings = []
    for position, c_parameter in enumerate(_signature_parameters(signature)):
        name = _identifier(c_parameter.get("name"), "C parameter")
        if c_parameter is components["input"]:
            rust_type = "&[i32]"
            source = {"kind": "fixture_field", "field": input_name, "encoding": "i32_slice"}
        elif c_parameter is components["length"]:
            rust_type = "i32"
            source = {"kind": "fixture_field", "field": length_name, "encoding": "i32"}
        else:
            rust_type = "&mut [i32]"
            source = {"kind": "binding_borrow_mut", "binding": output_name}
        parameters.append(
            {
                "position": position,
                "name": name,
                "rust_type": rust_type,
                "c_parameter": name,
                "length_retained": c_parameter is components["length"],
                "source": source,
            }
        )
        mappings.append(
            {
                "position": position,
                "c_parameter": name,
                "c_type": str(c_parameter.get("c_type") or ""),
                "direction": str(c_parameter.get("direction") or ""),
                "rust_parameter": name,
                "rust_type": rust_type,
            }
        )
    return parameters, mappings


def _output_binding(name: str, length_field: str, maximum: int) -> dict[str, Any]:
    return {
        "name": name,
        "rust_type": "Vec<i32>",
        "mutable": True,
        "initializer": {
            "kind": "vec_repeat",
            "rust_type": "Vec<i32>",
            "element_type": "i32",
            "length": {
                "kind": "fixture_field",
                "field": length_field,
                "encoding": "i32",
                "maximum": max(1, maximum),
            },
            "value": 0,
        },
    }


def _fixture_relations(
    input_field: str, length_field: str, output_field: str, write_count_field: str
) -> list[dict[str, Any]]:
    return [
        _equal_relation("inputs", input_field, "expected", input_field, "i32_vec"),
        _equal_relation("inputs", length_field, "expected", length_field, "i32"),
        _length_relation("inputs", input_field, "inputs", length_field),
        _length_relation("expected", output_field, "inputs", length_field),
        {
            "kind": "numeric_equal",
            "left": _ref("inputs", length_field, "i32"),
            "right": _ref("expected", write_count_field, "usize"),
        },
    ]


def _equal_relation(
    left_section: str,
    left_field: str,
    right_section: str,
    right_field: str,
    encoding: str,
) -> dict[str, Any]:
    return {
        "kind": "equal",
        "left": _ref(left_section, left_field, encoding),
        "right": _ref(right_section, right_field, encoding),
    }


def _length_relation(
    collection_section: str,
    collection_field: str,
    length_section: str,
    length_field: str,
) -> dict[str, Any]:
    return {
        "kind": "length_equals",
        "collection": _ref(collection_section, collection_field, "i32_vec"),
        "length": _ref(length_section, length_field, "i32"),
    }


def _ref(section: str, field: str, encoding: str) -> dict[str, str]:
    return {"section": section, "field": field, "encoding": encoding}


def _validate_fixture_cases(
    spec: dict[str, Any], fixture: dict[str, Any], input_field: str, length_field: str
) -> dict[str, Any]:
    cases = fixture.get("cases")
    observable = spec.get("fixture_contract", {}).get("observable_outputs")
    if not isinstance(cases, list) or not cases or not isinstance(observable, list):
        raise ValueError("implicit slice-output fixture contract is incomplete")
    first = cases[0].get("expected")
    if not isinstance(first, dict) or any(field not in first for field in observable):
        raise ValueError("implicit slice-output observable field is missing")
    list_fields = [field for field in observable if isinstance(first.get(field), list)]
    string_fields = [field for field in observable if isinstance(first.get(field), str)]
    numeric_fields = [field for field in observable if _is_i32(first.get(field))]
    output_fields = [field for field in list_fields if field != input_field]
    write_count_fields = [field for field in numeric_fields if field not in {"return_code", length_field}]
    if (
        input_field not in list_fields
        or len(output_fields) != 1
        or "status" not in string_fields
        or len(write_count_fields) != 1
        or set(observable) != set(list_fields + string_fields + numeric_fields)
    ):
        raise ValueError("implicit slice-output observable types are ambiguous")
    output_field = output_fields[0]
    write_count_field = write_count_fields[0]
    metadata_values = {field: first[field] for field in string_fields}
    maximum_length = 0
    for case in cases:
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ValueError("implicit slice-output fixture case is incomplete")
        if any(field not in expected for field in observable):
            raise ValueError("implicit slice-output observable field is missing")
        values = inputs.get(input_field)
        length = inputs.get(length_field)
        output = expected.get(output_field)
        if not _is_i32_list(values) or not _is_i32(length) or length < 0:
            raise ValueError("implicit slice-output input shape is invalid")
        if length > MAX_I32_SLICE_ITEMS or len(values) != length:
            raise ValueError("implicit slice-output input length is invalid")
        if not _is_i32_list(output) or len(output) != length:
            raise ValueError("implicit slice-output output length is invalid")
        if expected.get(input_field) != values or expected.get(length_field) != length:
            raise ValueError("implicit slice-output fixture echo drifted")
        if expected.get(write_count_field) != length:
            raise ValueError("implicit slice-output write count drifted")
        if not _is_i32(expected.get("return_code")):
            raise ValueError("implicit slice-output return code must be i32")
        if any(expected.get(field) != value for field, value in metadata_values.items()):
            raise ValueError("implicit slice-output metadata drifted")
        if expected.get("status") != "ok":
            raise ValueError("implicit slice-output status metadata drifted")
        maximum_length = max(maximum_length, length)
    return {
        "output_field": output_field,
        "write_count_field": write_count_field,
        "metadata_fields": [field for field in observable if field in string_fields],
        "metadata_values": metadata_values,
        "maximum_length": maximum_length,
    }


def _slice_parameters(signature: dict[str, Any]) -> dict[str, dict[str, Any]]:
    parameters = _signature_parameters(signature)
    if len(parameters) != 3:
        raise ValueError("implicit slice-output replay requires three C parameters")
    lengths = [item for item in parameters if item.get("direction") == "input" and _normalize_c_type(item.get("c_type")) == "int"]
    inputs = [item for item in parameters if item.get("direction") == "input" and _normalize_c_type(item.get("c_type")) == "const int*" and isinstance(item.get("buffer_length_parameter"), str)]
    outputs = [item for item in parameters if item.get("direction") == "output" and _normalize_c_type(item.get("c_type")) == "int*" and isinstance(item.get("buffer_length_parameter"), str)]
    if len(lengths) != 1 or len(inputs) != 1 or len(outputs) != 1:
        raise ValueError("implicit slice-output replay parameter roles are ambiguous")
    length_name = _identifier(lengths[0].get("name"), "length parameter")
    if inputs[0].get("buffer_length_parameter") != length_name or outputs[0].get("buffer_length_parameter") != length_name:
        raise ValueError("implicit slice-output length mapping drifted")
    return {"input": inputs[0], "length": lengths[0], "output": outputs[0]}


def _matching_signature(spec: dict[str, Any], function_name: str) -> dict[str, Any]:
    matches = [item for item in spec.get("c_boundary", {}).get("signatures") or [] if isinstance(item, dict) and item.get("function") == function_name]
    if len(matches) != 1:
        raise ValueError("implicit slice-output replay requires exactly one matching C signature")
    return matches[0]


def _signature_parameters(signature: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = signature.get("parameters")
    if not isinstance(parameters, list) or any(not isinstance(item, dict) for item in parameters):
        raise ValueError("implicit slice-output C parameters are invalid")
    return parameters


def _public_api_name(spec: dict[str, Any], fallback: str) -> str:
    entries = [item for item in spec.get("rust_boundary", {}).get("public_api") or [] if isinstance(item, dict)]
    if not entries:
        return fallback
    if len(entries) != 1:
        raise ValueError("implicit slice-output replay requires at most one Rust public API")
    return _identifier(entries[0].get("name"), "Rust API")


def _normalize_c_type(value: Any) -> str:
    return " ".join(str(value or "").replace(" *", "*").split())


def _is_i32(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and -(2**31) <= value <= 2**31 - 1


def _is_i32_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) <= MAX_I32_SLICE_ITEMS and all(_is_i32(item) for item in value)


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} identifier is invalid")
    return value


__all__ = [
    "build_implicit_i32_slice_output_plan",
    "supports_implicit_i32_slice_output_plan",
]
