from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .record_contract import (
    field_path,
    initializer_fixture_paths,
    noalias_pairs,
    normalize_c_type,
    require_dict,
    require_identifier,
    validate_initializer,
)


KIND = "record_interior_projection_u32_constant_state"


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("interior projection schema_version must be 1")
    if set(contract) != {
        "schema_version", "kind", "owner", "projection_path", "alias",
        "state_output", "constant_assign", "return", "noalias_required",
    }:
        raise ReporterError("interior projection contract shape drifted")

    owner = require_dict(contract.get("owner"), "owner")
    if set(owner) != {
        "parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer",
    }:
        raise ReporterError("interior projection owner shape drifted")
    owner_name = require_identifier(owner.get("parameter"), "owner.parameter")
    owner_type = require_identifier(owner.get("rust_type"), "owner.rust_type")
    if owner.get("pass_mode") != "mutable_ref" or owner.get("direction") != "inout":
        raise ReporterError("interior projection owner must be one mutable inout root")
    if normalize_c_type(owner.get("c_type")) != normalize_c_type(f"struct {owner_type} *"):
        raise ReporterError("interior projection owner C type drifted")
    validate_initializer(owner.get("initializer"), "owner.initializer")
    initializer = owner["initializer"]
    if initializer["record_type"] != owner_type:
        raise ReporterError("interior projection owner initializer type drifted")

    projection_path = field_path(contract.get("projection_path"), "projection_path")
    projected = projection_record_at(initializer, projection_path)
    alias = require_dict(contract.get("alias"), "alias")
    if set(alias) != {"local", "c_pointer_type", "rust_type"}:
        raise ReporterError("interior projection alias shape drifted")
    require_identifier(alias.get("local"), "alias.local")
    require_identifier(alias.get("c_pointer_type"), "alias.c_pointer_type")
    alias_type = require_identifier(alias.get("rust_type"), "alias.rust_type")
    if projected["record_type"] != alias_type:
        raise ReporterError("interior projection alias type does not match projected record")

    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {
        "alias_field_path", "owner_field_path", "fixture_field", "rust_type",
    }:
        raise ReporterError("interior projection state_output shape drifted")
    alias_state_path = field_path(state.get("alias_field_path"), "state_output.alias_field_path")
    if len(alias_state_path) < 2:
        raise ReporterError("interior projection state must be deeper than the projected record")
    owner_state_path = field_path(state.get("owner_field_path"), "state_output.owner_field_path")
    if owner_state_path != projection_path + alias_state_path:
        raise ReporterError("owner state path must extend projection_path")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    if state.get("rust_type") != "u32":
        raise ReporterError("state_output.rust_type must be u32")
    if owner_state_path not in dict(initializer_fixture_paths(initializer)).values():
        raise ReporterError("interior projection state field is not initialized")

    if contract.get("constant_assign") != {"rust_type": "u32", "value": 0}:
        raise ReporterError("constant_assign must declare u32 zero")
    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("interior projection return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or result.get("value") is not True:
        raise ReporterError("interior projection return must declare owner-observed bool true")

    validate_pointer_boundary(spec, contract, owner_name)
    validate_signature(spec, owner)
    fixture_fields = [field for field, _ in initializer_fixture_paths(initializer)]
    outputs = behavior_fields(contract)
    if len([*fixture_fields, *outputs]) != len(set([*fixture_fields, *outputs])):
        raise ReporterError("interior projection fixture and output fields must be unique")
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    if (fixture.get("observable_outputs") or fixture.get("behavior_fields")) != outputs:
        raise ReporterError("interior projection observable output mapping drifted")
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    return [
        str(contract["return"]["fixture_field"]),
        str(contract["state_output"]["fixture_field"]),
    ]


def projection_record_at(initializer: dict[str, Any], path: list[str]) -> dict[str, Any]:
    current = initializer
    for component in path:
        match = next(
            (
                item for item in current.get("fields", [])
                if isinstance(item, dict) and item.get("name") == component
            ),
            None,
        )
        if not isinstance(match, dict) or not isinstance(match.get("record"), dict):
            raise ReporterError("projection_path must select initialized nested records")
        current = match["record"]
    return current


def validate_pointer_boundary(
    spec: dict[str, Any], contract: dict[str, Any], owner_name: str
) -> None:
    if noalias_pairs(contract.get("noalias_required"), "noalias_required"):
        raise ReporterError("interior projection noalias_required must be empty")
    pointer = require_dict(
        spec.get("c_boundary", {}).get("pointer_contract"), "c_boundary.pointer_contract"
    )
    if pointer.get("aliasing_proven") is not True:
        raise ReporterError("interior projection requires one proven pointer root")
    if noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required"):
        raise ReporterError("pointer noalias_required must be empty")
    signatures = spec.get("c_boundary", {}).get("signatures") or []
    matches = [
        item for item in signatures
        if isinstance(item, dict) and item.get("function") == spec.get("function_name")
    ]
    parameters = matches[0].get("parameters", []) if len(matches) == 1 else []
    roots = [
        item for item in parameters
        if isinstance(item, dict) and "*" in str(item.get("c_type") or "")
    ]
    if len(roots) != 1 or roots[0].get("name") != owner_name:
        raise ReporterError("c_boundary must expose exactly one proven owner pointer root")


def validate_signature(spec: dict[str, Any], owner: dict[str, Any]) -> None:
    signatures = spec.get("c_boundary", {}).get("signatures") or []
    matches = [
        item for item in signatures
        if isinstance(item, dict) and item.get("function") == spec.get("function_name")
    ]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {
        "bool", "_Bool",
    }:
        raise ReporterError("interior projection entry signature drifted")
    actual = [item for item in matches[0].get("parameters", []) if isinstance(item, dict)]
    if len(actual) != 1 or actual[0].get("name") != owner["parameter"]:
        raise ReporterError("interior projection signature must contain only owner")
    if normalize_c_type(actual[0].get("c_type")) != normalize_c_type(owner["c_type"]):
        raise ReporterError("interior projection owner parameter type drifted")
    if actual[0].get("direction") != "inout":
        raise ReporterError("interior projection owner direction drifted")
