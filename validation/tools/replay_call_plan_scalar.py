from __future__ import annotations

import re
from typing import Any


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def build_implicit_scalar_contract(spec: dict[str, Any]) -> dict[str, Any] | None:
    function_name = spec.get("function_name")
    if not isinstance(function_name, str) or not IDENTIFIER_RE.fullmatch(function_name):
        return None
    signatures = [
        item
        for item in spec.get("c_boundary", {}).get("signatures") or []
        if isinstance(item, dict) and item.get("function") == function_name
    ]
    if len(signatures) != 1:
        return None
    signature = signatures[0]
    parameters = signature.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        return None
    observable = spec.get("fixture_contract", {}).get("observable_outputs")
    if not isinstance(observable, list):
        return None

    return_c_type = _normalize_c_type(signature.get("return_type"))
    parameter_c_types = [_normalize_c_type(item.get("c_type")) for item in parameters if isinstance(item, dict)]
    if len(parameter_c_types) != len(parameters) or any(
        item.get("direction") != "input" for item in parameters if isinstance(item, dict)
    ):
        return None

    fixture_assertions: list[dict[str, Any]] = []
    if return_c_type == "uint32_t" and parameter_c_types == ["uint32_t"] and observable == ["value"]:
        rust_type = "u32"
        return_field = "value"
    elif return_c_type == "int" and parameter_c_types == ["int"] and observable == ["return_value", "status"]:
        rust_type = "i32"
        return_field = "return_value"
        fixture_assertions = [_fixture_assertion("status", "ok")]
    elif (
        return_c_type == "int"
        and parameter_c_types == ["int", "int"]
        and observable == ["return_value", "status", "contract"]
        and spec.get("c_boundary", {}).get("scalar_arithmetic_contract", {}).get("signed_right_shift")
        == "explicit_implementation_defined_contract"
    ):
        rust_type = "i32"
        return_field = "return_value"
        fixture_assertions = [
            _fixture_assertion("status", "ok"),
            _fixture_assertion("contract", "implementation_defined_arithmetic_shift"),
        ]
    elif (
        return_c_type == "unsigned long"
        and parameter_c_types == ["unsigned long"]
        and observable == ["return_value", "status"]
    ):
        rust_type = "u64"
        return_field = "return_value"
        fixture_assertions = [_fixture_assertion("status", "ok")]
    else:
        return None

    normalized_parameters = []
    for item in parameters:
        name = item.get("name")
        if not isinstance(name, str) or not IDENTIFIER_RE.fullmatch(name):
            return None
        normalized_parameters.append(
            {
                "name": name,
                "rust_type": rust_type,
                "c_parameter": name,
                "length_retained": False,
                "source": {
                    "kind": "fixture_field",
                    "field": name,
                    "encoding": rust_type,
                },
            }
        )
    contract: dict[str, Any] = {
        "schema_version": 3,
        "kind": "declarative_call_plan",
        "rust_api": {
            "visibility": "pub",
            "abi": "Rust",
            "unsafe": False,
            "parameters": normalized_parameters,
            "return_type": rust_type,
            "supporting_types": [],
        },
        "omitted_c_parameters": [],
        "assertions": [
            {
                "actual": "return",
                "fixture_field": return_field,
                "rust_type": rust_type,
                "encoding": rust_type,
            }
        ],
    }
    if fixture_assertions:
        contract["fixture_assertions"] = fixture_assertions
    return contract


def _fixture_assertion(field: str, expected: str) -> dict[str, Any]:
    return {"fixture_field": field, "encoding": "string", "expected": expected}


def _normalize_c_type(value: Any) -> str:
    return " ".join(str(value or "").replace(" *", "*").split())


__all__ = ["build_implicit_scalar_contract"]
