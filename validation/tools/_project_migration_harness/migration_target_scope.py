from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .build_ir_index_targets import index_target_contexts
from .c_index_build_targets import normalized_build_target_context


SCOPE_KIND = "scc-build-target-scope"
SCOPE_SCHEMA_VERSION = 1
_SCOPE_KEYS = {
    "schema_version", "scope_kind", "source_unit_ids", "unit_scopes",
    "object_target_ids", "reachable_target_ids", "terminal_target_ids",
    "shared_reachable_target_ids", "domain_status", "scope_sha256",
}
_UNIT_SCOPE_KEYS = {
    "unit_id", "variant", "object_owner_target_id", "reachable_target_ids",
    "terminal_target_ids",
}


def derive_scc_target_scope(
    c_index: Mapping[str, Any], member_node_ids: Sequence[str],
) -> dict[str, Any] | None:
    nodes = c_index.get("nodes")
    if not _objects(nodes):
        raise ValueError("migration_target_scope_nodes_invalid")
    by_id: dict[str, Mapping[str, Any]] = {}
    for node in nodes:
        node_id = node.get("node_id")
        if not _text(node_id) or node_id in by_id:
            raise ValueError("migration_target_scope_nodes_invalid")
        by_id[node_id] = node
    members = list(member_node_ids)
    if (
        not members or any(not _text(item) for item in members)
        or len(members) != len(set(members)) or any(item not in by_id for item in members)
    ):
        raise ValueError("migration_target_scope_members_invalid")
    source_units = sorted({str(by_id[node_id].get("unit_id")) for node_id in members})
    if "None" in source_units or any(not item for item in source_units):
        raise ValueError("migration_target_scope_node_unit_invalid")
    contexts = _c_index_target_contexts(c_index)
    if contexts is None:
        return None
    return _scope(source_units, contexts)


def derive_build_ir_target_scopes(
    build_irs: Sequence[Mapping[str, Any]],
    source_units_by_group: Mapping[str, Sequence[str]],
) -> dict[str, dict[str, Any]]:
    if not build_irs or not isinstance(source_units_by_group, Mapping):
        raise ValueError("migration_target_scope_build_ir_invalid")
    contexts: dict[str, dict[str, Any]] = {}
    for build_ir in build_irs:
        for unit_id, context in index_target_contexts(build_ir).items():
            if unit_id in contexts:
                raise ValueError("migration_target_scope_build_unit_duplicate")
            contexts[unit_id] = context
    result: dict[str, dict[str, Any]] = {}
    for group_id in sorted(source_units_by_group):
        if not _text(group_id):
            raise ValueError("migration_target_scope_group_invalid")
        raw_units = source_units_by_group[group_id]
        if not _strings(raw_units):
            raise ValueError("migration_target_scope_source_units_invalid")
        units = list(raw_units)
        if units != sorted(set(units)) or any(item not in contexts for item in units):
            raise ValueError("migration_target_scope_source_units_invalid")
        result[group_id] = _scope(units, contexts)
    return result


