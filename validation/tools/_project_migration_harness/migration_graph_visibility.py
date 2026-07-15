from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .c_index_build_targets import normalized_build_target_context


TargetDomains = dict[str, frozenset[str]]


def unit_target_domains(c_index: Mapping[str, Any]) -> TargetDomains | None:
    inputs = _unit_ids(c_index.get("inputs"), "c_index.inputs")
    contexts = c_index.get("unit_contexts")
    if not _objects(contexts):
        raise ValueError("c_index.unit_contexts must be an array of objects")
    by_unit: dict[str, Mapping[str, Any]] = {}
    for context in contexts:
        unit_id = context.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id or unit_id in by_unit:
            raise ValueError("c_index.unit_contexts must cover unique units")
        by_unit[unit_id] = context
    if set(by_unit) != inputs:
        raise ValueError("c_index.unit_contexts must cover indexed units")
    raw_targets: dict[str, Any] = {}
    for unit_id, context in by_unit.items():
        compile_context = context.get("compile_context")
        if not isinstance(compile_context, Mapping):
            raise ValueError("c_index compile_context is invalid")
        raw_targets[unit_id] = compile_context.get("build_target_context")
    present = {unit_id for unit_id, value in raw_targets.items() if value is not None}
    if not present:
        return None
    if present != inputs:
        raise ValueError("migration_graph_target_domains_incomplete")
    result: TargetDomains = {}
    consumer_count = 0
    for unit_id in sorted(inputs):
        target_context = normalized_build_target_context(
            raw_targets[unit_id], unit_id=unit_id,
        )
        if target_context is None:
            raise ValueError("migration_graph_target_domains_incomplete")
        consumer_count += len(target_context["consumer_targets"])
        identifiers = {
            str(target_context["object_target"]["target_id"]),
            *(
                str(item["target_id"])
                for item in target_context["consumer_targets"]
            ),
        }
        if not identifiers:
            raise ValueError("migration_graph_target_domain_empty")
        result[unit_id] = frozenset(identifiers)
    return result if consumer_count else None


def visible_definitions(
    caller: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    id_key: str,
    target_domains: TargetDomains | None,
) -> list[Mapping[str, Any]]:
    local = [
        item for item in candidates
        if item.get("linkage") == "internal"
        and item.get("unit_id") == caller.get("unit_id")
    ]
    if local:
        return sorted(local, key=lambda item: str(item.get(id_key)))
    external = [item for item in candidates if item.get("linkage") == "external"]
    if target_domains is None:
        return sorted(external, key=lambda item: str(item.get(id_key)))
    caller_domain = _domain(caller, target_domains)
    visible = [
        item for item in external
        if caller_domain.intersection(_domain(item, target_domains))
    ]
    return sorted(visible, key=lambda item: str(item.get(id_key)))


def ambiguous_external_definition_nodes(
    functions: Mapping[str, Sequence[Mapping[str, Any]]],
    target_domains: TargetDomains | None,
) -> set[str]:
    result: set[str] = set()
    for definitions in functions.values():
        external = [item for item in definitions if item.get("linkage") == "external"]
        for definition in external:
            if len(visible_definitions(
                definition, external, "node_id", target_domains,
            )) > 1:
                result.add(str(definition["node_id"]))
    return result


def _domain(value: Mapping[str, Any], domains: TargetDomains) -> frozenset[str]:
    unit_id = value.get("unit_id")
    if not isinstance(unit_id, str) or unit_id not in domains:
        raise ValueError("migration_graph_target_domain_unit_missing")
    return domains[unit_id]


def _unit_ids(value: Any, label: str) -> set[str]:
    if not _objects(value):
        raise ValueError(f"{label} must be an array of objects")
    result: set[str] = set()
    for item in value:
        unit_id = item.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError(f"{label} entries require unit_id")
        if unit_id in result:
            raise ValueError(f"{label} entries require unique unit_id")
        result.add(unit_id)
    return result


def _objects(value: Any) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes, bytearray))
        and all(isinstance(item, Mapping) for item in value)
    )


__all__ = [
    "TargetDomains",
    "ambiguous_external_definition_nodes",
    "unit_target_domains",
    "visible_definitions",
]
