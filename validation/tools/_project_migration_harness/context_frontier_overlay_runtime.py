from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .context_frontier_binding import validate_context_against_frontier
from .context_frontier_cas import read_bound_frontier_cas_json
from .context_frontier_overlay import resolve_effective_context


def resolve_schedule_context_overlays(
    schedule: Mapping[str, Any], *, harness_root: Path,
) -> dict[str, Any]:
    ready = schedule.get("ready")
    if not isinstance(ready, list):
        raise ValueError("context overlay schedule.ready is invalid")
    resolved = []
    for item in ready:
        if not isinstance(item, Mapping):
            raise ValueError("context overlay ready item is invalid")
        assignment = item.get("assignment")
        frontier = item.get("context_frontier")
        if not isinstance(assignment, Mapping) or not isinstance(frontier, Mapping):
            raise ValueError("context overlay schedule binding is incomplete")
        overlay_ref = frontier.get("context_overlay")
        if overlay_ref is None:
            context = assignment.get("context")
            if not isinstance(context, Mapping):
                raise ValueError("context overlay assignment context is invalid")
            effective = dict(context)
        else:
            overlay = read_bound_frontier_cas_json(
                harness_root, overlay_ref, "context-frontier-overlay",
            )
            effective = resolve_effective_context(assignment, frontier, overlay)
        validate_context_against_frontier(frontier, effective)
        resolved.append({**dict(item), "effective_context": effective})
    return {**dict(schedule), "ready": resolved}


def resolve_request_effective_context(
    assignment: Mapping[str, Any], frontier: Mapping[str, Any], *,
    harness_root: Path,
) -> dict[str, Any]:
    overlay_ref = frontier.get("context_overlay")
    if overlay_ref is None:
        context = assignment.get("context")
        if not isinstance(context, Mapping):
            raise ValueError("worker assignment context is invalid")
        effective = dict(context)
    else:
        overlay = read_bound_frontier_cas_json(
            harness_root, overlay_ref, "context-frontier-overlay",
        )
        effective = resolve_effective_context(assignment, frontier, overlay)
    validate_context_against_frontier(frontier, effective)
    return effective


__all__ = [
    "resolve_request_effective_context", "resolve_schedule_context_overlays",
]
