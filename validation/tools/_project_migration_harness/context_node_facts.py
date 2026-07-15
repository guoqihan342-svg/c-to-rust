from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .context_contracts import (
    mapping, objects, required_string, source_ref, split_text, string_list,
)


AddFact = Callable[[str, Mapping[str, Any]], str]


def node_context_refs(
    nodes: Sequence[Mapping[str, Any]],
    graph_nodes: Sequence[Mapping[str, Any]],
    blockers_by_unit: Mapping[str, Sequence[Mapping[str, Any]]],
    valid_unit_ids: set[str],
    chunk_limit: int,
    add_fact: AddFact,
) -> tuple[
    dict[str, list[str]], dict[str, list[str]], dict[str, str],
    dict[str, Mapping[str, Any]],
]:
    full: dict[str, list[str]] = {}
    interfaces: dict[str, list[str]] = {}
    units: dict[str, str] = {}
    for node in sorted(nodes, key=lambda item: str(item.get("node_id"))):
        node_id = required_string(node, "node_id")
        unit_id = required_string(node, "unit_id")
        if unit_id not in valid_unit_ids or node_id in full:
            raise ValueError("C index node/unit identity is invalid")
        source = mapping(node.get("source"), f"node {node_id} source")
        content = source.get("content")
        if not isinstance(content, str):
            raise ValueError(f"node {node_id} source.content must be a string")
        base = [add_fact("function", {
            "node_id": node_id,
            "unit_id": unit_id,
            "node_kind": str(node.get("node_kind", "function")),
            "symbol": required_string(node, "symbol"),
            "linkage": required_string(node, "linkage"),
        }), add_fact("source_binding", {
            "node_id": node_id,
            "source": source_ref(source, include_content=False),
        })]
        base.extend(
            add_fact("parser_boundary", blocker)
            for blocker in blockers_by_unit.get(unit_id, [])
        )
        for macro in objects(
            node.get("macro_definitions", []),
            f"node {node_id} macro_definitions",
        ):
            replacement = macro.get("replacement")
            if not isinstance(replacement, str):
                raise ValueError("source macro replacement must be a string")
            base.append(add_fact("source_macro_definition", {
                "node_id": node_id,
                "unit_id": unit_id,
                "name": required_string(macro, "name"),
                "parameters": macro.get("parameters"),
                "replacement": replacement,
                "source_path": required_string(macro, "source_path"),
                "source_sha256": required_string(macro, "source_sha256"),
                "directive_sha256": required_string(macro, "directive_sha256"),
                "byte_offset": macro.get("byte_offset"),
                "conditional_depth": macro.get("conditional_depth"),
                "activation_status": required_string(
                    macro, "activation_status"
                ),
            }))
        full[node_id] = base + _source_chunks(
            "function_source", node_id, content, chunk_limit, add_fact
        )
        interfaces[node_id] = base + _signature_chunks(
            node, node_id, chunk_limit, add_fact
        )
        units[node_id] = unit_id

    graph_by_node: dict[str, Mapping[str, Any]] = {}
    for binding in graph_nodes:
        node_id = required_string(binding, "node_id")
        if node_id not in full or node_id in graph_by_node:
            raise ValueError("migration_graph.nodes do not match c_index.nodes")
        graph_by_node[node_id] = binding
        for item in objects(binding.get("resolved_calls", []), "resolved_calls"):
            full[node_id].append(add_fact("resolved_call", {
                "caller_node_id": node_id,
                "callee_node_id": required_string(item, "callee_node_id"),
                "symbol": required_string(item, "symbol"),
            }))
        for item in objects(binding.get("external_calls", []), "external_calls"):
            full[node_id].append(add_fact("external_call", {
                "caller_node_id": node_id,
                "symbol": required_string(item, "symbol"),
                "status": required_string(item, "status"),
                "candidate_node_ids": string_list(item.get("candidate_node_ids", [])),
            }))
        for item in objects(binding.get("global_references", []), "global_references"):
            full[node_id].append(add_fact("global_reference", {
                "node_id": node_id,
                "symbol": required_string(item, "symbol"),
                "status": required_string(item, "status"),
                "global_ids": string_list(item.get("global_ids", [])),
            }))
    if set(graph_by_node) != set(full):
        raise ValueError("migration_graph.nodes do not match c_index.nodes")
    return full, interfaces, units, graph_by_node


def _signature_chunks(
    node: Mapping[str, Any], node_id: str, chunk_limit: int, add_fact: AddFact
) -> list[str]:
    if node.get("node_kind") != "function":
        return []
    signature = mapping(node.get("signature"), f"node {node_id} signature")
    content = signature.get("content")
    if not isinstance(content, str):
        raise ValueError("function signature content must be a string")
    return _source_chunks("function_signature", node_id, content, chunk_limit, add_fact)


def _source_chunks(
    kind: str, node_id: str, content: str, chunk_limit: int, add_fact: AddFact
) -> list[str]:
    chunks = split_text(content, chunk_limit)
    return [
        add_fact(kind, {
            "node_id": node_id,
            "chunk_index": index,
            "chunk_count": len(chunks),
            "content": chunk,
        })
        for index, chunk in enumerate(chunks)
    ]


__all__ = ["node_context_refs"]
