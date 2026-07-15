from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import re

from .artifacts import content_sha256
from .native_object_inspection import MAX_NATIVE_OBJECT_BYTES


_INSPECTION_KEYS = {
    "schema_version", "artifact_kind", "object_format", "object_kind",
    "machine", "class_bits", "endianness", "member_count",
    "member_identity_sha256", "file_sha256", "size_bytes", "semantic_gate",
    "inspection_sha256",
}
_FORMAT_KIND = {
    "elf": "shared-object",
    "unix-ar": "static-archive",
}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def validate_native_object_inspection(value: Any) -> dict[str, Any]:
    """Reopen a path-free ELF/ar inspection without trusting its producer."""
    if not isinstance(value, Mapping) or set(value) != _INSPECTION_KEYS:
        raise ValueError("native_object_inspection_schema_invalid")
    result = dict(value)
    object_format = result.get("object_format")
    member_count = result.get("member_count")
    hashes = (
        result.get("member_identity_sha256"),
        result.get("file_sha256"),
        result.get("inspection_sha256"),
    )
    if (
        result.get("schema_version") != 1
        or result.get("artifact_kind") != "native-object-inspection"
        or object_format not in _FORMAT_KIND
        or result.get("object_kind") != _FORMAT_KIND.get(object_format)
        or type(result.get("machine")) is not int or result["machine"] <= 0
        or result.get("class_bits") not in {32, 64}
        or result.get("endianness") not in {"little", "big"}
        or type(member_count) is not int or member_count <= 0
        or (object_format == "elf" and member_count != 1)
        or type(result.get("size_bytes")) is not int
        or not 0 < result["size_bytes"] <= MAX_NATIVE_OBJECT_BYTES
        or any(type(item) is not str or _SHA256.fullmatch(item) is None for item in hashes)
        or result.get("semantic_gate") is not False
    ):
        raise ValueError("native_object_inspection_summary_invalid")
    claimed = result.pop("inspection_sha256")
    if claimed != content_sha256(result):
        raise ValueError("native_object_inspection_sha256_drift")
    return {**result, "inspection_sha256": claimed}


__all__ = ["validate_native_object_inspection"]
