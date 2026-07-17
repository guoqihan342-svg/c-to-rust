from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256, normalize_binding


_KEYS = {"ordinal", "binding_sha256"}


def project_link_search_roots(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    roots = raw.get("search_roots")
    if not isinstance(roots, list):
        raise ValueError("build_ir_raw_link_search_roots_invalid")
    return [
        {
            "ordinal": ordinal,
            "binding_sha256": content_sha256(
                _raw_binding(value)
            ),
        }
        for ordinal, value in enumerate(roots)
    ]


def _raw_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("build_ir_raw_link_search_root_invalid")
    materialized = value.get("materialized", True)
    if type(materialized) is not bool:
        raise ValueError("build_ir_raw_link_search_root_invalid")
    return normalize_binding(value, materialized=materialized)


def validate_link_search_roots(
    target: Mapping[str, Any], occurrences: Sequence[Mapping[str, Any]],
) -> None:
    roots = target.get("ordered_link_search_roots")
    if not isinstance(roots, list):
        raise ValueError("build_ir_link_search_root_authority_invalid")
    normalized = []
    for ordinal, value in enumerate(roots):
        if (
            not isinstance(value, Mapping)
            or set(value) != _KEYS
            or type(value.get("ordinal")) is not int
            or value.get("ordinal") != ordinal
            or not is_sha256(value.get("binding_sha256"))
        ):
            raise ValueError("build_ir_link_search_root_authority_invalid")
        normalized.append(dict(value))
    rows = [row for row in occurrences if row["kind"] == "search-root"]
    if any(
        not is_sha256(row["binding_sha256"])
        or any(row[key] is not None for key in (
            "input_ordinal", "dependency_target_id", "external_dependency_id",
        ))
        for row in rows
    ):
        raise ValueError("build_ir_link_search_root_occurrence_invalid")
    observed = [
        {"ordinal": ordinal, "binding_sha256": item["binding_sha256"]}
        for ordinal, item in enumerate(rows)
    ]
    if observed != normalized:
        raise ValueError("build_ir_link_search_root_closure_invalid")


__all__ = ["project_link_search_roots", "validate_link_search_roots"]
