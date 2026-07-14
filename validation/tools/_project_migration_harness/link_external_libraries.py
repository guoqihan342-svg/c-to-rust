from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

from .build_facts import is_absolute_any_platform, json_sha256, summarize_path


MAX_EXTERNAL_NATIVE_LIBRARIES = 16_384
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PORTABLE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}$")
_POSIX_SHARED = re.compile(
    r"^lib[A-Za-z0-9][A-Za-z0-9_+.-]{0,110}\.so(?:\.[0-9]+)*$",
    re.IGNORECASE,
)


def external_native_library(
    repo_root: Path, base: Path, value: str, *, argument_index: int,
) -> dict[str, Any] | None:
    """Describe an external native library without retaining its host path."""
    if (
        not is_absolute_any_platform(value)
        or summarize_path(value, repo_root, base).get("scope") != "external"
    ):
        return None
    name = value.replace("\\", "/").rsplit("/", 1)[-1]
    library_format = native_library_format(name)
    if library_format is None:
        return None
    return {
        "argument_index": argument_index,
        "format": library_format,
        "name": name,
        "resolution": "unresolved-host-native-link",
        "resolved": False,
        "source_argument_sha256": json_sha256(value),
    }


def native_library_format(name: Any) -> str | None:
    if not isinstance(name, str) or _PORTABLE_NAME.fullmatch(name) is None:
        return None
    lowered = name.lower()
    if _POSIX_SHARED.fullmatch(name) or lowered.endswith((".dylib", ".dll")):
        return "shared-library"
    if lowered.endswith(".a") and lowered.startswith("lib"):
        return "static-archive"
    if lowered.endswith(".lib"):
        return "import-or-static-library"
    return None


def validate_external_native_libraries(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_EXTERNAL_NATIVE_LIBRARIES:
        raise ValueError("external_native_library_list_invalid")
    result = []
    positions = []
    fields = {
        "argument_index", "format", "name", "resolution", "resolved",
        "source_argument_sha256",
    }
    for item in value:
        if not isinstance(item, Mapping) or set(item) != fields:
            raise ValueError("external_native_library_schema_invalid")
        current = dict(item)
        position = current["argument_index"]
        if (
            isinstance(position, bool) or not isinstance(position, int)
            or position < 0
            or native_library_format(current["name"]) != current["format"]
            or current["resolution"] != "unresolved-host-native-link"
            or current["resolved"] is not False
            or not isinstance(current["source_argument_sha256"], str)
            or _SHA256.fullmatch(current["source_argument_sha256"]) is None
        ):
            raise ValueError("external_native_library_schema_invalid")
        positions.append(position)
        result.append(current)
    if positions != sorted(set(positions)):
        raise ValueError("external_native_library_order_invalid")
    return result


__all__ = [
    "external_native_library", "native_library_format",
    "validate_external_native_libraries",
]
