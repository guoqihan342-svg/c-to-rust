from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def critical_path_weights(
    assignments: Sequence[Mapping[str, Any]], *,
    known_group_ids: Sequence[str] | set[str] | None = None,
) -> dict[str, int]:
    dependencies: dict[str, tuple[str, ...]] = {}
    for assignment in assignments:
        if not isinstance(assignment, Mapping):
            raise ValueError("portfolio assignment is invalid")
        group_id = assignment.get("group_id")
        raw = assignment.get("dependencies", [])
        if not isinstance(group_id, str) or not group_id:
            raise ValueError("assignment group_id must be a non-empty string")
        if not isinstance(raw, list) or not all(isinstance(item, str) and item for item in raw):
            raise ValueError("assignment dependencies must be non-empty strings")
        normalized = tuple(raw)
        previous = dependencies.setdefault(group_id, normalized)
        if previous != normalized:
            raise ValueError("assignments for one group must share dependencies")
    known = set(dependencies) if known_group_ids is None else set(known_group_ids)
    if not set(dependencies) <= known:
        raise ValueError("assignment groups are missing from known groups")
    unknown = {
        dependency for values in dependencies.values() for dependency in values
        if dependency not in known
    }
    if unknown:
        raise ValueError(f"assignment dependencies reference unknown groups: {sorted(unknown)}")
    dependents: dict[str, list[str]] = {group_id: [] for group_id in dependencies}
    for group_id, values in dependencies.items():
        for dependency in values:
            if dependency in dependents:
                dependents[dependency].append(group_id)
    memo: dict[str, int] = {}
    active: set[str] = set()

    def depth(group_id: str) -> int:
        if group_id in memo:
            return memo[group_id]
        if group_id in active:
            raise ValueError("assignment dependency graph contains a cycle")
        active.add(group_id)
        children = dependents[group_id]
        result = 0 if not children else 1 + max(depth(child) for child in children)
        active.remove(group_id)
        memo[group_id] = result
        return result

    return {group_id: depth(group_id) for group_id in sorted(dependencies)}


__all__ = ["critical_path_weights"]
