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


KIND = "record_u32_field_scalar_wrapping_add_state"


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("record field scalar-add schema_version must be 1")
    if set(contract) != {
        "schema_version", "kind", "entry_arguments", "state_output", "state_update",
        "return", "noalias_required",
    }:
        raise ReporterError("record field scalar-add contract shape drifted")

    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or len(entries) != 3:
        raise ReporterError("record field scalar-add requires exactly three entry arguments")
    records: dict[str, dict[str, Any]] = {}
    scalar: dict[str, Any] | None = None
    mutable: dict[str, Any] | None = None
    value_record: dict[str, Any] | None = None
    fixture_fields: list[str] = []
    for index, raw_entry in enumerate(entries):
        entry = require_dict(raw_entry, f"entry_arguments[{index}]")
        parameter = require_identifier(entry.get("parameter"), f"entry_arguments[{index}].parameter")
        if parameter in records or (scalar and parameter == scalar["parameter"]):
            raise ReporterError("entry argument parameters must be unique")
        if set(entry) == {
            "parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer",
        }:
            rust_type = require_identifier(entry.get("rust_type"), f"entry_arguments[{index}].rust_type")
            validate_initializer(entry.get("initializer"), f"entry_arguments[{index}].initializer")
            if entry["initializer"]["record_type"] != rust_type:
                raise ReporterError(f"entry_arguments[{index}] initializer type drifted")
            fixture_fields.extend(field for field, _ in initializer_fixture_paths(entry["initializer"]))
            if entry.get("pass_mode") == "mutable_ref":
                if mutable is not None or entry.get("direction") != "inout":
                    raise ReporterError("record field scalar-add requires one mutable inout record")
                expected_c_type = f"struct {rust_type} *"
                mutable = entry
            elif entry.get("pass_mode") == "value":
                if value_record is not None or entry.get("direction") != "input":
                    raise ReporterError("record field scalar-add requires one by-value input record")
                expected_c_type = f"struct {rust_type}"
                value_record = entry
            else:
                raise ReporterError("record field scalar-add record pass_mode is unsupported")
            if normalize_c_type(entry.get("c_type")) != normalize_c_type(expected_c_type):
                raise ReporterError(f"entry_arguments[{index}].c_type drifted")
            records[parameter] = entry
        elif set(entry) == {
            "parameter", "c_type", "rust_type", "pass_mode", "direction", "fixture_field",
        }:
            if scalar is not None:
                raise ReporterError("record field scalar-add requires one scalar entry")
            require_identifier(entry.get("fixture_field"), f"entry_arguments[{index}].fixture_field")
            if (
                normalize_c_type(entry.get("c_type")) != "uint32_t"
                or entry.get("rust_type") != "u32"
                or entry.get("pass_mode") != "value"
                or entry.get("direction") != "input"
            ):
                raise ReporterError("record field scalar-add scalar entry must be by-value u32")
            scalar = entry
            fixture_fields.append(str(entry["fixture_field"]))
        else:
            raise ReporterError(f"entry_arguments[{index}] shape drifted")
    if mutable is None or value_record is None or scalar is None:
        raise ReporterError("record field scalar-add entry role set is incomplete")

    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {"parameter", "field_path", "fixture_field", "rust_type"}:
        raise ReporterError("state_output shape drifted")
    state_parameter = require_identifier(state.get("parameter"), "state_output.parameter")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    state_path = field_path(state.get("field_path"), "state_output.field_path")
    if state.get("rust_type") != "u32" or len(state_path) < 2:
        raise ReporterError("state_output must bind a nested u32 field")
    if state_parameter != mutable["parameter"] or state_path not in dict(
        initializer_fixture_paths(mutable["initializer"])
    ).values():
        raise ReporterError("state_output target is not initialized")

    update = require_dict(contract.get("state_update"), "state_update")
    if set(update) != {"operation", "record_field", "scalar"}:
        raise ReporterError("state_update shape drifted")
    if update.get("operation") != "wrapping_add":
        raise ReporterError("state_update.operation must be wrapping_add")
    source = require_dict(update.get("record_field"), "state_update.record_field")
    if set(source) != {"parameter", "field_path", "rust_type", "mode"}:
        raise ReporterError("state_update.record_field shape drifted")
    source_parameter = require_identifier(source.get("parameter"), "state_update.record_field.parameter")
    source_path = field_path(source.get("field_path"), "state_update.record_field.field_path")
    if (
        source_parameter != value_record["parameter"]
        or source.get("rust_type") != "u32"
        or source.get("mode") != "direct_field_value"
        or len(source_path) != 1
        or source_path not in dict(initializer_fixture_paths(value_record["initializer"])).values()
    ):
        raise ReporterError("record_field must bind one direct initialized u32 field")
    scalar_binding = require_dict(update.get("scalar"), "state_update.scalar")
    if set(scalar_binding) != {"parameter", "fixture_field", "rust_type", "mode"}:
        raise ReporterError("state_update.scalar shape drifted")
    if (
        scalar_binding.get("parameter") != scalar["parameter"]
        or scalar_binding.get("fixture_field") != scalar["fixture_field"]
        or scalar_binding.get("rust_type") != "u32"
        or scalar_binding.get("mode") != "scalar_value"
    ):
        raise ReporterError("state_update.scalar binding drifted")

    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or type(result.get("value")) is not bool:
        raise ReporterError("return must declare a bool constant")

    validate_noalias(spec, contract)
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


def validate_noalias(spec: dict[str, Any], contract: dict[str, Any]) -> None:
    declared = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    pointer = require_dict(
        spec.get("c_boundary", {}).get("pointer_contract"), "c_boundary.pointer_contract"
    )
    boundary = noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required")
    if pointer.get("aliasing_proven") is not True:
        raise ReporterError("pointer aliasing metadata is not proven")
    if declared or boundary or declared != boundary:
        raise ReporterError("unique pointer root requires empty noalias pairs")


def validate_signature(spec: dict[str, Any], contract: dict[str, Any]) -> None:
    signatures = spec.get("c_boundary", {}).get("signatures")
    matches = [
        item for item in signatures or []
        if isinstance(item, dict) and item.get("function") == spec.get("function_name")
    ]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("record field scalar-add entry signature drifted")
    actual = [item for item in matches[0].get("parameters", []) if isinstance(item, dict)]
    entries = contract["entry_arguments"]
    if [item.get("name") for item in actual] != [item["parameter"] for item in entries]:
        raise ReporterError("record field scalar-add entry parameters drifted")
    if [normalize_c_type(item.get("c_type")) for item in actual] != [
        normalize_c_type(item["c_type"]) for item in entries
    ]:
        raise ReporterError("record field scalar-add entry parameter types drifted")
    if [item.get("direction") for item in actual] != [item["direction"] for item in entries]:
        raise ReporterError("record field scalar-add entry directions drifted")
