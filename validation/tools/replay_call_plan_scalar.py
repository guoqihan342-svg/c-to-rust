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
    fixture_field_by_parameter: dict[str, str] = {}
    if return_c_type == "uint32_t" and parameter_c_types == ["uint32_t"] and observable == ["value"]:
        rust_type = "u32"
        return_field = "value"
    elif (
        return_c_type == "int"
        and parameter_c_types == ["int"]
        and observable
        == [
            "return_value",
            "status",
            "call_expression_count",
            "call_expression_contexts",
            "source_calls",
        ]
    ):
        metadata = _call_expression_metadata(spec)
        if metadata is None:
            return None
        rust_type = "i32"
        return_field = "return_value"
        fixture_field_by_parameter = metadata["input_fixture_fields"]
        fixture_assertions = [
            _fixture_assertion("status", "string", "ok"),
            _fixture_assertion(
                "call_expression_count", "usize", len(metadata["contexts"])
            ),
            _fixture_assertion(
                "call_expression_contexts", "string_vec", metadata["contexts"]
            ),
            _fixture_assertion("source_calls", "string_vec", metadata["source_calls"]),
        ]
    elif return_c_type == "int" and parameter_c_types == ["int"] and observable == ["return_value", "status"]:
        rust_type = "i32"
        return_field = "return_value"
        fixture_assertions = [_fixture_assertion("status", "string", "ok")]
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
            _fixture_assertion("status", "string", "ok"),
            _fixture_assertion(
                "contract", "string", "implementation_defined_arithmetic_shift"
            ),
        ]
    elif (
        return_c_type == "unsigned long"
        and parameter_c_types == ["unsigned long"]
        and observable == ["return_value", "status"]
    ):
        rust_type = "u64"
        return_field = "return_value"
        fixture_assertions = [_fixture_assertion("status", "string", "ok")]
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
                    "field": fixture_field_by_parameter.get(name, name),
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


def _call_expression_metadata(spec: dict[str, Any]) -> dict[str, Any] | None:
    contract = spec.get("c_boundary", {}).get("call_expression_contract")
    if not isinstance(contract, dict):
        return None
    if contract.get("direct_call_only") is not True or contract.get("callee_scope") != "self_recursive":
        return None
    contexts = contract.get("contexts")
    source_calls = contract.get("source_calls")
    if not _bounded_string_list(contexts) or not _bounded_string_list(source_calls):
        return None
    if len(contexts) != len(source_calls):
        return None
    signatures = [
        item
        for item in spec.get("c_boundary", {}).get("signatures") or []
        if isinstance(item, dict) and item.get("function") == spec.get("function_name")
    ]
    if len(signatures) != 1:
        return None
    parameter_names = [
        item.get("name") for item in signatures[0].get("parameters") or [] if isinstance(item, dict)
    ]
    mapping = contract.get("input_fixture_fields")
    if (
        not isinstance(mapping, dict)
        or set(mapping) != set(parameter_names)
        or any(
            not isinstance(field, str) or not IDENTIFIER_RE.fullmatch(field)
            for field in mapping.values()
        )
    ):
        return None
    return {
        "contexts": list(contexts),
        "source_calls": list(source_calls),
        "input_fixture_fields": dict(mapping),
    }


def _bounded_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and 1 <= len(value) <= 64
        and all(isinstance(item, str) and item for item in value)
    )


def _fixture_assertion(field: str, encoding: str, expected: Any) -> dict[str, Any]:
    return {"fixture_field": field, "encoding": encoding, "expected": expected}


def _normalize_c_type(value: Any) -> str:
    return " ".join(str(value or "").replace(" *", "*").split())


__all__ = ["build_implicit_scalar_contract"]
