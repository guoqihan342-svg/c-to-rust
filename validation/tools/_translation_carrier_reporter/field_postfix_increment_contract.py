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


KIND = "record_u32_field_postfix_increment_state"


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("record field postfix-increment schema_version must be 1")
    if set(contract) != {
        "schema_version", "kind", "entry_arguments", "state_output", "state_update", "return",
        "noalias_required",
    }:
        raise ReporterError("record field postfix-increment contract shape drifted")

    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or len(entries) != 1:
        raise ReporterError("record field postfix-increment requires one entry argument")
    entry = require_dict(entries[0], "entry_arguments[0]")
    if set(entry) != {
        "parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer",
    }:
        raise ReporterError("entry_arguments[0] shape drifted")
    parameter = require_identifier(entry.get("parameter"), "entry_arguments[0].parameter")
    rust_type = require_identifier(entry.get("rust_type"), "entry_arguments[0].rust_type")
    if entry.get("pass_mode") != "mutable_ref" or entry.get("direction") != "inout":
        raise ReporterError("postfix-increment entry must be one mutable inout record pointer")
    if normalize_c_type(entry.get("c_type")) != normalize_c_type(f"struct {rust_type} *"):
        raise ReporterError("postfix-increment entry C type drifted")
    validate_initializer(entry.get("initializer"), "entry_arguments[0].initializer")
    if entry["initializer"]["record_type"] != rust_type:
        raise ReporterError("postfix-increment initializer type drifted")
    initialized = initializer_fixture_paths(entry["initializer"])
    if len(initialized) != 1 or len(initialized[0][1]) != 1:
        raise ReporterError("postfix-increment initializer must contain one direct u32 field")

    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {"parameter", "field_path", "fixture_field", "rust_type"}:
        raise ReporterError("state_output shape drifted")
    state_parameter = require_identifier(state.get("parameter"), "state_output.parameter")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    state_path = field_path(state.get("field_path"), "state_output.field_path")
    if state_parameter != parameter or state.get("rust_type") != "u32" or len(state_path) != 1:
        raise ReporterError("state_output must bind the direct mutable record u32 field")
    if state_path != initialized[0][1]:
        raise ReporterError("state_output field is not the sole initialized field")

    update = require_dict(contract.get("state_update"), "state_update")
    if set(update) != {"operation", "increment"}:
        raise ReporterError("state_update shape drifted")
    if update.get("operation") != "wrapping_add" or update.get("increment") != 1:
        raise ReporterError("state_update must declare fixed wrapping_add increment 1")

    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or type(result.get("value")) is not bool:
        raise ReporterError("return must declare a fixed bool value")

    validate_noalias(spec, contract)
    validate_signature(spec, entry)
    fields = behavior_fields(contract)
    fixture_field = initialized[0][0]
    if len({fixture_field, *fields}) != 3:
        raise ReporterError("fixture and output fields must be unique")
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    if (fixture.get("observable_outputs") or fixture.get("behavior_fields")) != fields:
        raise ReporterError("observable output mapping drifted")
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    return [
        str(contract["return"]["fixture_field"]),
        str(contract["state_output"]["fixture_field"]),
    ]


def input_fixture_field(contract: dict[str, Any]) -> str:
    entry = contract["entry_arguments"][0]
    return initializer_fixture_paths(entry["initializer"])[0][0]


def validate_noalias(spec: dict[str, Any], contract: dict[str, Any]) -> None:
    declared = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    pointer = require_dict(
        spec.get("c_boundary", {}).get("pointer_contract"), "c_boundary.pointer_contract"
    )
    boundary = noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required")
    if pointer.get("aliasing_proven") is not True:
        raise ReporterError("pointer aliasing metadata is not proven")
    if declared or boundary or declared != boundary:
        raise ReporterError("single pointer root requires empty noalias pairs")


def validate_signature(spec: dict[str, Any], entry: dict[str, Any]) -> None:
    signatures = spec.get("c_boundary", {}).get("signatures")
    matches = [
        item for item in signatures or []
        if isinstance(item, dict) and item.get("function") == spec.get("function_name")
    ]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("postfix-increment entry signature drifted")
    actual = [item for item in matches[0].get("parameters", []) if isinstance(item, dict)]
    if len(actual) != 1:
        raise ReporterError("postfix-increment entry signature must have one parameter")
    if (
        actual[0].get("name") != entry["parameter"]
        or normalize_c_type(actual[0].get("c_type")) != normalize_c_type(entry["c_type"])
        or actual[0].get("direction") != entry["direction"]
    ):
        raise ReporterError("postfix-increment entry parameter drifted")
