from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .context_contracts import (
    canonical, mapping, objects, required_string, source_ref, split_text,
)


AddFact = Callable[[str, Mapping[str, Any]], str]


def unit_context_refs(
    contexts: Sequence[Mapping[str, Any]], header_facts: Mapping[str, Any],
    chunk_limit: int, add_fact: AddFact,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for context in sorted(contexts, key=lambda value: str(value.get("unit_id"))):
        unit_id = required_string(context, "unit_id")
        if unit_id in result:
            raise ValueError("c_index.unit_contexts must have unique unit_id values")
        compile_context = mapping(
            context.get("compile_context"), f"unit {unit_id} compile_context"
        )
        refs = [add_fact("compile_unit", {
            "unit_id": unit_id,
            "compiler": str(compile_context.get("compiler", "unknown")),
            "language": str(compile_context.get("language", "c")),
            "working_directory": str(compile_context.get("working_directory", ".")),
            "redacted_define_count": int(compile_context.get("redacted_define_count", 0)),
        })]
        compiler_fact = context.get("compiler_fact")
        if compiler_fact is not None:
            refs.append(add_fact(
                "compiler_fact_binding",
                mapping(compiler_fact, f"unit {unit_id} compiler_fact"),
            ))
        for include in objects(compile_context.get("includes", []), "compile includes"):
            refs.append(add_fact("compile_include", {"unit_id": unit_id, **dict(include)}))
        for define in objects(compile_context.get("defines", []), "compile defines"):
            refs.append(add_fact("compile_define", {"unit_id": unit_id, **dict(define)}))
        flags = compile_context.get("semantic_flags", [])
        if not _strings(flags):
            raise ValueError("compile semantic_flags must be an array of strings")
        for index, flag in enumerate(flags):
            refs.append(add_fact("compile_semantic_flag", {
                "unit_id": unit_id, "index": index, "value": flag,
            }))
        for include in objects(context.get("includes", []), "resolved includes"):
            refs.append(add_fact("include_binding", {"unit_id": unit_id, **dict(include)}))
        top_level = mapping(context.get("top_level"), f"unit {unit_id} top_level")
        refs.extend(_source_refs(
            "top_level", unit_id, mapping(top_level.get("source"), "top_level source"),
            chunk_limit, add_fact,
        ))
        coverage = mapping(top_level.get("coverage"), "top_level coverage")
        refs.extend(_coverage_refs(unit_id, coverage, chunk_limit, add_fact))
        for header in objects(context.get("headers", []), "headers"):
            digest = required_string(header, "header_fact_sha256")
            fact = mapping(header_facts.get(digest), "header fact")
            if hashlib.sha256(canonical(fact)).hexdigest() != digest:
                raise ValueError("header fact SHA-256 does not match its payload")
            source = mapping(fact.get("source"), "header source")
            if (
                header.get("path") != source.get("path")
                or header.get("sha256") != source.get("sha256")
            ):
                raise ValueError("header reference does not match its shared fact")
            header_owner = "header-" + required_string(source, "sha256")
            refs.extend(_source_refs(
                "header", header_owner, source, chunk_limit, add_fact,
            ))
        result[unit_id] = list(dict.fromkeys(refs))
    return result


def global_context_refs(
    item: Mapping[str, Any], chunk_limit: int, add_fact: AddFact
) -> list[str]:
    global_id = required_string(item, "global_id")
    unit_id = required_string(item, "unit_id")
    source = mapping(item.get("source"), f"global {global_id} source")
    refs = [add_fact("global", {
        "global_id": global_id,
        "unit_id": unit_id,
        "symbol": required_string(item, "symbol"),
        "linkage": required_string(item, "linkage"),
    })]
    refs.extend(_source_refs(
        "global", global_id, source, chunk_limit, add_fact,
    ))
    return refs


def _source_refs(
    kind: str,
    owner_id: str,
    source: Mapping[str, Any],
    chunk_limit: int,
    add_fact: AddFact,
) -> list[str]:
    content = source.get("content")
    if not isinstance(content, str):
        raise ValueError(f"{kind} source.content must be a string")
    binding = source_ref(source, include_content=False)
    refs = [add_fact(f"{kind}_source_binding", {
        "owner_id": owner_id, "source": binding,
    })]
    chunks = split_text(content, chunk_limit)
    for index, chunk in enumerate(chunks):
        refs.append(add_fact(f"{kind}_source", {
            "owner_id": owner_id,
            "chunk_index": index,
            "chunk_count": len(chunks),
            "content": chunk,
        }))
    return refs


def _coverage_refs(
    unit_id: str,
    coverage: Mapping[str, Any],
    chunk_limit: int,
    add_fact: AddFact,
) -> list[str]:
    required = {
        "source_size_bytes", "function_spans", "top_level_projection_sha256",
        "uncovered_ranges", "status",
    }
    if set(coverage) != required:
        raise ValueError("translation-unit coverage fields are invalid")
    spans = objects(coverage["function_spans"], "function spans")
    uncovered = objects(coverage["uncovered_ranges"], "uncovered ranges")
    refs = [add_fact("translation_unit_coverage", {
        "unit_id": unit_id,
        "source_size_bytes": coverage["source_size_bytes"],
        "top_level_projection_sha256": coverage["top_level_projection_sha256"],
        "status": coverage["status"],
        "function_span_count": len(spans),
        "uncovered_range_count": len(uncovered),
    })]
    refs.extend(_record_chunk_refs(
        "translation_unit_function_spans", "spans", unit_id, spans,
        chunk_limit, add_fact,
    ))
    refs.extend(_record_chunk_refs(
        "translation_unit_uncovered_ranges", "ranges", unit_id, uncovered,
        chunk_limit, add_fact,
    ))
    return refs


def _record_chunk_refs(
    kind: str,
    field: str,
    unit_id: str,
    records: Sequence[Mapping[str, Any]],
    chunk_limit: int,
    add_fact: AddFact,
) -> list[str]:
    chunks = _record_chunks(records, max(64, chunk_limit // 2))
    return [
        add_fact(kind, {
            "unit_id": unit_id,
            "chunk_index": index,
            "chunk_count": len(chunks),
            field: chunk,
        })
        for index, chunk in enumerate(chunks)
    ]


def _record_chunks(
    records: Sequence[Mapping[str, Any]], max_bytes: int
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for record in records:
        value = dict(record)
        candidate = [*current, value]
        if current and len(canonical(candidate)) > max_bytes:
            chunks.append(current)
            current = [value]
        else:
            current = candidate
        if len(canonical(current)) > max_bytes:
            raise ValueError("coverage record cannot fit within the chunk budget")
    if current:
        chunks.append(current)
    return chunks


def _strings(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) \
        and all(isinstance(item, str) for item in value)


__all__ = ["global_context_refs", "unit_context_refs"]
