from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .context_frontier_state import (
    static_context_page_set_sha256,
    validate_context_frontier_schedule_binding,
)


def validate_context_against_frontier(
    frontier_value: Any, context_value: Any,
) -> dict[str, Any]:
    frontier = validate_context_frontier_schedule_binding(frontier_value)
    if not isinstance(context_value, Mapping):
        raise ValueError("context frontier assignment context is invalid")
    catalog = context_value.get("catalog")
    if not isinstance(catalog, Mapping) or frontier["catalog"] != catalog:
        raise ValueError("context frontier catalog binding drifted")
    retrieval = context_value.get("retrieval")
    if frontier["mode"] == "host_retrieval":
        if not isinstance(retrieval, Mapping) or any(
            frontier.get(key) != retrieval.get(key)
            for key in (
                "selection_receipt_sha256", "materialized_page_set_sha256",
                "selection_materialization_sha256",
            )
        ):
            raise ValueError("context frontier retrieval binding drifted")
    elif (
        retrieval is not None
        or frontier["materialized_page_set_sha256"]
        != static_context_page_set_sha256(context_value)
    ):
        raise ValueError("static context frontier page-set binding drifted")
    return frontier


__all__ = ["validate_context_against_frontier"]
