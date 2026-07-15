from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z", re.ASCII)
_MULTI_PUNCT = ("::", "->", "=>", "..=", "...", "..")


@dataclass(frozen=True, slots=True)
class RustToken:
    kind: str
    text: str
    start: int
    end: int

    @property
    def is_identifier(self) -> bool:
        return self.kind == "identifier"


def lex_rust(source: str) -> tuple[RustToken, ...]:
    tokens: list[RustToken] = []
    index = 0
    while index < len(source):
        start = index
        char = source[index]
        if char.isspace():
            index += 1
            while index < len(source) and source[index].isspace():
                index += 1
            kind = "trivia"
        elif source.startswith("//", index):
            newline = source.find("\n", index + 2)
            index = len(source) if newline < 0 else newline
            kind = "trivia"
        elif source.startswith("/*", index):
            index = _block_comment_end(source, index)
            kind = "trivia"
        else:
            literal_end = _literal_end(source, index)
            if literal_end is not None:
                index = literal_end
                kind = "literal"
            elif char.isalpha() or char == "_":
                index += 1
                while index < len(source) and (
                    source[index].isalnum() or source[index] == "_"
                ):
                    index += 1
                kind = "identifier"
            else:
                punct = next(
                    (value for value in _MULTI_PUNCT if source.startswith(value, index)),
                    char,
                )
                index += len(punct)
                kind = "punct"
        tokens.append(RustToken(kind, source[start:index], start, index))
    return tuple(tokens)


def significant_indexes(tokens: tuple[RustToken, ...]) -> tuple[int, ...]:
    return tuple(index for index, token in enumerate(tokens) if token.kind != "trivia")


def replace_token_text(
    source: str, tokens: tuple[RustToken, ...], replacements: Mapping[int, str],
) -> str:
    if not replacements:
        return source
    pieces: list[str] = []
    offset = 0
    for token_index in sorted(replacements):
        token = tokens[token_index]
        replacement = replacements[token_index]
        if not token.is_identifier or _IDENTIFIER.fullmatch(replacement) is None:
            raise ValueError("c2rust_rust_identifier_replacement_invalid")
        pieces.extend((source[offset:token.start], replacement))
        offset = token.end
    pieces.append(source[offset:])
    return "".join(pieces)


def matching_delimiter(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
    start_position: int,
) -> int:
    opening = tokens[significant[start_position]].text
    closing = {"(": ")", "[": "]", "{": "}"}.get(opening)
    if closing is None:
        raise ValueError("c2rust_rust_delimiter_invalid")
    depth = 0
    for position in range(start_position, len(significant)):
        text = tokens[significant[position]].text
        if text == opening:
            depth += 1
        elif text == closing:
            depth -= 1
            if depth == 0:
                return position
    raise ValueError("c2rust_rust_delimiter_unclosed")


def identifier(value: str) -> bool:
    return _IDENTIFIER.fullmatch(value) is not None


def _block_comment_end(source: str, start: int) -> int:
    depth = 1
    index = start + 2
    while index < len(source) and depth:
        if source.startswith("/*", index):
            depth += 1
            index += 2
        elif source.startswith("*/", index):
            depth -= 1
            index += 2
        else:
            index += 1
    if depth:
        raise ValueError("c2rust_rust_block_comment_unclosed")
    return index


def _literal_end(source: str, start: int) -> int | None:
    raw = _raw_literal_end(source, start)
    if raw is not None:
        return raw
    prefix = 0
    if source.startswith(('b"', 'c"'), start):
        prefix = 1
    quote_index = start + prefix
    if quote_index < len(source) and source[quote_index] == '"':
        return _quoted_end(source, quote_index, '"')
    if source[start] == "'":
        end = _quoted_end(source, start, "'", tolerate_missing=True)
        if end is not None and end - start <= 8:
            return end
    return None


def _raw_literal_end(source: str, start: int) -> int | None:
    index = start
    if source.startswith("br", index) or source.startswith("cr", index):
        index += 2
    elif source.startswith("r", index):
        index += 1
    else:
        return None
    hashes = 0
    while index < len(source) and source[index] == "#":
        hashes += 1
        index += 1
    if index >= len(source) or source[index] != '"':
        return None
    marker = '"' + "#" * hashes
    end = source.find(marker, index + 1)
    if end < 0:
        raise ValueError("c2rust_rust_raw_string_unclosed")
    return end + len(marker)


def _quoted_end(
    source: str, quote_index: int, quote: str, *, tolerate_missing: bool = False,
) -> int | None:
    escaped = False
    index = quote_index + 1
    while index < len(source):
        char = source[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return index + 1
        elif char == "\n" and quote == "'":
            break
        index += 1
    if tolerate_missing:
        return None
    raise ValueError("c2rust_rust_string_unclosed")


__all__ = [
    "RustToken", "identifier", "lex_rust", "matching_delimiter",
    "replace_token_text", "significant_indexes",
]
