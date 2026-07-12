from __future__ import annotations

import re
from typing import Any

from validation.tools.replay_call_plan_v2 import (
    _plan_sha256,
    validate_replay_call_plan_v2,
)


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def supports_implicit_single_i32_output_plan(spec: dict[str, Any]) -> bool:
    try:
        function_name = _identifier(spec.get("function_name"), "source function")
        signature = _matching_signature(spec, function_name)
        parameters = _signature_parameters(signature)
        observable = _observable_output_field(spec)
    except ValueError:
        return False
    return (
        _normalize_c_type(signature.get("return_type")) == "int"
        and len(parameters) == 2
        and len(_input_parameters(parameters)) == 1
        and len(_output_parameters(parameters)) == 1
        and bool(observable)
    )


def build_implicit_single_i32_output_plan(
    spec: dict[str, Any], fixture: dict[str, Any]
) -> dict[str, Any]:
    if not supports_implicit_single_i32_output_plan(spec):
        raise ValueError("implicit single i32 output replay shape is unsupported")

    function_name = _identifier(spec.get("function_name"), "source function")
    signature = _matching_signature(spec, function_name)
    c_parameters = _signature_parameters(signature)
    input_parameter = _input_parameters(c_parameters)[0]
    output_parameter = _output_parameters(c_parameters)[0]
    input_name = _identifier(input_parameter.get("name"), "input parameter")
    output_name = _identifier(output_parameter.get("name"), "output parameter")
    output_field = _observable_output_field(spec)

    binding = {
        "name": output_name,
        "rust_type": "[i32; 1]",
        "mutable": True,
        "initializer": {
            "kind": "array_repeat",
            "rust_type": "[i32; 1]",
            "element_type": "i32",
            "length": 1,
            "value": 0,
        },
    }
    parameters: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for position, c_parameter in enumerate(c_parameters):
        name = _identifier(c_parameter.get("name"), "C parameter")
        if c_parameter is input_parameter:
            rust_type = "i32"
            source = {"kind": "fixture_field", "field": input_name, "encoding": "i32"}
        else:
            rust_type = "&mut [i32]"
            source = {"kind": "binding_borrow_mut", "binding": output_name}
        parameters.append(
            {
                "position": position,
                "name": name,
                "rust_type": rust_type,
                "c_parameter": name,
                "length_retained": False,
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

    _validate_fixture_cases(fixture, input_name, output_field)
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
        "length_parameters_retained": [],
        "return_type": "i32",
        "supporting_types": [],
        "bindings": [binding],
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
                "actual": f"binding.{output_name}.0",
                "fixture_field": output_field,
                "rust_type": "i32",
                "encoding": "i32",
            },
        ],
        "fixture_assertions": [
            {"fixture_field": "status", "encoding": "string", "expected": "ok"}
        ],
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


def _matching_signature(spec: dict[str, Any], function_name: str) -> dict[str, Any]:
    matches = [
        item
        for item in spec.get("c_boundary", {}).get("signatures") or []
        if isinstance(item, dict) and item.get("function") == function_name
    ]
    if len(matches) != 1:
        raise ValueError("implicit output replay requires exactly one matching C signature")
    return matches[0]


def _signature_parameters(signature: dict[str, Any]) -> list[dict[str, Any]]:
    parameters = signature.get("parameters")
    if not isinstance(parameters, list) or any(not isinstance(item, dict) for item in parameters):
        raise ValueError("implicit output replay C parameters are invalid")
    return parameters


def _input_parameters(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in parameters
        if item.get("direction") == "input" and _normalize_c_type(item.get("c_type")) == "int"
    ]


def _output_parameters(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in parameters
        if item.get("direction") == "output" and _normalize_c_type(item.get("c_type")) == "int*"
    ]


def _observable_output_field(spec: dict[str, Any]) -> str:
    observable = spec.get("fixture_contract", {}).get("observable_outputs")
    if not isinstance(observable, list) or len(observable) != 3 or len(set(observable)) != 3:
        raise ValueError("implicit output replay observable outputs are invalid")
    if "return_code" not in observable or "status" not in observable:
        raise ValueError("implicit output replay metadata outputs are missing")
    return _identifier(
        next(item for item in observable if item not in {"return_code", "status"}),
        "output fixture field",
    )


def _public_api_name(spec: dict[str, Any], fallback: str) -> str:
    public_api = spec.get("rust_boundary", {}).get("public_api")
    entries = [item for item in public_api or [] if isinstance(item, dict)]
    if not entries:
        return fallback
    if len(entries) != 1:
        raise ValueError("implicit output replay requires at most one Rust public API")
    return _identifier(entries[0].get("name"), "Rust API")


def _validate_fixture_cases(
    fixture: dict[str, Any], input_field: str, output_field: str
) -> None:
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("implicit output replay fixture cases are required")
    for case in cases:
        inputs = case.get("inputs")
        expected = case.get("expected")
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ValueError("implicit output replay fixture case is incomplete")
        if not _is_i32(inputs.get(input_field)):
            raise ValueError("implicit output replay input must be i32")
        if not _is_i32(expected.get("return_code")) or not _is_i32(expected.get(output_field)):
            raise ValueError("implicit output replay result must be i32")
        if expected.get("status") != "ok":
            raise ValueError("implicit output replay status metadata drifted")


def _normalize_c_type(value: Any) -> str:
    return " ".join(str(value or "").replace(" *", "*").split())


def _is_i32(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and -(2**31) <= value <= 2**31 - 1


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} identifier is invalid")
    return value


__all__ = [
    "build_implicit_single_i32_output_plan",
    "supports_implicit_single_i32_output_plan",
]
