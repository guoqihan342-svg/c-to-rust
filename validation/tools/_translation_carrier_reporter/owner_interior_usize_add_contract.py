from __future__ import annotations

from typing import Any

from .errors import ReporterError
from .record_contract import (
    field_path,
    noalias_pairs,
    normalize_c_type,
    require_dict,
    require_identifier,
    require_nonempty_string,
)


KIND = "record_owner_interior_u32_to_usize_wrapping_add_state"
SCALAR_TYPES = {"u32", "usize"}


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("owner interior usize-add schema_version must be 1")
    if set(contract) != {
        "schema_version", "kind", "owner", "projection_path", "alias", "state_output",
        "rhs", "widening", "state_update", "return", "noalias_required",
    }:
        raise ReporterError("owner interior usize-add contract shape drifted")

    owner = _parse_owner(contract)
    projection_path = field_path(contract.get("projection_path"), "projection_path")
    projected = _record_at(owner["initializer"], projection_path)
    _validate_alias(contract, projected)
    _validate_state_and_rhs(contract, owner, projection_path)
    _validate_widening(spec, contract)
    _validate_return(contract)
    _validate_boundary(spec, contract, owner)
    _validate_fixture_fields(spec, contract, owner)
    return contract


def behavior_fields(contract: dict[str, Any]) -> list[str]:
    return [
        str(contract["return"]["fixture_field"]),
        str(contract["state_output"]["fixture_field"]),
    ]


def initializer_fixture_paths(
    initializer: dict[str, Any], prefix: tuple[str, ...] = ()
) -> list[tuple[str, tuple[str, ...], str]]:
    result: list[tuple[str, tuple[str, ...], str]] = []
    for field in initializer["fields"]:
        path = (*prefix, str(field["name"]))
        if "fixture_field" in field:
            result.append((str(field["fixture_field"]), path, str(field["rust_type"])))
        else:
            result.extend(initializer_fixture_paths(field["record"], path))
    return result


def rust_initializer(initializer: dict[str, Any], inputs: dict[str, Any]) -> str:
    fields: list[str] = []
    for field in initializer["fields"]:
        if "fixture_field" in field:
            rust_type = str(field["rust_type"])
            value = f"{int(inputs[str(field['fixture_field'])])}{rust_type}"
        else:
            value = rust_initializer(field["record"], inputs)
        fields.append(f"{field['name']}: {value}")
    return f"{initializer['record_type']} {{ " + ", ".join(fields) + " }"


def _parse_owner(contract: dict[str, Any]) -> dict[str, Any]:
    owner = require_dict(contract.get("owner"), "owner")
    if set(owner) != {
        "parameter", "c_type", "rust_type", "pass_mode", "direction", "initializer",
    }:
        raise ReporterError("owner interior usize-add owner shape drifted")
    owner_type = require_identifier(owner.get("rust_type"), "owner.rust_type")
    require_identifier(owner.get("parameter"), "owner.parameter")
    if owner.get("pass_mode") != "mutable_ref" or owner.get("direction") != "inout":
        raise ReporterError("owner must be one mutable inout record root")
    if normalize_c_type(owner.get("c_type")) != normalize_c_type(f"struct {owner_type} *"):
        raise ReporterError("owner C type drifted")
    _validate_initializer(owner.get("initializer"), "owner.initializer")
    if owner["initializer"]["record_type"] != owner_type:
        raise ReporterError("owner initializer type drifted")
    return owner


def _validate_initializer(value: Any, label: str) -> None:
    initializer = require_dict(value, label)
    if set(initializer) != {"record_type", "fields"}:
        raise ReporterError(f"{label} shape drifted")
    require_identifier(initializer.get("record_type"), f"{label}.record_type")
    fields = initializer.get("fields")
    if not isinstance(fields, list) or not fields:
        raise ReporterError(f"{label}.fields are missing")
    names: set[str] = set()
    for index, raw_field in enumerate(fields):
        field = require_dict(raw_field, f"{label}.fields[{index}]")
        name = require_identifier(field.get("name"), f"{label}.fields[{index}].name")
        if name in names:
            raise ReporterError(f"{label} field names must be unique")
        names.add(name)
        if set(field) == {"name", "fixture_field", "rust_type"}:
            require_identifier(field.get("fixture_field"), f"{label}.fields[{index}].fixture_field")
            if field.get("rust_type") not in SCALAR_TYPES:
                raise ReporterError(f"{label}.fields[{index}].rust_type is unsupported")
        elif set(field) == {"name", "record"}:
            _validate_initializer(field.get("record"), f"{label}.fields[{index}].record")
        else:
            raise ReporterError(f"{label}.fields[{index}] shape drifted")


def _record_at(initializer: dict[str, Any], path: tuple[str, ...]) -> dict[str, Any]:
    current = initializer
    for component in path:
        match = next(
            (item for item in current["fields"] if item.get("name") == component), None
        )
        if not isinstance(match, dict) or not isinstance(match.get("record"), dict):
            raise ReporterError("projection_path must select initialized nested records")
        current = match["record"]
    return current


def _validate_alias(contract: dict[str, Any], projected: dict[str, Any]) -> None:
    alias = require_dict(contract.get("alias"), "alias")
    if set(alias) != {"local", "c_type", "rust_type", "pass_mode"}:
        raise ReporterError("owner interior usize-add alias shape drifted")
    require_identifier(alias.get("local"), "alias.local")
    alias_type = require_identifier(alias.get("rust_type"), "alias.rust_type")
    require_identifier(alias.get("c_type"), "alias.c_type pointer typedef")
    if (
        alias.get("pass_mode") != "mutable_ref"
        or projected["record_type"] != alias_type
    ):
        raise ReporterError("alias pointer typedef must bind the mutable projected record")


