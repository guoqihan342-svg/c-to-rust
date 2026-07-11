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


KIND = "record_interior_projection_u32_reset_add_while_continue_state"


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1 or set(contract) != {
        "schema_version", "kind", "entry_arguments", "owner_parameter", "projection",
        "reset_state", "add_state", "control_flow", "return", "noalias_required",
    }:
        raise ReporterError("reset-add while-continue contract shape drifted")
    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or len(entries) != 2:
        raise ReporterError("reset-add while-continue requires exactly two record roots")
    by_name: dict[str, dict[str, Any]] = {}
    fixture_fields: list[str] = []
    for index, raw in enumerate(entries):
        entry = require_dict(raw, f"entry_arguments[{index}]")
        if set(entry) != {
            "parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer",
        }:
            raise ReporterError(f"entry_arguments[{index}] shape drifted")
        name = require_identifier(entry.get("parameter"), f"entry_arguments[{index}].parameter")
        rust_type = require_identifier(entry.get("rust_type"), f"entry_arguments[{index}].rust_type")
        if name in by_name or entry.get("pass_mode") != "mutable_ref":
            raise ReporterError("reset-add entry root or pass mode drifted")
        if entry.get("direction") not in {"input", "inout"}:
            raise ReporterError("reset-add entry direction drifted")
        expected_c_type = (
            f"const struct {rust_type} *" if entry.get("direction") == "input"
            else f"struct {rust_type} *"
        )
        if normalize_c_type(entry.get("c_type")) != normalize_c_type(expected_c_type):
            raise ReporterError("reset-add entry C type drifted")
        validate_initializer(entry.get("initializer"), f"entry_arguments[{index}].initializer")
        if entry["initializer"]["record_type"] != rust_type:
            raise ReporterError("reset-add entry initializer type drifted")
        fixture_fields.extend(field for field, _ in initializer_fixture_paths(entry["initializer"]))
        by_name[name] = entry

    owner_name = require_identifier(contract.get("owner_parameter"), "owner_parameter")
    owner = by_name.get(owner_name)
    readonly = [entry for entry in entries if entry["direction"] == "input"]
    if owner is None or owner["direction"] != "inout" or len(readonly) != 1:
        raise ReporterError("reset-add owner/source roles drifted")
    projection = require_dict(contract.get("projection"), "projection")
    if set(projection) != {"path", "alias_local", "alias_c_pointer_type", "alias_rust_type"}:
        raise ReporterError("reset-add projection shape drifted")
    projection_path = field_path(projection.get("path"), "projection.path")
    projected = projection_record_at(owner["initializer"], projection_path)
    alias = require_identifier(projection.get("alias_local"), "projection.alias_local")
    require_identifier(projection.get("alias_c_pointer_type"), "projection.alias_c_pointer_type")
    alias_type = require_identifier(projection.get("alias_rust_type"), "projection.alias_rust_type")
    if alias in by_name or projected["record_type"] != alias_type:
        raise ReporterError("reset-add projection alias drifted")

    reset = require_dict(contract.get("reset_state"), "reset_state")
    if set(reset) != {
        "alias_field_path", "owner_field_path", "fixture_field", "rust_type", "value",
    }:
        raise ReporterError("reset_state shape drifted")
    alias_path = field_path(reset.get("alias_field_path"), "reset_state.alias_field_path")
    owner_reset_path = field_path(reset.get("owner_field_path"), "reset_state.owner_field_path")
    if len(alias_path) < 2 or owner_reset_path != projection_path + alias_path:
        raise ReporterError("reset path must extend projection path")
    require_identifier(reset.get("fixture_field"), "reset_state.fixture_field")
    if reset.get("rust_type") != "u32" or reset.get("value") != 0:
        raise ReporterError("reset_state must declare exact u32 zero")
    owner_paths = dict(initializer_fixture_paths(owner["initializer"]))
    if owner_reset_path not in owner_paths.values():
        raise ReporterError("reset_state path is not initialized")

    add = require_dict(contract.get("add_state"), "add_state")
    if set(add) != {"owner_field_path", "fixture_field", "rust_type", "operation", "rhs"}:
        raise ReporterError("add_state shape drifted")
    add_path = field_path(add.get("owner_field_path"), "add_state.owner_field_path")
    require_identifier(add.get("fixture_field"), "add_state.fixture_field")
    if add_path == owner_reset_path or add_path not in owner_paths.values():
        raise ReporterError("add_state path is not a distinct initialized owner field")
    if add.get("rust_type") != "u32" or add.get("operation") != "wrapping_add":
        raise ReporterError("add_state must declare u32 wrapping_add")
    rhs = require_dict(add.get("rhs"), "add_state.rhs")
    if set(rhs) != {"mode", "parameter", "field_path", "source_expression"}:
        raise ReporterError("add_state.rhs shape drifted")
    source_name = require_identifier(rhs.get("parameter"), "add_state.rhs.parameter")
    source = by_name.get(source_name)
    source_path = field_path(rhs.get("field_path"), "add_state.rhs.field_path")
    if (
        rhs.get("mode") != "direct_record_u32_field"
        or source not in readonly
        or len(source_path) != 1
        or source_path not in dict(initializer_fixture_paths(source["initializer"])).values()
    ):
        raise ReporterError("add rhs must be one direct readonly record u32 field")
    if not isinstance(rhs.get("source_expression"), str) or not rhs["source_expression"]:
        raise ReporterError("add rhs source_expression is missing")

    control = require_dict(contract.get("control_flow"), "control_flow")
    if set(control) != {
        "kind", "sentinel_local", "initial_value", "body_first_assignment",
        "continue_target", "unreachable_return", "terminal_return",
    }:
        raise ReporterError("control_flow shape drifted")
    require_identifier(control.get("sentinel_local"), "control_flow.sentinel_local")
    if control != {
        "kind": "single_iteration_while_continue",
        "sentinel_local": control["sentinel_local"],
        "initial_value": True,
        "body_first_assignment": False,
        "continue_target": "current_while",
        "unreachable_return": False,
        "terminal_return": True,
    }:
        raise ReporterError("control_flow semantics drifted")
    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or result.get("value") is not True:
        raise ReporterError("return must bind terminal true")

    pointer = require_dict(spec.get("c_boundary", {}).get("pointer_contract"), "pointer_contract")
    expected_pair = {tuple(sorted((source_name, owner_name)))}
    declared = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    boundary = noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required")
    if pointer.get("aliasing_proven") is not True or declared != expected_pair or boundary != expected_pair:
        raise ReporterError("noalias must be the exact source-owner pair")
    if alias in {root for pair in declared for root in pair}:
        raise ReporterError("projection alias cannot enter noalias roots")
    validate_signature(spec, entries)
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
        str(contract["reset_state"]["fixture_field"]),
        str(contract["add_state"]["fixture_field"]),
    ]


def projection_record_at(initializer: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    current = initializer
    for component in path:
        match = next((item for item in current["fields"] if item.get("name") == component), None)
        if not isinstance(match, dict) or not isinstance(match.get("record"), dict):
            raise ReporterError("projection path must select initialized nested records")
        current = match["record"]
    return current


def validate_signature(spec: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    signatures = spec.get("c_boundary", {}).get("signatures") or []
    matches = [item for item in signatures if item.get("function") == spec.get("function_name")]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("reset-add entry signature drifted")
    actual = matches[0].get("parameters") or []
    if [item.get("name") for item in actual] != [item["parameter"] for item in entries]:
        raise ReporterError("reset-add entry parameter order drifted")
    if [normalize_c_type(item.get("c_type")) for item in actual] != [
        normalize_c_type(item["c_type"]) for item in entries
    ] or [item.get("direction") for item in actual] != [item["direction"] for item in entries]:
        raise ReporterError("reset-add entry parameter boundary drifted")
