from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import re
from typing import Any

from .artifacts import content_sha256
from .c_toolchain_files import read_stable_file
from .native_object_symbols_parsing import (
    MAX_SYMBOL_NAME_BYTES, MAX_SYMBOLS, MAX_SYMBOL_SET_UTF8_BYTES,
    parse_native_object_symbols,
)


MAX_NATIVE_OBJECT_BYTES = 256 * 1024 * 1024
NATIVE_OBJECT_SYMBOLS_KIND = "native-object-symbols"
_FIELDS = {
    "schema_version", "artifact_kind", "object_format", "object_kind",
    "member_count", "symbols", "symbol_count", "file_sha256", "size_bytes",
    "symbol_set_sha256", "semantic_gate", "report_sha256",
}
_FORMAT_KIND = {"elf": "shared-object", "unix-ar": "static-archive"}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def extract_native_object_symbols(
    path: Path | str, *, limit: int = MAX_NATIVE_OBJECT_BYTES,
) -> dict[str, Any]:
    """Extract a deterministic, path-free set of native definitions."""
    if type(limit) is not int or not 0 < limit <= MAX_NATIVE_OBJECT_BYTES:
        raise ValueError("native_object_symbols_limit_invalid")
    data, identity = read_stable_file(Path(path), limit)
    object_format, object_kind, member_count, symbols = (
        parse_native_object_symbols(data)
    )
    core = {
        "schema_version": 1,
        "artifact_kind": NATIVE_OBJECT_SYMBOLS_KIND,
        "object_format": object_format,
        "object_kind": object_kind,
        "member_count": member_count,
        "symbols": symbols,
        "symbol_count": len(symbols),
        "file_sha256": identity["sha256"],
        "size_bytes": identity["size_bytes"],
        "symbol_set_sha256": content_sha256(symbols),
        "semantic_gate": False,
    }
    return validate_native_object_symbols({
        **core, "report_sha256": content_sha256(core),
    })


def validate_native_object_symbols(value: Any) -> dict[str, Any]:
    """Validate report shape and independently recompute all derived claims."""
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("native_object_symbols_report_schema_invalid")
    result = dict(value)
    object_format = result.get("object_format")
    member_count = result.get("member_count")
    symbols = result.get("symbols")
    size = result.get("size_bytes")
    hashes = (
        result.get("file_sha256"), result.get("symbol_set_sha256"),
        result.get("report_sha256"),
    )
    if (
        type(result.get("schema_version")) is not int
        or result.get("schema_version") != 1
        or result.get("artifact_kind") != NATIVE_OBJECT_SYMBOLS_KIND
        or type(object_format) is not str or object_format not in _FORMAT_KIND
        or result.get("object_kind") != _FORMAT_KIND.get(object_format)
        or type(member_count) is not int or member_count <= 0
        or (object_format == "elf" and member_count != 1)
        or not isinstance(symbols, list) or len(symbols) > MAX_SYMBOLS
        or any(type(symbol) is not str or not symbol or "\x00" in symbol for symbol in symbols)
        or type(result.get("symbol_count")) is not int
        or result.get("symbol_count") != len(symbols)
        or type(size) is not int or not 0 < size <= MAX_NATIVE_OBJECT_BYTES
        or any(type(item) is not str or _SHA256.fullmatch(item) is None for item in hashes)
        or result.get("semantic_gate") is not False
    ):
        raise ValueError("native_object_symbols_report_invalid")
    encoded_total = 0
    try:
        for symbol in symbols:
            encoded_size = len(symbol.encode("utf-8"))
            if (
                encoded_size > MAX_SYMBOL_NAME_BYTES
                or encoded_size > MAX_SYMBOL_SET_UTF8_BYTES - encoded_total
            ):
                raise ValueError("native_object_symbols_report_invalid")
            encoded_total += encoded_size
    except UnicodeEncodeError as error:
        raise ValueError("native_object_symbols_report_invalid") from error
    if symbols != sorted(set(symbols)):
        raise ValueError("native_object_symbols_report_invalid")
    if result["symbol_set_sha256"] != content_sha256(symbols):
        raise ValueError("native_object_symbols_symbol_set_sha256_drift")
    core = {key: result[key] for key in _FIELDS if key != "report_sha256"}
    if result["report_sha256"] != content_sha256(core):
        raise ValueError("native_object_symbols_report_sha256_drift")
    return result


def reopen_native_object_symbols(
    path: Path | str, stored: Any, *, limit: int = MAX_NATIVE_OBJECT_BYTES,
) -> dict[str, Any]:
    """Strictly reopen the source bytes and reject any report or file drift."""
    validated = validate_native_object_symbols(stored)
    current = extract_native_object_symbols(path, limit=limit)
    if current != validated:
        raise ValueError("native_object_symbols_reopen_drift")
    return current


__all__ = [
    "MAX_NATIVE_OBJECT_BYTES", "MAX_SYMBOL_NAME_BYTES", "MAX_SYMBOLS",
    "MAX_SYMBOL_SET_UTF8_BYTES", "NATIVE_OBJECT_SYMBOLS_KIND",
    "extract_native_object_symbols", "reopen_native_object_symbols",
    "validate_native_object_symbols",
]
