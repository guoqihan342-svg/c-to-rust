from __future__ import annotations

from dataclasses import dataclass

from . import native_object_inspection as native
from ._rust_link_product_common import (
    ET_DYN,
    ET_EXEC,
    MAX_DYNAMIC_ENTRIES,
    MAX_ELF_PROGRAM_HEADERS,
    MAX_INTERPRETER_BYTES,
    ProductFacts,
    dependency_failure,
    fail,
    span,
    uint,
)


_PT_LOAD = 1
_PT_DYNAMIC = 2
_PT_INTERP = 3
_PF_X = 1
_DT_NULL = 0
_DT_FLAGS_1 = 0x6FFFFFFB
_DF_1_PIE = 0x08000000


@dataclass(frozen=True)
class _ProgramHeader:
    kind: int
    flags: int
    offset: int
    virtual_address: int
    file_size: int
    memory_size: int
    alignment: int


def inspect_elf(data: bytes) -> ProductFacts:
    object_type = _raw_elf_type(data)
    try:
        identity = native._parse_elf(data, required_type=object_type)
    except ValueError as error:
        dependency_failure(error)
    if object_type not in {ET_EXEC, ET_DYN}:
        fail("elf_type_unsupported")

    entry, headers, interpreter, dynamic_flags = _program_headers(
        data, identity.class_bits, identity.endianness,
    )
    loads = [header for header in headers if header.kind == _PT_LOAD]
    executable_loads = [
        header for header in loads
        if header.flags & _PF_X and header.memory_size > 0
    ]
    if not loads or not executable_loads:
        fail("elf_load_layout_invalid")
    entry_is_executable = any(
        header.virtual_address <= entry
        and entry - header.virtual_address < header.memory_size
        for header in executable_loads
        if entry >= header.virtual_address
    )
    pie_flag = bool(dynamic_flags & _DF_1_PIE)

    if object_type == ET_EXEC:
        if entry == 0 or not entry_is_executable or pie_flag:
            fail("elf_executable_layout_ambiguous")
        product_kind, elf_type, pie = "bin", "ET_EXEC", False
    else:
        has_dynamic = any(header.kind == _PT_DYNAMIC for header in headers)
        if not has_dynamic:
            fail("elf_dynamic_segment_missing")
        if interpreter or pie_flag:
            if entry == 0 or not entry_is_executable:
                fail("elf_dynamic_layout_ambiguous")
            product_kind, elf_type, pie = "bin", "ET_DYN", True
        else:
            if entry != 0:
                fail("elf_dynamic_layout_ambiguous")
            product_kind, elf_type, pie = "cdylib", "ET_DYN", False

    return ProductFacts(
        product_kind=product_kind,
        object_format="elf",
        elf_type=elf_type,
        pie=pie,
        machine=identity.machine,
        class_bits=identity.class_bits,
        endianness=identity.endianness,
        member_count=0,
        members=(),
    )


def _raw_elf_type(data: bytes) -> int:
    raw = span(data, 16, 2, "elf_header")
    data_code = data[5] if len(data) > 5 else 0
    byteorder = "little" if data_code == 1 else "big"
    return int.from_bytes(raw, byteorder)


def _program_headers(
    data: bytes,
    class_bits: int,
    byteorder: str,
) -> tuple[int, tuple[_ProgramHeader, ...], bool, int]:
    if class_bits == 32:
        entry = uint(data, 24, 4, byteorder, "elf_header")
        table_offset = uint(data, 28, 4, byteorder, "elf_header")
        entry_size = uint(data, 42, 2, byteorder, "elf_header")
        count = uint(data, 44, 2, byteorder, "elf_header")
        header_size, expected_size, table_alignment = 52, 32, 4
    else:
        entry = uint(data, 24, 8, byteorder, "elf_header")
        table_offset = uint(data, 32, 8, byteorder, "elf_header")
        entry_size = uint(data, 54, 2, byteorder, "elf_header")
        count = uint(data, 56, 2, byteorder, "elf_header")
        header_size, expected_size, table_alignment = 64, 56, 8
    if (
        entry_size != expected_size
        or not 0 < count <= MAX_ELF_PROGRAM_HEADERS
        or table_offset < header_size
        or table_offset % table_alignment
    ):
        fail("elf_program_header_layout_invalid")
    span(data, table_offset, count * entry_size, "elf_program_header_table")
    headers = tuple(
        _program_header(data, table_offset + index * entry_size, class_bits, byteorder)
        for index in range(count)
    )
    _validate_segments(data, headers)
    interpreter = _has_interpreter(data, headers)
    dynamic_headers = [header for header in headers if header.kind == _PT_DYNAMIC]
    if len(dynamic_headers) > 1:
        fail("elf_dynamic_segment_ambiguous")
    dynamic_flags = (
        _dynamic_flags(data, dynamic_headers[0], class_bits, byteorder)
        if dynamic_headers
        else 0
    )
    return entry, headers, interpreter, dynamic_flags


