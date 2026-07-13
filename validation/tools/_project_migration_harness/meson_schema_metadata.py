from __future__ import annotations

from typing import Any

from .meson_schema_common import (
    MAX_BUILDSYSTEM_FILES, MAX_COMPILERS, MAX_DEPENDENCIES, MAX_OPTIONS,
    MesonSchemaError, array_value, command_value, object_value, string_array,
    string_value, summarizable, summary,
)


DEPENDENCY_SUMMARY_FIELDS = {
    "compile_args", "extra_files", "include_directories", "link_args", "sources",
}


def sanitize_build_options(value: Any) -> tuple[list[dict[str, Any]], bool]:
    items = array_value(value, "meson_buildoptions_schema_invalid", MAX_OPTIONS)
    result: list[dict[str, Any]] = []
    backend_values: list[Any] = []
    for item in items:
        obj = object_value(item, "meson_buildoption_schema_invalid")
        name = string_value(obj.get("name"), "meson_buildoption_name_invalid")
        option_value = summarizable(
            obj.get("value"), "meson_buildoption_value_invalid"
        )
        if name == "backend":
            backend_values.append(obj.get("value"))
        current = {
            "name": name,
            "type": string_value(obj.get("type"), "meson_buildoption_type_invalid"),
            "section": string_value(
                obj.get("section"), "meson_buildoption_section_invalid"
            ),
            "machine": string_value(
                obj.get("machine"), "meson_buildoption_machine_invalid"
            ),
            "value_summary": summary(option_value),
        }
        if "choices" in obj:
            current["choices_summary"] = summary(
                summarizable(obj["choices"], "meson_buildoption_choices_invalid")
            )
        result.append(current)
    return result, backend_values == ["ninja"]


def sanitize_dependencies(value: Any) -> list[dict[str, Any]]:
    items = array_value(value, "meson_dependencies_schema_invalid", MAX_DEPENDENCIES)
    result: list[dict[str, Any]] = []
    for item in items:
        obj = object_value(item, "meson_dependency_schema_invalid")
        current: dict[str, Any] = {
            "name": string_value(obj.get("name"), "meson_dependency_name_invalid"),
            "target_dependency_ids": _unique_strings(
                obj.get("depends", []), "meson_dependency_depends_invalid"
            ),
            "external_dependency_names": _unique_strings(
                obj.get("dependencies", []), "meson_dependency_dependencies_invalid"
            ),
        }
        for field in ("type", "version"):
            if field in obj:
                current[field] = string_value(
                    obj[field], f"meson_dependency_{field}_invalid"
                )
        for field in sorted(DEPENDENCY_SUMMARY_FIELDS):
            if field in obj:
                current[f"{field}_summary"] = summary(
                    string_array(obj[field], f"meson_dependency_{field}_invalid")
                )
        result.append(current)
    return result


def sanitize_compilers(value: Any) -> dict[str, list[dict[str, Any]]]:
    obj = object_value(value, "meson_compilers_schema_invalid")
    if set(obj) != {"host", "build"}:
        raise MesonSchemaError("meson_compiler_machines_invalid")
    result: dict[str, list[dict[str, Any]]] = {"host": [], "build": []}
    total = 0
    for machine in ("host", "build"):
        languages = object_value(obj[machine], "meson_compiler_languages_invalid")
        for language, raw in sorted(languages.items()):
            total += 1
            if total > MAX_COMPILERS:
                raise MesonSchemaError("meson_compiler_limit_exceeded")
            string_value(language, "meson_compiler_language_invalid")
            compiler = object_value(raw, "meson_compiler_schema_invalid")
            result[machine].append({
                "language": language,
                "id": string_value(compiler.get("id"), "meson_compiler_id_invalid"),
                "version": string_value(
                    compiler.get("version"), "meson_compiler_version_invalid"
                ),
                "full_version": string_value(
                    compiler.get("full_version"), "meson_compiler_full_version_invalid"
                ),
                "linker_id": string_value(
                    compiler.get("linker_id"), "meson_compiler_linker_id_invalid"
                ),
                "default_suffix": string_value(
                    compiler.get("default_suffix"),
                    "meson_compiler_default_suffix_invalid",
                ),
                "exelist_summary": summary(command_value(compiler.get("exelist"))),
                "linker_exelist_summary": summary(
                    command_value(compiler.get("linker_exelist"))
                ),
                "file_suffixes_summary": summary(
                    string_array(
                        compiler.get("file_suffixes"),
                        "meson_compiler_file_suffixes_invalid",
                    )
                ),
            })
    return result


def sanitize_buildsystem_files(value: Any) -> list[str]:
    paths = string_array(
        value, "meson_buildsystem_files_invalid", limit=MAX_BUILDSYSTEM_FILES
    )
    if len(paths) != len(set(paths)):
        raise MesonSchemaError("meson_buildsystem_file_duplicate")
    return sorted(paths)


def _unique_strings(value: Any, code: str) -> list[str]:
    items = string_array(value, code)
    if len(items) != len(set(items)):
        raise MesonSchemaError(code.replace("_invalid", "_duplicate"))
    return sorted(items)


__all__ = [
    "sanitize_build_options", "sanitize_buildsystem_files", "sanitize_compilers",
    "sanitize_dependencies",
]
