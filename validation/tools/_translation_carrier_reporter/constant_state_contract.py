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


KIND = "record_u32_field_constant_state"


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("record field constant-state schema_version must be 1")
    if set(contract) != {
        "schema_version", "kind", "entry_arguments", "state_output", "state_update",
        "return", "noalias_required",
    }:
        raise ReporterError("record field constant-state contract shape drifted")

    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or not entries:
        raise ReporterError("record field constant-state entry arguments are missing")
    entry_by_name: dict[str, dict[str, Any]] = {}
    fixture_fields: list[str] = []
    for index, raw_entry in enumerate(entries):
        entry = require_dict(raw_entry, f"entry_arguments[{index}]")
        if set(entry) != {
            "parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer",
        }:
            raise ReporterError(f"entry_arguments[{index}] shape drifted")
        parameter = require_identifier(entry.get("parameter"), f"entry_arguments[{index}].parameter")
        rust_type = require_identifier(entry.get("rust_type"), f"entry_arguments[{index}].rust_type")
        if entry.get("pass_mode") != "mutable_ref":
            raise ReporterError("record field constant-state roots must be mutable_ref")
        if entry.get("direction") not in {"input", "inout"}:
            raise ReporterError(f"entry_arguments[{index}].direction is unsupported")
        if normalize_c_type(entry.get("c_type")) != normalize_c_type(f"struct {rust_type} *"):
            raise ReporterError(f"entry_arguments[{index}].c_type drifted")
        if parameter in entry_by_name:
            raise ReporterError("entry argument parameters must be unique")
        validate_initializer(entry.get("initializer"), f"entry_arguments[{index}].initializer")
        if entry["initializer"]["record_type"] != rust_type:
            raise ReporterError(f"entry_arguments[{index}] initializer type drifted")
        fixture_fields.extend(field for field, _ in initializer_fixture_paths(entry["initializer"]))
        entry_by_name[parameter] = entry

    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {"parameter", "field_path", "fixture_field", "rust_type"}:
        raise ReporterError("state_output shape drifted")
    state_parameter = require_identifier(state.get("parameter"), "state_output.parameter")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    if state.get("rust_type") != "u32":
        raise ReporterError("state_output.rust_type must be u32")
    state_path = field_path(state.get("field_path"), "state_output.field_path")
    if len(state_path) < 2:
        raise ReporterError("state_output.field_path must be nested")
    state_entry = entry_by_name.get(state_parameter)
    if state_entry is None or state_entry.get("direction") != "inout":
        raise ReporterError("state_output must bind an inout entry root")
    if state_path not in dict(initializer_fixture_paths(state_entry["initializer"])).values():
        raise ReporterError("state_output.field_path is not initialized")

    update = require_dict(contract.get("state_update"), "state_update")
    if update != {"operation": "constant_assign", "rust_type": "u32", "value": 0}:
        raise ReporterError("state_update must assign declared u32 constant 0")
    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or type(result.get("value")) is not bool:
        raise ReporterError("return must declare a bool constant")

    validate_noalias(spec, contract, sorted(entry_by_name))
    validate_signature(spec, contract)
    fields = behavior_fields(contract)
    if len([*fixture_fields, *fields]) != len(set([*fixture_fields, *fields])):
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


def validate_noalias(spec: dict[str, Any], contract: dict[str, Any], names: list[str]) -> None:
    declared = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    pointer = require_dict(
        spec.get("c_boundary", {}).get("pointer_contract"), "c_boundary.pointer_contract"
    )
    if pointer.get("aliasing_proven") is not True:
        raise ReporterError("pointer aliasing metadata is not proven")
    boundary = noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required")
    required = {
        (names[left], names[right])
        for left in range(len(names)) for right in range(left + 1, len(names))
    }
    if declared != boundary or declared != required:
        raise ReporterError("noalias must cover every mutable root pair")


def validate_signature(spec: dict[str, Any], contract: dict[str, Any]) -> None:
    signatures = spec.get("c_boundary", {}).get("signatures")
    matches = [
        item for item in signatures or []
        if isinstance(item, dict) and item.get("function") == spec.get("function_name")
    ]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("record field constant-state entry signature drifted")
    actual = [item for item in matches[0].get("parameters", []) if isinstance(item, dict)]
    entries = contract["entry_arguments"]
    if [item.get("name") for item in actual] != [item["parameter"] for item in entries]:
        raise ReporterError("record field constant-state entry parameters drifted")
    if [normalize_c_type(item.get("c_type")) for item in actual] != [
        normalize_c_type(item["c_type"]) for item in entries
    ]:
        raise ReporterError("record field constant-state entry parameter types drifted")
    if [item.get("direction") for item in actual] != [item["direction"] for item in entries]:
        raise ReporterError("record field constant-state entry directions drifted")
