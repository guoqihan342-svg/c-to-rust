from __future__ import annotations

from dataclasses import dataclass

from .c2rust_project_baseline_rust_lexer import (
    RustToken, matching_delimiter,
)


@dataclass(frozen=True, slots=True)
class RustFunction:
    name: str
    name_token: int
    parameter_names: frozenset[str]
    parameter_tokens: frozenset[int]
    parameter_count: int
    returns_value: bool
    public: bool
    body_open: int
    body_close: int


def find_rust_functions(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
) -> tuple[RustFunction, ...]:
    depths = _brace_depths(tokens, significant)
    result: list[RustFunction] = []
    for position, token_index in enumerate(significant):
        if tokens[token_index].text != "fn" or depths[position] != 0:
            continue
        name_position = position + 1
        if name_position >= len(significant):
            continue
        name_token = significant[name_position]
        if not tokens[name_token].is_identifier:
            continue
        open_position = _find_after(tokens, significant, name_position + 1, "(")
        if open_position is None:
            continue
        close_position = matching_delimiter(tokens, significant, open_position)
        body_open = _function_body(tokens, significant, close_position + 1)
        if body_open is None:
            continue
        body_close = matching_delimiter(tokens, significant, body_open)
        parameter_names, parameter_tokens, count = _parameters(
            tokens, significant, open_position, close_position,
        )
        between = [
            tokens[significant[index]].text
            for index in range(close_position + 1, body_open)
        ]
        result.append(RustFunction(
            tokens[name_token].text, name_token,
            frozenset(parameter_names), frozenset(parameter_tokens), count,
            "->" in between, _is_public(tokens, significant, position),
            body_open, body_close,
        ))
    return tuple(result)


def module_static_declarations(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
) -> dict[str, int]:
    depths = _brace_depths(tokens, significant)
    result: dict[str, int] = {}
    for position, token_index in enumerate(significant):
        if tokens[token_index].text != "static" or depths[position] != 0:
            continue
        cursor = position + 1
        if cursor < len(significant) and tokens[significant[cursor]].text == "mut":
            cursor += 1
        if cursor >= len(significant) or not tokens[significant[cursor]].is_identifier:
            continue
        name = tokens[significant[cursor]].text
        if name in result:
            raise ValueError("c2rust_duplicate_module_static")
        result[name] = significant[cursor]
    return result


def _parameters(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
    opening: int, closing: int,
) -> tuple[set[str], set[int], int]:
    segments: list[list[int]] = [[]]
    nested = 0
    for position in range(opening + 1, closing):
        text = tokens[significant[position]].text
        if text in {"(", "[", "{"}:
            nested += 1
        elif text in {")", "]", "}"}:
            nested -= 1
        if text == "," and nested == 0:
            segments.append([])
        else:
            segments[-1].append(significant[position])
    nonempty = [segment for segment in segments if segment]
    names: set[str] = set()
    name_tokens: set[int] = set()
    for segment in nonempty:
        colon = next(
            (index for index, token in enumerate(segment) if tokens[token].text == ":"),
            None,
        )
        candidates = segment if colon is None else segment[:colon]
        identifiers = [token for token in candidates if tokens[token].is_identifier]
        if identifiers:
            selected = identifiers[-1]
            if tokens[selected].text not in {"mut", "self"}:
                names.add(tokens[selected].text)
                name_tokens.add(selected)
    return names, name_tokens, len(nonempty)


def _brace_depths(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
) -> list[int]:
    depths: list[int] = []
    depth = 0
    for token_index in significant:
        text = tokens[token_index].text
        if text == "}":
            depth -= 1
        depths.append(depth)
        if text == "{":
            depth += 1
    return depths


def _find_after(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...],
    start: int, wanted: str,
) -> int | None:
    for position in range(start, len(significant)):
        text = tokens[significant[position]].text
        if text == wanted:
            return position
        if text in {";", "{"}:
            return None
    return None


def _function_body(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], start: int,
) -> int | None:
    for position in range(start, len(significant)):
        text = tokens[significant[position]].text
        if text == "{":
            return position
        if text == ";":
            return None
    return None


def _is_public(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], position: int,
) -> bool:
    for cursor in range(position - 1, max(-1, position - 24), -1):
        text = tokens[significant[cursor]].text
        if text in {";", "}"}:
            break
        if text == "pub":
            return True
    return False


__all__ = [
    "RustFunction", "find_rust_functions", "module_static_declarations",
]
