from __future__ import annotations

from collections.abc import Mapping
import copy
from typing import Any

_TARGET_KINDS = {"archive", "link", "object"}

def project_terminal_target_plan(build_ir: Mapping[str, Any]) -> dict[str, Any]:
    """Project occurrence-preserving terminal plans from validated BuildIR."""
    if not isinstance(build_ir, Mapping):
        _fail("build_ir_invalid")
    units, unit_by_output = _index_units(build_ir.get("translation_units"))
    targets, target_by_output = _index_targets(build_ir.get("targets"))
    owners = _object_owners(targets, units, unit_by_output)
    consumers = _validate_graph(targets, target_by_output)
    external, boundary_refs = _external_boundaries(build_ir, set(targets))
    terminal_ids = sorted(set(targets).difference(consumers))
    if not terminal_ids:
        _fail("terminal_missing")
    plans = []
    fan_out: dict[str, list[dict[str, Any]]] = {item: [] for item in units}
    context = (targets, units, owners, external, boundary_refs)
    for terminal_id in terminal_ids:
        occurrences: dict[str, list[dict[str, Any]]] = {
            "target_occurrences": [], "unit_occurrences": [],
            "target_owned_boundaries": []}
        _expand_occurrence(terminal_id, (), None, context, occurrences)
        for occurrence in occurrences["unit_occurrences"]:
            fan_out[occurrence["unit_id"]].append({
                "terminal_target_id": terminal_id,
                "target_occurrence_path": list(occurrence["target_occurrence_path"]),
            })
        terminal = targets[terminal_id]
        plans.append({
            "terminal_target_id": terminal_id,
            "terminal_kind": terminal["kind"],
            "execution_mode": "compile_only" if terminal["kind"] == "object" else "target_assembly",
            **occurrences,
        })
    return {
        "schema_version": 1,
        "terminal_target_ids": terminal_ids,
        "terminal_targets": plans,
        "unit_fan_out": [{
            "unit_id": unit_id, "occurrence_count": len(fan_out[unit_id]),
            "occurrences": fan_out[unit_id],
        } for unit_id in sorted(fan_out)],
    }

def _index_units(value: Any) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    if not isinstance(value, list) or not value:
        _fail("units_invalid")
    units: dict[str, Mapping[str, Any]] = {}
    by_output: dict[str, str] = {}
    variants: dict[str, list[Mapping[str, Any]]] = {}
    for unit in value:
        if not isinstance(unit, Mapping):
            _fail("unit_invalid")
        unit_id = unit.get("unit_id")
        source_path = _binding_path(unit.get("source"))
        output_path = _binding_path(unit.get("output"))
        if not _text(unit_id) or unit_id in units:
            _fail("unit_invalid")
        if output_path in by_output:
            _fail("unit_output_conflict")
        units[unit_id] = unit
        by_output[output_path] = unit_id
        variants.setdefault(source_path, []).append(unit)
    for group in variants.values():
        count = len(group)
        if (
            {item.get("variant_index") for item in group} != set(range(count))
            or {item.get("variant_count") for item in group} != {count}
        ):
            _fail("variant_invalid")
    return units, by_output

def _index_targets(value: Any) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    if not isinstance(value, list) or not value:
        _fail("targets_invalid")
    targets: dict[str, Mapping[str, Any]] = {}
    output_owners: dict[str, str] = {}
    for target in value:
        if not isinstance(target, Mapping):
            _fail("target_invalid")
        target_id = target.get("target_id")
        outputs = target.get("outputs")
        dependencies = target.get("dependency_target_ids")
        inputs = target.get("ordered_inputs")
        arguments = target.get("ordered_link_arguments")
        if (
            not _text(target_id) or target_id in targets
            or not _text(target.get("name"))
            or target.get("kind") not in _TARGET_KINDS
            or not isinstance(outputs, list) or not outputs
            or not isinstance(dependencies, list)
            or any(not _text(item) for item in dependencies)
            or len(dependencies) != len(set(dependencies))
            or not isinstance(inputs, list) or not isinstance(arguments, list)
            or any(not isinstance(item, str) or "\0" in item for item in arguments)
        ):
            _fail("target_invalid")
        for output in outputs:
            path = _binding_path(output)
            if path in output_owners:
                _fail("output_conflict")
            output_owners[path] = target_id
        _archive_semantics(target)
        targets[target_id] = target
    return targets, output_owners

