from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .record_contract import (
    field_path,
    initializer_fixture_paths,
    normalize_c_type,
    require_dict,
    require_identifier,
    validate_initializer,
)
from .sequence_contract_validation import (
    initializer_record_type,
    validate_noalias,
    validate_signatures,
)


KIND = "scripted_external_record_u32_sequence_do_while_state"
U32_MAX = (1 << 32) - 1


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    schema_version = contract.get("schema_version")
    if schema_version not in {1, 2}:
        raise ReporterError("sequence replay contract schema_version must be 1 or 2")
    required_fields = {
        "schema_version",
        "kind",
        "external_callee",
        "entry_arguments",
        "state_output",
        "loop",
        "return",
        "noalias_required",
    }
    if set(contract) not in {frozenset(required_fields), frozenset((*required_fields, "body_callee"))}:
        raise ReporterError("sequence replay contract shape drifted")
    if "body_callee" in contract and schema_version != 2:
        raise ReporterError("sequence replay body_callee requires schema_version 2")

    entries = contract.get("entry_arguments")
    if not isinstance(entries, list) or not entries:
        raise ReporterError("sequence replay entry arguments are missing")
    entry_by_name: dict[str, dict[str, Any]] = {}
    fixture_fields: list[str] = []
    for index, raw_entry in enumerate(entries):
        entry = require_dict(raw_entry, f"entry_arguments[{index}]")
        if set(entry) != {
            "parameter",
            "c_type",
            "rust_type",
            "pass_mode",
            "direction",
            "initializer",
        }:
            raise ReporterError(f"entry_arguments[{index}] shape drifted")
        parameter = require_identifier(entry.get("parameter"), f"entry_arguments[{index}].parameter")
        rust_type = require_identifier(entry.get("rust_type"), f"entry_arguments[{index}].rust_type")
        if entry.get("pass_mode") not in {"mutable_ref", "value"}:
            raise ReporterError(f"entry_arguments[{index}].pass_mode is unsupported")
        if entry.get("direction") not in {"input", "inout"}:
            raise ReporterError(f"entry_arguments[{index}].direction is unsupported")
        expected_c_type = (
            f"struct {rust_type} *" if entry["pass_mode"] == "mutable_ref" else f"struct {rust_type}"
        )
        if normalize_c_type(entry.get("c_type")) != normalize_c_type(expected_c_type):
            raise ReporterError(f"entry_arguments[{index}].c_type drifted")
        if parameter in entry_by_name:
            raise ReporterError("entry argument parameters must be unique")
        validate_initializer(entry.get("initializer"), f"entry_arguments[{index}].initializer")
        if entry["initializer"]["record_type"] != rust_type:
            raise ReporterError(f"entry_arguments[{index}] initializer type drifted")
        fixture_fields.extend(field for field, _ in initializer_fixture_paths(entry["initializer"]))
        entry_by_name[parameter] = entry

    external = require_dict(contract.get("external_callee"), "external_callee")
    if set(external) != {
        "name",
        "return_sequence_fixture_field",
        "call_count_output",
        "call_args_output",
        "arguments",
    }:
        raise ReporterError("external_callee shape drifted")
    for key in (
        "name",
        "return_sequence_fixture_field",
        "call_count_output",
        "call_args_output",
    ):
        require_identifier(external.get(key), f"external_callee.{key}")
    owner_alias_state_keys = validate_observations(
        external.get("arguments"),
        label="external_callee.arguments",
        schema_version=schema_version,
        entry_by_name=entry_by_name,
    )

    if schema_version == 2 and len(owner_alias_state_keys) != 1:
        raise ReporterError(
            "sequence replay schema_version 2 requires exactly one owner interior alias"
        )

    body = contract.get("body_callee")
    if body is not None:
        body = require_dict(body, "body_callee")
        if set(body) != {
            "name",
            "return_value",
            "call_count_output",
            "call_args_output",
            "call_order_output",
            "event_id",
            "tail_event_id",
            "arguments",
        }:
            raise ReporterError("body_callee shape drifted")
        for key in ("name", "call_count_output", "call_args_output", "call_order_output"):
            require_identifier(body.get(key), f"body_callee.{key}")
        if body["name"] == external["name"]:
            raise ReporterError("body and sequence callees must differ")
        return_value = body.get("return_value")
        if type(return_value) is not int or not -(1 << 31) <= return_value < (1 << 31):
            raise ReporterError("body_callee.return_value must be an i32 integer")
        for key in ("event_id", "tail_event_id"):
            value = body.get(key)
            if type(value) is not int or not 0 <= value <= U32_MAX:
                raise ReporterError(f"body_callee.{key} must be a u32 integer")
        if body["event_id"] == body["tail_event_id"]:
            raise ReporterError("body_callee event ids must be unique")
        validate_observations(
            body.get("arguments"),
            label="body_callee.arguments",
            schema_version=schema_version,
            entry_by_name=entry_by_name,
        )

    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {"parameter", "field_path", "fixture_field", "rust_type"}:
        raise ReporterError("state_output shape drifted")
    state_parameter = require_identifier(state.get("parameter"), "state_output.parameter")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    state_path = field_path(state.get("field_path"), "state_output.field_path")
    state_entry = entry_by_name.get(state_parameter)
    if state.get("rust_type") != "u32" or state_entry is None or state_entry.get("pass_mode") != "mutable_ref":
        raise ReporterError("state_output must bind a mutable u32 entry field")
    if state_path not in dict(initializer_fixture_paths(state_entry["initializer"])).values():
        raise ReporterError("state_output.field_path is not initialized")
    if any(
        (state_parameter, state_path) != owner_alias_state_key
        for owner_alias_state_key in owner_alias_state_keys
    ):
        raise ReporterError("state_output does not match owner interior alias")

    loop = require_dict(contract.get("loop"), "loop")
    if set(loop) != {"sentinel", "comparison", "max_calls"}:
        raise ReporterError("loop shape drifted")
    if isinstance(loop.get("sentinel"), bool) or not isinstance(loop.get("sentinel"), int) or not 0 <= loop["sentinel"] <= U32_MAX:
        raise ReporterError("loop.sentinel must be a u32 integer")
    if loop.get("comparison") != "not_equal":
        raise ReporterError("loop.comparison must be not_equal")
    if type(loop.get("max_calls")) is not int or not 1 <= loop["max_calls"] <= 1024:
        raise ReporterError("loop.max_calls must be between 1 and 1024")

    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or type(result.get("value")) is not bool:
        raise ReporterError("return must declare a bool value")

    validate_noalias(spec, contract, entry_by_name)
    validate_signatures(spec, contract, entry_by_name)
    output_fields = behavior_fields(contract)
    all_fields = [
        *fixture_fields,
        str(external["return_sequence_fixture_field"]),
        *output_fields,
    ]
    if len(all_fields) != len(set(all_fields)):
        raise ReporterError("fixture and output fields must be unique")
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    if (fixture.get("observable_outputs") or fixture.get("behavior_fields")) != output_fields:
        raise ReporterError("observable output mapping drifted")
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    external = contract["external_callee"]
    prefix = [
        str(contract["return"]["fixture_field"]),
        str(contract["state_output"]["fixture_field"]),
    ]
    body = contract.get("body_callee")
    if isinstance(body, dict):
        return [
            *prefix,
            str(body["call_count_output"]),
            str(body["call_args_output"]),
            str(external["call_count_output"]),
            str(external["call_args_output"]),
            str(body["call_order_output"]),
        ]
    return [
        *prefix,
        str(external["call_count_output"]),
        str(external["call_args_output"]),
    ]


