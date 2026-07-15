from __future__ import annotations

from dataclasses import dataclass


AR_MAGIC = b"!<arch>\n"
MAX_ARCHIVE_MEMBERS = 65_536
_BSD_INDEX_NAMES = {
    b"__.SYMDEF", b"__.SYMDEF SORTED",
    b"__.SYMDEF_64", b"__.SYMDEF_64 SORTED",
}


@dataclass(frozen=True)
class _ArMember:
    token: bytes
    payload: bytes


def archive_payloads(data: bytes) -> list[bytes]:
    members = _raw_members(data)
    long_tables = [member.payload for member in members if member.token == b"//"]
    if len(long_tables) > 1:
        _fail("long_name_table_invalid")
    names = _gnu_names(long_tables[0]) if long_tables else {}
    payloads: list[bytes] = []
    member_names: set[bytes] = set()
    symbol_index_seen = False
    for member in members:
        if member.token == b"//":
            continue
        name, payload = _resolve_member(member, names)
        is_index = name in _BSD_INDEX_NAMES or member.token in {b"/", b"/SYM64/"}
        if is_index:
            if symbol_index_seen:
                _fail("duplicate_symbol_index")
            symbol_index_seen = True
            continue
        if name in member_names:
            _fail("duplicate_member_name")
        member_names.add(name)
        payloads.append(payload)
    if not payloads:
        _fail("empty")
    return payloads


def _raw_members(data: bytes) -> list[_ArMember]:
    if not data.startswith(AR_MAGIC):
        _fail("magic_invalid")
    offset = len(AR_MAGIC)
    members: list[_ArMember] = []
    while offset < len(data):
        if len(members) >= MAX_ARCHIVE_MEMBERS:
            _fail("member_count_invalid")
        header = _span(data, offset, 60, "header")
        if header[58:60] != b"`\n":
            _fail("header_invalid")
        token = header[:16].rstrip(b" ")
        if not token or any(byte in b"\x00\r\n" for byte in token):
            _fail("name_invalid")
        raw_size = header[48:58]
        size_text = raw_size.rstrip(b" ")
        if (
            not size_text or not size_text.isdigit()
            or raw_size != size_text.ljust(10, b" ")
        ):
            _fail("size_invalid")
        size = int(size_text, 10)
        payload = _span(data, offset + 60, size, "member")
        members.append(_ArMember(token, payload))
        offset += 60 + size
        if size & 1:
            if _span(data, offset, 1, "padding") != b"\n":
                _fail("padding_invalid")
            offset += 1
    return members


def _gnu_names(table: bytes) -> dict[int, bytes]:
    if not table:
        _fail("long_name_table_invalid")
    result: dict[int, bytes] = {}
    seen: set[bytes] = set()
    offset = 0
    while offset < len(table):
        end = table.find(b"/\n", offset)
        if end < 0:
            _fail("long_name_table_invalid")
        name = _valid_name(table[offset:end])
        if name in seen:
            _fail("duplicate_long_name")
        result[offset] = name
        seen.add(name)
        offset = end + 2
    return result


def _resolve_member(
    member: _ArMember, names: dict[int, bytes],
) -> tuple[bytes, bytes]:
    token, payload = member.token, member.payload
    if token in {b"/", b"/SYM64/"}:
        return token, payload
    if token.startswith(b"#1/"):
        length = token[3:]
        if not length.isdigit() or not 0 < int(length) <= len(payload):
            _fail("bsd_name_invalid")
        count = int(length)
        return _valid_name(payload[:count].rstrip(b"\x00")), payload[count:]
    if token.startswith(b"/"):
        reference = token[1:]
        if not reference.isdigit() or int(reference) not in names:
            _fail("name_reference_invalid")
        return names[int(reference)], payload
    name = token[:-1] if token.endswith(b"/") else token
    return _valid_name(name), payload


def _valid_name(value: bytes) -> bytes:
    if not value or any(byte in b"\x00\r\n" for byte in value):
        _fail("name_invalid")
    return value


def _span(data: bytes, offset: int, size: int, label: str) -> bytes:
    if offset < 0 or size < 0 or offset > len(data) or size > len(data) - offset:
        _fail(f"{label}_out_of_bounds")
    return data[offset:offset + size]


def _fail(code: str):
    raise ValueError(f"native_object_symbols_archive_{code}")


__all__ = ["AR_MAGIC", "archive_payloads"]
