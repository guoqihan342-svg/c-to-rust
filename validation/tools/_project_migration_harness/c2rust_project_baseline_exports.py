from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping

from .c2rust_project_baseline_rust_lexer import (
    RustToken, lex_rust, significant_indexes,
)


@dataclass(frozen=True, slots=True)
class DuplicateExportRepair:
    sources: dict[str, str]
    privatized: dict[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _Export:
    symbol: str
    start: int
    end: int


def privatize_duplicate_exports(
    sources: Mapping[str, str],
) -> DuplicateExportRepair:
    inventory: dict[str, list[tuple[str, _Export]]] = defaultdict(list)
    for path in sorted(sources):
        for item in _no_mangle_exports(sources[path]):
            inventory[item.symbol].append((path, item))
    removals: dict[str, list[_Export]] = defaultdict(list)
    for symbol in sorted(inventory):
        entries = sorted(
            inventory[symbol], key=lambda item: (item[0], item[1].start),
        )
        for path, item in entries[1:]:
            removals[path].append(item)
    rewritten = dict(sources)
    privatized: dict[str, tuple[str, ...]] = {}
    for path in sorted(removals):
        rewritten[path] = _remove_attributes(rewritten[path], removals[path])
        privatized[path] = tuple(sorted(item.symbol for item in removals[path]))
    return DuplicateExportRepair(rewritten, privatized)


def _no_mangle_exports(source: str) -> tuple[_Export, ...]:
    tokens = lex_rust(source)
    significant = significant_indexes(tokens)
    result = []
    for position in range(max(0, len(significant) - 3)):
        indexes = significant[position:position + 4]
        if [tokens[index].text for index in indexes] != [
            "#", "[", "no_mangle", "]",
        ]:
            continue
        declaration = _declaration_name(tokens, significant, position + 4)
        if declaration is not None:
            result.append(_Export(
                declaration, tokens[indexes[0]].start, tokens[indexes[-1]].end,
            ))
    return tuple(result)


def _declaration_name(
    tokens: tuple[RustToken, ...], significant: tuple[int, ...], start: int,
) -> str | None:
    limit = min(len(significant), start + 24)
    for position in range(start, limit):
        text = tokens[significant[position]].text
        if text == "fn" and position + 1 < len(significant):
            candidate = tokens[significant[position + 1]]
            return candidate.text if candidate.is_identifier else None
        if text == "static":
            name_position = position + 1
            if (
                name_position < len(significant)
                and tokens[significant[name_position]].text == "mut"
            ):
                name_position += 1
            if name_position < len(significant):
                candidate = tokens[significant[name_position]]
                return candidate.text if candidate.is_identifier else None
            return None
        if text in {";", "{"}:
            return None
    return None


def _remove_attributes(source: str, removals: list[_Export]) -> str:
    result = source
    for item in sorted(removals, key=lambda value: value.start, reverse=True):
        result = result[:item.start] + result[item.end:]
    return result


__all__ = ["DuplicateExportRepair", "privatize_duplicate_exports"]
