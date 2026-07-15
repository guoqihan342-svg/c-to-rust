from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .c2rust_project_baseline_target_export_unit import (
    project_unit_export_inventory,
)


ARTIFACT_KIND = "c2rust-target-scoped-export-inventory"
CONFLICT_CODE = "c2rust_target_export_conflict"
UNAVAILABLE_CODE = "c2rust_target_export_inventory_unavailable"


def project_target_scoped_exports(
    terminal_target_plan: Mapping[str, Any],
    generated_trees: Mapping[str, Mapping[str, str | bytes]],
    unit_identities: Mapping[str, Any],
) -> dict[str, Any]:
    plan = _json_object(terminal_target_plan, "target_plan_invalid")
    _scopes, required_units = _terminal_scopes(plan)
    trees = _unit_mapping(generated_trees, "generated_trees_invalid")
    identities = _unit_mapping(unit_identities, "unit_identities_invalid")
    if set(trees) != required_units or set(identities) != required_units:
        _fail("unit_coverage_invalid")
    inventories = [
        project_unit_export_inventory(
            unit_id, trees[unit_id], identities[unit_id],
        )
        for unit_id in sorted(required_units)
    ]
    return project_target_export_inventory(plan, inventories)


def project_target_export_inventory(
    terminal_target_plan: Mapping[str, Any],
    unit_inventories: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    plan = _json_object(terminal_target_plan, "target_plan_invalid")
    scopes, required_units = _terminal_scopes(plan)
    inventories = [_json_object(item, "unit_inventory_invalid")
                   for item in unit_inventories]
    inventories.sort(key=lambda item: str(item.get("unit_id")))
    unit_ids = [item.get("unit_id") for item in inventories]
    if (
        unit_ids != sorted(required_units)
        or len(unit_ids) != len(set(unit_ids))
    ):
        _fail("unit_coverage_invalid")
    by_unit = {str(item["unit_id"]): item for item in inventories}
    targets = [_target_inventory(scope, by_unit) for scope in scopes]
    refusals = [
        {
            "code": CONFLICT_CODE,
            "terminal_target_id": target["terminal_target_id"],
            **conflict,
        }
        for target in targets
        for conflict in target["conflicts"]
    ]
    core = {
        "schema_version": 1,
        "artifact_kind": ARTIFACT_KIND,
        "status": "refused" if refusals else "passed",
        "target_plan_sha256": content_sha256(plan),
        "unit_inventory_sha256": content_sha256(inventories),
        "unit_inventories": inventories,
        "terminal_targets": targets,
        "refusal_count": len(refusals),
        "refusals": refusals,
        "blockers": [CONFLICT_CODE] if refusals else [],
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return {**core, "report_sha256": content_sha256(core)}


def unavailable_target_export_summary() -> dict[str, Any]:
    return {
        "status": "unavailable", "ref": None,
        "report_sha256": None, "refusal_count": 0,
        "blockers": [UNAVAILABLE_CODE],
    }


def target_export_summary(
    inventory: Mapping[str, Any], reference: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": inventory["status"], "ref": dict(reference),
        "report_sha256": inventory["report_sha256"],
        "refusal_count": inventory["refusal_count"],
        "blockers": list(inventory["blockers"]),
    }


def _terminal_scopes(
    plan: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], set[str]]:
    if plan.get("schema_version") != 1:
        _fail("target_plan_invalid")
    values = plan.get("terminal_targets")
    declared_ids = plan.get("terminal_target_ids")
    if (
        not isinstance(values, list) or not values
        or not isinstance(declared_ids, list)
    ):
        _fail("target_plan_invalid")
    scopes = []
    required_units: set[str] = set()
    seen_targets: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping):
            _fail("target_plan_invalid")
        target_id = value.get("terminal_target_id")
        occurrences = value.get("unit_occurrences")
        if (
            not _text(target_id) or target_id in seen_targets
            or not isinstance(occurrences, list)
        ):
            _fail("target_plan_invalid")
        seen_targets.add(target_id)
        normalized = []
        seen_occurrences: set[tuple[str, tuple[int, ...]]] = set()
        for ordinal, occurrence in enumerate(occurrences):
            if not isinstance(occurrence, Mapping):
                _fail("target_plan_occurrence_invalid")
            unit_id = occurrence.get("unit_id")
            path = occurrence.get("target_occurrence_path")
            if (
                not _text(unit_id) or not isinstance(path, list)
                or any(type(item) is not int or item < 0 for item in path)
            ):
                _fail("target_plan_occurrence_invalid")
            key = (unit_id, tuple(path))
            if key in seen_occurrences:
                _fail("target_plan_occurrence_invalid")
            seen_occurrences.add(key)
            required_units.add(unit_id)
            normalized.append({
                "occurrence_ordinal": ordinal, "unit_id": unit_id,
                "target_occurrence_path": list(path),
            })
        scopes.append({
            "terminal_target_id": target_id,
            "unit_occurrences": normalized,
        })
    actual_ids = [item["terminal_target_id"] for item in scopes]
    if declared_ids != actual_ids or actual_ids != sorted(actual_ids):
        _fail("target_plan_invalid")
    return scopes, required_units


