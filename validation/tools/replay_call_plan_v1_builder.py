from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools.replay_call_plan_fixture import _fixture_binding
from validation.tools.replay_call_plan_render_literal import _plan_sha256
from validation.tools.replay_call_plan_schema import (
    _identifier,
    _normalize_assertions,
    _normalize_fixture_assertions,
    _normalize_source,
    _normalize_supporting_types,
    _rust_type,
    _validate_case_values,
    validate_replay_call_plan,
)


def _build_bound_plan(
    spec: dict[str, Any],
    contract: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    if contract.get("schema_version") != 3:
        raise ValueError("declarative replay contract schema_version must be 3")
    source_function_name = _identifier(spec.get("function_name"), "source function")
    signatures = spec.get("c_boundary", {}).get("signatures")
    matching_signatures = [
        item
        for item in signatures or []
        if isinstance(item, dict) and item.get("function") == source_function_name
    ]
    if len(matching_signatures) != 1:
        raise ValueError("declarative replay requires exactly one matching C signature")
    signature = matching_signatures[0]
    c_parameters = [
        item for item in signature.get("parameters", []) if isinstance(item, dict)
    ]
    c_names = [_identifier(item.get("name"), "C parameter") for item in c_parameters]
    if len(c_names) != len(set(c_names)):
        raise ValueError("C signature parameter names must be unique")

    public_api = spec.get("rust_boundary", {}).get("public_api")
    api_entries = [item for item in public_api or [] if isinstance(item, dict)]
    if len(api_entries) != 1:
        raise ValueError("declarative replay requires exactly one Rust public API")
    api_name = _identifier(api_entries[0].get("name"), "Rust API")

    rust_api = contract.get("rust_api")
    if not isinstance(rust_api, dict):
        raise ValueError("declarative replay rust_api is required")
    visibility = rust_api.get("visibility")
    if visibility not in {"pub", "pub(crate)", "private"}:
        raise ValueError("Rust API visibility is unsupported")
    abi = rust_api.get("abi")
    if abi not in {"Rust", "C"}:
        raise ValueError("Rust API ABI is unsupported")
    unsafe = rust_api.get("unsafe")
    if not isinstance(unsafe, bool):
        raise ValueError("Rust API unsafe must be boolean")
    return_type = _rust_type(rust_api.get("return_type"), "return type")

    raw_parameters = rust_api.get("parameters")
    if not isinstance(raw_parameters, list):
        raise ValueError("Rust API parameters must be an array")
    normalized_parameters: list[dict[str, Any]] = []
    mapped_c_names: list[str] = []
    for position, raw_parameter in enumerate(raw_parameters):
        if not isinstance(raw_parameter, dict):
            raise ValueError("Rust API parameter must be an object")
        name = _identifier(raw_parameter.get("name"), "Rust parameter")
        c_parameter = _identifier(
            raw_parameter.get("c_parameter"), "C parameter mapping"
        )
        if c_parameter not in c_names:
            raise ValueError(
                f"Rust parameter {name} maps unknown C parameter {c_parameter}"
            )
        if c_parameter in mapped_c_names:
            raise ValueError(f"C parameter {c_parameter} is mapped more than once")
        source = _normalize_source(raw_parameter.get("source"))
        length_retained = raw_parameter.get("length_retained")
        if not isinstance(length_retained, bool):
            raise ValueError(f"Rust parameter {name} length_retained must be boolean")
        if source["kind"] == "encoded_length" and not length_retained:
            raise ValueError(f"derived length parameter {name} must be retained")
        normalized_parameters.append(
            {
                "position": position,
                "name": name,
                "rust_type": _rust_type(
                    raw_parameter.get("rust_type"), "parameter type"
                ),
                "c_parameter": c_parameter,
                "length_retained": length_retained,
                "source": source,
            }
        )
        mapped_c_names.append(c_parameter)
    rust_names = [item["name"] for item in normalized_parameters]
    if len(rust_names) != len(set(rust_names)):
        raise ValueError("Rust API parameter names must be unique")

    omitted = contract.get("omitted_c_parameters")
    if not isinstance(omitted, list):
        raise ValueError("omitted_c_parameters must be an array")
    omitted_names = [_identifier(item, "omitted C parameter") for item in omitted]
    if len(omitted_names) != len(set(omitted_names)):
        raise ValueError("omitted C parameters must be unique")
    if any(item not in c_names for item in omitted_names):
        raise ValueError("omitted_c_parameters contains an unknown C parameter")
    if set(mapped_c_names) & set(omitted_names):
        raise ValueError("a C parameter cannot be both mapped and omitted")
    if set(mapped_c_names) | set(omitted_names) != set(c_names):
        raise ValueError("C parameter mappings are not closed")

    assertions = _normalize_assertions(contract.get("assertions"))
    fixture_assertions = _normalize_fixture_assertions(
        contract.get("fixture_assertions", [])
    )
    observable_outputs = spec.get("fixture_contract", {}).get("observable_outputs")
    if not isinstance(observable_outputs, list) or not observable_outputs:
        raise ValueError("fixture observable_outputs are required")
    covered_outputs = {
        item["fixture_field"] for item in [*assertions, *fixture_assertions]
    }
    if covered_outputs != set(observable_outputs):
        raise ValueError("replay assertions must cover every observable output exactly")

    fixture = _fixture_binding(spec, repo_root)
    _validate_case_values(
        fixture["cases"], normalized_parameters, assertions, fixture_assertions
    )
    c_by_name = {item["name"]: item for item in c_parameters}
    plan: dict[str, Any] = {
        "schema_version": 1,
        "status": "bound",
        "source_function_name": source_function_name,
        "api_name": api_name,
        "visibility": visibility,
        "abi": abi,
        "unsafe": unsafe,
        "parameters": normalized_parameters,
        "c_parameter_mappings": [
            {
                "position": item["position"],
                "c_parameter": item["c_parameter"],
                "c_type": str(c_by_name[item["c_parameter"]].get("c_type") or ""),
                "direction": str(
                    c_by_name[item["c_parameter"]].get("direction") or ""
                ),
                "rust_parameter": item["name"],
                "rust_type": item["rust_type"],
            }
            for item in normalized_parameters
        ],
        "omitted_c_parameters": omitted_names,
        "length_parameters_retained": [
            item["name"] for item in normalized_parameters if item["length_retained"]
        ],
        "return_type": return_type,
        "supporting_types": _normalize_supporting_types(
            rust_api.get("supporting_types")
        ),
        "call_args": [
            {
                "position": item["position"],
                "parameter": item["name"],
                "source": item["source"],
            }
            for item in normalized_parameters
        ],
        "assertions": assertions,
        "fixture": {
            "path": fixture["path"],
            "sha256": fixture["sha256"],
            "case_count": len(fixture["cases"]),
            "case_ids": [item["id"] for item in fixture["cases"]],
        },
    }
    if fixture_assertions:
        plan["fixture_assertions"] = fixture_assertions
    plan["plan_sha256"] = _plan_sha256(plan)
    validate_replay_call_plan(plan)
    return plan