def validate_observations(
    raw_observations: Any,
    *,
    label: str,
    schema_version: int,
    entry_by_name: dict[str, dict[str, Any]],
) -> list[tuple[str, tuple[str, ...]]]:
    if not isinstance(raw_observations, list) or not raw_observations:
        raise ReporterError(f"{label} are missing")
    names: set[str] = set()
    owner_alias_state_keys: list[tuple[str, tuple[str, ...]]] = []
    for index, raw_observation in enumerate(raw_observations):
        item_label = f"{label}[{index}]"
        observation = require_dict(raw_observation, item_label)
        mode = observation.get("mode")
        supported_modes = {"record_ref", "scalar_field_value"}
        if schema_version == 2:
            supported_modes.add("owner_interior_alias")
        if mode not in supported_modes:
            raise ReporterError(f"{item_label}.mode is unsupported")
        expected_shape = {"parameter", "mode", "entry_parameter", "field_path"}
        if mode == "owner_interior_alias":
            expected_shape.update({"projection_path", "alias_local"})
        if set(observation) != expected_shape:
            raise ReporterError(f"{item_label} shape drifted")
        name = require_identifier(observation.get("parameter"), f"{item_label}.parameter")
        entry_name = require_identifier(
            observation.get("entry_parameter"), f"{item_label}.entry_parameter"
        )
        if name in names or entry_name not in entry_by_name:
            raise ReporterError(f"{item_label} binding drifted")
        names.add(name)
        path = field_path(observation.get("field_path"), f"{item_label}.field_path")
        combined_path = path
        if mode == "owner_interior_alias":
            require_identifier(observation.get("alias_local"), f"{item_label}.alias_local")
            owner_entry = entry_by_name[entry_name]
            if owner_entry["pass_mode"] != "mutable_ref":
                raise ReporterError(f"{item_label} owner entry must use mutable_ref")
            projection_path = field_path(
                observation.get("projection_path"), f"{item_label}.projection_path"
            )
            initializer_record_type(owner_entry["initializer"], projection_path, f"{item_label}.projection_path")
            combined_path = (*projection_path, *path)
            owner_alias_state_keys.append((entry_name, combined_path))
        initialized_paths = {
            initialized_path
            for _, initialized_path in initializer_fixture_paths(
                entry_by_name[entry_name]["initializer"]
            )
        }
        if combined_path not in initialized_paths:
            raise ReporterError(f"{item_label} field path is not initialized")
    return owner_alias_state_keys
