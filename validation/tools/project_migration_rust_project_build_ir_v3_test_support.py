from __future__ import annotations

import copy

from validation.tools._project_migration_harness.build_ir import finalize_build_ir
from validation.tools._project_migration_harness.build_ir_external_dependencies import (
    project_link_external_dependencies,
)
from validation.tools._project_migration_harness.build_ir_link_authority import (
    link_authority_claim,
)
from validation.tools._project_migration_harness.build_ir_link_occurrences import (
    project_link_authority,
)
from validation.tools._project_migration_harness.build_ir_projection import (
    target_closure,
)


def scope_build_ir_fixture(
    source: dict, *, product: str | None,
    link_arguments: tuple[str, ...] = (),
) -> dict:
    """Keep one product and rebuild schema-v3 link-order authority."""
    if product not in {None, "archive", "link"}:
        raise ValueError("unsupported fixture product")
    if product != "link" and link_arguments:
        raise ValueError("link arguments require a link product")
    build_ir = copy.deepcopy(source)
    retained_kinds = {"object"}
    if product is not None:
        retained_kinds.add(product)
    build_ir["targets"] = [
        item for item in build_ir["targets"]
        if item["kind"] in retained_kinds
    ]
    for target in build_ir["targets"]:
        if target["kind"] == "link":
            target["ordered_link_arguments"] = list(link_arguments)
    return rebuild_build_ir_fixture_authority(build_ir)


def rebuild_build_ir_fixture_authority(source: dict) -> dict:
    """Rebuild schema-v3 authority after a test changes target topology."""
    build_ir = copy.deepcopy(source)
    external_dependencies = []
    for target in build_ir["targets"]:
        if target["kind"] not in {"archive", "link"}:
            continue
        arguments = list(target["ordered_link_arguments"])
        input_offset = 1 if target["kind"] == "archive" else 0
        inputs = [copy.deepcopy(item["binding"]) for item in target["ordered_inputs"]]
        raw = {
            "inputs": inputs,
            "search_roots": [],
            "ordered_system_link_args": arguments,
            "external_native_libraries": [],
            "ordered_link_occurrences": [
                {
                    "ordinal": ordinal,
                    "argument_index": input_offset + ordinal,
                    "argument_count": 1,
                    "kind": "input",
                    "reference_ordinal": ordinal,
                }
                for ordinal in range(len(inputs))
            ],
        }
        first_argument = input_offset + len(inputs)
        raw["ordered_link_occurrences"].extend(
            {
                "ordinal": len(inputs) + ordinal,
                "argument_index": first_argument + ordinal,
                "argument_count": 1,
                "kind": "system-argument",
                "reference_ordinal": ordinal,
            }
            for ordinal in range(len(arguments))
        )
        dependencies, boundaries = project_link_external_dependencies(
            raw, target["target_id"],
        )
        if boundaries:
            raise ValueError("fixture link dependencies must be fully modeled")
        authority = project_link_authority(
            raw, target["target_id"], target["ordered_inputs"], dependencies,
        )
        if authority is None:
            raise ValueError("fixture link occurrence authority missing")
        target.update(authority)
        external_dependencies.extend(dependencies)
    build_ir["external_dependencies"] = sorted(
        external_dependencies, key=lambda item: item["dependency_id"],
    )
    build_ir["target_closure"] = target_closure(build_ir["targets"])
    boundary = build_ir["claim_boundary"]
    boundary.pop("link_occurrence_authority", None)
    boundary.update(link_authority_claim(
        build_ir["extractor"], build_ir["targets"],
        build_ir["translation_units"],
    ))
    return finalize_build_ir(build_ir)


__all__ = [
    "rebuild_build_ir_fixture_authority", "scope_build_ir_fixture",
]
