from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .c_toolchain_files import read_stable_file


MAX_NATIVE_OBJECT_BYTES = 256 * 1024 * 1024

_AR_MAGIC = b"!<arch>\n"
_AR_HEADER_BYTES = 60
_ELF_MAGIC = b"\x7fELF"
_ET_REL = 1
_ET_DYN = 3
_BSD_SYMBOL_NAMES = {
    b"__.SYMDEF", b"__.SYMDEF SORTED",
    b"__.SYMDEF_64", b"__.SYMDEF_64 SORTED",
}
@dataclass(frozen=True)
class _ElfIdentity:
    class_bits: int
    endianness: str
    machine: int
    object_type: int


@dataclass(frozen=True)
class _ArMember:
    token: bytes
    payload: bytes


def inspect_native_object(
    path: Path | str, *, limit: int = MAX_NATIVE_OBJECT_BYTES,
) -> dict[str, Any]:
    if type(limit) is not int or not 0 < limit <= MAX_NATIVE_OBJECT_BYTES:
        raise ValueError("native_object_limit_invalid")
    data, file_identity = read_stable_file(Path(path), limit)
    if data.startswith(_ELF_MAGIC):
        elf = _parse_elf(data, required_type=_ET_DYN)
        members = [(b"", data, elf)]
        return _inspection(
            "elf", "shared-object", elf, members, file_identity,
        )
    if data.startswith(_AR_MAGIC):
        return _inspect_archive(data, file_identity)
    raise ValueError("native_object_format_invalid")


def _parse_elf(data: bytes, *, required_type: int) -> _ElfIdentity:
    if len(data) < 4 or data[:4] != _ELF_MAGIC:
        raise ValueError("native_object_elf_magic_invalid")
    if len(data) < 16:
        raise ValueError("native_object_elf_header_truncated")
    class_code, data_code = data[4], data[5]
    if class_code not in (1, 2):
        raise ValueError("native_object_elf_class_invalid")
    if data_code not in (1, 2):
        raise ValueError("native_object_elf_endianness_invalid")
    if data[6] != 1:
        raise ValueError("native_object_elf_ident_version_invalid")
    class_bits = 32 if class_code == 1 else 64
    header_size = 52 if class_bits == 32 else 64
    if len(data) < header_size:
        raise ValueError("native_object_elf_header_truncated")
    byteorder = "little" if data_code == 1 else "big"
    object_type = int.from_bytes(data[16:18], byteorder)
    machine = int.from_bytes(data[18:20], byteorder)
    version = int.from_bytes(data[20:24], byteorder)
    ehsize_offset = 40 if class_bits == 32 else 52
    encoded_header_size = int.from_bytes(
        data[ehsize_offset:ehsize_offset + 2], byteorder,
    )
    if version != 1 or encoded_header_size != header_size:
        raise ValueError("native_object_elf_header_invalid")
    if machine == 0:
        raise ValueError("native_object_elf_machine_invalid")
    if object_type != required_type:
        raise ValueError("native_object_elf_type_invalid")
    return _ElfIdentity(class_bits, byteorder, machine, object_type)


def _inspect_archive(
    data: bytes, file_identity: dict[str, Any],
) -> dict[str, Any]:
    raw_members = _parse_ar_layout(data)
    long_tables = [member for member in raw_members if member.token == b"//"]
    if len(long_tables) > 1:
        raise ValueError("native_object_archive_duplicate_long_names")
    gnu_names = _parse_gnu_names(long_tables[0].payload) if long_tables else {}
    objects: list[tuple[bytes, bytes, _ElfIdentity]] = []
    names: set[bytes] = set()
    symbol_index_seen = False
    for member in raw_members:
        if member.token == b"//":
            continue
        name, payload, is_gnu_index = _resolve_member(member, gnu_names)
        is_symbol_index = is_gnu_index or name in _BSD_SYMBOL_NAMES
        if is_symbol_index:
            if symbol_index_seen:
                raise ValueError("native_object_archive_duplicate_symbol_index")
            symbol_index_seen = True
            continue
        if name in names:
            raise ValueError("native_object_archive_duplicate_member")
        names.add(name)
        objects.append((name, payload, _parse_elf(payload, required_type=_ET_REL)))
    if not objects:
        raise ValueError("native_object_archive_empty")
    first = objects[0][2]
    abi = (first.class_bits, first.endianness, first.machine)
    if any(
        (elf.class_bits, elf.endianness, elf.machine) != abi
        for _, _, elf in objects[1:]
    ):
        raise ValueError("native_object_archive_mixed_abi")
    return _inspection(
        "unix-ar", "static-archive", first, objects, file_identity,
    )