def validate_scc_target_scope(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SCOPE_KEYS:
        raise ValueError("migration_target_scope_schema_invalid")
    if (
        value.get("schema_version") != SCOPE_SCHEMA_VERSION
        or value.get("scope_kind") != SCOPE_KIND
    ):
        raise ValueError("migration_target_scope_schema_invalid")
    units = value.get("source_unit_ids")
    records = value.get("unit_scopes")
    if not _strings(units) or units != sorted(set(units)) or not _objects(records):
        raise ValueError("migration_target_scope_units_invalid")
    normalized = [_validated_unit_scope(item) for item in records]
    if [item["unit_id"] for item in normalized] != units:
        raise ValueError("migration_target_scope_units_invalid")
    payload = _scope_payload(units, normalized)
    expected = {**payload, "scope_sha256": content_sha256(payload)}
    if dict(value) != expected:
        raise ValueError("migration_target_scope_content_invalid")
    return expected


def _c_index_target_contexts(
    c_index: Mapping[str, Any],
) -> dict[str, dict[str, Any]] | None:
    inputs = c_index.get("inputs")
    contexts = c_index.get("unit_contexts")
    if not _objects(inputs) or not _objects(contexts):
        raise ValueError("migration_target_scope_c_index_invalid")
    unit_ids = [item.get("unit_id") for item in inputs]
    if any(not _text(item) for item in unit_ids) or len(unit_ids) != len(set(unit_ids)):
        raise ValueError("migration_target_scope_c_index_invalid")
    raw: dict[str, Any] = {}
    for context in contexts:
        unit_id = context.get("unit_id")
        compile_context = context.get("compile_context")
        if (
            not _text(unit_id) or unit_id in raw or unit_id not in unit_ids
            or not isinstance(compile_context, Mapping)
        ):
            raise ValueError("migration_target_scope_c_index_invalid")
        raw[unit_id] = compile_context.get("build_target_context")
    if set(raw) != set(unit_ids):
        raise ValueError("migration_target_scope_c_index_invalid")
    present = {key for key, item in raw.items() if item is not None}
    if not present:
        return None
    if present != set(unit_ids):
        raise ValueError("migration_target_scope_context_incomplete")
    return {
        unit_id: _required_context(raw[unit_id], unit_id)
        for unit_id in sorted(raw)
    }


def _required_context(value: Any, unit_id: str) -> dict[str, Any]:
    result = normalized_build_target_context(value, unit_id=unit_id)
    if result is None:
        raise ValueError("migration_target_scope_context_incomplete")
    return result


def _scope(
    source_units: Sequence[str], contexts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    records = []
    for unit_id in source_units:
        context = contexts.get(unit_id)
        if context is None:
            raise ValueError("migration_target_scope_source_unit_missing")
        consumers = list(context["consumer_targets"])
        reachable = sorted(str(item["target_id"]) for item in consumers)
        records.append({
            "unit_id": unit_id,
            "variant": dict(context["variant"]),
            "object_owner_target_id": str(context["object_target"]["target_id"]),
            "reachable_target_ids": reachable,
            "terminal_target_ids": _terminal_target_ids(
                str(context["object_target"]["target_id"]), consumers,
            ),
        })
    payload = _scope_payload(list(source_units), records)
    return {**payload, "scope_sha256": content_sha256(payload)}


def _scope_payload(
    source_units: Sequence[str], records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    object_ids = [str(item["object_owner_target_id"]) for item in records]
    if len(object_ids) != len(set(object_ids)):
        raise ValueError("migration_target_scope_object_owner_conflict")
    reachable_sets = [set(item["reachable_target_ids"]) for item in records]
    any_reachable = any(reachable_sets)
    if not any_reachable:
        shared: set[str] = set()
        status = "object-only-conservative"
    elif len(reachable_sets) == 1:
        shared = set(reachable_sets[0])
        status = "target-bound"
    else:
        if any(not item for item in reachable_sets):
            raise ValueError("migration_target_scope_disjoint")
        shared = set.intersection(*reachable_sets)
        if not shared:
            raise ValueError("migration_target_scope_disjoint")
        status = "shared-target-domain"
    return {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "scope_kind": SCOPE_KIND,
        "source_unit_ids": list(source_units),
        "unit_scopes": [dict(item) for item in records],
        "object_target_ids": sorted(object_ids),
        "reachable_target_ids": sorted(set().union(*reachable_sets)),
        "terminal_target_ids": sorted({
            target for item in records for target in item["terminal_target_ids"]
        }),
        "shared_reachable_target_ids": sorted(shared),
        "domain_status": status,
    }


def _terminal_target_ids(
    object_id: str, consumers: Sequence[Mapping[str, Any]],
) -> list[str]:
    target_ids = {object_id, *(str(item["target_id"]) for item in consumers)}
    outgoing = {target_id: set() for target_id in target_ids}
    indegree = {target_id: 0 for target_id in target_ids}
    for target in consumers:
        target_id = str(target["target_id"])
        for dependency in target["dependency_target_ids"]:
            if dependency in target_ids:
                outgoing[dependency].add(target_id)
                indegree[target_id] += 1
    ready = sorted(target_id for target_id, count in indegree.items() if count == 0)
    visited = []
    while ready:
        current = ready.pop(0)
        visited.append(current)
        for target_id in sorted(outgoing[current]):
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                ready.append(target_id)
                ready.sort()
    if len(visited) != len(target_ids):
        raise ValueError("migration_target_scope_target_cycle")
    consumers_ids = target_ids - {object_id}
    return sorted(target_id for target_id in consumers_ids if not outgoing[target_id])


def _validated_unit_scope(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != _UNIT_SCOPE_KEYS or not _text(value.get("unit_id")):
        raise ValueError("migration_target_scope_unit_schema_invalid")
    variant = value.get("variant")
    if not isinstance(variant, Mapping) or set(variant) != {"key", "index", "count"}:
        raise ValueError("migration_target_scope_unit_schema_invalid")
    index, count = variant.get("index"), variant.get("count")
    if (
        variant.get("key") != value["unit_id"] or type(index) is not int
        or type(count) is not int or count < 1 or not 0 <= index < count
        or not _text(value.get("object_owner_target_id"))
    ):
        raise ValueError("migration_target_scope_unit_schema_invalid")
    reachable = value.get("reachable_target_ids")
    terminal = value.get("terminal_target_ids")
    if (
        not _string_list(reachable) or reachable != sorted(set(reachable))
        or not _string_list(terminal) or terminal != sorted(set(terminal))
        or not set(terminal) <= set(reachable)
    ):
        raise ValueError("migration_target_scope_unit_targets_invalid")
    return {
        "unit_id": value["unit_id"], "variant": dict(variant),
        "object_owner_target_id": value["object_owner_target_id"],
        "reachable_target_ids": list(reachable),
        "terminal_target_ids": list(terminal),
    }


def _objects(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, Mapping) for item in value)


def _strings(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and bool(value) and all(_text(item) for item in value)


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(_text(item) for item in value)


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value


__all__ = [
    "SCOPE_KIND", "SCOPE_SCHEMA_VERSION", "derive_build_ir_target_scopes",
    "derive_scc_target_scope", "validate_scc_target_scope",
]
