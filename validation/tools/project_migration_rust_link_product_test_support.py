from __future__ import annotations

import struct


ET_REL = 1
ET_EXEC = 2
ET_DYN = 3
_PT_LOAD = 1
_PT_DYNAMIC = 2
_PT_INTERP = 3
_DT_FLAGS_1 = 0x6FFFFFFB
_DF_1_PIE = 0x08000000
OBJECT_KINDS = {
    "bin": "executable",
    "cdylib": "dynamic-library",
    "staticlib": "static-library",
    "rlib": "rust-library",
}
REPORT_FIELDS = {
    "schema_version", "artifact_kind", "product_kind", "object_kind",
    "object_format", "elf_type", "pie", "machine", "class_bits",
    "endianness", "member_count", "member_identity_sha256", "file_sha256",
    "size_bytes", "semantic_gate", "translation_coverage_numerator",
    "inspection_sha256",
}


def elf_product(
    object_type: int,
    *,
    class_bits: int = 64,
    endianness: str = "little",
    interpreter: bool = False,
    pie_flag: bool = False,
    executable_entry: bool = True,
) -> bytes:
    prefix = "<" if endianness == "little" else ">"
    header_size = 52 if class_bits == 32 else 64
    program_size = 32 if class_bits == 32 else 56
    value_size = 4 if class_bits == 32 else 8
    machine = 3 if class_bits == 32 else 62
    base = 0 if object_type == ET_DYN else 0x10000
    entry = base + header_size if executable_entry else 0
    dynamic = object_type == ET_DYN
    count = 1 + int(interpreter) + int(dynamic)
    cursor = header_size + count * program_size

    interpreter_bytes = b"/lib/ld-test.so\x00" if interpreter else b""
    interpreter_offset = cursor
    cursor += len(interpreter_bytes)
    dynamic_offset, dynamic_bytes = 0, b""
    if dynamic:
        cursor = (cursor + value_size - 1) // value_size * value_size
        dynamic_offset = cursor
        entries = [(_DT_FLAGS_1, _DF_1_PIE)] if pie_flag else []
        entries.append((0, 0))
        dynamic_format = prefix + ("II" if class_bits == 32 else "QQ")
        dynamic_bytes = b"".join(
            struct.pack(dynamic_format, tag, value) for tag, value in entries
        )
        cursor += len(dynamic_bytes)
    total_size = cursor

    programs = []
    if interpreter:
        programs.append((
            _PT_INTERP, 4, interpreter_offset, base + interpreter_offset,
            len(interpreter_bytes), len(interpreter_bytes), 1,
        ))
    if dynamic:
        programs.append((
            _PT_DYNAMIC, 6, dynamic_offset, base + dynamic_offset,
            len(dynamic_bytes), len(dynamic_bytes), value_size,
        ))
    programs.append((_PT_LOAD, 5, 0, base, total_size, total_size, 0x1000))

    result = bytearray(
        _elf_ident(class_bits, endianness)
        + _elf_header(
            object_type, class_bits, prefix, machine, entry, count,
        )
        + b"".join(
            _program_header(class_bits, prefix, *program) for program in programs
        )
    )
    result.extend(b"\x00" * (total_size - len(result)))
    if interpreter_bytes:
        result[
            interpreter_offset:interpreter_offset + len(interpreter_bytes)
        ] = interpreter_bytes
    if dynamic_bytes:
        result[dynamic_offset:dynamic_offset + len(dynamic_bytes)] = dynamic_bytes
    return bytes(result)


def relocatable_elf(
    *,
    class_bits: int = 64,
    endianness: str = "little",
    machine: int | None = None,
    suffix: bytes = b"",
) -> bytes:
    prefix = "<" if endianness == "little" else ">"
    machine = machine if machine is not None else (3 if class_bits == 32 else 62)
    if class_bits == 32:
        header = struct.pack(
            prefix + "HHIIIIIHHHHHH",
            ET_REL, machine, 1, 0, 0, 0, 0, 52, 0, 0, 40, 0, 0,
        )
    else:
        header = struct.pack(
            prefix + "HHIQQQIHHHHHH",
            ET_REL, machine, 1, 0, 0, 0, 0, 64, 0, 0, 64, 0, 0,
        )
    return _elf_ident(class_bits, endianness) + header + suffix


def ar_member(
    name: str,
    payload: bytes,
    *,
    declared_size: int | None = None,
) -> bytes:
    token = name.encode("ascii")
    if len(token) > 16:
        raise AssertionError("archive test member name is too long")
    size = len(payload) if declared_size is None else declared_size
    header = b"".join((
        token.ljust(16, b" "),
        b"0".ljust(12, b" "),
        b"0".ljust(6, b" "),
        b"0".ljust(6, b" "),
        b"100644".ljust(8, b" "),
        str(size).encode("ascii").ljust(10, b" "),
        b"`\n",
    ))
    return header + payload + (b"\n" if size % 2 else b"")


def archive(*members: bytes) -> bytes:
    return b"!<arch>\n" + b"".join(members)


def product_cases() -> list[tuple[str, bytes, str, str, bool, int]]:
    relocatable = relocatable_elf()
    return [
        ("et-exec", elf_product(ET_EXEC), "bin", "ET_EXEC", False, 1),
        (
            "pie-interp",
            elf_product(
                ET_DYN, class_bits=32, endianness="big", interpreter=True,
            ),
            "bin", "ET_DYN", True, 1,
        ),
        (
            "pie-flags", elf_product(ET_DYN, pie_flag=True),
            "bin", "ET_DYN", True, 1,
        ),
        (
            "cdylib", elf_product(ET_DYN, executable_entry=False),
            "cdylib", "ET_DYN", False, 1,
        ),
        (
            "staticlib", archive(ar_member("unit.o/", relocatable)),
            "staticlib", "ET_REL", False, 1,
        ),
        (
            "rlib",
            archive(
                ar_member("lib.rmeta/", relocatable),
                ar_member("unit.o/", relocatable + b"code"),
            ),
            "rlib", "ET_REL", False, 2,
        ),
    ]


def _elf_ident(class_bits: int, endianness: str) -> bytes:
    class_code = 1 if class_bits == 32 else 2
    data_code = 1 if endianness == "little" else 2
    return b"\x7fELF" + bytes((class_code, data_code, 1, 0, 0)) + b"\x00" * 7


def _elf_header(
    object_type: int,
    class_bits: int,
    prefix: str,
    machine: int,
    entry: int,
    program_count: int,
) -> bytes:
    if class_bits == 32:
        return struct.pack(
            prefix + "HHIIIIIHHHHHH",
            object_type, machine, 1, entry, 52, 0, 0, 52, 32,
            program_count, 40, 0, 0,
        )
    return struct.pack(
        prefix + "HHIQQQIHHHHHH",
        object_type, machine, 1, entry, 64, 0, 0, 64, 56,
        program_count, 64, 0, 0,
    )


def _program_header(
    class_bits: int,
    prefix: str,
    kind: int,
    flags: int,
    offset: int,
    virtual_address: int,
    file_size: int,
    memory_size: int,
    alignment: int,
) -> bytes:
    if class_bits == 32:
        return struct.pack(
            prefix + "IIIIIIII",
            kind, offset, virtual_address, virtual_address,
            file_size, memory_size, flags, alignment,
        )
    return struct.pack(
        prefix + "IIQQQQQQ",
        kind, flags, offset, virtual_address, virtual_address,
        file_size, memory_size, alignment,
    )
