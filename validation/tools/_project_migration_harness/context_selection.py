from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from .context_contracts import canonical
from .context_required_facts import (
    build_required_fact_query, required_fact_resolution,
)
from .context_selection_index import ContextSelectionIndex
from .context_selection_query import (
    IDENTIFIER, identifiers as extract_identifiers, semantic_identifiers,
)


SELECTION_POLICY = "deterministic-symbol-selection-v1"
_SOURCE_KINDS = frozenset({"header_source", "top_level_source"})


def select_deferred_context(
    scc_id: str,
    required_refs: Sequence[str],
    deferred_refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
    *,
    max_selected_bytes: int,
    identifier_cache: dict[str, frozenset[str]] | None = None,
    selection_index: ContextSelectionIndex | None = None,
) -> dict[str, Any]:
    if not isinstance(scc_id, str) or not scc_id:
        raise ValueError("context selection SCC identity is invalid")
    if (
        isinstance(max_selected_bytes, bool)
        or not isinstance(max_selected_bytes, int)
        or max_selected_bytes < 1
    ):
        raise ValueError("context selection byte budget is invalid")
    required = _unique_refs(required_refs, facts, "required")
    deferred = _unique_refs(deferred_refs, facts, "deferred")
    if set(required) & set(deferred):
        raise ValueError("context selection fact classes overlap")

    query = _query_seed(scc_id, required, facts)
    required_fact_query = build_required_fact_query(scc_id, required, facts)
    ranked = _ranked_candidates(
        query, deferred, facts,
        identifier_cache={} if identifier_cache is None else identifier_cache,
        selection_index=selection_index,
    )
    selected: set[str] = set()
    selected_bytes = 0
    overflow = 0
    for _priority, digest in ranked:
        size = _fact_bytes(digest, facts[digest])
        if selected_bytes + size > max_selected_bytes:
            overflow += 1
            continue
        selected.add(digest)
        selected_bytes += size
    selected_refs = sorted(selected)
    omitted_refs = sorted(set(deferred) - selected)
    resolution = required_fact_resolution(
        required_fact_query, [*required, *selected_refs], facts,
    )
    blockers = []
    if overflow:
        blockers.append("exact_context_selection_budget_exceeded")
    if resolution["unresolved_required_fact_count"]:
        blockers.append("required_fact_query_unresolved")
    status = "blocked" if blockers else "ready"
    binding = {
        "selection_policy": SELECTION_POLICY,
        "query_seed_sha256": query["sha256"],
        "query_identifier_count": len(query["identifiers"]),
        "required_fact_count": len(required),
        "required_fact_set_sha256": _set_sha(required),
        "selection_byte_budget": max_selected_bytes,
        "selected_fact_count": len(selected_refs),
        "selected_fact_set_sha256": _set_sha(selected_refs),
        "selected_fact_bytes": selected_bytes,
        "selection_status": status,
        "selection_blockers": blockers,
        "selection_overflow_fact_count": overflow,
        **resolution,
    }
    return {
        "selected_fact_refs": selected_refs,
        "omitted_fact_refs": omitted_refs,
        "binding": binding,
    }


