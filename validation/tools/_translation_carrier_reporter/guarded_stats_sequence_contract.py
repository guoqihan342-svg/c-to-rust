from __future__ import annotations

import copy
from typing import Any

from .errors import ReporterError
from .owner_interior_usize_add_contract import initializer_fixture_paths
from .record_contract import field_path, require_dict, require_identifier
from .stats_sequence_contract import (
    KIND as UNGUARDED_KIND,
    behavior_fields,
    parse_contract as parse_unguarded_contract,
)


KIND = "record_owner_interior_guarded_stats_sequence_state"


def parse_contract(spec: dict[str, Any]) -> dict[str, Any]:
    contract = require_dict(spec.get("replay_contract"), "replay_contract")
    if contract.get("kind") != KIND:
        raise ReporterError(f"replay_contract.kind must be {KIND}")
    if contract.get("schema_version") != 1:
        raise ReporterError("guarded owner interior stats sequence schema_version must be 1")
    if set(contract) != {
        "schema_version",
        "kind",
        "owner",
        "projection_path",
        "alias",
        "guard",
        "updates",
        "return",
        "noalias_required",
    }:
        raise ReporterError("guarded owner interior stats sequence contract shape drifted")

    unguarded_spec = copy.deepcopy(spec)
    unguarded_contract = copy.deepcopy(contract)
    unguarded_contract.pop("guard")
    unguarded_contract["kind"] = UNGUARDED_KIND
    unguarded_spec["replay_contract"] = unguarded_contract
    parse_unguarded_contract(unguarded_spec)

    _validate_guard(contract)
    _validate_fixture_fields(spec, contract)
    return contract


def _validate_guard(contract: dict[str, Any]) -> None:
    guard = require_dict(contract.get("guard"), "guard")
    if set(guard) != {"operator", "predicates", "false_path"}:
        raise ReporterError("guard shape drifted")
    if guard.get("operator") != "short_circuit_and":
        raise ReporterError("guard operator must be short_circuit_and")
    predicates = guard.get("predicates")
    if not isinstance(predicates, list) or len(predicates) != 2:
        raise ReporterError("guard must contain exactly two ordered equality predicates")

    projection = field_path(contract.get("projection_path"), "projection_path")
    initialized = {
        path: (fixture, rust_type)
        for fixture, path, rust_type in initializer_fixture_paths(
            contract["owner"]["initializer"]
        )
    }
    predicate_paths: list[tuple[str, ...]] = []
    expected_types = ("u32", "bool")
    for index, (raw_predicate, expected_type) in enumerate(
        zip(predicates, expected_types, strict=True)
    ):
        predicate = require_dict(raw_predicate, f"guard.predicates[{index}]")
        if set(predicate) != {"operation", "lhs", "rhs"}:
            raise ReporterError(f"guard.predicates[{index}] shape drifted")
        if predicate.get("operation") != "equality":
            raise ReporterError(f"guard.predicates[{index}] must declare equality")
        lhs = require_dict(predicate.get("lhs"), f"guard.predicates[{index}].lhs")
        if set(lhs) != {
            "alias_field_path",
            "owner_field_path",
            "rust_type",
            "mode",
        }:
            raise ReporterError(f"guard.predicates[{index}].lhs shape drifted")
        alias_path = field_path(
            lhs.get("alias_field_path"),
            f"guard.predicates[{index}].lhs.alias_field_path",
        )
        owner_path = field_path(
            lhs.get("owner_field_path"),
            f"guard.predicates[{index}].lhs.owner_field_path",
        )
        if (
            len(alias_path) != 1
            or owner_path != projection + alias_path
            or lhs.get("rust_type") != expected_type
            or lhs.get("mode") != "direct_field_value"
            or initialized.get(owner_path, (None, None))[1] != expected_type
        ):
            raise ReporterError(
                f"guard.predicates[{index}] lhs must bind one direct alias {expected_type} field"
            )
        predicate_paths.append(owner_path)

        rhs = require_dict(predicate.get("rhs"), f"guard.predicates[{index}].rhs")
        if set(rhs) != {"kind", "c_expression", "rust_type", "value"}:
            raise ReporterError(f"guard.predicates[{index}].rhs shape drifted")
        if rhs.get("kind") != "constant" or rhs.get("rust_type") != expected_type:
            raise ReporterError(
                f"guard.predicates[{index}] rhs must be a {expected_type} constant"
            )
        if expected_type == "u32":
            require_identifier(rhs.get("c_expression"), "guard.predicates[0].rhs.c_expression")
            value = rhs.get("value")
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 1 << 32:
                raise ReporterError("guard.predicates[0].rhs.value must be u32")
        elif rhs.get("c_expression") != "true" or rhs.get("value") is not True:
            raise ReporterError("guard.predicates[1].rhs must declare bool true")

    if len(set(predicate_paths)) != 2:
        raise ReporterError("guard predicate fields must be distinct")
    update_paths = {
        tuple(update["target"]["owner_field_path"]) for update in contract["updates"]
    } | {
        tuple(update["source"]["owner_field_path"])
        for update in contract["updates"][1:]
    }
    if set(predicate_paths) & update_paths:
        raise ReporterError("guard predicate fields must be distinct from update fields")

    false_path = require_dict(guard.get("false_path"), "guard.false_path")
    if set(false_path) != {"return_value", "state_effect"}:
        raise ReporterError("guard false_path shape drifted")
    if false_path.get("return_value") is not False or false_path.get("state_effect") != "none":
        raise ReporterError("guard false path must return false with no state effect")


def _validate_fixture_fields(spec: dict[str, Any], contract: dict[str, Any]) -> None:
    fixtures = [
        field
        for field, _, _ in initializer_fixture_paths(contract["owner"]["initializer"])
    ]
    outputs = behavior_fields(contract)
    if len([*fixtures, *outputs]) != len(set([*fixtures, *outputs])):
        raise ReporterError("guarded stats fixture and output fields must be unique")
    fixture = require_dict(spec.get("fixture_contract"), "fixture_contract")
    if (fixture.get("observable_outputs") or fixture.get("behavior_fields")) != outputs:
        raise ReporterError("guarded stats observable output mapping drifted")


def rust_guard_expression(contract: dict[str, Any], root: str) -> str:
    expressions: list[str] = []
    for predicate in contract["guard"]["predicates"]:
        lhs = f"{root}." + ".".join(predicate["lhs"]["owner_field_path"])
        rhs = predicate["rhs"]
        value = str(rhs["value"]).lower() if rhs["rust_type"] == "bool" else f"{rhs['value']}u32"
        expressions.append(f"{lhs} == {value}")
    return " && ".join(expressions)


def c_guard_expression(contract: dict[str, Any], root: str) -> str:
    expressions: list[str] = []
    for predicate in contract["guard"]["predicates"]:
        lhs = f"{root}." + ".".join(predicate["lhs"]["owner_field_path"])
        expressions.append(f"{lhs} == {predicate['rhs']['c_expression']}")
    return " && ".join(expressions)
