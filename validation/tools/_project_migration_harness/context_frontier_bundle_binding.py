from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def require_context_bundle_binding(
    contexts: Mapping[str, Any], portfolio: Mapping[str, Any],
    unit_ids: Sequence[str],
) -> None:
    assignments = portfolio.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("context frontier portfolio assignments are invalid")
    for unit_id in unit_ids:
        expected = _identity(contexts.get(unit_id))
        values = [
            _identity(assignment.get("context"))
            for assignment in assignments
            if isinstance(assignment, Mapping)
            and assignment.get("unit_id") == unit_id
        ]
        if not values or any(value != expected for value in values):
            raise ValueError("context frontier context bundle binding drifted")


def _identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("context frontier context binding is invalid")
    pages = value.get("pages")
    if not isinstance(pages, list):
        raise ValueError("context frontier context page binding is invalid")
    normalized_pages = []
    for page in pages:
        if not isinstance(page, Mapping):
            raise ValueError("context frontier context page is invalid")
        normalized_pages.append({
            "page_id": page.get("page_id"),
            "path": page.get("path"),
            "sha256": page.get("sha256"),
            "size_bytes": page.get("size_bytes", page.get("byte_count")),
        })
    return {
        "path": value.get("path"),
        "byte_count": value.get("byte_count"),
        "token_count": value.get("token_count"),
        "page_count": value.get("page_count"),
        "pages": normalized_pages,
        "catalog": value.get("catalog"),
        "retrieval": value.get("retrieval"),
    }


__all__ = ["require_context_bundle_binding"]
