from __future__ import annotations


def ar_member(
    token: str, payload: bytes, *, declared_size: int | None = None,
) -> bytes:
    encoded = token.encode("ascii")
    if len(encoded) > 16:
        raise AssertionError("test archive token too long")
    size = len(payload) if declared_size is None else declared_size
    header = b"".join((
        encoded.ljust(16, b" "), b"0".ljust(12, b" "),
        b"0".ljust(6, b" "), b"0".ljust(6, b" "),
        b"100644".ljust(8, b" "), str(size).encode().ljust(10, b" "),
        b"`\n",
    ))
    result = header + payload
    if len(payload) & 1:
        result += b"\n"
    return result


def archive(*members: bytes) -> bytes:
    return b"!<arch>\n" + b"".join(members)


def indexed_archives(
    gnu_object: bytes, bsd_object: bytes,
) -> list[tuple[str, bytes]]:
    gnu_name = b"very-long-gnu-object-name.o"
    bsd_name = b"very-long-bsd-object-name.o"
    sorted_index = b"__.SYMDEF_64 SORTED"
    return [
        ("gnu", archive(
            ar_member("/", b"index"), ar_member("//", gnu_name + b"/\n"),
            ar_member("/0", gnu_object),
        )),
        ("gnu64", archive(
            ar_member("/SYM64/", b"wide-index"),
            ar_member("object.o/", gnu_object),
        )),
        ("bsd", archive(
            ar_member("__.SYMDEF/", b"index"),
            ar_member(f"#1/{len(bsd_name)}", bsd_name + bsd_object),
        )),
        ("bsd64", archive(
            ar_member(f"#1/{len(sorted_index)}", sorted_index + b"wide-index"),
            ar_member("object.o/", bsd_object),
        )),
    ]


def duplicate_archives(obj: bytes) -> list[bytes]:
    name = b"same.o"
    long_entry = b"long-object-name.o/\n"
    return [
        archive(ar_member("same.o/", obj), ar_member("same.o/", obj)),
        archive(
            ar_member("same.o/", obj),
            ar_member(f"#1/{len(name)}", name + obj),
        ),
        archive(
            ar_member("//", long_entry + long_entry), ar_member("/0", obj),
        ),
        archive(
            ar_member("/", b"index"), ar_member("/SYM64/", b"wide-index"),
            ar_member("object.o/", obj),
        ),
    ]


__all__ = ["ar_member", "archive", "duplicate_archives", "indexed_archives"]
