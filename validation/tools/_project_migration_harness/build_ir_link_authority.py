from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .build_ir import (
    BUILD_IR_EXTRACTOR, BUILD_IR_SCHEMA_VERSION, LEGACY_BUILD_IR_EXTRACTOR,
    LEGACY_BUILD_IR_SCHEMA_VERSION,
)
from .link_closure_schema import (
    LEGACY_LINK_CLOSURE_SCHEMA_VERSION,
    LINK_CLOSURE_SCHEMA_VERSION,
    link_closure_schema_version,
)


AUTHORITY_KIND = "source-cross-class-link-occurrences"
AUTHORITY_SCHEMA_VERSION = 1


def extractor_for_generated_closure(
    closure: Mapping[str, Any],
) -> dict[str, str]:
    link = closure.get("target_link_closure")
    if not isinstance(link, Mapping):
        raise ValueError("build_ir_target_link_closure_invalid")
    version = link_closure_schema_version(link)
    if version == LINK_CLOSURE_SCHEMA_VERSION:
        return dict(BUILD_IR_EXTRACTOR)
    if version == LEGACY_LINK_CLOSURE_SCHEMA_VERSION:
        return dict(LEGACY_BUILD_IR_EXTRACTOR)
    raise ValueError("build_ir_target_link_closure_schema_invalid")


def link_authority_claim(
    extractor: Mapping[str, Any], targets: Sequence[Mapping[str, Any]],
    units: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if dict(extractor) != BUILD_IR_EXTRACTOR:
        return {}
    target_ids = _source_link_target_ids(targets, units)
    if not target_ids:
        return {}
    return {"link_occurrence_authority": {
        "schema_version": AUTHORITY_SCHEMA_VERSION,
        "kind": AUTHORITY_KIND,
        "target_ids": target_ids,
    }}


def schema_for_extractor(extractor: Mapping[str, Any]) -> int:
    if dict(extractor) == BUILD_IR_EXTRACTOR:
        return BUILD_IR_SCHEMA_VERSION
    if dict(extractor) == LEGACY_BUILD_IR_EXTRACTOR:
        return LEGACY_BUILD_IR_SCHEMA_VERSION
    raise ValueError("build_ir_extractor_invalid")


def validate_schema_extractor(
    schema_version: Any, extractor: Any, *, allow_legacy: bool,
) -> None:
    if schema_version not in {
        LEGACY_BUILD_IR_SCHEMA_VERSION, BUILD_IR_SCHEMA_VERSION,
    }:
        raise ValueError("build_ir_schema_version_invalid")
    if (
        schema_version == BUILD_IR_SCHEMA_VERSION
        and extractor == BUILD_IR_EXTRACTOR
    ):
        return
    if (
        allow_legacy
        and schema_version == LEGACY_BUILD_IR_SCHEMA_VERSION
        and extractor == LEGACY_BUILD_IR_EXTRACTOR
    ):
        return
    raise ValueError("build_ir_schema_extractor_invalid")


def validate_link_authority_claim(
    extractor: Any, claim_boundary: Mapping[str, Any],
    targets: Sequence[Mapping[str, Any]], units: Sequence[Mapping[str, Any]],
) -> set[str]:
    if extractor not in (BUILD_IR_EXTRACTOR, LEGACY_BUILD_IR_EXTRACTOR):
        raise ValueError("build_ir_extractor_invalid")
    expected = link_authority_claim(extractor, targets, units).get(
        "link_occurrence_authority"
    )
    actual = claim_boundary.get("link_occurrence_authority")
    if actual != expected:
        raise ValueError("build_ir_link_occurrence_authority_claim_invalid")
    return set(expected["target_ids"]) if expected is not None else set()


def _source_link_target_ids(
    targets: Sequence[Mapping[str, Any]], units: Sequence[Mapping[str, Any]],
) -> list[str]:
    object_units = _object_units_by_output(units)
    return sorted(
        str(target["target_id"]) for target in targets
        if not _is_source_object_target(target, object_units)
        and isinstance(target.get("target_id"), str)
    )


def _object_units_by_output(
    units: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    ambiguous: set[str] = set()
    for unit in units:
        output = unit.get("output")
        path = output.get("path") if isinstance(output, Mapping) else None
        if not isinstance(path, str) or not path:
            continue
        if path in result:
            ambiguous.add(path)
        else:
            result[path] = unit
    for path in ambiguous:
        result.pop(path, None)
    return result


def _is_source_object_target(
    target: Mapping[str, Any], units: Mapping[str, Mapping[str, Any]],
) -> bool:
    outputs = target.get("outputs")
    if target.get("kind") != "object" or not isinstance(outputs, list) \
            or len(outputs) != 1 or not isinstance(outputs[0], Mapping):
        return False
    path = outputs[0].get("path")
    unit = units.get(path) if isinstance(path, str) else None
    if unit is None or outputs[0] != unit.get("output"):
        return False
    inputs = target.get("ordered_inputs")
    if not isinstance(inputs, list) or len(inputs) != 1 \
            or not isinstance(inputs[0], Mapping):
        return False
    item = inputs[0]
    return (
        item.get("ordinal") == 0
        and item.get("role") == "source"
        and item.get("binding") == unit.get("source")
        and item.get("dependency_target_id") is None
    )


__all__ = [
    "AUTHORITY_KIND",
    "AUTHORITY_SCHEMA_VERSION",
    "extractor_for_generated_closure",
    "link_authority_claim",
    "schema_for_extractor",
    "validate_link_authority_claim",
    "validate_schema_extractor",
]