def _validate_segments(data: bytes, headers: tuple[_ProgramHeader, ...]) -> None:
    for header in headers:
        if header.file_size:
            span(data, header.offset, header.file_size, "elf_segment")
        if header.alignment not in {0, 1} and (
            header.alignment & (header.alignment - 1)
        ):
            fail("elf_segment_alignment_invalid")
        if header.kind == _PT_LOAD and (
            header.file_size > header.memory_size
            or header.memory_size == 0
            or (
                header.alignment > 1
                and header.offset % header.alignment
                != header.virtual_address % header.alignment
            )
        ):
            fail("elf_load_segment_invalid")


def _has_interpreter(data: bytes, headers: tuple[_ProgramHeader, ...]) -> bool:
    interpreters = [
        (index, header)
        for index, header in enumerate(headers)
        if header.kind == _PT_INTERP
    ]
    if len(interpreters) > 1:
        fail("elf_interpreter_ambiguous")
    if not interpreters:
        return False
    index, header = interpreters[0]
    load_indexes = [
        candidate for candidate, item in enumerate(headers)
        if item.kind == _PT_LOAD
    ]
    if load_indexes and index > min(load_indexes):
        fail("elf_interpreter_order_invalid")
    if (
        header.file_size != header.memory_size
        or not 2 <= header.file_size <= MAX_INTERPRETER_BYTES
    ):
        fail("elf_interpreter_invalid")
    interpreter = span(data, header.offset, header.file_size, "elf_interpreter")
    if interpreter[-1:] != b"\x00" or b"\x00" in interpreter[:-1]:
        fail("elf_interpreter_invalid")
    return True


def _program_header(
    data: bytes,
    offset: int,
    class_bits: int,
    byteorder: str,
) -> _ProgramHeader:
    if class_bits == 32:
        fields = (
            uint(data, offset, 4, byteorder, "elf_program_header"),
            uint(data, offset + 24, 4, byteorder, "elf_program_header"),
            uint(data, offset + 4, 4, byteorder, "elf_program_header"),
            uint(data, offset + 8, 4, byteorder, "elf_program_header"),
            uint(data, offset + 16, 4, byteorder, "elf_program_header"),
            uint(data, offset + 20, 4, byteorder, "elf_program_header"),
            uint(data, offset + 28, 4, byteorder, "elf_program_header"),
        )
    else:
        fields = (
            uint(data, offset, 4, byteorder, "elf_program_header"),
            uint(data, offset + 4, 4, byteorder, "elf_program_header"),
            uint(data, offset + 8, 8, byteorder, "elf_program_header"),
            uint(data, offset + 16, 8, byteorder, "elf_program_header"),
            uint(data, offset + 32, 8, byteorder, "elf_program_header"),
            uint(data, offset + 40, 8, byteorder, "elf_program_header"),
            uint(data, offset + 48, 8, byteorder, "elf_program_header"),
        )
    return _ProgramHeader(*fields)


def _dynamic_flags(
    data: bytes,
    header: _ProgramHeader,
    class_bits: int,
    byteorder: str,
) -> int:
    item_size = 8 if class_bits == 32 else 16
    if (
        header.file_size > header.memory_size
        or header.file_size == 0
        or header.file_size % item_size
        or header.file_size // item_size > MAX_DYNAMIC_ENTRIES
    ):
        fail("elf_dynamic_layout_invalid")
    flags: int | None = None
    null_seen = False
    value_size = item_size // 2
    for offset in range(header.offset, header.offset + header.file_size, item_size):
        tag = uint(data, offset, value_size, byteorder, "elf_dynamic_entry")
        value = uint(
            data, offset + value_size, value_size, byteorder, "elf_dynamic_entry",
        )
        if null_seen:
            if tag != _DT_NULL or value != 0:
                fail("elf_dynamic_terminator_ambiguous")
        elif tag == _DT_NULL:
            null_seen = True
        elif tag == _DT_FLAGS_1:
            if flags is not None:
                fail("elf_dynamic_flags_ambiguous")
            flags = value
    if not null_seen:
        fail("elf_dynamic_terminator_missing")
    return flags or 0
