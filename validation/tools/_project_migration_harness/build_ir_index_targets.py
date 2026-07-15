from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def index_target_contexts(
    build_ir: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    units = build_ir.get("translation_units")
    targets = build_ir.get("targets")
    if not isinstance(units, list) or not isinstance(targets, list):
        raise ValueError("build_ir_index_target_context_invalid")
    _validate_variants(units)
    unit_by_output = _unit_output_owners(units)
    descriptors: dict[str, dict[str, Any]] = {}
    object_by_unit: dict[str, str] = {}
    for target in targets:
        descriptor = _target_descriptor(target)
        target_id = descriptor["target_id"]
        if target_id in descriptors:
            raise ValueError("build_ir_index_target_duplicate")
        descriptors[target_id] = descriptor
        provenance = target.get("provenance")
        if target.get("kind") != "object":
            continue
        output_paths = descriptor["output_paths"]
        derived_unit_id = (
            unit_by_output.get(output_paths[0]) if len(output_paths) == 1 else None
        )
        provenance_unit_id = (
            provenance.get("unit_id") if isinstance(provenance, Mapping) else None
        )
        if derived_unit_id is None:
            raise ValueError("build_ir_index_object_target_orphan")
        if provenance_unit_id is not None and provenance_unit_id != derived_unit_id:
            raise ValueError("build_ir_index_object_target_mismatch")
        unit_id = derived_unit_id
        if unit_id in object_by_unit:
            raise ValueError("build_ir_index_object_target_ambiguous")
        object_by_unit[unit_id] = target_id
    result: dict[str, dict[str, Any]] = {}
    for unit in units:
        if not isinstance(unit, Mapping):
            raise ValueError("build_ir_index_translation_unit_invalid")
        unit_id = unit.get("unit_id")
        object_id = object_by_unit.get(str(unit_id))
        if not isinstance(unit_id, str) or object_id is None:
            raise ValueError("build_ir_index_object_target_missing")
        object_target = descriptors[object_id]
        output = unit.get("output")
        output_path = output.get("path") if isinstance(output, Mapping) else None
        if object_target["output_paths"] != [output_path]:
            raise ValueError("build_ir_index_object_output_mismatch")
        consumers = _consumer_closure(descriptors, object_id)
        result[unit_id] = {
            "variant": {
                "key": unit_id,
                "index": unit.get("variant_index"),
                "count": unit.get("variant_count"),
            },
            "object_target": object_target,
            "consumer_targets": consumers,
        }
    if set(result) != set(object_by_unit):
        raise ValueError("build_ir_index_object_target_orphan")
    return result


def _validate_variants(units: list[Any]) -> None:
    by_source: dict[str, list[Mapping[str, Any]]] = {}
    unit_ids: set[str] = set()
    for unit in units:
        source = unit.get("source") if isinstance(unit, Mapping) else None
        unit_id = unit.get("unit_id") if isinstance(unit, Mapping) else None
        source_path = source.get("path") if isinstance(source, Mapping) else None
        if (
            not isinstance(unit_id, str) or not unit_id or unit_id in unit_ids
            or not isinstance(source_path, str) or not source_path
        ):
            raise ValueError("build_ir_index_variant_invalid")
        unit_ids.add(unit_id)
        by_source.setdefault(source_path, []).append(unit)
    for variants in by_source.values():
        count = len(variants)
        indexes = {unit.get("variant_index") for unit in variants}
        counts = {unit.get("variant_count") for unit in variants}
        if indexes != set(range(count)) or counts != {count}:
            raise ValueError("build_ir_index_variant_invalid")


def _unit_output_owners(units: list[Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for unit in units:
        output = unit.get("output") if isinstance(unit, Mapping) else None
        output_path = output.get("path") if isinstance(output, Mapping) else None
        unit_id = unit.get("unit_id") if isinstance(unit, Mapping) else None
        if (
            not isinstance(output_path, str) or not output_path
            or not isinstance(unit_id, str) or not unit_id
            or output_path in result
        ):
            raise ValueError("build_ir_index_unit_output_ambiguous")
        result[output_path] = unit_id
    return result


def _consumer_closure(
    descriptors: dict[str, dict[str, Any]], object_id: str,
) -> list[dict[str, Any]]:
    consumers: dict[str, list[str]] = {target_id: [] for target_id in descriptors}
    for target_id, descriptor in descriptors.items():
        for dependency_id in descriptor["dependency_target_ids"]:
            if dependency_id not in descriptors:
                raise ValueError("build_ir_index_target_dependency_missing")
            consumers[dependency_id].append(target_id)
    reachable = {object_id}
    pending = [object_id]
    while pending:
        dependency_id = pending.pop()
        for target_id in consumers[dependency_id]:
            if target_id not in reachable:
                reachable.add(target_id)
                pending.append(target_id)
    indegree = {target_id: 0 for target_id in reachable}
    for dependency_id in reachable:
        for target_id in consumers[dependency_id]:
            if target_id in reachable:
                indegree[target_id] += 1
    ready = [target_id for target_id, count in indegree.items() if count == 0]
    visited = 0
    while ready:
        dependency_id = ready.pop()
        visited += 1
        for target_id in consumers[dependency_id]:
            if target_id not in indegree:
                continue
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
    if visited != len(reachable):
        raise ValueError("build_ir_index_target_cycle")
    reachable.remove(object_id)
    return [descriptors[target_id] for target_id in sorted(reachable)]


def _target_descriptor(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("build_ir_index_target_invalid")
    target_id = value.get("target_id")
    name = value.get("name")
    kind = value.get("kind")
    outputs = value.get("outputs")
    dependencies = value.get("dependency_target_ids")
    inputs = value.get("ordered_inputs")
    link_arguments = value.get("ordered_link_arguments")
    if (
        not all(isinstance(item, str) and item for item in (target_id, name, kind))
        or not isinstance(outputs, list) or not outputs
        or not isinstance(dependencies, list)
        or not isinstance(inputs, list)
        or not isinstance(link_arguments, list)
    ):
        raise ValueError("build_ir_index_target_invalid")
    output_paths = [
        item.get("path") if isinstance(item, Mapping) else None
        for item in outputs
    ]
    ordered_input_targets = [
        item.get("dependency_target_id") if isinstance(item, Mapping) else None
        for item in inputs
    ]
    if (
        any(not isinstance(item, str) or not item for item in output_paths)
        or any(not isinstance(item, str) or not item for item in dependencies)
        or any(
            item is not None and (not isinstance(item, str) or not item)
            for item in ordered_input_targets
        )
        or any(not isinstance(item, str) or "\0" in item for item in link_arguments)
    ):
        raise ValueError("build_ir_index_target_invalid")
    return {
        "target_id": target_id,
        "name": name,
        "kind": kind,
        "output_paths": output_paths,
        "dependency_target_ids": list(dependencies),
        "ordered_input_target_ids": ordered_input_targets,
        "ordered_link_arguments": list(link_arguments),
    }


__all__ = ["index_target_contexts"]
