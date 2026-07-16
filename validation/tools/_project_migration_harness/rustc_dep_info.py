from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .sandbox_execution_schema import is_sha256


SCHEMA_VERSION = 1
MAX_RUSTC_DEP_INFO_BYTES = 8 * 1024 * 1024
MAX_RUSTC_DEPENDENCY_COUNT = 16_384
_TARGET_ROOT = PurePosixPath("/runtime/target")
_SOURCE_ROOT = PurePosixPath("/workspace")
_TOP_KEYS = {
    "schema_version", "product_guest_path_sha256", "source_count", "sources",
    "source_order_sha256", "raw_sha256", "semantic_gate",
    "translation_coverage_numerator",
}
_SOURCE_KEYS = {"ordinal", "guest_path_sha256"}


def parse_rustc_dep_info(data: bytes) -> dict[str, Any]:
    if type(data) is not bytes:
        raise TypeError("rustc dep-info input must be bytes")
    if not data or len(data) > MAX_RUSTC_DEP_INFO_BYTES:
        raise ValueError("rustc_dep_info_input_limit")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("rustc_dep_info_not_utf8") from error
    if "\x00" in text or "\r" in text.replace("\r\n", ""):
        raise ValueError("rustc_dep_info_control_character")
    logical = text.replace("\\\r\n", " ").replace("\\\n", " ")
    first = logical.splitlines()[0] if logical.splitlines() else ""
    target, separator, dependencies = first.partition(": ")
    if not separator or not dependencies:
        raise ValueError("rustc_dep_info_primary_rule_invalid")
    product = _guest_path(target, _TARGET_ROOT, "product")
    tokens = dependencies.split()
    if not tokens or len(tokens) > MAX_RUSTC_DEPENDENCY_COUNT:
        raise ValueError("rustc_dep_info_dependency_count_invalid")
    paths = [_guest_path(item, _SOURCE_ROOT, "source") for item in tokens]
    if len(paths) != len(set(paths)):
        raise ValueError("rustc_dep_info_source_duplicate")
    sources = [
        {
            "ordinal": ordinal,
            "guest_path_sha256": hashlib.sha256(
                path.encode("utf-8"),
            ).hexdigest(),
        }
        for ordinal, path in enumerate(paths)
    ]
    result = {
        "schema_version": SCHEMA_VERSION,
        "product_guest_path_sha256": hashlib.sha256(
            product.encode("utf-8"),
        ).hexdigest(),
        "source_count": len(sources), "sources": sources,
        "source_order_sha256": content_sha256(sources),
        "raw_sha256": hashlib.sha256(data).hexdigest(),
        "semantic_gate": False, "translation_coverage_numerator": 0,
    }
    return validate_rustc_dep_info(result)


def validate_rustc_dep_info(
    value: Any, source: bytes | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("rustc_dep_info_schema_invalid")
    sources = value.get("sources")
    if not isinstance(sources, list) or not sources \
            or len(sources) > MAX_RUSTC_DEPENDENCY_COUNT:
        raise ValueError("rustc_dep_info_sources_invalid")
    normalized = []
    for ordinal, item in enumerate(sources):
        if not isinstance(item, Mapping) or set(item) != _SOURCE_KEYS \
                or item.get("ordinal") != ordinal \
                or not is_sha256(item.get("guest_path_sha256")):
            raise ValueError("rustc_dep_info_source_invalid")
        normalized.append(dict(item))
    if (
        value.get("schema_version") != SCHEMA_VERSION
        or value.get("source_count") != len(normalized)
        or not is_sha256(value.get("product_guest_path_sha256"))
        or value.get("source_order_sha256") != content_sha256(normalized)
        or not is_sha256(value.get("raw_sha256"))
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("rustc_dep_info_invalid")
    result = dict(value)
    if source is not None and result != parse_rustc_dep_info(source):
        raise ValueError("rustc_dep_info_source_reparse_drift")
    return result


def _guest_path(value: str, root: PurePosixPath, label: str) -> str:
    if not value or "\\" in value or any(character.isspace() for character in value):
        raise ValueError(f"rustc_dep_info_{label}_path_invalid")
    path = PurePosixPath(value)
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(f"rustc_dep_info_{label}_root_invalid") from error
    if (
        not path.is_absolute() or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or path.as_posix() != value
    ):
        raise ValueError(f"rustc_dep_info_{label}_path_invalid")
    return value


__all__ = [
    "MAX_RUSTC_DEPENDENCY_COUNT", "MAX_RUSTC_DEP_INFO_BYTES",
    "SCHEMA_VERSION", "parse_rustc_dep_info", "validate_rustc_dep_info",
]
