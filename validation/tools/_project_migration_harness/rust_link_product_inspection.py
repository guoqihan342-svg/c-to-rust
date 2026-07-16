from __future__ import annotations

from collections.abc import Mapping
import hashlib
import re
from typing import Any

from ._rust_link_product_archive import inspect_archive
from ._rust_link_product_common import (
    AR_MAGIC,
    ELF_MAGIC,
    MAX_ARCHIVE_MEMBERS,
    MAX_DYNAMIC_ENTRIES,
    MAX_ELF_PROGRAM_HEADERS,
    MAX_INTERPRETER_BYTES,
    MAX_RUST_LINK_PRODUCT_BYTES,
    PRODUCT_OBJECT_KIND,
    RUST_LINK_PRODUCT_INSPECTION_KIND,
    fail,
)
from ._rust_link_product_elf import inspect_elf
from .artifacts import content_sha256


_FIELD_ORDER = (
    "schema_version",
    "artifact_kind",
    "product_kind",
    "object_kind",
    "object_format",
    "elf_type",
    "pie",
    "machine",
    "class_bits",
    "endianness",
    "member_count",
    "member_identity_sha256",
    "file_sha256",
    "size_bytes",
    "semantic_gate",
    "translation_coverage_numerator",
    "inspection_sha256",
)
_FIELDS = set(_FIELD_ORDER)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def inspect_rust_link_product(
    data: bytes,
    product_kind: str,
    *,
    limit: int = MAX_RUST_LINK_PRODUCT_BYTES,
) -> dict[str, Any]:
    """Inspect one final Cargo product without paths, tools, or host metadata."""
    if type(limit) is not int or not 0 < limit <= MAX_RUST_LINK_PRODUCT_BYTES:
        fail("limit_invalid")
    if type(data) is not bytes or not data or len(data) > limit:
        fail("bytes_invalid")
    if type(product_kind) is not str or product_kind not in PRODUCT_OBJECT_KIND:
        fail("product_kind_invalid")

    if data.startswith(ELF_MAGIC):
        facts = inspect_elf(data)
    elif data.startswith(AR_MAGIC):
        facts = inspect_archive(data)
    else:
        fail("format_invalid")
    if facts.product_kind != product_kind:
        fail("type_mismatch")

    core = {
        "schema_version": 1,
        "artifact_kind": RUST_LINK_PRODUCT_INSPECTION_KIND,
        "product_kind": facts.product_kind,
        "object_kind": PRODUCT_OBJECT_KIND[facts.product_kind],
        "object_format": facts.object_format,
        "elf_type": facts.elf_type,
        "pie": facts.pie,
        "machine": facts.machine,
        "class_bits": facts.class_bits,
        "endianness": facts.endianness,
        "member_count": facts.member_count,
        "member_identity_sha256": facts.member_identity_sha256,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return validate_rust_link_product_inspection({
        **core,
        "inspection_sha256": content_sha256(core),
    })


def inspect_rust_link_product_bytes(
    data: bytes,
    product_kind: str,
    *,
    limit: int = MAX_RUST_LINK_PRODUCT_BYTES,
) -> dict[str, Any]:
    """Explicit bytes-named alias for callers that expose several inspectors."""
    return inspect_rust_link_product(data, product_kind, limit=limit)


def validate_rust_link_product_inspection(value: Any) -> dict[str, Any]:
    """Validate the canonical, path-free inspection and its content hash."""
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        fail("report_schema_invalid")
    result = {key: value[key] for key in _FIELD_ORDER}
    product_kind = result.get("product_kind")
    object_format = result.get("object_format")
    elf_type = result.get("elf_type")
    class_bits = result.get("class_bits")
    endianness = result.get("endianness")
    member_count = result.get("member_count")
    hashes = (
        result.get("member_identity_sha256"),
        result.get("file_sha256"),
        result.get("inspection_sha256"),
    )
    if (
        type(result.get("schema_version")) is not int
        or result["schema_version"] != 1
        or result.get("artifact_kind") != RUST_LINK_PRODUCT_INSPECTION_KIND
        or type(product_kind) is not str
        or product_kind not in PRODUCT_OBJECT_KIND
        or result.get("object_kind") != PRODUCT_OBJECT_KIND.get(product_kind)
        or type(object_format) is not str
        or object_format not in {"elf", "unix-ar"}
        or type(elf_type) is not str
        or elf_type not in {"ET_REL", "ET_EXEC", "ET_DYN"}
        or type(result.get("pie")) is not bool
        or type(result.get("machine")) is not int
        or not 0 < result["machine"] <= 0xFFFF
        or type(class_bits) is not int
        or class_bits not in {32, 64}
        or type(endianness) is not str
        or endianness not in {"little", "big"}
        or type(member_count) is not int
        or not 0 < member_count <= MAX_ARCHIVE_MEMBERS
        or type(result.get("size_bytes")) is not int
        or not 0 < result["size_bytes"] <= MAX_RUST_LINK_PRODUCT_BYTES
        or any(
            type(item) is not str or _SHA256.fullmatch(item) is None
            for item in hashes
        )
        or result.get("semantic_gate") is not False
        or type(result.get("translation_coverage_numerator")) is not int
        or result["translation_coverage_numerator"] != 0
        or not _valid_type_shape(
            product_kind, object_format, elf_type, result["pie"], member_count,
        )
    ):
        fail("report_invalid")

    core = {key: result[key] for key in _FIELD_ORDER[:-1]}
    if result["inspection_sha256"] != content_sha256(core):
        fail("inspection_sha256_drift")
    return {**core, "inspection_sha256": result["inspection_sha256"]}


def reopen_rust_link_product_inspection(
    data: bytes,
    stored: Any,
    *,
    limit: int = MAX_RUST_LINK_PRODUCT_BYTES,
) -> dict[str, Any]:
    """Reinspect the supplied bytes and reject report or product-byte drift."""
    validated = validate_rust_link_product_inspection(stored)
    current = inspect_rust_link_product(
        data, validated["product_kind"], limit=limit,
    )
    if current != validated:
        fail("reopen_drift")
    return current


def _valid_type_shape(
    product_kind: str,
    object_format: str,
    elf_type: str,
    pie: bool,
    member_count: int,
) -> bool:
    if product_kind == "bin":
        return (
            object_format == "elf"
            and member_count == 1
            and (
                (elf_type == "ET_EXEC" and not pie)
                or (elf_type == "ET_DYN" and pie)
            )
        )
    if product_kind == "cdylib":
        return (
            object_format == "elf"
            and elf_type == "ET_DYN"
            and not pie
            and member_count == 1
        )
    return object_format == "unix-ar" and elf_type == "ET_REL" and not pie


__all__ = [
    "MAX_DYNAMIC_ENTRIES",
    "MAX_ELF_PROGRAM_HEADERS",
    "MAX_INTERPRETER_BYTES",
    "MAX_RUST_LINK_PRODUCT_BYTES",
    "RUST_LINK_PRODUCT_INSPECTION_KIND",
    "inspect_rust_link_product",
    "inspect_rust_link_product_bytes",
    "reopen_rust_link_product_inspection",
    "validate_rust_link_product_inspection",
]
