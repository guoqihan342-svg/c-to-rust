from __future__ import annotations

import re
from typing import Any

IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"


def derive_rust_metadata(source: str) -> dict[str, Any]:
    masked = mask_rust_non_code(source)
    unsafe_count = len(re.findall(r"\bunsafe\b", masked))
    public_pattern = re.compile(
        rf"\bpub(?:\s*\([^)]*\))?\s+"
        rf"(?:(?:async|const|unsafe)\s+)*(?:extern\s+)?"
        rf"(?:fn|struct|enum|union|trait|type|const|static|mod)\s+({IDENTIFIER})"
    )
    public = set(public_pattern.findall(masked))
    required: set[str] = set()
    for statement in re.findall(r"\buse\s+([^;]+);", masked, re.DOTALL):
        aliases = re.findall(rf"\bas\s+({IDENTIFIER})", statement)
        if aliases:
            required.update(aliases)
            continue
        identifiers = re.findall(IDENTIFIER, statement)
        required.update(
            item for item in identifiers[-1:]
            if item not in {"crate", "self", "super"}
        )
    required.update(re.findall(rf"\b(?:crate|super)\s*::\s*({IDENTIFIER})", masked))
    return {
        "public_symbols": sorted(public),
        "required_symbols": sorted(required - public),
        "unsafe_count": unsafe_count,
    }


def mask_rust_non_code(
    source: str, *, preserve_string_delimiters: bool = False,
) -> str:
    output = list(source)
    index = 0
    while index < len(source):
        pair = source[index:index + 2]
        if pair == "//":
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            _blank(output, source, index, end)
            index = end
            continue
        if pair == "/*":
            end = _block_comment_end(source, index)
            _blank(output, source, index, end)
            index = end
            continue
        raw = _raw_string_end(source, index)
        if raw is not None:
            start, end = raw
            _blank(output, source, start, end, delimiters=preserve_string_delimiters)
            index = end
            continue
        if source[index] == '"':
            end = _quoted_end(source, index, '"')
            _blank(output, source, index, end, delimiters=preserve_string_delimiters)
            index = end
            continue
        if source[index] == "'":
            end = _char_literal_end(source, index)
            if end is not None:
                _blank(output, source, index, end)
                index = end
                continue
        index += 1
    return "".join(output)


def _block_comment_end(source: str, start: int) -> int:
    depth, index = 1, start + 2
    while index < len(source) and depth:
        if source[index:index + 2] == "/*":
            depth += 1
            index += 2
        elif source[index:index + 2] == "*/":
            depth -= 1
            index += 2
        else:
            index += 1
    return index


def _raw_string_end(source: str, index: int) -> tuple[int, int] | None:
    match = re.match(r"(?:br|cr|r)(#{0,255})\"", source[index:])
    if match is None:
        return None
    hashes = match.group(1)
    closing = '"' + hashes
    content_start = index + match.end()
    found = source.find(closing, content_start)
    return index, len(source) if found < 0 else found + len(closing)


def _quoted_end(source: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == quote:
            return index + 1
        elif source[index] == "\n":
            return index
        else:
            index += 1
    return len(source)


def _char_literal_end(source: str, start: int) -> int | None:
    end = _quoted_end(source, start, "'")
    if end <= start + 2 or end > len(source) or source[end - 1] != "'":
        return None
    return end


def _blank(
    output: list[str], source: str, start: int, end: int, *, delimiters: bool = False,
) -> None:
    for position in range(start, min(end, len(source))):
        if delimiters and source[position] in {'"', '#'}:
            continue
        output[position] = "\n" if source[position] == "\n" else " "


__all__ = ["derive_rust_metadata", "mask_rust_non_code"]