def _validate_state_and_rhs(
    contract: dict[str, Any], owner: dict[str, Any], projection_path: tuple[str, ...]
) -> None:
    initialized = {path: (field, rust_type) for field, path, rust_type in initializer_fixture_paths(owner["initializer"])}
    state = require_dict(contract.get("state_output"), "state_output")
    if set(state) != {"owner_field_path", "fixture_field", "rust_type"}:
        raise ReporterError("state_output shape drifted")
    state_path = field_path(state.get("owner_field_path"), "state_output.owner_field_path")
    require_identifier(state.get("fixture_field"), "state_output.fixture_field")
    if len(state_path) != 1 or state.get("rust_type") != "usize":
        raise ReporterError("state_output must bind one direct usize accumulator")
    if state_path[0] == projection_path[0]:
        raise ReporterError("accumulator must not overlap the projection first segment")
    if initialized.get(state_path, (None, None))[1] != "usize":
        raise ReporterError("direct usize accumulator is not initialized")

    rhs = require_dict(contract.get("rhs"), "rhs")
    if set(rhs) != {"alias_field_path", "owner_field_path", "rust_type", "mode"}:
        raise ReporterError("rhs shape drifted")
    alias_path = field_path(rhs.get("alias_field_path"), "rhs.alias_field_path")
    owner_path = field_path(rhs.get("owner_field_path"), "rhs.owner_field_path")
    if (
        len(alias_path) != 1
        or owner_path != projection_path + alias_path
        or rhs.get("rust_type") != "u32"
        or rhs.get("mode") != "direct_field_value"
        or initialized.get(owner_path, (None, None))[1] != "u32"
    ):
        raise ReporterError("rhs must bind one direct initialized u32 field in the projection")
    update = require_dict(contract.get("state_update"), "state_update")
    if set(update) != {"operation"} or update.get("operation") != "wrapping_add":
        raise ReporterError("state_update must declare wrapping_add")


def _validate_widening(spec: dict[str, Any], contract: dict[str, Any]) -> None:
    widening = require_dict(contract.get("widening"), "widening")
    if widening != {
        "conversion": "u32_to_usize",
        "source_rust_type": "u32",
        "target_rust_type": "usize",
        "source_bits": 32,
        "target_bits": 64,
        "signedness": "unsigned",
        "lossless": True,
        "target_abi_binding": "build_profile.target+c_boundary.target_abi_contract",
    }:
        raise ReporterError("widening must be ABI-bound lossless u32_to_usize on LP64")
    build_target = require_dict(spec.get("build_profile", {}).get("target"), "build_profile.target")
    boundary_target = require_dict(
        spec.get("c_boundary", {}).get("target_abi_contract"),
        "c_boundary.target_abi_contract",
    )
    for label, target in (("build_profile.target", build_target), ("target_abi_contract", boundary_target)):
        require_nonempty_string(target.get("triple_or_abi"), f"{label}.triple_or_abi")
        if (
            target.get("int_width") != 32
            or target.get("long_width") != 64
            or target.get("pointer_width") != 64
            or target.get("size_t_width") != 64
        ):
            raise ReporterError(f"{label} must bind an LP64 target ABI")
    for key in ("triple_or_abi", "int_width", "long_width", "pointer_width", "size_t_width"):
        if build_target.get(key) != boundary_target.get(key):
            raise ReporterError("target ABI bindings drifted")


def _validate_return(contract: dict[str, Any]) -> None:
    result = require_dict(contract.get("return"), "return")
    if set(result) != {"fixture_field", "rust_type", "value"}:
        raise ReporterError("return shape drifted")
    require_identifier(result.get("fixture_field"), "return.fixture_field")
    if result.get("rust_type") != "bool" or type(result.get("value")) is not bool:
        raise ReporterError("return must declare a fixed bool value")


def _validate_boundary(
    spec: dict[str, Any], contract: dict[str, Any], owner: dict[str, Any]
) -> None:
    declared = noalias_pairs(contract.get("noalias_required"), "noalias_required")
    pointer = require_dict(spec.get("c_boundary", {}).get("pointer_contract"), "pointer_contract")
    boundary = noalias_pairs(pointer.get("noalias_required"), "pointer noalias_required")
    if pointer.get("aliasing_proven") is not True or declared or boundary or declared != boundary:
        raise ReporterError("single owner root requires proven metadata and empty noalias pairs")
    signatures = spec.get("c_boundary", {}).get("signatures") or []
    matches = [item for item in signatures if isinstance(item, dict) and item.get("function") == spec.get("function_name")]
    if len(matches) != 1 or normalize_c_type(matches[0].get("return_type")) not in {"bool", "_Bool"}:
        raise ReporterError("owner interior usize-add entry signature drifted")
    actual = [item for item in matches[0].get("parameters", []) if isinstance(item, dict)]
    if len(actual) != 1:
        raise ReporterError("entry signature must expose only the owner root")
    if (
        actual[0].get("name") != owner["parameter"]
        or normalize_c_type(actual[0].get("c_type")) != normalize_c_type(owner["c_type"])
        or actual[0].get("direction") != "inout"
    ):
        raise ReporterError("owner entry parameter drifted")


def _validate_fixture_fields(
    spec: dict[str, Any], contract: dict[str, Any], owner: dict[str, Any]
) -> None:
    fixtures = [field for field, _, _ in initializer_fixture_paths(owner["initializer"])]
    outputs = behavior_fields(contract)
    if len([*fixtures, *outputs]) != len(set([*fixtures, *outputs])):
        raise ReporterError("fixture and output fields must be unique")
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    if (fixture.get("observable_outputs") or fixture.get("behavior_fields")) != outputs:
        raise ReporterError("observable output mapping drifted")
