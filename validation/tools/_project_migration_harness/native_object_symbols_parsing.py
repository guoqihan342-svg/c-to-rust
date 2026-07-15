from __future__ import annotations

from dataclasses import dataclass
import struct

from .native_object_symbols_archive import AR_MAGIC, archive_payloads


ELF_MAGIC = b"\x7fELF"
MAX_SECTIONS = 65_536
MAX_SYMBOLS = 262_144
MAX_SYMBOL_NAME_BYTES = 4096
MAX_SYMBOL_SET_UTF8_BYTES = 16 * 1024 * 1024

_ET_REL = 1
_ET_DYN = 3
_SHT_NULL = 0
_SHT_SYMTAB = 2
_SHT_STRTAB = 3
_SHT_NOBITS = 8
_SHT_DYNSYM = 11
_SHN_UNDEF = 0
_SHN_LORESERVE = 0xFF00
_SHN_ABS = 0xFFF1
_SHN_COMMON = 0xFFF2
_SHN_XINDEX = 0xFFFF
_STB_GLOBAL = 1
_STB_WEAK = 2
_STV_DEFAULT = 0
_STV_PROTECTED = 3


@dataclass(frozen=True)
class _Section:
    name: int
    kind: int
    offset: int
    size: int
    link: int
    info: int
    alignment: int
    entry_size: int


@dataclass(frozen=True)
class _ElfLayout:
    bits: int
    endian: str
    sections: tuple[_Section, ...]


def parse_native_object_symbols(
    data: bytes,
) -> tuple[str, str, int, list[str]]:
    if data.startswith(ELF_MAGIC):
        symbols, _count = _elf_symbols(
            data, required_type=_ET_DYN, shared=True,
        )
        return "elf", "shared-object", 1, sorted(symbols)
    if data.startswith(AR_MAGIC):
        symbols: set[str] = set()
        symbol_bytes = 0
        scanned = 0
        payloads = archive_payloads(data)
        for payload in payloads:
            member_symbols, member_count = _elf_symbols(
                payload, required_type=_ET_REL, shared=False,
                symbol_limit=MAX_SYMBOLS - scanned,
            )
            scanned += member_count
            if scanned > MAX_SYMBOLS:
                _fail("symbol_count_invalid")
            for symbol in member_symbols:
                symbol_bytes = _add_symbol(
                    symbols, symbol, len(symbol.encode("utf-8")), symbol_bytes,
                )
        return "unix-ar", "static-archive", len(payloads), sorted(symbols)
    _fail("format_invalid")


def _elf_symbols(
    data: bytes, *, required_type: int, shared: bool,
    symbol_limit: int = MAX_SYMBOLS,
) -> tuple[set[str], int]:
    layout = _elf_layout(data, required_type)
    wanted = _SHT_DYNSYM if shared else _SHT_SYMTAB
    tables = [section for section in layout.sections if section.kind == wanted]
    if shared and not tables:
        tables = [
            section for section in layout.sections
            if section.kind == _SHT_SYMTAB
        ]
    if len(tables) != 1:
        _fail("symbol_table_invalid")
    return _symbols_from_table(
        data, layout, tables[0], shared=shared, symbol_limit=symbol_limit,
    )


def _elf_layout(data: bytes, required_type: int) -> _ElfLayout:
    if len(data) < 16 or data[:4] != ELF_MAGIC:
        _fail("elf_header_invalid")
    class_code, data_code = data[4], data[5]
    if class_code not in (1, 2) or data_code not in (1, 2) or data[6] != 1:
        _fail("elf_ident_invalid")
    bits = 32 if class_code == 1 else 64
    endian = "<" if data_code == 1 else ">"
    header_format = "HHIIIIIHHHHHH" if bits == 32 else "HHIQQQIHHHHHH"
    header_size = 52 if bits == 32 else 64
    values = _unpack(endian + header_format, data, 16, "elf_header")
    (
        object_type, machine, version, _entry, _phoff, section_offset,
        _flags, encoded_header_size, _phentsize, _phnum,
        section_entry_size, raw_count, raw_names_index,
    ) = values
    expected_section_size = 40 if bits == 32 else 64
    if (
        object_type != required_type or machine == 0 or version != 1
        or encoded_header_size != header_size
        or section_entry_size != expected_section_size
        or section_offset <= 0
    ):
        _fail("elf_header_invalid")
    first = _section(data, section_offset, bits, endian)
    count = first.size if raw_count == 0 else raw_count
    names_index = first.link if raw_names_index == _SHN_XINDEX else raw_names_index
    if not 0 < count <= MAX_SECTIONS:
        _fail("section_count_invalid")
    _span(data, section_offset, count * section_entry_size, "section_table")
    sections = tuple(
        _section(data, section_offset + index * section_entry_size, bits, endian)
        for index in range(count)
    )
    if sections[0].kind != _SHT_NULL:
        _fail("section_zero_invalid")
    for section in sections:
        if section.kind != _SHT_NOBITS:
            _span(data, section.offset, section.size, "section")
        if section.alignment and section.alignment & (section.alignment - 1):
            _fail("section_alignment_invalid")
    if names_index:
        if names_index >= count or sections[names_index].kind != _SHT_STRTAB:
            _fail("section_name_table_invalid")
        names = _string_table(data, sections[names_index], "section_name_table")
        for section in sections:
            _string(names, section.name, "section_name")
    return _ElfLayout(bits, endian, sections)


