from __future__ import annotations

from typing import Any

from .meson_schema_common import (
    MAX_ARRAY_ITEMS, MAX_PATH_REFERENCES, MAX_TARGETS, MesonSchemaError,
    array_value, boolean_value, command_value, object_value, string_array,
    string_list, string_value, summary,
)


TARGET_TYPES = {
    "custom", "executable", "jar", "run", "shared library", "shared module",
    "static library",
}


def sanitize_targets(value: Any) -> list[dict[str, Any]]:
    items = array_value(value, "meson_targets_schema_invalid", MAX_TARGETS)
    result: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    path_count = 0
    for item in items:
        obj = object_value(item, "meson_target_schema_invalid")
        identifier = string_value(obj.get("id"), "meson_target_id_invalid")
        if identifier in identifiers:
            raise MesonSchemaError("meson_target_id_duplicate")
        identifiers.add(identifier)
        target_type = string_value(obj.get("type"), "meson_target_type_invalid")
        if target_type not in TARGET_TYPES:
            raise MesonSchemaError("meson_target_type_unsupported")
        outputs = string_list(obj.get("filename"), "meson_target_filename_invalid")
        if not outputs and target_type != "run":
            raise MesonSchemaError("meson_target_output_missing")
        groups, group_paths = _source_groups(obj.get("target_sources", []))
        extra_files = string_array(
            obj.get("extra_files", []), "meson_target_extra_files_invalid"
        )
        target_ids = _unique_strings(obj.get("depends", []), "meson_target_depends_invalid")
        external = _unique_strings(
            obj.get("dependencies", []), "meson_target_dependencies_invalid"
        )
        path_count += 1 + len(outputs) + len(extra_files) + group_paths
        if path_count > MAX_PATH_REFERENCES:
            raise MesonSchemaError("meson_path_reference_limit_exceeded")
        current = {
            "id": identifier,
            "name": string_value(obj.get("name"), "meson_target_name_invalid"),
            "type": target_type,
            "defined_in_path": string_value(
                obj.get("defined_in"), "meson_target_defined_in_invalid"
            ),
            "output_paths": outputs,
            "extra_file_paths": extra_files,
            "build_by_default": boolean_value(
                obj.get("build_by_default"), "meson_build_by_default_invalid"
            ),
            "installed": boolean_value(obj.get("installed"), "meson_installed_invalid"),
            "target_dependency_ids": target_ids,
            "external_dependency_names": external,
            "source_groups": groups,
        }
        subproject = obj.get("subproject")
        if subproject is not None:
            current["subproject"] = string_value(
                subproject, "meson_target_subproject_invalid"
            )
        result.append(current)
    _validate_target_dependencies(result, identifiers)
    return result


def _source_groups(value: Any) -> tuple[list[dict[str, Any]], int]:
    groups = array_value(value, "meson_target_sources_invalid", MAX_ARRAY_ITEMS)
    result: list[dict[str, Any]] = []
    path_count = 0
    for item in groups:
        obj = object_value(item, "meson_target_source_invalid")
        parameters = string_array(
            obj.get("parameters", []), "meson_target_parameters_invalid"
        )
        if "language" in obj:
            sources = string_array(obj.get("sources", []), "meson_sources_invalid")
            generated = string_array(
                obj.get("generated_sources", []), "meson_generated_sources_invalid"
            )
            current = {
                "kind": "compiler",
                "language": string_value(obj["language"], "meson_language_invalid"),
                "compiler_summary": summary(command_value(obj.get("compiler"))),
                "parameters_summary": summary(parameters),
                "source_paths": sources,
                "generated_source_paths": generated,
            }
            if "machine" in obj:
                current["machine"] = string_value(
                    obj["machine"], "meson_machine_invalid"
                )
            path_count += len(sources) + len(generated)
        elif "linker" in obj:
            current = {
                "kind": "linker",
                "linker_summary": summary(command_value(obj["linker"])),
                "parameters_summary": summary(parameters),
            }
        else:
            raise MesonSchemaError("meson_target_source_kind_invalid")
        result.append(current)
    return result, path_count


def _unique_strings(value: Any, code: str) -> list[str]:
    items = string_array(value, code)
    if len(items) != len(set(items)):
        raise MesonSchemaError(code.replace("_invalid", "_duplicate"))
    return sorted(items)


def _validate_target_dependencies(
    targets: list[dict[str, Any]], identifiers: set[str],
) -> None:
    for target in targets:
        if any(item not in identifiers for item in target["target_dependency_ids"]):
            raise MesonSchemaError("meson_target_dependency_id_unknown")


__all__ = ["TARGET_TYPES", "sanitize_targets"]