def _target_inventory(
    scope: Mapping[str, Any], by_unit: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    paths_by_unit: dict[str, list[list[int]]] = defaultdict(list)
    occurrences = []
    for occurrence in scope["unit_occurrences"]:
        unit_id = occurrence["unit_id"]
        inventory = by_unit.get(unit_id)
        if not isinstance(inventory, Mapping):
            _fail("unit_inventory_invalid")
        identity_sha = inventory.get("unit_identity_sha256")
        path = occurrence["target_occurrence_path"]
        paths_by_unit[unit_id].append(path)
        occurrences.append({
            **occurrence, "unit_identity_sha256": identity_sha,
        })
    exports = []
    for unit_id in sorted(paths_by_unit):
        paths = sorted(paths_by_unit[unit_id])
        definitions = by_unit[unit_id].get("exports")
        if not isinstance(definitions, list):
            _fail("unit_inventory_invalid")
        for definition in definitions:
            if not isinstance(definition, Mapping):
                _fail("unit_inventory_invalid")
            exports.append({**definition, "target_occurrence_paths": paths})
    exports.sort(key=lambda item: (
        str(item.get("symbol")), str(item.get("definition_sha256")),
    ))
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for definition in exports:
        symbol = definition.get("symbol")
        if not _text(symbol):
            _fail("unit_inventory_invalid")
        by_symbol[symbol].append(definition)
    conflicts = []
    for symbol in sorted(by_symbol):
        definitions = by_symbol[symbol]
        definition_ids = [item.get("definition_sha256") for item in definitions]
        if len(definition_ids) > 1:
            conflicts.append({
                "symbol": symbol,
                "definition_count": len(definition_ids),
                "unit_ids": sorted({str(item["unit_id"]) for item in definitions}),
                "unit_identity_sha256s": sorted({
                    str(item["unit_identity_sha256"]) for item in definitions
                }),
                "definition_sha256s": sorted(str(item) for item in definition_ids),
            })
    return {
        "terminal_target_id": scope["terminal_target_id"],
        "status": "refused" if conflicts else "passed",
        "unit_occurrences": occurrences,
        "export_count": len(exports),
        "export_symbol_count": len(by_symbol),
        "exports": exports,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


def _unit_mapping(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code)
    result = dict(value)
    if any(not _text(key) for key in result):
        _fail(code)
    return result


def _json_object(value: Any, code: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        _fail(code)
    normalized = _json_value(value)
    if not isinstance(normalized, dict):
        _fail(code)
    return normalized


def _json_value(value: Any) -> Any:
    if value is None or type(value) in {bool, int, str}:
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            _fail("json_input_invalid")
        return {key: _json_value(value[key]) for key in sorted(value)}
    _fail("json_input_invalid")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value


def _fail(code: str) -> None:
    raise ValueError(f"c2rust_target_exports_{code}")


project_target_export_inventory_from_trees = project_target_scoped_exports

__all__ = [
    "ARTIFACT_KIND", "CONFLICT_CODE", "UNAVAILABLE_CODE",
    "project_target_export_inventory", "project_target_export_inventory_from_trees",
    "project_target_scoped_exports", "target_export_summary",
    "unavailable_target_export_summary",
]
