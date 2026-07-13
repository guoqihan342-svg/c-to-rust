from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


FATAL_SPAN_BLOCKERS = frozenset({
    "unbalanced_brace",
    "unexpected_closing_brace",
    "unterminated_block_comment",
    "unterminated_character",
    "unterminated_string",
})


def function_spans_reliable(
    functions: Sequence[Mapping[str, Any]], blockers: Sequence[Mapping[str, Any]]
) -> bool:
    if not functions:
        return False
    return not any(str(item.get("kind")) in FATAL_SPAN_BLOCKERS for item in blockers)


__all__ = ["FATAL_SPAN_BLOCKERS", "function_spans_reliable"]