def _object_owners(
    targets: Mapping[str, Mapping[str, Any]], units: Mapping[str, Mapping[str, Any]],
    unit_by_output: Mapping[str, str],
) -> dict[str, str]:
    owners: dict[str, str] = {}
    owned_units: set[str] = set()
    for target_id, target in targets.items():
        if target["kind"] != "object":
            continue
        outputs = target["outputs"]
        unit_id = (
            unit_by_output.get(_binding_path(outputs[0]))
            if len(outputs) == 1 else None
        )
        provenance = target.get("provenance")
        declared = (
            provenance.get("unit_id") if isinstance(provenance, Mapping) else None
        )
        if unit_id is None or declared is not None and declared != unit_id:
            _fail("object_owner_missing")
        if unit_id in owned_units:
            _fail("object_owner_conflict")
        owners[target_id] = unit_id
        owned_units.add(unit_id)
    if owned_units != set(units):
        _fail("object_owner_missing")
    return owners

def _validate_graph(
    targets: Mapping[str, Mapping[str, Any]], output_owners: Mapping[str, str],
) -> set[str]:
    consumers: set[str] = set()
    for target in targets.values():
        dependencies = target["dependency_target_ids"]
        if any(dependency not in targets for dependency in dependencies):
            _fail("unknown_dependency")
        consumers.update(dependencies)
        represented: set[str] = set()
        for ordinal, item in enumerate(target["ordered_inputs"]):
            if (
                not isinstance(item, Mapping) or item.get("ordinal") != ordinal
                or not _text(item.get("role"))
            ):
                _fail("ordered_input_unrepresentable")
            path = _binding_path(item.get("binding"))
            dependency = item.get("dependency_target_id")
            if dependency is None:
                if path in output_owners:
                    _fail("ordered_input_unrepresentable")
                continue
            if not _text(dependency) or dependency not in targets:
                _fail("unknown_dependency")
            if dependency not in dependencies:
                _fail("ordered_input_unrepresentable")
            outputs = {_binding_path(value) for value in targets[dependency]["outputs"]}
            if path not in outputs:
                _fail("ordered_input_unrepresentable")
            represented.add(dependency)
        if represented != set(dependencies):
            _fail("ordered_input_unrepresentable")
    pending = {
        target_id: set(target["dependency_target_ids"])
        for target_id, target in targets.items()
    }
    while pending:
        ready = {target_id for target_id, dependencies in pending.items()
                 if not dependencies}
        if not ready:
            _fail("cycle")
        for target_id in ready:
            del pending[target_id]
        for dependencies in pending.values():
            dependencies.difference_update(ready)
    return consumers

