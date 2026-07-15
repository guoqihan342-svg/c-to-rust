from __future__ import annotations

from dataclasses import dataclass
import struct
from typing import Sequence

from validation.tools.project_migration_native_object_archive_test_support import (
    ar_member, archive, duplicate_archives, indexed_archives,
)


@dataclass(frozen=True)
class Symbol:
    name: str
    binding: int = 1
    defined: bool = True
    visibility: int = 0
    name_offset: int | None = None
    section_index: int | None = None


def elf_object(
    class_bits: int,
    endianness: str,
    *,
    object_type: int,
    tables: Sequence[tuple[str, Sequence[Symbol]]],
    machine: int | None = None,
) -> bytes:
    prefix = "<" if endianness == "little" else ">"
    header_size = 52 if class_bits == 32 else 64
    section_size = 40 if class_bits == 32 else 64
    symbol_size = 16 if class_bits == 32 else 24
    table_names = []
    for table_kind, _table_symbols in tables:
        if table_kind not in {"dynsym", "symtab"}:
            raise AssertionError("unsupported test symbol table")
        table_names.extend((
            ".dynstr" if table_kind == "dynsym" else ".strtab",
            f".{table_kind}",
        ))
    section_names = ["", ".shstrtab", *table_names, ".text"]
    shstr, shstr_offsets = _string_bytes(section_names)
    text_index = len(section_names) - 1
    payloads: list[bytes] = [b"", shstr]
    section_specs: list[dict[str, int]] = [
        _section_spec(0, 0, 0, 0, 0),
        _section_spec(shstr_offsets[".shstrtab"], 3, 0, 1, 0),
    ]
    for table_kind, symbols in tables:
        string_name = ".dynstr" if table_kind == "dynsym" else ".strtab"
        symbol_name = f".{table_kind}"
        strings, offsets = _symbol_strings(symbols)
        string_index = len(section_specs)
        payloads.append(strings)
        section_specs.append(_section_spec(
            shstr_offsets[string_name], 3, 0, 1, 0,
        ))
        encoded_symbols = _symbols(
            class_bits, prefix, symbols, offsets, text_index,
        )
        payloads.append(encoded_symbols)
        section_specs.append(_section_spec(
            shstr_offsets[symbol_name],
            11 if table_kind == "dynsym" else 2,
            string_index,
            8 if class_bits == 64 else 4,
            symbol_size,
            info=1,
        ))
    payloads.append(b"\x90")
    section_specs.append(_section_spec(
        shstr_offsets[".text"], 1, 0, 1, 0,
    ))
    image = bytearray(b"\x00" * header_size)
    for payload, spec in zip(payloads[1:], section_specs[1:], strict=True):
        _align(image, spec["alignment"])
        spec["offset"] = len(image)
        spec["size"] = len(payload)
        image.extend(payload)
    _align(image, 8 if class_bits == 64 else 4)
    section_offset = len(image)
    for spec in section_specs:
        image.extend(_section_header(class_bits, prefix, spec))
    ident = (
        b"\x7fELF"
        + bytes((1 if class_bits == 32 else 2, 1 if endianness == "little" else 2, 1, 0, 0))
        + b"\x00" * 7
    )
    selected_machine = machine if machine is not None else (3 if class_bits == 32 else 62)
    if class_bits == 32:
        header = struct.pack(
            prefix + "HHIIIIIHHHHHH",
            object_type, selected_machine, 1, 0, 0, section_offset, 0,
            header_size, 32, 0, section_size, len(section_specs), 1,
        )
    else:
        header = struct.pack(
            prefix + "HHIQQQIHHHHHH",
            object_type, selected_machine, 1, 0, 0, section_offset, 0,
            header_size, 56, 0, section_size, len(section_specs), 1,
        )
    image[:header_size] = ident + header
    return bytes(image)


def patch_section(
    data: bytes, section_index: int, field: str, value: int,
) -> bytes:
    result = bytearray(data)
    bits = 32 if data[4] == 1 else 64
    prefix = "<" if data[5] == 1 else ">"
    section_offset = struct.unpack_from(
        prefix + ("I" if bits == 32 else "Q"), data, 32 if bits == 32 else 40,
    )[0]
    entry_size = 40 if bits == 32 else 64
    offsets = {
        32: {"name": (0, "I"), "offset": (16, "I"), "size": (20, "I"),
             "link": (24, "I"), "entry_size": (36, "I")},
        64: {"name": (0, "I"), "offset": (24, "Q"), "size": (32, "Q"),
             "link": (40, "I"), "entry_size": (56, "Q")},
    }
    relative, code = offsets[bits][field]
    struct.pack_into(
        prefix + code, result, section_offset + section_index * entry_size + relative,
        value,
    )
    return bytes(result)