def _parse_ar_layout(data: bytes) -> list[_ArMember]:
    if not data.startswith(_AR_MAGIC):
        raise ValueError("native_object_archive_magic_invalid")
    offset = len(_AR_MAGIC)
    members: list[_ArMember] = []
    while offset < len(data):
        if len(data) - offset < _AR_HEADER_BYTES:
            raise ValueError("native_object_archive_header_truncated")
        header = data[offset:offset + _AR_HEADER_BYTES]
        if header[58:60] != b"`\n":
            raise ValueError("native_object_archive_header_invalid")
        token = header[:16].rstrip(b" ")
        if not token or b"\x00" in token or b"\n" in token or b"\r" in token:
            raise ValueError("native_object_archive_name_invalid")
        _numeric_field(header[16:28], 10)
        _numeric_field(header[28:34], 10)
        _numeric_field(header[34:40], 10)
        _numeric_field(header[40:48], 8)
        size = _numeric_field(header[48:58], 10)
        payload_start = offset + _AR_HEADER_BYTES
        payload_end = payload_start + size
        if payload_end > len(data):
            raise ValueError("native_object_archive_member_out_of_bounds")
        members.append(_ArMember(token, data[payload_start:payload_end]))
        offset = payload_end
        if size % 2:
            if offset >= len(data) or data[offset:offset + 1] != b"\n":
                raise ValueError("native_object_archive_padding_invalid")
            offset += 1
    if offset != len(data):
        raise ValueError("native_object_archive_layout_invalid")
    return members


def _numeric_field(raw: bytes, base: int) -> int:
    value = raw.rstrip(b" ")
    allowed = b"01234567" if base == 8 else b"0123456789"
    if not value or raw != value.ljust(len(raw), b" "):
        raise ValueError("native_object_archive_numeric_field_invalid")
    if any(byte not in allowed for byte in value):
        raise ValueError("native_object_archive_numeric_field_invalid")
    return int(value, base)


def _parse_gnu_names(table: bytes) -> dict[int, bytes]:
    if not table:
        raise ValueError("native_object_archive_long_names_invalid")
    result: dict[int, bytes] = {}
    seen: set[bytes] = set()
    offset = 0
    while offset < len(table):
        end = table.find(b"/\n", offset)
        if end < 0:
            raise ValueError("native_object_archive_long_names_invalid")
        name = _valid_name(table[offset:end])
        if name in seen:
            raise ValueError("native_object_archive_duplicate_long_name")
        result[offset] = name
        seen.add(name)
        offset = end + 2
    return result


def _resolve_member(
    member: _ArMember, gnu_names: dict[int, bytes],
) -> tuple[bytes, bytes, bool]:
    token, payload = member.token, member.payload
    if token in {b"/", b"/SYM64/"}:
        return token, payload, True
    if token.startswith(b"/"):
        reference = token[1:]
        if not reference or not reference.isdigit():
            raise ValueError("native_object_archive_name_reference_invalid")
        name = gnu_names.get(int(reference, 10))
        if name is None:
            raise ValueError("native_object_archive_name_reference_invalid")
        return name, payload, False
    if token.startswith(b"#1/"):
        encoded_length = token[3:]
        if not encoded_length or not encoded_length.isdigit():
            raise ValueError("native_object_archive_bsd_name_invalid")
        name_length = int(encoded_length, 10)
        if name_length <= 0 or name_length > len(payload):
            raise ValueError("native_object_archive_bsd_name_invalid")
        name = _valid_name(payload[:name_length].rstrip(b"\x00"))
        return name, payload[name_length:], False
    name = token[:-1] if token.endswith(b"/") else token
    return _valid_name(name), payload, False


def _valid_name(name: bytes) -> bytes:
    if not name or any(byte in b"\x00\r\n" for byte in name):
        raise ValueError("native_object_archive_name_invalid")
    return name


def _inspection(
    object_format: str,
    object_kind: str,
    elf: _ElfIdentity,
    members: list[tuple[bytes, bytes, _ElfIdentity]],
    file_identity: dict[str, Any],
) -> dict[str, Any]:
    result = {
        "schema_version": 1,
        "artifact_kind": "native-object-inspection",
        "object_format": object_format,
        "object_kind": object_kind,
        "machine": elf.machine,
        "class_bits": elf.class_bits,
        "endianness": elf.endianness,
        "member_count": len(members),
        "member_identity_sha256": _member_identity(members),
        "file_sha256": file_identity["sha256"],
        "size_bytes": file_identity["size_bytes"],
        "semantic_gate": False,
    }
    result["inspection_sha256"] = content_sha256(result)
    return result


def _member_identity(
    members: list[tuple[bytes, bytes, _ElfIdentity]],
) -> str:
    digest = hashlib.sha256(b"native-object-members-v1\x00")
    for name, payload, elf in members:
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(hashlib.sha256(payload).digest())
        digest.update(elf.class_bits.to_bytes(1, "big"))
        digest.update(b"L" if elf.endianness == "little" else b"B")
        digest.update(elf.machine.to_bytes(2, "big"))
        digest.update(elf.object_type.to_bytes(2, "big"))
    return digest.hexdigest()


__all__ = [
    "MAX_NATIVE_OBJECT_BYTES", "inspect_native_object",
]