def _section(data: bytes, offset: int, bits: int, endian: str) -> _Section:
    if bits == 32:
        values = _unpack(endian + "IIIIIIIIII", data, offset, "section")
    else:
        values = _unpack(endian + "IIQQQQIIQQ", data, offset, "section")
    name, kind, _flags, _address, file_offset, size, link, info, align, entsize = values
    return _Section(name, kind, file_offset, size, link, info, align, entsize)


def _symbols_from_table(
    data: bytes, layout: _ElfLayout, table: _Section, *, shared: bool,
    symbol_limit: int,
) -> tuple[set[str], int]:
    symbol_size = 16 if layout.bits == 32 else 24
    if table.entry_size != symbol_size or table.size % symbol_size:
        _fail("symbol_table_layout_invalid")
    count = table.size // symbol_size
    if not 0 < count <= symbol_limit or not 0 < table.info <= count:
        _fail("symbol_count_invalid")
    if table.link <= 0 or table.link >= len(layout.sections):
        _fail("symbol_string_table_invalid")
    strings_section = layout.sections[table.link]
    if strings_section.kind != _SHT_STRTAB:
        _fail("symbol_string_table_invalid")
    strings = _string_table(data, strings_section, "symbol_string_table")
    result: set[str] = set()
    symbol_bytes = 0
    for index in range(count):
        offset = table.offset + index * symbol_size
        if layout.bits == 32:
            name, _value, _size, info, other, section = _unpack(
                layout.endian + "IIIBBH", data, offset, "symbol",
            )
        else:
            name, info, other, section, _value, _size = _unpack(
                layout.endian + "IBBHQQ", data, offset, "symbol",
            )
        encoded_name = _string(strings, name, "symbol_name")
        if index == 0 and any((name, _value, _size, info, other, section)):
            _fail("symbol_zero_invalid")
        if section == _SHN_XINDEX:
            _fail("symbol_extended_index_unsupported")
        if section not in {_SHN_UNDEF, _SHN_ABS, _SHN_COMMON} and not (
            0 < section < len(layout.sections) and section < _SHN_LORESERVE
        ):
            _fail("symbol_section_index_invalid")
        binding = info >> 4
        visible = other & 0x3
        if (
            encoded_name and section != _SHN_UNDEF
            and binding in {_STB_GLOBAL, _STB_WEAK}
            and (not shared or visible in {_STV_DEFAULT, _STV_PROTECTED})
        ):
            try:
                decoded = encoded_name.decode("utf-8")
            except UnicodeDecodeError:
                _fail("symbol_name_encoding_invalid")
            symbol_bytes = _add_symbol(
                result, decoded, len(encoded_name), symbol_bytes,
            )
    return result, count


def _add_symbol(
    result: set[str], symbol: str, encoded_size: int, total_bytes: int,
) -> int:
    if symbol in result:
        return total_bytes
    if (
        len(result) >= MAX_SYMBOLS
        or encoded_size > MAX_SYMBOL_SET_UTF8_BYTES - total_bytes
    ):
        _fail("symbol_budget_exceeded")
    result.add(symbol)
    return total_bytes + encoded_size


def _string_table(data: bytes, section: _Section, label: str) -> bytes:
    value = _span(data, section.offset, section.size, label)
    if not value or value[0] != 0 or value[-1] != 0:
        _fail(f"{label}_invalid")
    return value


def _string(table: bytes, offset: int, label: str) -> bytes:
    if offset < 0 or offset >= len(table):
        _fail(f"{label}_offset_invalid")
    search_end = min(len(table), offset + MAX_SYMBOL_NAME_BYTES + 1)
    end = table.find(b"\x00", offset, search_end)
    if end < 0:
        _fail(f"{label}_unterminated")
    return table[offset:end]


def _unpack(format_string: str, data: bytes, offset: int, label: str) -> tuple:
    layout = struct.Struct(format_string)
    return layout.unpack(_span(data, offset, layout.size, label))


def _span(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        _fail(f"{label}_out_of_bounds")
    return data[offset:offset + size]


def _fail(code: str):
    raise ValueError(f"native_object_symbols_{code}")


__all__ = [
    "AR_MAGIC", "ELF_MAGIC", "MAX_SYMBOL_NAME_BYTES", "MAX_SYMBOLS",
    "MAX_SYMBOL_SET_UTF8_BYTES", "parse_native_object_symbols",
]
