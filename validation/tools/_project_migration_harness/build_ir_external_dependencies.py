from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir import is_sha256, stable_build_id, string_list
from .link_external_libraries import (
    native_library_format, validate_external_native_libraries,
)


NATIVE_DEPENDENCY_KIND = "unresolved-native-library"
ORDERED_LINK_ARGUMENT_KIND = "ordered-link-argument"
DECLARED_EXTERNAL_KIND = "declared-external-dependency"
MAKE_EXTERNAL_KINDS = {"library-name", "library-search-path"}


def project_link_external_dependencies(
    raw: Mapping[str, Any], target_id: str, *,
    provenance_role: str = "generated-build-closure",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if provenance_role not in {"generated-build-closure", "make-dry-run-report"}:
        raise ValueError("build_ir_external_dependency_provenance_invalid")
    dependencies = [
        {
            "dependency_id": stable_build_id("external", {
                "target": target_id, "ordinal": ordinal, "argument": argument,
            }),
            "kind": ORDERED_LINK_ARGUMENT_KIND,
            "name": argument,
            "consumer_target_ids": [target_id],
            "ordinal": ordinal,
            "provenance": {"raw_fact_role": provenance_role},
        }
        for ordinal, argument in enumerate(
            string_list(raw.get("ordered_system_link_args"))
        )
    ]
    boundaries = []
    for library in validate_external_native_libraries(
        raw.get("external_native_libraries")
    ):
        identity = {
            "target": target_id,
            "ordinal": library["argument_index"],
            "name": library["name"],
            "format": library["format"],
        }
        dependency_id = stable_build_id("external", identity)
        dependencies.append({
            "dependency_id": dependency_id,
            "kind": NATIVE_DEPENDENCY_KIND,
            "name": library["name"],
            "consumer_target_ids": [target_id],
            "ordinal": library["argument_index"],
            "format": library["format"],
            "resolved": False,
            "provenance": {
                "raw_fact_role": "generated-build-closure",
                "resolution": library["resolution"],
                "source_argument_sha256": library["source_argument_sha256"],
            },
        })
        boundaries.append({
            "kind": "native_link_config_unresolved",
            "dependency_id": dependency_id,
        })
    return dependencies, boundaries


def validate_native_dependency(
    value: Mapping[str, Any], target_ids: set[str],
) -> None:
    if value.get("kind") != NATIVE_DEPENDENCY_KIND:
        return
    fields = {
        "dependency_id", "kind", "name", "consumer_target_ids", "ordinal",
        "format", "resolved", "provenance",
    }
    consumers = value.get("consumer_target_ids")
    ordinal = value.get("ordinal")
    provenance = value.get("provenance")
    if (
        set(value) != fields
        or not isinstance(consumers, list) or len(consumers) != 1
        or consumers[0] not in target_ids
        or isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0
        or native_library_format(value.get("name")) != value.get("format")
        or value.get("resolved") is not False
        or not isinstance(provenance, Mapping)
        or set(provenance) != {
            "raw_fact_role", "resolution", "source_argument_sha256",
        }
        or provenance.get("raw_fact_role") != "generated-build-closure"
        or provenance.get("resolution") != "unresolved-host-native-link"
        or not is_sha256(provenance.get("source_argument_sha256"))
    ):
        raise ValueError("build_ir_native_dependency_invalid")
    expected = stable_build_id("external", {
        "target": consumers[0], "ordinal": ordinal,
        "name": value["name"], "format": value["format"],
    })
    if value.get("dependency_id") != expected:
        raise ValueError("build_ir_native_dependency_identity_invalid")


def validate_external_dependency(
    value: Mapping[str, Any], target_ids: set[str],
) -> None:
    kind = value.get("kind")
    if kind == NATIVE_DEPENDENCY_KIND:
        validate_native_dependency(value, target_ids)
        return
    if kind == ORDERED_LINK_ARGUMENT_KIND:
        _validate_ordered_link_argument(value, target_ids)
        return
    if kind == DECLARED_EXTERNAL_KIND:
        _validate_declared_external(value, target_ids)
        return
    if kind in MAKE_EXTERNAL_KINDS:
        _validate_make_external(value, target_ids)
        return
    raise ValueError("build_ir_external_dependency_kind_invalid")


def validate_native_dependency_summary(
    dependencies: list[Mapping[str, Any]], boundaries: list[Mapping[str, Any]],
    claim_boundary: Mapping[str, Any], status: Any,
) -> None:
    native_ids = sorted(
        str(item["dependency_id"])
        for item in dependencies if item.get("kind") == NATIVE_DEPENDENCY_KIND
    )
    boundary_ids = []
    for item in boundaries:
        if item.get("kind") != "native_link_config_unresolved":
            continue
        if (
            set(item) != {"kind", "dependency_id"}
            or not isinstance(item.get("dependency_id"), str)
        ):
            raise ValueError("build_ir_native_boundary_invalid")
        boundary_ids.append(item.get("dependency_id"))
    if sorted(boundary_ids) != native_ids or len(boundary_ids) != len(set(boundary_ids)):
        raise ValueError("build_ir_native_boundary_mismatch")
    tracked = (
        bool(native_ids)
        or "native_link_config_resolved" in claim_boundary
        or "unresolved_native_dependency_count" in claim_boundary
    )
    if tracked and (
        claim_boundary.get("native_link_config_resolved") is not (not native_ids)
        or claim_boundary.get("unresolved_native_dependency_count") != len(native_ids)
        or isinstance(claim_boundary.get("unresolved_native_dependency_count"), bool)
    ):
        raise ValueError("build_ir_native_claim_boundary_invalid")
    if native_ids and status != "ready_with_boundaries":
        raise ValueError("build_ir_native_status_invalid")


def _validate_ordered_link_argument(
    value: Mapping[str, Any], target_ids: set[str],
) -> None:
    fields = {
        "dependency_id", "kind", "name", "consumer_target_ids", "ordinal",
        "provenance",
    }
    provenance = value.get("provenance")
    role = provenance.get("raw_fact_role") if isinstance(provenance, Mapping) else None
    if role not in {"generated-build-closure", "make-dry-run-report"}:
        raise ValueError("build_ir_external_dependency_invalid")
    consumer, ordinal, name = _common_dependency(
        value, fields, target_ids, role,
    )
    expected = stable_build_id("external", {
        "target": consumer, "ordinal": ordinal, "argument": name,
    })
    if value.get("dependency_id") != expected:
        raise ValueError("build_ir_external_dependency_identity_invalid")


def _validate_declared_external(
    value: Mapping[str, Any], target_ids: set[str],
) -> None:
    fields = {
        "dependency_id", "kind", "name", "consumer_target_ids", "ordinal",
        "provenance",
    }
    consumer, ordinal, name = _common_dependency(
        value, fields, target_ids, "generated-build-closure", ordinal_optional=True,
    )
    if ordinal is not None:
        raise ValueError("build_ir_external_dependency_invalid")
    expected = stable_build_id("external", {"target": consumer, "name": name})
    if value.get("dependency_id") != expected:
        raise ValueError("build_ir_external_dependency_identity_invalid")


def _validate_make_external(
    value: Mapping[str, Any], target_ids: set[str],
) -> None:
    fields = {
        "dependency_id", "kind", "name", "consumer_target_ids", "ordinal",
        "arguments", "resolved", "provenance",
    }
    consumer, ordinal, name = _common_dependency(
        value, fields, target_ids, "make-dry-run-report",
    )
    arguments = value.get("arguments")
    if (
        not isinstance(arguments, list) or not arguments
        or not all(isinstance(item, str) and item for item in arguments)
        or name != " ".join(arguments) or value.get("resolved") is not False
    ):
        raise ValueError("build_ir_external_dependency_invalid")
    expected = stable_build_id("external", {
        "target": consumer, "ordinal": ordinal, "arguments": arguments,
    })
    if value.get("dependency_id") != expected:
        raise ValueError("build_ir_external_dependency_identity_invalid")


def _common_dependency(
    value: Mapping[str, Any], fields: set[str], target_ids: set[str],
    provenance_role: str, *, ordinal_optional: bool = False,
) -> tuple[str, int | None, str]:
    consumers = value.get("consumer_target_ids")
    ordinal = value.get("ordinal")
    name = value.get("name")
    if (
        set(value) != fields
        or not isinstance(consumers, list) or len(consumers) != 1
        or consumers[0] not in target_ids
        or not isinstance(name, str) or not name or len(name) > 4096
        or value.get("provenance") != {"raw_fact_role": provenance_role}
        or (
            ordinal is not None or not ordinal_optional
        ) and (
            isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0
        )
    ):
        raise ValueError("build_ir_external_dependency_invalid")
    return consumers[0], ordinal, name


__all__ = [
    "NATIVE_DEPENDENCY_KIND", "project_link_external_dependencies",
    "validate_external_dependency", "validate_native_dependency",
    "validate_native_dependency_summary",
]
