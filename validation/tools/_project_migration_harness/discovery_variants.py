from __future__ import annotations

from typing import Any

from .build_facts import json_sha256, rejection


def finalize_variants(
    parsed: list[dict[str, Any]], max_units: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    deduplicated: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    blockers: list[str] = []
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for unit in sorted(parsed, key=lambda item: item["entry"]["index"]):
        response_key = tuple(
            (item.get("path"), item.get("sha256"))
            for item in unit["response_files"]
        )
        key = (
            unit["source"]["path"],
            unit["working_directory"],
            unit["expanded_argv_sha256"],
            unit["output"],
            response_key,
        )
        duplicate = seen.get(key)
        if duplicate is not None:
            rejected.append(rejection(
                unit["entry"]["index"], unit["entry_sha256"],
                "exact_duplicate_variant", False,
                duplicate_of=duplicate["entry"]["index"],
                source=unit["source"]["path"],
            ))
            continue
        seen[key] = unit
        deduplicated.append(unit)
    output_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for unit in deduplicated:
        if isinstance(unit["output"], str):
            output_groups.setdefault(
                (unit["source"]["path"], unit["output"]), []
            ).append(unit)
    ambiguous = {
        unit["entry"]["index"]
        for group in output_groups.values()
        if len(group) > 1
        for unit in group
    }
    if ambiguous:
        blockers.append("ambiguous_translation_unit_variants")
    survivors = []
    for unit in deduplicated:
        if unit["entry"]["index"] in ambiguous:
            rejected.append(rejection(
                unit["entry"]["index"], unit["entry_sha256"],
                "ambiguous_variant_output", True,
                source=unit["source"]["path"], output=unit["output"],
            ))
        else:
            survivors.append(unit)
    for unit in survivors:
        unit["variant_id"] = json_sha256({
            "source": unit["source"]["path"],
            "working_directory": unit["working_directory"],
            "expanded_argv_sha256": unit["expanded_argv_sha256"],
            "output": unit["output"],
            "response_files": unit["response_files"],
        })
        unit["unit_id"] = unit["variant_id"]
    survivors.sort(key=lambda item: (item["source"]["path"], item["variant_id"]))
    per_source: dict[str, list[dict[str, Any]]] = {}
    for unit in survivors:
        per_source.setdefault(unit["source"]["path"], []).append(unit)
    for group in per_source.values():
        for variant_index, unit in enumerate(group):
            unit["variant_index"] = variant_index
            unit["variant_count"] = len(group)
    if len(survivors) > max_units:
        blockers.append("translation_unit_limit_exceeded")
        for unit in survivors[max_units:]:
            rejected.append(rejection(
                unit["entry"]["index"], unit["entry_sha256"],
                "translation_unit_limit_exceeded", True,
                source=unit["source"]["path"],
            ))
        survivors = survivors[:max_units]
    return survivors, rejected, blockers


__all__ = ["finalize_variants"]
