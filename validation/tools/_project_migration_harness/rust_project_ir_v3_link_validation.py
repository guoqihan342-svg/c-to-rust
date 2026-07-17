from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .native_link_requirement_projection import native_link_requirement_id
from .rust_project_cargo_v3_link_semantics import occurrence_module_order
from .rust_project_ir_v3_link_expectation import (
    ARTIFACT_KIND, OCCURRENCE_KEYS, SCHEMA_VERSION,
    layered_link_occurrence_id,
)
from .rust_project_link_system_argument import supported_system_link_argument
from .rust_project_ir_v3_topology_products import input_occurrence_id
from .rust_project_ir_validation import _sha, _text


_EXPECTATION_KEYS = {
    "schema_version", "artifact_kind", "source_build_ir_sha256",
    "source_target_id", "consumer_target_id", "occurrences",
    "expectation_sha256",
}
_LAYERS = {
    "module-dep-info-commitment", "cargo-package-product",
    "native-link-input", "system-link-argument",
}
def validate_target_occurrences(
    target: Mapping[str, Any], native_requirement_ids: set[str],
) -> None:
    _validate_input_occurrences(target)
    _validate_link_expectation(target, native_requirement_ids)


def validate_link_target_closure(
    target: Mapping[str, Any], targets: Mapping[str, Mapping[str, Any]],
    modules: Mapping[str, Mapping[str, Any]],
) -> None:
    for row in target["link_expectation"]["occurrences"]:
        layer = row["representation_layer"]
        if layer == "module-dep-info-commitment":
            module = modules.get(str(row["module_id"]))
            if (
                module is None or module.get("target_id") != target["target_id"]
                or row["source_unit_id"] not in module.get("source_unit_ids", [])
            ):
                raise ValueError("RustProjectIR v3 link module closure drifted")
        elif layer == "cargo-package-product":
            dependency = targets.get(str(row["target_id"]))
            if dependency is None or dependency.get("package_id") != row["package_id"]:
                raise ValueError("RustProjectIR v3 link package closure drifted")


def _validate_input_occurrences(target: Mapping[str, Any]) -> None:
    value = target.get("input_occurrences")
    if not isinstance(value, list):
        raise ValueError("RustProjectIR v3 input_occurrences must be an array")
    try:
        explicit_order = occurrence_module_order(target)
    except ValueError as error:
        raise ValueError(str(error)) from error
    build_shas = target["evidence"]["build_ir_sha256s"]
    if explicit_order is not None and len(build_shas) != 1:
        raise ValueError("RustProjectIR v3 occurrence BuildIR binding is ambiguous")
    ordinals = []
    for item in value:
        ordinal = item.get("ordinal")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
            raise ValueError("RustProjectIR v3 input occurrence ordinal is invalid")
        _text(item.get("role"), "input occurrence role")
        if item.get("dependency_target_id") is not None:
            _text(item["dependency_target_id"], "input occurrence dependency_target_id")
        if explicit_order is not None and item["occurrence_id"] != input_occurrence_id(
            build_shas[0], target["build_ir_target_id"], ordinal,
        ):
            raise ValueError("RustProjectIR v3 occurrence identity is invalid")
        _sha(item.get("binding_sha256"), "input occurrence binding_sha256")
        ordinals.append(ordinal)
    if ordinals != list(range(len(value))):
        raise ValueError("RustProjectIR v3 input occurrences are not canonical")


