from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .record_contract import (
    field_path,
    initializer_fixture_paths,
    normalize_c_type,
    require_dict,
    require_identifier,
    require_u32,
    validate_initializer,
)


KIND = "scripted_external_u32_call_interior_reset_add_while_continue_state"
ARGUMENT_MODES = ("entry_root", "entry_local_copy", "owner_interior_alias")


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1 or set(contract) != {
        "schema_version", "kind", "entry_arguments", "owner_parameter", "projection",
        "external_callee", "comparison", "assigned_state", "add_state", "control_flow",
        "return", "noalias_required",
    }:
        raise ReporterError("call-continue replay contract shape drifted")
    entries = _entries(contract)
    by_name = {entry["parameter"]: entry for entry in entries}
    owner = require_identifier(contract.get("owner_parameter"), "owner_parameter")
    if owner != entries[2]["parameter"]:
        raise ReporterError("owner_parameter must bind the third mutable entry")
    projection = _projection(contract, entries[2])
    external = _external(contract, entries, projection)
    _comparison(contract)
    assigned_path = _assigned_state(contract, entries[2], projection)
    _add_state(contract, entries[0], entries[2], assigned_path)
    _control_flow(contract)
    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type"} or result.get("rust_type") != "bool":
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    _strict_noalias(spec, contract, entries, projection)
    _signature(spec, entries)
    fields = behavior_fields(contract)
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    if (fixture.get("observable_outputs") or fixture.get("behavior_fields")) != fields:
        raise ReporterError("observable output mapping drifted")
    fixture_inputs = [
        field for entry in entries for field, _ in initializer_fixture_paths(entry["initializer"])
    ] + [external["return_fixture_field"]]
    if len([*fixture_inputs, *fields]) != len(set([*fixture_inputs, *fields])):
        raise ReporterError("fixture and output fields must be unique")
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    external = contract["external_callee"]
    return [
        str(contract["return"]["fixture_field"]),
        str(external["call_count_output"]),
        *(str(item["snapshot_output"]) for item in external["arguments"]),
        str(contract["assigned_state"]["fixture_field"]),
        str(contract["add_state"]["fixture_field"]),
    ]


def _entries(contract: dict[str, Any]) -> list[dict[str, Any]]:
    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or len(entries) != 3:
        raise ReporterError("call-continue replay requires exactly three entry arguments")
    expected = (("mutable_ref", "inout"), ("value", "input"), ("mutable_ref", "inout"))
    names: set[str] = set()
    for index, (entry, modes) in enumerate(zip(entries, expected, strict=True)):
        entry = require_dict(entry, f"entry_arguments[{index}]")
        if set(entry) != {"parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer"}:
            raise ReporterError(f"entry_arguments[{index}] shape drifted")
        name = require_identifier(entry.get("parameter"), f"entry_arguments[{index}].parameter")
        rust_type = require_identifier(entry.get("rust_type"), f"entry_arguments[{index}].rust_type")
        if name in names or (entry.get("pass_mode"), entry.get("direction")) != modes:
            raise ReporterError("entry argument order or modes drifted")
        names.add(name)
        expected_c = f"struct {rust_type} *" if modes[0] == "mutable_ref" else f"struct {rust_type}"
        if normalize_c_type(entry.get("c_type")) != normalize_c_type(expected_c):
            raise ReporterError(f"entry_arguments[{index}].c_type drifted")
        validate_initializer(entry.get("initializer"), f"entry_arguments[{index}].initializer")
        if entry["initializer"]["record_type"] != rust_type:
            raise ReporterError(f"entry_arguments[{index}] initializer type drifted")
    return entries


def _projection(contract: dict[str, Any], owner: dict[str, Any]) -> dict[str, Any]:
    value = require_dict(contract.get("projection"), "projection")
    if set(value) != {"path", "alias_local", "alias_c_pointer_type", "alias_rust_type"}:
        raise ReporterError("projection shape drifted")
    path = field_path(value.get("path"), "projection.path")
    alias = require_identifier(value.get("alias_local"), "projection.alias_local")
    require_identifier(value.get("alias_c_pointer_type"), "projection.alias_c_pointer_type")
    alias_type = require_identifier(value.get("alias_rust_type"), "projection.alias_rust_type")
    current = owner["initializer"]
    for component in path:
        item = next((field for field in current["fields"] if field.get("name") == component), None)
        if not isinstance(item, dict) or not isinstance(item.get("record"), dict):
            raise ReporterError("projection must select initialized nested records")
        current = item["record"]
    if current.get("record_type") != alias_type or alias in {
        str(item["parameter"]) for item in contract["entry_arguments"]
    }:
        raise ReporterError("projection alias drifted or became an entry root")
    return value


def _external(
    contract: dict[str, Any], entries: list[dict[str, Any]], projection: dict[str, Any]
) -> dict[str, Any]:
    value = require_dict(contract.get("external_callee"), "external_callee")
    if set(value) != {"name", "return_fixture_field", "call_count_output", "arguments"}:
        raise ReporterError("external_callee shape drifted")
    for key in ("name", "return_fixture_field", "call_count_output"):
        require_identifier(value.get(key), f"external_callee.{key}")
    args = value.get("arguments")
    if not isinstance(args, list) or len(args) != 3:
        raise ReporterError("external_callee requires three ordered arguments")
    for index, (arg, mode, entry) in enumerate(zip(args, ARGUMENT_MODES, entries, strict=True)):
        arg = require_dict(arg, f"external_callee.arguments[{index}]")
        if set(arg) != {"mode", "entry_parameter", "callee_parameter", "snapshot_field_path", "snapshot_output"}:
            raise ReporterError(f"external_callee.arguments[{index}] shape drifted")
        if arg.get("mode") != mode or arg.get("entry_parameter") != entry["parameter"]:
            raise ReporterError("external callee ordered argument binding drifted")
        require_identifier(arg.get("callee_parameter"), f"external_callee.arguments[{index}].callee_parameter")
        require_identifier(arg.get("snapshot_output"), f"external_callee.arguments[{index}].snapshot_output")
        path = field_path(arg.get("snapshot_field_path"), f"external_callee.arguments[{index}].snapshot_field_path")
        initializer = entry["initializer"]
        if mode == "owner_interior_alias":
            expected = tuple(projection["path"]) + path
        else:
            expected = path
        if expected not in dict(initializer_fixture_paths(initializer)).values():
            raise ReporterError("external callee snapshot path is not initialized")
    return value


