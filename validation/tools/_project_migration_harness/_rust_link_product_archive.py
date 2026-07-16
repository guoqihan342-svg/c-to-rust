from __future__ import annotations

import hashlib

from . import native_object_inspection as native
from . import native_object_symbols_archive as archive
from ._rust_link_product_common import (
    ET_REL,
    ProductFacts,
    dependency_failure,
    fail,
)


def inspect_archive(data: bytes) -> ProductFacts:
    parse_data = data
    payload_count: int | None
    try:
        payloads = archive.archive_payloads(parse_data)
    except ValueError as error:
        detail = str(error)
        if detail == "native_object_symbols_archive_duplicate_member_name":
            parse_data = _normalize_special_fields(data)
            if parse_data is None:
                dependency_failure(error)
            payload_count = None
        elif detail != "native_object_symbols_archive_long_name_table_invalid":
            dependency_failure(error)
        else:
            parse_data = _normalize_gnu_long_name_padding(data)
            if parse_data is None:
                dependency_failure(error)
            try:
                payloads = archive.archive_payloads(parse_data)
            except ValueError as normalized_error:
                dependency_failure(normalized_error)
            payload_count = len(payloads)
    else:
        normalized_fields = _normalize_special_fields(data)
        if normalized_fields is None:
            fail("archive_layout_invalid")
        parse_data = normalized_fields
        payload_count = len(payloads)

    objects = _archive_objects(parse_data)
    if not objects or (
        payload_count is not None and len(objects) != payload_count
    ):
        fail("archive_member_set_ambiguous")
    first = objects[0][2]
    abi = (first.class_bits, first.endianness, first.machine)
    if any(
        (identity.class_bits, identity.endianness, identity.machine) != abi
        for _name, _payload, identity in objects[1:]
    ):
        fail("archive_mixed_abi")

    metadata_positions = [
        index for index, (name, _payload, _identity) in enumerate(objects)
        if name == b"lib.rmeta"
    ]
    if metadata_positions and metadata_positions != [0]:
        fail("archive_rust_metadata_ambiguous")
    product_kind = "rlib" if metadata_positions else "staticlib"
    members = tuple(
        {
            "ordinal": ordinal,
            "member_name_sha256": hashlib.sha256(name).hexdigest(),
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "elf_type": "ET_REL",
            "machine": identity.machine,
            "class_bits": identity.class_bits,
            "endianness": identity.endianness,
        }
        for ordinal, (name, payload, identity) in enumerate(objects)
    )
    return ProductFacts(
        product_kind=product_kind,
        object_format="unix-ar",
        elf_type="ET_REL",
        pie=False,
        machine=first.machine,
        class_bits=first.class_bits,
        endianness=first.endianness,
        member_count=len(objects),
        members=members,
    )


def _archive_objects(parse_data: bytes) -> list[tuple[bytes, bytes, object]]:
    try:
        raw_members = native._parse_ar_layout(parse_data)
        long_tables = [member for member in raw_members if member.token == b"//"]
        if len(long_tables) > 1:
            raise ValueError("native_object_archive_duplicate_long_names")
        names = native._parse_gnu_names(long_tables[0].payload) if long_tables else {}
        objects = []
        symbol_index_seen = False
        for member in raw_members:
            if member.token == b"//":
                continue
            name, payload, is_gnu_index = native._resolve_member(member, names)
            if is_gnu_index or name in native._BSD_SYMBOL_NAMES:
                if symbol_index_seen:
                    raise ValueError("native_object_archive_duplicate_symbol_index")
                symbol_index_seen = True
                continue
            identity = native._parse_elf(payload, required_type=ET_REL)
            objects.append((name, payload, identity))
        return objects
    except ValueError as error:
        dependency_failure(error)


def _normalize_gnu_long_name_padding(data: bytes) -> bytes | None:
    """Reclassify GNU's in-table newline as ar padding when that is unique."""
    normalized_fields = _normalize_special_fields(data)
    if normalized_fields is None:
        return None
    try:
        members = native._parse_ar_layout(normalized_fields)
    except ValueError as error:
        dependency_failure(error)
    tables = [member for member in members if member.token == b"//"]
    if len(tables) != 1:
        return None
    payload = tables[0].payload
    if len(payload) < 2 or len(payload) % 2 or payload[-1:] != b"\n":
        return None
    try:
        native._parse_gnu_names(payload[:-1])
    except ValueError:
        return None

    offset = len(archive.AR_MAGIC)
    table_header_offset: int | None = None
    table_size = 0
    while offset < len(normalized_fields):
        header = normalized_fields[offset:offset + 60]
        token = header[:16].rstrip(b" ")
        size = native._numeric_field(header[48:58], 10)
        if token == b"//":
            if table_header_offset is not None:
                return None
            table_header_offset, table_size = offset, size
        offset += 60 + size + (size & 1)
    if table_header_offset is None or table_size != len(payload):
        return None

    encoded_size = str(table_size - 1).encode("ascii")
    if not encoded_size or len(encoded_size) > 10:
        return None
    normalized = bytearray(normalized_fields)
    normalized[
        table_header_offset + 48:table_header_offset + 58
    ] = encoded_size.ljust(10, b" ")
    return bytes(normalized)


def _normalize_special_fields(data: bytes) -> bytes | None:
    """Canonicalize omitted metadata only on recognized GNU ar pseudo-members."""
    if not data.startswith(archive.AR_MAGIC):
        return None
    normalized = bytearray(data)
    offset = len(archive.AR_MAGIC)
    count = 0
    while offset < len(data):
        if len(data) - offset < 60 or count >= archive.MAX_ARCHIVE_MEMBERS:
            return None
        header = data[offset:offset + 60]
        if header[58:60] != b"`\n":
            return None
        token = header[:16].rstrip(b" ")
        raw_size = header[48:58]
        size_text = raw_size.rstrip(b" ")
        if (
            not token
            or not size_text
            or not size_text.isdigit()
            or raw_size != size_text.ljust(10, b" ")
        ):
            return None
        size = int(size_text, 10)
        payload_end = offset + 60 + size
        if payload_end > len(data):
            return None
        if token in {b"/", b"/SYM64/", b"//"}:
            _fill_special_zeros(normalized, header, offset)
        offset = payload_end
        if size & 1:
            if offset >= len(data) or data[offset:offset + 1] != b"\n":
                return None
            offset += 1
        count += 1
    return bytes(normalized) if offset == len(data) else None


def _fill_special_zeros(
    normalized: bytearray,
    header: bytes,
    offset: int,
) -> None:
    for start, end in ((16, 28), (28, 34), (34, 40), (40, 48)):
        if header[start:end] == b" " * (end - start):
            normalized[offset + start:offset + end] = b"0".ljust(
                end - start, b" ",
            )