def _validate_link_expectation(
    target: Mapping[str, Any], native_requirement_ids: set[str],
) -> None:
    value = target.get("link_expectation")
    if not isinstance(value, Mapping) or set(value) != _EXPECTATION_KEYS:
        raise ValueError("RustProjectIR v3 link expectation schema is invalid")
    build_shas = target["evidence"]["build_ir_sha256s"]
    occurrences = value.get("occurrences")
    core = {key: value[key] for key in value if key != "expectation_sha256"}
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("artifact_kind") != ARTIFACT_KIND
        or len(build_shas) != 1
        or value.get("source_build_ir_sha256") != build_shas[0]
        or value.get("source_target_id") != target["build_ir_target_id"]
        or value.get("consumer_target_id") != target["target_id"]
        or not isinstance(occurrences, list)
        or value.get("expectation_sha256") != content_sha256(core)
    ):
        raise ValueError("RustProjectIR v3 link expectation binding is invalid")
    inputs = {
        item.get("occurrence_id"): item for item in target["input_occurrences"]
        if isinstance(item, Mapping) and isinstance(item.get("occurrence_id"), str)
    }
    if len(inputs) != len(target["input_occurrences"]):
        raise ValueError("RustProjectIR v3 link input identity is unavailable")
    used_inputs = []
    external_ids = []
    system_arguments = []
    previous_end = -1
    occurrence_ids = set()
    for ordinal, row in enumerate(occurrences):
        if not isinstance(row, Mapping) or set(row) != OCCURRENCE_KEYS:
            raise ValueError("RustProjectIR v3 link occurrence schema is invalid")
        occurrence_id = row.get("occurrence_id")
        layer = row.get("representation_layer")
        source_kind = row.get("source_kind")
        if (
            type(row.get("ordinal")) is not int or row["ordinal"] != ordinal
            or not _is_text(layer) or layer not in _LAYERS
            or not _is_text(source_kind) or source_kind not in {
                "input", "external-native-library", "system-argument",
            }
            or type(row.get("argument_index")) is not int
            or type(row.get("argument_count")) is not int
            or row["argument_index"] < previous_end
            or row["argument_count"] not in {1, 2}
            or not _is_text(occurrence_id) or occurrence_id in occurrence_ids
            or occurrence_id != layered_link_occurrence_id(
                build_shas[0], target["build_ir_target_id"], ordinal,
            )
            or row.get("consumer_target_id") != target["target_id"]
        ):
            raise ValueError("RustProjectIR v3 link occurrence order is invalid")
        previous_end = row["argument_index"] + row["argument_count"]
        occurrence_ids.add(occurrence_id)
        if layer in {"module-dep-info-commitment", "cargo-package-product"}:
            _validate_input_layer(row, inputs, object_layer=(
                layer == "module-dep-info-commitment"
            ))
            used_inputs.append(row["input_occurrence_id"])
        elif layer == "native-link-input":
            _validate_native_layer(row, native_requirement_ids)
            external_ids.append(row["external_dependency_id"])
        else:
            _validate_system_layer(row)
            external_ids.append(row["external_dependency_id"])
            system_arguments.append(row["system_argument"])
    if used_inputs != list(inputs) or len(external_ids) != len(set(external_ids)):
        raise ValueError("RustProjectIR v3 link occurrence closure drifted")
    if system_arguments != target["ordered_link_arguments"]:
        raise ValueError("RustProjectIR v3 link system argument order drifted")


def _validate_input_layer(row, inputs, *, object_layer: bool) -> None:
    input_id = row.get("input_occurrence_id")
    source = inputs.get(input_id)
    if (
        row.get("source_kind") != "input" or source is None
        or row.get("binding_sha256") != source.get("binding_sha256")
        or any(row.get(key) is not None for key in (
            "external_dependency_id", "native_requirement_id", "portable_name",
            "library_format", "system_argument",
        ))
    ):
        raise ValueError("RustProjectIR v3 link input mapping is invalid")
    if object_layer:
        expected = {
            key: source.get(key)
            for key in ("object_target_id", "source_unit_id", "module_id")
        }
        if (
            source.get("dependency_target_id") is not None
            or any(not _is_text(value) for value in expected.values())
            or any(row.get(key) != value for key, value in expected.items())
            or row.get("package_id") is not None or row.get("target_id") is not None
        ):
            raise ValueError("RustProjectIR v3 link object mapping is invalid")
        return
    if (
        not _is_text(source.get("dependency_target_id"))
        or row.get("target_id") != source["dependency_target_id"]
        or not _is_text(row.get("package_id"))
        or any(row.get(key) is not None for key in (
            "object_target_id", "source_unit_id", "module_id",
        ))
    ):
        raise ValueError("RustProjectIR v3 link package mapping is invalid")


def _validate_native_layer(row, requirement_ids: set[str]) -> None:
    name = row.get("portable_name")
    library_format = row.get("library_format")
    if (
        row.get("source_kind") != "external-native-library"
        or not _is_text(row.get("external_dependency_id"))
        or row.get("native_requirement_id") not in requirement_ids
        or not _is_text(name) or not _is_text(library_format)
        or row.get("native_requirement_id") != native_link_requirement_id(
            name, library_format,
        )
        or any(row.get(key) is not None for key in (
            "input_occurrence_id", "binding_sha256", "object_target_id",
            "source_unit_id", "module_id", "package_id", "target_id",
            "system_argument",
        ))
    ):
        raise ValueError("RustProjectIR v3 native link mapping is invalid")


def _validate_system_layer(row) -> None:
    argument = row.get("system_argument")
    if (
        row.get("source_kind") != "system-argument"
        or not _is_text(row.get("external_dependency_id"))
        or not _is_text(argument) or not supported_system_link_argument(argument)
        or any(row.get(key) is not None for key in (
            "input_occurrence_id", "binding_sha256", "object_target_id",
            "source_unit_id", "module_id", "package_id", "target_id",
            "native_requirement_id", "portable_name", "library_format",
        ))
    ):
        raise ValueError("RustProjectIR v3 system link mapping is invalid")


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 4096


__all__ = ["validate_link_target_closure", "validate_target_occurrences"]
