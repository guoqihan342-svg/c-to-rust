from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .build_ir import normalize_binding
from .build_ir_external_dependencies import (
    NATIVE_DEPENDENCY_KIND,
    ORDERED_LINK_ARGUMENT_KIND,
)
from .build_ir_link_search_roots import (
    project_link_search_roots, validate_link_search_roots,
)

_KINDS = {
    "input", "search-root", "system-argument", "external-native-library",
}
_RAW_KEYS = {
    "ordinal", "argument_index", "argument_count", "kind",
    "reference_ordinal",
}
_PROJECTED_KEYS = {
    "ordinal", "argument_index", "argument_count", "kind",
    "input_ordinal", "binding_sha256", "dependency_target_id",
    "external_dependency_id",
}


def project_link_authority(
    raw: Mapping[str, Any], target_id: str,
    inputs: Sequence[Mapping[str, Any]],
    external_dependencies: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    occurrences = project_link_occurrences(
        raw, target_id, inputs, external_dependencies,
    )
    if occurrences is None:
        return None
    return {
        "ordered_link_occurrences": occurrences,
        "ordered_link_search_roots": project_link_search_roots(raw),
    }


def project_link_occurrences(
    raw: Mapping[str, Any], target_id: str,
    inputs: Sequence[Mapping[str, Any]],
    external_dependencies: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]] | None:
    """Project raw cross-category order without copying path-like values."""
    occurrences = raw.get("ordered_link_occurrences")
    if occurrences is None:
        return None
    if not isinstance(occurrences, list):
        raise ValueError("build_ir_raw_link_occurrences_invalid")
    raw_inputs = _raw_list(raw, "inputs")
    search_roots = _raw_list(raw, "search_roots")
    system_arguments = _raw_list(raw, "ordered_system_link_args")
    native_libraries = _raw_list(
        raw, "external_native_libraries", optional=True,
    )
    if not all(isinstance(item, str) for item in system_arguments):
        raise ValueError("build_ir_raw_link_system_arguments_invalid")
    external_by_kind = {
        "system-argument": [
            item for item in external_dependencies
            if item.get("kind") == ORDERED_LINK_ARGUMENT_KIND
        ],
        "external-native-library": [
            item for item in external_dependencies
            if item.get("kind") == NATIVE_DEPENDENCY_KIND
        ],
    }
    sources = {
        "input": raw_inputs,
        "search-root": search_roots,
        "system-argument": system_arguments,
        "external-native-library": native_libraries,
    }
    normalized_occurrences = [
        _raw_occurrence(item, ordinal)
        for ordinal, item in enumerate(occurrences)
    ]
    _validate_partition_closure(normalized_occurrences, sources)
    result = []
    for ordinal, occurrence in enumerate(normalized_occurrences):
        kind = occurrence["kind"]
        reference = occurrence["reference_ordinal"]
        values = sources[kind]
        if reference >= len(values):
            raise ValueError("build_ir_raw_link_occurrence_reference_invalid")
        projected = {
            "ordinal": ordinal,
            "argument_index": occurrence["argument_index"],
            "argument_count": occurrence["argument_count"],
            "kind": kind,
            "input_ordinal": None,
            "binding_sha256": None,
            "dependency_target_id": None,
            "external_dependency_id": None,
        }
        if kind == "input":
            if reference >= len(inputs):
                raise ValueError("build_ir_raw_link_input_reference_invalid")
            raw_binding = _raw_binding(values[reference])
            current = inputs[reference]
            if raw_binding != current.get("binding"):
                raise ValueError("build_ir_raw_link_input_binding_drift")
            projected.update({
                "input_ordinal": reference,
                "binding_sha256": content_sha256(raw_binding),
                "dependency_target_id": current.get("dependency_target_id"),
            })
        elif kind == "search-root":
            binding = _raw_binding(values[reference])
            projected["binding_sha256"] = content_sha256(binding)
        else:
            dependencies = external_by_kind[kind]
            if reference >= len(dependencies):
                raise ValueError("build_ir_raw_link_external_reference_invalid")
            dependency = dependencies[reference]
            if dependency.get("consumer_target_ids") != [target_id]:
                raise ValueError("build_ir_raw_link_external_consumer_drift")
            projected["external_dependency_id"] = dependency["dependency_id"]
        result.append(projected)
    return result


def validate_link_occurrence_authority(
    targets: Sequence[Mapping[str, Any]],
    external_dependencies: Sequence[Mapping[str, Any]],
    authority_target_ids: set[str] | None = None,
) -> None:
    dependencies = {
        str(item.get("dependency_id")): item for item in external_dependencies
        if isinstance(item, Mapping)
    }
    for target in targets:
        target_id = target.get("target_id")
        has_occurrences = "ordered_link_occurrences" in target
        has_search_roots = "ordered_link_search_roots" in target
        if has_occurrences is not has_search_roots:
            raise ValueError("build_ir_link_occurrence_authority_incomplete")
        if authority_target_ids is not None and (
            target_id in authority_target_ids
        ) is not has_occurrences:
            raise ValueError("build_ir_link_occurrence_authority_scope_invalid")
        occurrences = target.get("ordered_link_occurrences")
        if not has_occurrences:
            continue
        if target.get("kind") not in {"archive", "link"} \
                or not isinstance(occurrences, list):
            raise ValueError("build_ir_link_occurrences_invalid")
        normalized = [
            _projected_occurrence(item, ordinal)
            for ordinal, item in enumerate(occurrences)
        ]
        _validate_positions(normalized)
        _validate_inputs(target, normalized)
        validate_link_search_roots(target, normalized)
        _validate_external(target, normalized, dependencies)