def _query_seed(
    scc_id: str,
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    own_nodes = {
        str(facts[ref]["payload"]["node_id"])
        for ref in refs
        if facts[ref].get("kind") == "function_source"
        and isinstance(facts[ref].get("payload"), Mapping)
        and isinstance(facts[ref]["payload"].get("node_id"), str)
    }
    own_units: set[str] = set()
    own_paths: set[str] = set()
    identifiers: set[str] = set()
    for ref in refs:
        fact = facts[ref]
        payload = fact.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("context selection fact payload is invalid")
        node_id = payload.get("node_id")
        if fact.get("kind") == "function" and node_id in own_nodes:
            unit_id = payload.get("unit_id")
            if isinstance(unit_id, str):
                own_units.add(unit_id)
        if fact.get("kind") == "source_binding" and node_id in own_nodes:
            source = payload.get("source")
            if isinstance(source, Mapping) and isinstance(source.get("path"), str):
                own_paths.add(str(source["path"]))
        symbol = payload.get("symbol")
        kind = fact.get("kind")
        if isinstance(symbol, str) and (
            kind in {"resolved_call", "external_call", "global_reference", "global"}
            or (kind == "function" and node_id in own_nodes)
        ):
            identifiers.update(extract_identifiers(symbol))
        if kind in {
            "function_source", "function_signature", "global_source",
        } \
                and isinstance(payload.get("content"), str):
            identifiers.update(semantic_identifiers(
                str(payload["content"]),
                declaration_context=kind != "function_source",
            ))
    payload = {
        "policy": SELECTION_POLICY,
        "scc_id": scc_id,
        "identifiers": sorted(identifiers),
        "own_node_ids": sorted(own_nodes),
        "own_unit_ids": sorted(own_units),
        "own_source_paths": sorted(own_paths),
    }
    return {**payload, "sha256": hashlib.sha256(canonical(payload)).hexdigest()}


def _ranked_candidates(
    query: Mapping[str, Any],
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
    *,
    identifier_cache: dict[str, frozenset[str]],
    selection_index: ContextSelectionIndex | None,
) -> list[tuple[int, str]]:
    own_units = set(query["own_unit_ids"])
    identifiers = set(query["identifiers"])
    header_bindings: dict[str, tuple[str, str]] = {}
    for ref in refs:
        fact = facts[ref]
        payload = fact.get("payload")
        if fact.get("kind") != "header_source_binding" or not isinstance(payload, Mapping):
            continue
        source = payload.get("source")
        owner = payload.get("owner_id")
        if (
            isinstance(owner, str) and isinstance(source, Mapping)
            and isinstance(source.get("path"), str)
        ):
            header_bindings[owner] = (ref, str(source["path"]))

    matched_source_refs = _matching_source_chunks(
        refs, facts, identifiers, own_units, set(header_bindings),
        identifier_cache, selection_index,
    )
    matched_header_owners = {
        str(facts[ref]["payload"]["owner_id"])
        for ref in matched_source_refs
        if facts[ref].get("kind") == "header_source"
    }
    relevant_paths = {
        header_bindings[owner][1] for owner in matched_header_owners
    }
    binding_refs = {
        ref for owner, (ref, path) in header_bindings.items()
        if owner in matched_header_owners
    }
    include_by_path: dict[str, list[str]] = {}
    for ref in refs:
        fact = facts[ref]
        payload = fact.get("payload")
        if fact.get("kind") == "include_binding" and isinstance(payload, Mapping) \
                and payload.get("path") in relevant_paths:
            include_by_path.setdefault(str(payload["path"]), []).append(ref)
    include_refs = {
        sorted(path_refs)[0] for path_refs in include_by_path.values()
    }
    ranked = [
        (0 if ref in include_refs else 1 if ref in binding_refs else 2, ref)
        for ref in include_refs | binding_refs | matched_source_refs
    ]
    return sorted(ranked)


def _matching_source_chunks(
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
    identifiers: set[str],
    own_units: set[str],
    header_owners: set[str],
    identifier_cache: dict[str, frozenset[str]],
    selection_index: ContextSelectionIndex | None,
) -> set[str]:
    if selection_index is not None:
        return selection_index.matching_refs(
            sorted(identifiers), refs, own_units, header_owners
        )
    groups: dict[tuple[str, str], list[tuple[int, str, frozenset[str]]]] = {}
    for ref in refs:
        fact = facts[ref]
        kind = fact.get("kind")
        payload = fact.get("payload")
        if kind not in _SOURCE_KINDS or not isinstance(payload, Mapping):
            continue
        owner = payload.get("owner_id")
        if kind == "header_source" and owner not in header_owners:
            continue
        if kind == "top_level_source" and owner not in own_units:
            continue
        content = payload.get("content")
        index = payload.get("chunk_index")
        if isinstance(content, str) and isinstance(index, int) and isinstance(owner, str):
            tokens = identifier_cache.setdefault(
                ref, frozenset(IDENTIFIER.findall(content))
            )
            groups.setdefault((str(kind), owner), []).append((index, ref, tokens))
    matched: set[str] = set()
    for chunks in groups.values():
        ordered = sorted(chunks)
        matching = {
            index for index, (_chunk_index, _ref, tokens) in enumerate(ordered)
            if identifiers & tokens
        }
        selected_indexes = {
            neighbor for index in matching for neighbor in (index - 1, index, index + 1)
            if 0 <= neighbor < len(ordered)
        }
        matched.update(ordered[index][1] for index in selected_indexes)
    return matched


def _unique_refs(
    refs: Sequence[str], facts: Mapping[str, Mapping[str, Any]], label: str
) -> list[str]:
    if any(not isinstance(ref, str) or ref not in facts for ref in refs):
        raise ValueError(f"context selection {label} fact reference is invalid")
    if len(refs) != len(set(refs)):
        raise ValueError(f"context selection {label} fact references are duplicated")
    return sorted(refs)


def _fact_bytes(digest: str, fact: Mapping[str, Any]) -> int:
    return len(canonical({"sha256": digest, **dict(fact)}))


def _set_sha(refs: Sequence[str]) -> str:
    return hashlib.sha256(canonical(sorted(refs))).hexdigest()


__all__ = ["SELECTION_POLICY", "select_deferred_context"]