def patch_section_table_offset(data: bytes, value: int) -> bytes:
    result = bytearray(data)
    bits = 32 if data[4] == 1 else 64
    prefix = "<" if data[5] == 1 else ">"
    struct.pack_into(
        prefix + ("I" if bits == 32 else "Q"), result,
        32 if bits == 32 else 40, value,
    )
    return bytes(result)


def patch_symbol_name(
    data: bytes, symbol_section_index: int, symbol_index: int, value: int,
) -> bytes:
    result = bytearray(data)
    bits = 32 if data[4] == 1 else 64
    prefix = "<" if data[5] == 1 else ">"
    section_table = struct.unpack_from(
        prefix + ("I" if bits == 32 else "Q"), data, 32 if bits == 32 else 40,
    )[0]
    section_size = 40 if bits == 32 else 64
    offset_field = 16 if bits == 32 else 24
    symbol_table = struct.unpack_from(
        prefix + ("I" if bits == 32 else "Q"), data,
        section_table + symbol_section_index * section_size + offset_field,
    )[0]
    symbol_size = 16 if bits == 32 else 24
    struct.pack_into(prefix + "I", result, symbol_table + symbol_index * symbol_size, value)
    return bytes(result)


def overflowing_symbols(single_limit: int, total_limit: int) -> list[Symbol]:
    count = total_limit // single_limit + 1
    return [
        Symbol(f"{index:08x}" + "x" * (single_limit - 8))
        for index in range(count)
    ]


def invalid_symbol_boundary_objects(single_limit: int) -> list[bytes]:
    return [
        elf_object(64, "little", object_type=3, tables=[(
            "dynsym", [Symbol("x" * (single_limit + 1))],
        )]),
        elf_object(64, "little", object_type=3, tables=[(
            "dynsym", [Symbol("bad-index", section_index=99)],
        )]),
        elf_object(64, "little", object_type=3, tables=[(
            "dynsym", [Symbol("bad-reserved", section_index=0xFF10)],
        )]),
    ]


def _symbol_strings(symbols: Sequence[Symbol]) -> tuple[bytes, dict[str, int]]:
    return _string_bytes(["", *(symbol.name for symbol in symbols if symbol.name)])


def _string_bytes(names: Sequence[str]) -> tuple[bytes, dict[str, int]]:
    data = bytearray(b"\x00")
    offsets = {"": 0}
    for name in names:
        if not name or name in offsets:
            continue
        offsets[name] = len(data)
        data.extend(name.encode("utf-8") + b"\x00")
    return bytes(data), offsets


def _symbols(
    bits: int, prefix: str, symbols: Sequence[Symbol], offsets: dict[str, int],
    text_index: int,
) -> bytes:
    result = bytearray(b"\x00" * (16 if bits == 32 else 24))
    for symbol in symbols:
        name = symbol.name_offset if symbol.name_offset is not None else offsets[symbol.name]
        info = (symbol.binding << 4) | 2
        section = (
            symbol.section_index if symbol.section_index is not None
            else text_index if symbol.defined else 0
        )
        if bits == 32:
            result.extend(struct.pack(
                prefix + "IIIBBH", name, 0, 0, info, symbol.visibility, section,
            ))
        else:
            result.extend(struct.pack(
                prefix + "IBBHQQ", name, info, symbol.visibility, section, 0, 0,
            ))
    return bytes(result)


def _section_spec(
    name: int, kind: int, link: int, alignment: int, entry_size: int, *, info: int = 0,
) -> dict[str, int]:
    return {
        "name": name, "kind": kind, "offset": 0, "size": 0, "link": link,
        "info": info, "alignment": alignment, "entry_size": entry_size,
    }


def _section_header(bits: int, prefix: str, spec: dict[str, int]) -> bytes:
    values = (
        spec["name"], spec["kind"], 0, 0, spec["offset"], spec["size"],
        spec["link"], spec["info"], spec["alignment"], spec["entry_size"],
    )
    return struct.pack(
        prefix + ("IIIIIIIIII" if bits == 32 else "IIQQQQIIQQ"), *values,
    )


def _align(data: bytearray, alignment: int) -> None:
    if alignment:
        data.extend(b"\x00" * (-len(data) % alignment))


__all__ = [
    "Symbol", "ar_member", "archive", "duplicate_archives", "elf_object",
    "indexed_archives", "invalid_symbol_boundary_objects",
    "overflowing_symbols", "patch_section",
    "patch_section_table_offset", "patch_symbol_name",
]
