from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256
from .build_ir_external_dependencies import (
    NATIVE_DEPENDENCY_KIND, ORDERED_LINK_ARGUMENT_KIND,
)
from .native_link_requirement_projection import native_link_requirement_id
from .rust_project_link_system_argument import supported_system_link_argument


SCHEMA_VERSION = 1
ARTIFACT_KIND = "rust-project-layered-link-expectation"
OCCURRENCE_KEYS = {
    "ordinal", "occurrence_id", "argument_index", "argument_count",
    "source_kind", "representation_layer", "consumer_target_id",
    "input_occurrence_id", "binding_sha256", "object_target_id",
    "source_unit_id", "module_id", "package_id", "target_id",
    "external_dependency_id", "native_requirement_id", "portable_name",
    "library_format", "system_argument",
}
_SOURCE_KEYS = {
    "ordinal", "argument_index", "argument_count", "kind", "input_ordinal",
    "binding_sha256", "dependency_target_id", "external_dependency_id",
}
def project_layered_link_expectation(
    build_ir: Mapping[str, Any], source_target: Mapping[str, Any],
    products: Mapping[str, Mapping[str, Any]],
    input_occurrences: Sequence[Mapping[str, Any]], *,
    rust_target_id: str, build_ir_artifact_sha256: str,
) -> dict[str, Any]:
    """Map current BuildIR link authority to explicit Rust proof layers."""
    source_target_id = _text(source_target.get("target_id"), "source target")
    if source_target.get("kind") not in {"archive", "link"}:
        raise ValueError("rust_project_ir_v3_link_source_target_invalid")
    source_rows = source_target.get("ordered_link_occurrences")
    roots = source_target.get("ordered_link_search_roots")
    response_files = source_target.get("link_response_files")
    if (
        not isinstance(source_rows, list) or not isinstance(roots, list)
        or not isinstance(response_files, list)
    ):
        raise ValueError("rust_project_ir_v3_link_authority_missing")
    if response_files:
        raise ValueError("rust_project_ir_v3_link_response_file_unsupported")
    if roots or any(
        isinstance(item, Mapping) and item.get("kind") == "search-root"
        for item in source_rows
    ):
        raise ValueError("rust_project_ir_v3_link_search_root_unsupported")
    inputs = list(input_occurrences)
    dependencies = _external_dependencies(build_ir)
    result = []
    input_ordinals = []
    external_ids = []
    system_arguments = []
    previous_end = -1
    for ordinal, raw in enumerate(source_rows):
        row = _source_occurrence(raw, ordinal)
        if row["argument_index"] < previous_end:
            raise ValueError("rust_project_ir_v3_link_argument_order_invalid")
        previous_end = row["argument_index"] + row["argument_count"]
        kind = row["kind"]
        if kind == "input":
            input_ordinal = row["input_ordinal"]
            if type(input_ordinal) is not int or not 0 <= input_ordinal < len(inputs):
                raise ValueError("rust_project_ir_v3_link_input_reference_invalid")
            projected = inputs[input_ordinal]
            result.append(_input_row(
                row, projected, products,
                occurrence_id=layered_link_occurrence_id(
                    build_ir_artifact_sha256, source_target_id, ordinal,
                ),
                consumer_target_id=rust_target_id,
            ))
            input_ordinals.append(input_ordinal)
            continue
        if kind not in {"system-argument", "external-native-library"}:
            raise ValueError("rust_project_ir_v3_link_source_kind_unsupported")
        dependency_id = row["external_dependency_id"]
        if not isinstance(dependency_id, str) or not dependency_id:
            raise ValueError("rust_project_ir_v3_link_external_binding_invalid")
        dependency = dependencies.get(dependency_id)
        expected_kind = (
            ORDERED_LINK_ARGUMENT_KIND
            if kind == "system-argument" else NATIVE_DEPENDENCY_KIND
        )
        if (
            dependency is None or dependency.get("kind") != expected_kind
            or dependency.get("consumer_target_ids") != [source_target_id]
        ):
            raise ValueError("rust_project_ir_v3_link_external_binding_invalid")
        result.append(_external_row(
            row, dependency,
            occurrence_id=layered_link_occurrence_id(
                build_ir_artifact_sha256, source_target_id, ordinal,
            ),
            consumer_target_id=rust_target_id,
        ))
        external_ids.append(dependency_id)
        if kind == "system-argument":
            system_arguments.append(dependency["name"])
    if input_ordinals != list(range(len(inputs))):
        raise ValueError("rust_project_ir_v3_link_input_closure_invalid")
    package_targets = [
        item["target_id"] for item in result
        if item["representation_layer"] == "cargo-package-product"
    ]
    if len(package_targets) != len(set(package_targets)):
        raise ValueError("rust_project_ir_v3_link_package_repeat_unsupported")
    expected_external = sorted(
        str(item["dependency_id"])
        for item in dependencies.values()
        if item.get("kind") in {
            ORDERED_LINK_ARGUMENT_KIND, NATIVE_DEPENDENCY_KIND,
        } and item.get("consumer_target_ids") == [source_target_id]
    )
    if sorted(external_ids) != expected_external \
            or len(external_ids) != len(set(external_ids)):
        raise ValueError("rust_project_ir_v3_link_external_closure_invalid")
    if system_arguments != source_target.get("ordered_link_arguments"):
        raise ValueError("rust_project_ir_v3_link_system_order_invalid")
    core = {
        "schema_version": SCHEMA_VERSION, "artifact_kind": ARTIFACT_KIND,
        "source_build_ir_sha256": build_ir_artifact_sha256,
        "source_target_id": source_target_id,
        "consumer_target_id": rust_target_id, "occurrences": result,
    }
    return {**core, "expectation_sha256": content_sha256(core)}