def _raw_occurrence(value: Any, ordinal: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _RAW_KEYS:
        raise ValueError("build_ir_raw_link_occurrence_invalid")
    result = dict(value)
    if result.get("ordinal") != ordinal or result.get("kind") not in _KINDS:
        raise ValueError("build_ir_raw_link_occurrence_invalid")
    for key in ("argument_index", "reference_ordinal"):
        if isinstance(result.get(key), bool) or not isinstance(result.get(key), int) \
                or result[key] < 0:
            raise ValueError("build_ir_raw_link_occurrence_invalid")
    count = result.get("argument_count")
    if isinstance(count, bool) or not isinstance(count, int) or count not in {1, 2}:
        raise ValueError("build_ir_raw_link_occurrence_invalid")
    return result


def _projected_occurrence(value: Any, ordinal: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PROJECTED_KEYS:
        raise ValueError("build_ir_link_occurrence_invalid")
    result = dict(value)
    if result.get("ordinal") != ordinal or result.get("kind") not in _KINDS:
        raise ValueError("build_ir_link_occurrence_invalid")
    for key in ("argument_index", "argument_count"):
        if isinstance(result.get(key), bool) or not isinstance(result.get(key), int) \
                or result[key] < 0:
            raise ValueError("build_ir_link_occurrence_invalid")
    if result["argument_count"] not in {1, 2}:
        raise ValueError("build_ir_link_occurrence_invalid")
    return result


def _validate_positions(values: Sequence[Mapping[str, Any]]) -> None:
    previous_end = -1
    for item in values:
        if item["argument_index"] < previous_end:
            raise ValueError("build_ir_link_occurrence_argument_order_invalid")
        previous_end = item["argument_index"] + item["argument_count"]


def _validate_inputs(
    target: Mapping[str, Any], values: Sequence[Mapping[str, Any]],
) -> None:
    inputs = target.get("ordered_inputs")
    rows = [item for item in values if item["kind"] == "input"]
    if not isinstance(inputs, list) or len(rows) != len(inputs):
        raise ValueError("build_ir_link_occurrence_input_closure_invalid")
    for ordinal, (row, source) in enumerate(zip(rows, inputs, strict=True)):
        if (
            type(row["input_ordinal"]) is not int
            or row["input_ordinal"] != ordinal
            or row["binding_sha256"] != content_sha256(source["binding"])
            or row["dependency_target_id"] != source["dependency_target_id"]
            or row["external_dependency_id"] is not None
        ):
            raise ValueError("build_ir_link_occurrence_input_binding_invalid")


def _validate_external(
    target: Mapping[str, Any], values: Sequence[Mapping[str, Any]],
    dependencies: Mapping[str, Mapping[str, Any]],
) -> None:
    expected_kinds = {
        "system-argument": ORDERED_LINK_ARGUMENT_KIND,
        "external-native-library": NATIVE_DEPENDENCY_KIND,
    }
    used = []
    system_names = []
    for row in values:
        expected = expected_kinds.get(row["kind"])
        if expected is None:
            continue
        dependency_id = row["external_dependency_id"]
        dependency = (
            dependencies.get(dependency_id)
            if isinstance(dependency_id, str) else None
        )
        if (
            dependency is None or dependency.get("kind") != expected
            or dependency.get("consumer_target_ids") != [target["target_id"]]
            or (
                expected == NATIVE_DEPENDENCY_KIND
                and dependency.get("ordinal") != row["argument_index"]
            )
            or any(row[key] is not None for key in (
                "input_ordinal", "binding_sha256", "dependency_target_id",
            ))
        ):
            raise ValueError("build_ir_link_occurrence_external_invalid")
        used.append(dependency["dependency_id"])
        if expected == ORDERED_LINK_ARGUMENT_KIND:
            system_names.append(dependency["name"])
    relevant = sorted(
        str(item["dependency_id"]) for item in dependencies.values()
        if item.get("kind") in set(expected_kinds.values())
        and item.get("consumer_target_ids") == [target["target_id"]]
    )
    if sorted(used) != relevant or len(used) != len(set(used)):
        raise ValueError("build_ir_link_occurrence_external_closure_invalid")
    if system_names != target.get("ordered_link_arguments"):
        raise ValueError("build_ir_link_occurrence_system_order_invalid")


def _validate_partition_closure(
    values: Sequence[Mapping[str, Any]], sources: Mapping[str, Sequence[Any]],
) -> None:
    for kind in _KINDS:
        references = [item["reference_ordinal"] for item in values
                      if item["kind"] == kind]
        if references != list(range(len(sources[kind]))):
            raise ValueError("build_ir_raw_link_occurrence_partition_invalid")


def _raw_list(
    raw: Mapping[str, Any], key: str, *, optional: bool = False,
) -> list[Any]:
    value = raw.get(key)
    if value is None and optional:
        return []
    if not isinstance(value, list):
        raise ValueError("build_ir_raw_link_category_invalid")
    return value


def _raw_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("build_ir_raw_link_binding_invalid")
    materialized = value.get("materialized", True)
    if type(materialized) is not bool:
        raise ValueError("build_ir_raw_link_binding_invalid")
    return normalize_binding(value, materialized=materialized)


__all__ = [
    "project_link_authority", "project_link_occurrences",
    "validate_link_occurrence_authority",
]
