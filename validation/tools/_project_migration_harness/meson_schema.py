from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .meson_schema_common import (
    MesonSchemaError, boolean_value, object_value, strict_json, string_value,
)
from .meson_schema_metadata import (
    sanitize_build_options, sanitize_buildsystem_files, sanitize_compilers,
    sanitize_dependencies,
)
from .meson_schema_targets import sanitize_targets


REQUIRED_INFORMATION = {
    "targets": "intro-targets.json",
    "buildoptions": "intro-buildoptions.json",
    "dependencies": "intro-dependencies.json",
    "compilers": "intro-compilers.json",
    "buildsystem_files": "intro-buildsystem_files.json",
}
MAX_INFORMATION_ENTRIES = 64


def validate_meson_info(value: Any) -> dict[str, str]:
    obj = object_value(value, "meson_info_schema_invalid")
    if obj.get("error") is not False:
        raise MesonSchemaError("meson_info_error_not_false")
    introspection = object_value(
        obj.get("introspection"), "meson_introspection_schema_invalid"
    )
    version = object_value(
        introspection.get("version"), "meson_introspection_version_invalid"
    )
    major = version.get("major")
    if major != 1 or isinstance(major, bool):
        raise MesonSchemaError("meson_introspection_major_unsupported")
    information = object_value(
        introspection.get("information"), "meson_information_schema_invalid"
    )
    if len(information) > MAX_INFORMATION_ENTRIES:
        raise MesonSchemaError("meson_information_limit_exceeded")
    for name, item in information.items():
        string_value(name, "meson_information_name_invalid")
        entry = object_value(item, "meson_information_entry_invalid")
        filename = string_value(entry.get("file"), "meson_information_file_invalid")
        if PurePosixPath(filename).name != filename or "\\" in filename:
            raise MesonSchemaError("meson_information_file_not_basename")
        boolean_value(entry.get("updated"), "meson_information_updated_invalid")
    for name, filename in REQUIRED_INFORMATION.items():
        entry = information.get(name)
        if not isinstance(entry, dict) or entry.get("file") != filename:
            raise MesonSchemaError(f"meson_{name}_information_mismatch")
    directories = object_value(obj.get("directories"), "meson_directories_schema_invalid")
    return {
        name: string_value(directories.get(name), f"meson_{name}_directory_invalid")
        for name in ("source", "build", "info")
    }


__all__ = [
    "MesonSchemaError", "sanitize_build_options", "sanitize_buildsystem_files",
    "sanitize_compilers", "sanitize_dependencies", "sanitize_targets", "strict_json",
    "validate_meson_info",
]