def layered_link_occurrence_id(
    build_ir_artifact_sha256: str, source_target_id: str, ordinal: int,
) -> str:
    digest = content_sha256({
        "build_ir_artifact_sha256": build_ir_artifact_sha256,
        "source_target_id": source_target_id, "ordinal": ordinal,
    })
    return f"link-occurrence-{digest[:24]}"


def _input_row(row, projected, products, *, occurrence_id, consumer_target_id):
    if not isinstance(projected, Mapping) \
            or projected.get("binding_sha256") != row["binding_sha256"]:
        raise ValueError("rust_project_ir_v3_link_input_binding_invalid")
    result = _row(row, occurrence_id, consumer_target_id)
    result.update({
        "input_occurrence_id": projected.get("occurrence_id"),
        "binding_sha256": projected.get("binding_sha256"),
    })
    dependency = row["dependency_target_id"]
    if projected.get("dependency_target_id") is None:
        required = ("object_target_id", "source_unit_id", "module_id")
        if (
            projected.get("object_target_id") != dependency
            or not all(_is_text(projected.get(key)) for key in required)
        ):
            raise ValueError("rust_project_ir_v3_link_object_mapping_invalid")
        result.update({
            "representation_layer": "module-dep-info-commitment",
            **{key: projected[key] for key in required},
        })
        return result
    if not _is_text(dependency):
        raise ValueError("rust_project_ir_v3_link_package_mapping_invalid")
    product = products.get(dependency)
    if product is None or projected.get("dependency_target_id") != product.get(
        "target_id"
    ):
        raise ValueError("rust_project_ir_v3_link_package_mapping_invalid")
    result.update({
        "representation_layer": "cargo-package-product",
        "package_id": product["package_id"], "target_id": product["target_id"],
    })
    return result


def _external_row(row, dependency, *, occurrence_id, consumer_target_id):
    result = _row(row, occurrence_id, consumer_target_id)
    result["external_dependency_id"] = dependency["dependency_id"]
    if row["kind"] == "system-argument":
        argument = _text(dependency.get("name"), "system argument")
        if not supported_system_link_argument(argument):
            raise ValueError("rust_project_ir_v3_link_system_control_unsupported")
        result.update({
            "representation_layer": "system-link-argument",
            "system_argument": argument,
        })
        return result
    name = _text(dependency.get("name"), "native name")
    library_format = _text(dependency.get("format"), "native format")
    result.update({
        "representation_layer": "native-link-input",
        "native_requirement_id": native_link_requirement_id(name, library_format),
        "portable_name": name, "library_format": library_format,
    })
    return result


def _row(row, occurrence_id, consumer_target_id):
    return {
        "ordinal": row["ordinal"], "occurrence_id": occurrence_id,
        "argument_index": row["argument_index"],
        "argument_count": row["argument_count"], "source_kind": row["kind"],
        "representation_layer": None, "consumer_target_id": consumer_target_id,
        "input_occurrence_id": None, "binding_sha256": None,
        "object_target_id": None, "source_unit_id": None, "module_id": None,
        "package_id": None, "target_id": None,
        "external_dependency_id": None, "native_requirement_id": None,
        "portable_name": None, "library_format": None, "system_argument": None,
    }


def _source_occurrence(value: Any, ordinal: int) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _SOURCE_KEYS:
        raise ValueError("rust_project_ir_v3_link_source_occurrence_invalid")
    result = dict(value)
    if result.get("ordinal") != ordinal:
        raise ValueError("rust_project_ir_v3_link_source_occurrence_invalid")
    for key in ("argument_index", "argument_count"):
        if type(result.get(key)) is not int or result[key] < 0:
            raise ValueError("rust_project_ir_v3_link_source_occurrence_invalid")
    if result["argument_count"] not in {1, 2}:
        raise ValueError("rust_project_ir_v3_link_source_occurrence_invalid")
    return result


def _external_dependencies(build_ir: Mapping[str, Any]):
    values = build_ir.get("external_dependencies")
    if not isinstance(values, list) or any(not isinstance(item, Mapping) for item in values):
        raise ValueError("rust_project_ir_v3_link_external_dependencies_invalid")
    identifiers = [item.get("dependency_id") for item in values]
    if any(not _is_text(item) for item in identifiers) \
            or len(identifiers) != len(set(identifiers)):
        raise ValueError("rust_project_ir_v3_link_external_dependencies_invalid")
    return dict(zip(identifiers, values, strict=True))


def _text(value: Any, label: str) -> str:
    if not _is_text(value):
        raise ValueError(f"rust_project_ir_v3_link_{label.replace(' ', '_')}_invalid")
    return str(value)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 4096

__all__ = [
    "ARTIFACT_KIND", "OCCURRENCE_KEYS", "SCHEMA_VERSION",
    "layered_link_occurrence_id", "project_layered_link_expectation",
]
