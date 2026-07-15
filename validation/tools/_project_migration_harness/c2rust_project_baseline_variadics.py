from __future__ import annotations

from dataclasses import dataclass

from .c2rust_project_baseline_rust_lexer import (
    RustToken, lex_rust, significant_indexes,
)


@dataclass(frozen=True, slots=True)
class VariadicRepairResult:
    source: str
    va_list_type_rewrite_count: int
    va_list_adapter_rewrite_count: int


def modernize_c2rust_variadics(source: str) -> VariadicRepairResult:
    """Update the pre-1.95 C2Rust VaList API without touching user text."""
    tokens = lex_rust(source)
    significant = significant_indexes(tokens)
    bound_names: set[str] = set()
    replacements: list[tuple[int, int, str]] = []
    type_rewrites = 0

    for position in range(len(significant)):
        path_start = _ffi_va_list_path_start(tokens, significant, position)
        if path_start is None:
            continue
        token = tokens[significant[position]]
        if token.text == "VaListImpl":
            replacements.append((token.start, token.end, "VaList"))
            type_rewrites += 1
        bound = _bound_name(tokens, significant, path_start)
        if bound is not None:
            bound_names.add(bound)

    adapter_rewrites = 0
    for position in range(2, len(significant) - 2):
        receiver = tokens[significant[position - 2]]
        dot = tokens[significant[position - 1]]
        method = tokens[significant[position]]
        opening = tokens[significant[position + 1]]
        closing = tokens[significant[position + 2]]
        if (
            receiver.is_identifier
            and receiver.text in bound_names
            and dot.text == "."
            and method.text == "as_va_list"
            and opening.text == "("
            and closing.text == ")"
        ):
            replacements.append((dot.start, closing.end, ""))
            adapter_rewrites += 1

    return VariadicRepairResult(
        _replace_spans(source, replacements),
        type_rewrites,
        adapter_rewrites,
    )


def _ffi_va_list_path_start(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], position: int,
) -> int | None:
    final = tokens[significant[position]].text
    if final not in {"VaList", "VaListImpl"}:
        return None
    for expected in (
        ("::", "core", "::", "ffi", "::"),
        ("core", "::", "ffi", "::"),
    ):
        start = position - len(expected)
        if start < 0:
            continue
        actual = tuple(
            tokens[significant[index]].text
            for index in range(start, position)
        )
        if actual == expected:
            return start
    return None


def _bound_name(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], path_start: int,
) -> str | None:
    if path_start < 2 or tokens[significant[path_start - 1]].text != ":":
        return None
    candidate = tokens[significant[path_start - 2]]
    return candidate.text if candidate.is_identifier else None


def _replace_spans(
    source: str, replacements: list[tuple[int, int, str]],
) -> str:
    if not replacements:
        return source
    pieces: list[str] = []
    offset = 0
    for start, end, replacement in sorted(replacements):
        if start < offset or not 0 <= start <= end <= len(source):
            raise ValueError("c2rust_variadic_repair_span_invalid")
        pieces.extend((source[offset:start], replacement))
        offset = end
    pieces.append(source[offset:])
    return "".join(pieces)


__all__ = ["VariadicRepairResult", "modernize_c2rust_variadics"]
