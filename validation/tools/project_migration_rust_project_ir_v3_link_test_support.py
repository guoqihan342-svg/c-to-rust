from __future__ import annotations

from collections.abc import Mapping

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_project_ir_v3_link_expectation import (
    ARTIFACT_KIND, SCHEMA_VERSION, layered_link_occurrence_id,
)


def attach_link_expectation(
    target: dict, *, package_by_target: Mapping[str, str] | None = None,
) -> None:
    package_by_target = package_by_target or {}
    rows = []
    for item in target["input_occurrences"]:
        row = _row(target, len(rows), "input")
        row.update({
            "input_occurrence_id": item["occurrence_id"],
            "binding_sha256": item["binding_sha256"],
        })
        dependency = item["dependency_target_id"]
        if dependency is None:
            row.update({
                "representation_layer": "module-dep-info-commitment",
                "object_target_id": item["object_target_id"],
                "source_unit_id": item["source_unit_id"],
                "module_id": item["module_id"],
            })
        else:
            package_id = package_by_target.get(dependency)
            if package_id is None:
                raise ValueError("test package mapping is required")
            row.update({
                "representation_layer": "cargo-package-product",
                "package_id": package_id, "target_id": dependency,
            })
        rows.append(row)
    for argument in target["ordered_link_arguments"]:
        ordinal = len(rows)
        row = _row(target, ordinal, "system-argument")
        row.update({
            "representation_layer": "system-link-argument",
            "external_dependency_id": (
                f"external-{content_sha256([target['target_id'], ordinal, argument])[:24]}"
            ),
            "system_argument": argument,
        })
        rows.append(row)
    core = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": ARTIFACT_KIND,
        "source_build_ir_sha256": target["evidence"]["build_ir_sha256s"][0],
        "source_target_id": target["build_ir_target_id"],
        "consumer_target_id": target["target_id"], "occurrences": rows,
    }
    target["link_expectation"] = {
        **core, "expectation_sha256": content_sha256(core),
    }


def rehash_link_expectation(target: dict) -> None:
    value = target["link_expectation"]
    core = {key: item for key, item in value.items()
            if key != "expectation_sha256"}
    value["expectation_sha256"] = content_sha256(core)


def _row(target: dict, ordinal: int, source_kind: str) -> dict:
    build_sha = target["evidence"]["build_ir_sha256s"][0]
    return {
        "ordinal": ordinal,
        "occurrence_id": layered_link_occurrence_id(
            build_sha, target["build_ir_target_id"], ordinal,
        ),
        "argument_index": ordinal, "argument_count": 1,
        "source_kind": source_kind, "representation_layer": None,
        "consumer_target_id": target["target_id"],
        "input_occurrence_id": None, "binding_sha256": None,
        "object_target_id": None, "source_unit_id": None, "module_id": None,
        "package_id": None, "target_id": None,
        "external_dependency_id": None, "native_requirement_id": None,
        "portable_name": None, "library_format": None, "system_argument": None,
    }


__all__ = ["attach_link_expectation", "rehash_link_expectation"]