def _external_boundaries(
    build_ir: Mapping[str, Any], target_ids: set[str],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    values = build_ir.get("external_dependencies", [])
    boundaries = build_ir.get("boundaries", [])
    if not isinstance(values, list) or not isinstance(boundaries, list):
        _fail("external_boundary_invalid")
    result = {target_id: [] for target_id in target_ids}
    identifiers: set[str] = set()
    for value in values:
        if not isinstance(value, Mapping) or not _text(value.get("dependency_id")):
            _fail("external_boundary_invalid")
        dependency_id = value["dependency_id"]
        consumers = value.get("consumer_target_ids")
        ordinal = value.get("ordinal")
        if (
            dependency_id in identifiers
            or not isinstance(consumers, list) or len(consumers) != 1
            or consumers[0] not in target_ids
            or ordinal is not None and (type(ordinal) is not int or ordinal < 0)
        ):
            _fail("external_boundary_invalid")
        identifiers.add(dependency_id)
        result[consumers[0]].append(copy.deepcopy(dict(value)))
    refs: dict[str, list[dict[str, Any]]] = {}
    for value in boundaries:
        if not isinstance(value, Mapping):
            _fail("external_boundary_invalid")
        dependency_id = value.get("dependency_id")
        if dependency_id in identifiers:
            refs.setdefault(dependency_id, []).append(copy.deepcopy(dict(value)))
    return result, refs

def _expand_occurrence(
    target_id: str, path: tuple[int, ...], parent: tuple[int, ...] | None,
    context: tuple[Any, ...], result: dict[str, list[dict[str, Any]]],
) -> None:
    targets, units, owners, external, boundary_refs = context
    target = targets[target_id]
    owner = owners.get(target_id)
    result["target_occurrences"].append({
        "target_occurrence_path": list(path),
        "parent_target_occurrence_path": None if parent is None else list(parent),
        "via_input_ordinal": None if parent is None else path[-1],
        "target_id": target_id, "name": target["name"], "kind": target["kind"],
        "outputs": copy.deepcopy(target["outputs"]),
        "ordered_inputs": copy.deepcopy(target["ordered_inputs"]),
        "ordered_link_arguments": list(target["ordered_link_arguments"]),
        "archive_semantics": _archive_semantics(target),
        "object_owner_unit_id": owner,
        "external_dependencies": copy.deepcopy(external[target_id]),
    })
    if owner is not None:
        unit = units[owner]
        result["unit_occurrences"].append({
            "target_occurrence_path": list(path), "object_target_id": target_id,
            "unit_id": owner, "variant_index": unit.get("variant_index"),
            "variant_count": unit.get("variant_count"),
            "source": copy.deepcopy(unit["source"]),
            "object_output": copy.deepcopy(unit["output"]),
        })
    for dependency in external[target_id]:
        result["target_owned_boundaries"].append({
            "target_occurrence_path": list(path), "target_id": target_id,
            "boundary_kind": "external-dependency",
            "ordinal": dependency.get("ordinal"),
            "external_dependency": copy.deepcopy(dependency),
            "build_ir_boundaries": copy.deepcopy(
                boundary_refs.get(dependency["dependency_id"], [])
            ),
        })
    for item in target["ordered_inputs"]:
        ordinal = item["ordinal"]
        dependency = item.get("dependency_target_id")
        if dependency is not None:
            _expand_occurrence(
                dependency, (*path, ordinal), path, context, result,
            )
        elif not (target["kind"] == "object" and item["role"] == "source"):
            result["target_owned_boundaries"].append({
                "target_occurrence_path": list(path), "target_id": target_id,
                "boundary_kind": "ordered-input", "ordinal": ordinal,
                "ordered_input": copy.deepcopy(dict(item)),
            })

def _archive_semantics(target: Mapping[str, Any]) -> dict[str, Any] | None:
    value = target.get("archive_semantics")
    if target.get("kind") != "archive":
        if value is not None:
            _fail("archive_semantics_invalid")
        return None
    if (
        not isinstance(value, Mapping)
        or set(value) != {"operation", "ranlib_passes"}
        or not _text(value.get("operation"))
        or type(value.get("ranlib_passes")) is not int
        or value["ranlib_passes"] < 0
    ):
        _fail("archive_semantics_invalid")
    return copy.deepcopy(dict(value))

def _binding_path(value: Any) -> str:
    path = value.get("path") if isinstance(value, Mapping) else None
    if not _text(path):
        _fail("binding_invalid")
    return path
def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value

def _fail(code: str) -> None:
    raise ValueError(f"c2rust_target_plan_{code}")

__all__ = ["project_terminal_target_plan"]