def _comparison(contract: dict[str, Any]) -> None:
    value = require_dict(contract.get("comparison"), "comparison")
    if set(value) != {"operation", "rust_type", "sentinel"} or value.get("operation") != "eq":
        raise ReporterError("comparison must be exact u32 equality")
    if value.get("rust_type") != "u32":
        raise ReporterError("comparison must use u32")
    require_u32(value.get("sentinel"), "comparison.sentinel")


def _assigned_state(
    contract: dict[str, Any], owner: dict[str, Any], projection: dict[str, Any]
) -> tuple[str, ...]:
    value = require_dict(contract.get("assigned_state"), "assigned_state")
    if set(value) != {"alias_field_path", "owner_field_path", "fixture_field", "rust_type"}:
        raise ReporterError("assigned_state shape drifted")
    alias_path = field_path(value.get("alias_field_path"), "assigned_state.alias_field_path")
    owner_path = field_path(value.get("owner_field_path"), "assigned_state.owner_field_path")
    if owner_path != tuple(projection["path"]) + alias_path or value.get("rust_type") != "u32":
        raise ReporterError("assigned_state must bind the owner interior alias")
    require_identifier(value.get("fixture_field"), "assigned_state.fixture_field")
    if owner_path not in dict(initializer_fixture_paths(owner["initializer"])).values():
        raise ReporterError("assigned_state path is not initialized")
    return owner_path


def _add_state(
    contract: dict[str, Any], db: dict[str, Any], owner: dict[str, Any], assigned: tuple[str, ...]
) -> None:
    value = require_dict(contract.get("add_state"), "add_state")
    if set(value) != {"owner_field_path", "fixture_field", "rust_type", "operation", "rhs"}:
        raise ReporterError("add_state shape drifted")
    path = field_path(value.get("owner_field_path"), "add_state.owner_field_path")
    if path == assigned or path not in dict(initializer_fixture_paths(owner["initializer"])).values():
        raise ReporterError("add_state owner path drifted")
    require_identifier(value.get("fixture_field"), "add_state.fixture_field")
    rhs = require_dict(value.get("rhs"), "add_state.rhs")
    if value.get("rust_type") != "u32" or value.get("operation") != "wrapping_add" or set(rhs) != {
        "mode", "parameter", "field_path", "source_expression"
    }:
        raise ReporterError("add_state must declare u32 wrapping_add")
    rhs_path = field_path(rhs.get("field_path"), "add_state.rhs.field_path")
    if rhs.get("mode") != "direct_record_u32_field" or rhs.get("parameter") != db["parameter"]:
        raise ReporterError("add rhs must bind the first entry root")
    if rhs_path not in dict(initializer_fixture_paths(db["initializer"])).values():
        raise ReporterError("add rhs path is not initialized")
    if not isinstance(rhs.get("source_expression"), str) or not rhs["source_expression"]:
        raise ReporterError("add rhs source_expression is missing")


def _control_flow(contract: dict[str, Any]) -> None:
    value = require_dict(contract.get("control_flow"), "control_flow")
    if set(value) != {"kind", "sentinel_local", "initial_value", "body_first_assignment", "hit_reset_value", "continue_target", "miss_return", "terminal_return"}:
        raise ReporterError("control_flow shape drifted")
    require_identifier(value.get("sentinel_local"), "control_flow.sentinel_local")
    if value != {"kind": "single_iteration_while_call_compare_continue", "sentinel_local": value["sentinel_local"], "initial_value": True, "body_first_assignment": False, "hit_reset_value": 0, "continue_target": "current_while", "miss_return": False, "terminal_return": True}:
        raise ReporterError("control_flow semantics drifted")


def _strict_noalias(
    spec: dict[str, Any], contract: dict[str, Any], entries: list[dict[str, Any]], projection: dict[str, Any]
) -> None:
    expected = [[entries[0]["parameter"], entries[2]["parameter"]]]
    pointer = require_dict(spec.get("c_boundary", {}).get("pointer_contract"), "pointer_contract")
    if pointer.get("aliasing_proven") is not True or contract.get("noalias_required") != expected:
        raise ReporterError("noalias must be the exact ordered db-to-owner policy")
    if pointer.get("noalias_required") != expected:
        raise ReporterError("pointer noalias must preserve ordered db-to-owner policy")
    alias = projection["alias_local"]
    if any(alias in pair for pair in expected):
        raise ReporterError("projection alias cannot become a noalias root")


def _signature(spec: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    signatures = spec.get("c_boundary", {}).get("signatures") or []
    matches = [item for item in signatures if item.get("function") == spec.get("function_name")]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("carrier signature drifted")
    actual = matches[0].get("parameters") or []
    if [(item.get("name"), normalize_c_type(item.get("c_type")), item.get("direction")) for item in actual] != [(item["parameter"], normalize_c_type(item["c_type"]), item["direction"]) for item in entries]:
        raise ReporterError("carrier parameter boundary drifted")
