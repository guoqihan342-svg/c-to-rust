from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


LEGACY_OCCURRENCE_KEYS = frozenset({
    "ordinal", "role", "dependency_target_id", "binding_sha256",
})
EXPLICIT_OCCURRENCE_KEYS = frozenset({
    *LEGACY_OCCURRENCE_KEYS, "occurrence_id", "object_target_id",
    "source_unit_id", "module_id",
})


def occurrence_module_order(
    target: Mapping[str, Any],
    module_sources: Mapping[str, Sequence[str]] | None = None,
) -> list[str] | None:
    """Return occurrence-folded module order, or None for legacy v3 inputs."""
    occurrences = target.get("input_occurrences")
    if not isinstance(occurrences, list):
        raise ValueError("rust_project_cargo_v3_input_occurrences_invalid")
    shapes = {frozenset(item) for item in occurrences if isinstance(item, Mapping)}
    if len(shapes) != (1 if occurrences else 0) or any(
        not isinstance(item, Mapping) for item in occurrences
    ):
        raise ValueError("rust_project_cargo_v3_input_occurrence_schema_invalid")
    if not occurrences or shapes == {LEGACY_OCCURRENCE_KEYS}:
        return None
    if shapes != {EXPLICIT_OCCURRENCE_KEYS}:
        raise ValueError("rust_project_cargo_v3_input_occurrence_schema_invalid")
    occurrence_ids = set()
    object_bindings = {}
    object_records: list[tuple[int, str, str]] = []
    order = []
    for ordinal, item in enumerate(occurrences):
        occurrence_id = item.get("occurrence_id")
        if not _text(occurrence_id) or occurrence_id in occurrence_ids:
            raise ValueError("rust_project_cargo_v3_occurrence_id_invalid")
        occurrence_ids.add(occurrence_id)
        dependency = item.get("dependency_target_id")
        object_id = item.get("object_target_id")
        source_id = item.get("source_unit_id")
        module_id = item.get("module_id")
        package_input = _text(dependency) and all(
            value is None for value in (object_id, source_id, module_id)
        )
        object_input = dependency is None and all(
            _text(value) for value in (object_id, source_id, module_id)
        )
        if not package_input and not object_input:
            raise ValueError("rust_project_cargo_v3_input_occurrence_mapping_invalid")
        if not object_input:
            continue
        binding = (str(module_id), str(source_id), str(item["binding_sha256"]))
        previous = object_bindings.get(object_id)
        if previous is not None:
            if previous != binding:
                raise ValueError("rust_project_cargo_v3_object_occurrence_binding_drift")
            continue
        object_bindings[object_id] = binding
        object_records.append((len(object_records), str(module_id), str(source_id)))
        if module_id not in order:
            order.append(str(module_id))
    if module_sources is not None:
        _validate_module_closure(object_records, module_sources, order)
    return order


def _validate_module_closure(
    records: Sequence[tuple[int, str, str]],
    module_sources: Mapping[str, Sequence[str]], order: Sequence[str],
) -> None:
    if set(order) != set(module_sources):
        raise ValueError("rust_project_cargo_v3_object_occurrence_closure_drift")
    for module_id, expected_sources in module_sources.items():
        owned = [item for item in records if item[1] == module_id]
        ordinals = [item[0] for item in owned]
        if (
            [item[2] for item in owned] != list(expected_sources)
            or not ordinals
            or ordinals != list(range(ordinals[0], ordinals[0] + len(ordinals)))
        ):
            raise ValueError("rust_project_cargo_v3_object_occurrence_order_invalid")


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 1_024 and all(
        ord(char) >= 32 for char in value
    )


def link_order_unproven(target: Mapping[str, Any]) -> bool:
    occurrences = target["input_occurrences"]
    try:
        explicit_order = occurrence_module_order(target)
    except ValueError:
        return True
    products = [
        item["dependency_target_id"] for item in occurrences
        if item["dependency_target_id"] is not None
    ]
    if explicit_order is not None:
        return (
            len(products) != len(set(products))
            or bool(unrepresented_link_arguments(target))
        )
    native = [item for item in occurrences if item["dependency_target_id"] is None]
    return (
        len(products) != len(set(products))
        or bool(products and native)
        or bool(unrepresented_link_arguments(target))
    )


def unrepresented_link_arguments(target: Mapping[str, Any]) -> list[str]:
    represented = {"-shared", "--shared", "/dll"}
    kind = target.get("kind")
    return [
        str(argument) for argument in target.get("ordered_link_arguments", [])
        if not (kind == "cdylib" and str(argument).casefold() in represented)
    ]


__all__ = [
    "EXPLICIT_OCCURRENCE_KEYS", "LEGACY_OCCURRENCE_KEYS", "link_order_unproven",
    "occurrence_module_order", "unrepresented_link_arguments",
]
