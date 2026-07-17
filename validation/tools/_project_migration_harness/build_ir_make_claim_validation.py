from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256


_MAKE_ROLE = "make-dry-run-report"
_MAKE_EXTERNAL_KINDS = {"library-name", "library-search-path"}


def validate_make_build_ir_claims(
    value: Mapping[str, Any], raw_roles: Sequence[Any],
    units: Sequence[Mapping[str, Any]],
    generated: Sequence[Mapping[str, Any]],
    targets: Sequence[Mapping[str, Any]],
    external: Sequence[Mapping[str, Any]],
    boundaries: Sequence[Mapping[str, Any]],
) -> None:
    if _MAKE_ROLE not in raw_roles:
        return
    claim = value.get("claim_boundary")
    if not isinstance(claim, Mapping):
        raise ValueError("build_ir_make_claim_invalid")
    required = {
        "role": "canonical_build_projection_only",
        "closure_complete": False,
        "command_graph_complete": True,
        "generated_output_graph_complete": True,
        "selected_translation_units_complete": True,
        "generated_outputs_materialized": False,
        "external_dependencies_complete": True,
        "link_argument_classification_error_count": 0,
        "parameters_guessed": False,
        "commands_executed": False,
        "fact_collection_executed": True,
    }
    if value.get("status") != "ready_with_boundaries" or any(
        claim.get(key) != expected for key, expected in required.items()
    ):
        raise ValueError("build_ir_make_claim_invalid")
    if any(_materialized(unit.get("output")) for unit in units):
        raise ValueError("build_ir_make_output_materialization_invalid")
    outputs = [
        output for target in targets for output in target.get("outputs", [])
        if isinstance(output, Mapping)
    ]
    if any(_materialized(output) for output in outputs):
        raise ValueError("build_ir_make_output_materialization_invalid")
    generated_bindings = [
        item.get("binding") for item in generated
        if isinstance(item.get("binding"), Mapping)
    ]
    if len(generated_bindings) != len(generated) or any(
        _materialized(binding) for binding in generated_bindings
    ):
        raise ValueError("build_ir_make_output_materialization_invalid")
    _validate_generated_closure(targets, generated)
    search_root_count = sum(
        occurrence.get("kind") == "search-root"
        for target in targets
        for occurrence in target.get("ordered_link_occurrences", [])
        if isinstance(occurrence, Mapping)
    )
    if claim.get("unmaterialized_link_search_root_count") != search_root_count:
        raise ValueError("build_ir_make_search_root_claim_invalid")
    _required_boundary(
        boundaries, "make_dry_run_nonsemantic_fact_collection", {},
    )
    _required_boundary(
        boundaries, "make_generated_outputs_not_materialized", {},
    )
    _required_boundary(
        boundaries, "make_link_search_roots_not_materialized",
        {"count": search_root_count}, required=search_root_count > 0,
    )
    make_external = [
        item for item in external if item.get("kind") in _MAKE_EXTERNAL_KINDS
    ]
    dependency_ids = sorted(str(item.get("dependency_id")) for item in make_external)
    if (
        any(item.get("resolved") is not False for item in make_external)
        or claim.get("unresolved_external_dependency_count") != len(make_external)
        or claim.get("external_dependency_resolution_complete") is not (
            not make_external
        )
        or claim.get("external_dependency_resolution_records") != []
        or claim.get("external_dependency_resolution_error_count") != 0
    ):
        raise ValueError("build_ir_make_external_claim_invalid")
    _validate_resolution_boundary(boundaries, dependency_ids)


def _validate_generated_closure(
    targets: Sequence[Mapping[str, Any]],
    generated: Sequence[Mapping[str, Any]],
) -> None:
    consumers: dict[str, set[str]] = {}
    for target in targets:
        for item in target.get("ordered_inputs", []):
            binding = item.get("binding") if isinstance(item, Mapping) else None
            path = binding.get("path") if isinstance(binding, Mapping) else None
            if isinstance(path, str):
                consumers.setdefault(path, set()).add(str(target.get("target_id")))
    expected = [
        {
            "binding": dict(output), "role": "target-output",
            "producer_target_id": str(target.get("target_id")),
            "consumer_target_ids": sorted(consumers.get(str(output.get("path")), set())),
        }
        for target in targets for output in target.get("outputs", [])
        if isinstance(output, Mapping)
    ]
    actual = [
        {
            "binding": dict(item["binding"]), "role": item.get("role"),
            "producer_target_id": str(item.get("producer_target_id")),
            "consumer_target_ids": item.get("consumer_target_ids"),
        }
        for item in generated if isinstance(item.get("binding"), Mapping)
    ]
    expected.sort(key=content_sha256)
    actual.sort(key=content_sha256)
    if actual != expected:
        raise ValueError("build_ir_make_generated_closure_invalid")


def _validate_resolution_boundary(
    boundaries: Sequence[Mapping[str, Any]], dependency_ids: list[str],
) -> None:
    matches = [
        item for item in boundaries
        if item.get("kind") == "make_external_dependency_resolution_unverified"
    ]
    if not dependency_ids:
        if matches:
            raise ValueError("build_ir_make_external_boundary_invalid")
        return
    if len(matches) != 1 or (
        matches[0].get("dependency_count") != len(dependency_ids)
        or matches[0].get("dependency_ids") != dependency_ids
    ):
        raise ValueError("build_ir_make_external_boundary_invalid")


def _required_boundary(
    boundaries: Sequence[Mapping[str, Any]], kind: str,
    fields: Mapping[str, Any], *, required: bool = True,
) -> None:
    matches = [item for item in boundaries if item.get("kind") == kind]
    if (required and len(matches) != 1) or (not required and matches):
        raise ValueError("build_ir_make_boundary_invalid")
    if required and any(matches[0].get(key) != value for key, value in fields.items()):
        raise ValueError("build_ir_make_boundary_invalid")


def _materialized(value: Any) -> bool:
    return isinstance(value, Mapping) and value.get("materialized") is not False


__all__ = ["validate_make_build_ir_claims"]
