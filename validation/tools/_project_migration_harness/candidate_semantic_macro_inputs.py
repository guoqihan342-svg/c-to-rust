from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .candidate_semantic_backend_contract import SemanticBackendError
from .candidate_semantic_integer_macros import (
    IntegerMacroBoundaries,
    collect_integer_macro_boundaries,
)


def macro_boundaries_from_context(
    *, facts: Sequence[Mapping[str, Any]], node: Mapping[str, Any],
    function_source: bytes, source_path: str, source_bytes: bytes,
    source_reference: Mapping[str, Any],
    headers: Sequence[tuple[str, bytes]], compile_arguments: Sequence[str],
) -> IntegerMacroBoundaries:
    try:
        return _macro_boundaries_from_context(
            facts=facts, node=node, function_source=function_source,
            source_path=source_path, source_bytes=source_bytes,
            source_reference=source_reference, headers=headers,
            compile_arguments=compile_arguments,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SemanticBackendError("semantic_integer_macro_binding_invalid") from error


def _macro_boundaries_from_context(
    *, facts: Sequence[Mapping[str, Any]], node: Mapping[str, Any],
    function_source: bytes, source_path: str, source_bytes: bytes,
    source_reference: Mapping[str, Any],
    headers: Sequence[tuple[str, bytes]], compile_arguments: Sequence[str],
) -> IntegerMacroBoundaries:
    span = source_reference.get("span")
    if not isinstance(span, Mapping):
        raise ValueError("macro source span is missing")
    node_id, unit_id = node.get("node_id"), node.get("unit_id")
    if not isinstance(node_id, str) or not isinstance(unit_id, str):
        raise ValueError("macro CIndex identity is invalid")
    macro_facts = tuple(
        fact["payload"] for fact in facts
        if fact.get("kind") == "source_macro_definition"
        and isinstance(fact.get("payload"), Mapping)
        and fact["payload"].get("node_id") == node_id
    )
    return collect_integer_macro_boundaries(
        function_source=function_source,
        source_path=source_path,
        source_bytes=source_bytes,
        function_byte_start=span.get("byte_start"),
        node_id=node_id,
        unit_id=unit_id,
        header_sources=tuple(headers),
        cindex_macro_facts=macro_facts,
        compile_arguments=tuple(compile_arguments),
    )


__all__ = ["IntegerMacroBoundaries", "macro_boundaries_from_context"]
