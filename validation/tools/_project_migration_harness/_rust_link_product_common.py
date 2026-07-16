from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from . import native_object_inspection as native
from . import native_object_symbols_archive as archive


MAX_RUST_LINK_PRODUCT_BYTES = native.MAX_NATIVE_OBJECT_BYTES
MAX_ELF_PROGRAM_HEADERS = 4_096
MAX_DYNAMIC_ENTRIES = 65_536
MAX_INTERPRETER_BYTES = 4_096
MAX_ARCHIVE_MEMBERS = archive.MAX_ARCHIVE_MEMBERS
RUST_LINK_PRODUCT_INSPECTION_KIND = "rust-link-product-inspection"

ELF_MAGIC = b"\x7fELF"
AR_MAGIC = archive.AR_MAGIC
ET_REL = 1
ET_EXEC = 2
ET_DYN = 3
PRODUCT_OBJECT_KIND = {
    "bin": "executable",
    "cdylib": "dynamic-library",
    "staticlib": "static-library",
    "rlib": "rust-library",
}


@dataclass(frozen=True)
class ProductFacts:
    product_kind: str
    object_format: str
    elf_type: str
    pie: bool
    machine: int
    class_bits: int
    endianness: str
    member_count: int
    member_identity_sha256: str


def uint(
    data: bytes,
    offset: int,
    size: int,
    byteorder: str,
    label: str,
) -> int:
    return int.from_bytes(span(data, offset, size, label), byteorder)


def span(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        fail(f"{label}_truncated")
    return data[offset:offset + size]


def dependency_failure(error: ValueError) -> NoReturn:
    detail = str(error)
    if (
        not detail
        or len(detail) > 128
        or any(
            not (
                character.isascii()
                and (character.isalnum() or character == "_")
            )
            for character in detail
        )
    ):
        detail = "dependency_structure_invalid"
    raise ValueError(f"rust_link_product_{detail}") from error


def fail(code: str) -> NoReturn:
    raise ValueError(f"rust_link_product_{code}")
