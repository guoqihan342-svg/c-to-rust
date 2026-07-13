"""Deduplicated, budgeted ContextPack pages for migration graph units."""
from __future__ import annotations
import hashlib
from collections.abc import Mapping, Sequence
from typing import Any

from .context_contracts import (
    budget as _budget,
    canonical as _canonical,
    mapping as _mapping,
    objects as _objects,
    required_string as _required_string,
    safe_blockers as _safe_blockers,
    string_list as _string_list,
)
from .migration_graph import build_migration_graph
from .context_source_facts import global_context_refs, unit_context_refs
from .context_retrieval import partition_context_refs
from .context_selection_index import ContextSelectionIndex
from .context_node_facts import node_context_refs


DEFAULT_PAGE_BYTES = 16_384
DEFAULT_PAGE_TOKENS = 4_096
def build_context_pages(
    c_index: Mapping[str, Any],
    migration_graph: Mapping[str, Any],
    *,
    max_page_bytes: int = DEFAULT_PAGE_BYTES,
    max_page_tokens: int = DEFAULT_PAGE_TOKENS,
    byte_budget: int | None = None,
    token_budget: int | None = None,
) -> dict[str, Any]:
    """Build pages whose dereferenced facts fit both conservative budgets."""
    byte_limit = _budget(byte_budget if byte_budget is not None else max_page_bytes, "byte")
    token_limit = _budget(token_budget if token_budget is not None else max_page_tokens, "token")
    if dict(migration_graph) != build_migration_graph(c_index):
        raise ValueError("migration_graph does not match the supplied C index")
    effective_limit = min(byte_limit, token_limit)
    selection_limit = min(65_536, effective_limit * 16)
    nodes = _objects(c_index.get("nodes"), "c_index.nodes")
    globals_ = _objects(c_index.get("globals", []), "c_index.globals")
    unit_contexts = _objects(c_index.get("unit_contexts", []), "c_index.unit_contexts")
    header_facts = _mapping(c_index.get("header_facts", {}), "c_index.header_facts")
    graph_nodes = _objects(migration_graph.get("nodes"), "migration_graph.nodes")
    sccs = _objects(migration_graph.get("sccs"), "migration_graph.sccs")
    waves = _objects(migration_graph.get("waves"), "migration_graph.waves")
    facts: dict[str, dict[str, Any]] = {}
    global_refs: dict[str, list[str]] = {}
    parser = _mapping(c_index.get("parser", {}), "c_index.parser")
    parser_blockers = _safe_blockers(parser.get("blockers", []))
    blockers_by_unit: dict[str, list[dict[str, Any]]] = {}
    for blocker in parser_blockers:
        blockers_by_unit.setdefault(blocker["unit_id"], []).append(blocker)

    chunk_limit = max(1, (effective_limit - 480) // 6)
    add_fact = lambda kind, payload: _add_fact(facts, kind, payload)
    unit_refs = unit_context_refs(unit_contexts, header_facts, chunk_limit, add_fact)
    node_refs, interface_refs, node_units, graph_by_node = node_context_refs(
        nodes, graph_nodes, blockers_by_unit, set(unit_refs), chunk_limit, add_fact
    )

    for item in sorted(globals_, key=lambda value: str(value.get("global_id"))):
        global_id = _required_string(item, "global_id")
        if global_id in global_refs:
            raise ValueError("c_index.globals must have unique global_id values")
        global_refs[global_id] = global_context_refs(
            item, chunk_limit, add_fact
        )

    scc_by_id: dict[str, Mapping[str, Any]] = {}
    node_ids_by_scc: dict[str, list[str]] = {}
    for scc in sccs:
        scc_id = _required_string(scc, "scc_id")
        member_ids = _string_list(scc.get("node_ids"))
        if not member_ids or any(item not in node_refs for item in member_ids):
            raise ValueError("migration_graph.sccs contain invalid node_ids")
        if scc_id in scc_by_id:
            raise ValueError("migration_graph.sccs must have unique scc_id values")
        scc_by_id[scc_id] = scc
        node_ids_by_scc[scc_id] = member_ids
    wave_by_scc: dict[str, int] = {}
    for wave in waves:
        wave_index = wave.get("wave_index")
        if isinstance(wave_index, bool) or not isinstance(wave_index, int) or wave_index < 0:
            raise ValueError("migration_graph wave_index must be a non-negative integer")
        for scc_id in _string_list(wave.get("scc_ids")):
            if scc_id in wave_by_scc or scc_id not in scc_by_id:
                raise ValueError("migration_graph waves must partition SCCs")
            wave_by_scc[scc_id] = wave_index
    if set(wave_by_scc) != set(scc_by_id):
        raise ValueError("migration_graph waves must partition SCCs")

    pages: list[dict[str, Any]] = []
    retrieval_bindings: list[dict[str, Any]] = []
    retrieval_sets: dict[str, dict[str, Any]] = {}
    retrieval_segments: dict[str, dict[str, Any]] = {}
    selection_identifier_cache: dict[str, frozenset[str]] = {}
    selection_index = ContextSelectionIndex(facts)
    for scc_id in sorted(scc_by_id, key=lambda item: (wave_by_scc[item], item)):
        scc = scc_by_id[scc_id]
        dependencies = _string_list(scc.get("dependency_scc_ids", []))
        if any(item not in scc_by_id for item in dependencies):
            raise ValueError("SCC dependency references an unknown SCC")
        own_nodes = node_ids_by_scc[scc_id]
        dependency_nodes = [
            node_id for dependency in dependencies for node_id in node_ids_by_scc[dependency]
        ]
        refs = [_add_fact(facts, "scc_dependency", {"scc_id": scc_id,
                 "dependency_scc_id": dependency}) for dependency in dependencies]
        for node_id in own_nodes:
            refs.extend(node_refs[node_id])
            refs.extend(unit_refs[node_units[node_id]])
            binding = graph_by_node[node_id]
            for item in _objects(binding.get("global_references", []), "global_references"):
                for value in _string_list(item.get("global_ids", [])):
                    refs.extend(global_refs.get(value, []))
        for node_id in dependency_nodes:
            refs.extend(interface_refs[node_id])
        refs = list(dict.fromkeys(refs))
        refs, retrieval_binding, retrieval_set, segments = partition_context_refs(
            scc_id, refs, facts, add_fact,
            max_selected_bytes=selection_limit,
            identifier_cache=selection_identifier_cache,
            selection_index=selection_index,
        )
        if retrieval_binding is not None and retrieval_set is not None:
            set_sha256 = retrieval_binding["retrieval_set_sha256"]
            existing = retrieval_sets.setdefault(set_sha256, retrieval_set)
            if existing != retrieval_set:
                raise ValueError("context retrieval set identity collision")
            for segment_sha256, segment in segments.items():
                existing_segment = retrieval_segments.setdefault(
                    segment_sha256, segment
                )
                if existing_segment != segment:
                    raise ValueError("context retrieval segment identity collision")
            retrieval_bindings.append(retrieval_binding)
        meta = {
            "wave_index": wave_by_scc[scc_id],
            "scc_id": scc_id,
            "classification": _required_string(scc, "classification"),
            "dependency_count": len(dependencies),
            "dependency_set_sha256": hashlib.sha256(_canonical(dependencies)).hexdigest(),
        }
        pages.extend(_paginate(meta, refs, facts, byte_limit, token_limit))

    parser_limitations = _string_list(migration_graph.get("parser_limitations", []))
    blockers = _safe_blockers(migration_graph.get("blockers", []))
    return {
        "schema_version": 1,
        "status": "ready_with_boundaries" if blockers else "ready",
        "budgets": {"max_page_bytes": byte_limit, "max_page_tokens": token_limit,
                    "max_selected_bytes": selection_limit,
                    "token_estimator": "utf8_bytes_upper_bound"},
        "shared_facts": {key: facts[key] for key in sorted(facts)},
        "pages": pages,
        "retrieval_bindings": retrieval_bindings,
        "retrieval_segments": {
            key: retrieval_segments[key] for key in sorted(retrieval_segments)
        },
        "retrieval_sets": {key: retrieval_sets[key] for key in sorted(retrieval_sets)},
        "parser_limitations": parser_limitations,
        "blockers": blockers,
        "model_input_policy": {
            "source_storage": "shared_fact_store_only",
            "visibility": "bounded_seed_with_host_retrieval_index",
            "oracle_values": "withheld", "expected_actual": "withheld",
        },
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }


def _paginate(meta: Mapping[str, Any], refs: Sequence[str], facts: Mapping[str, Any],
              byte_limit: int, token_limit: int) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    current: list[str] = []
    for ref in refs:
        candidate = current + [ref]
        if _fits(meta, len(pages), candidate, facts, byte_limit, token_limit):
            current = candidate
            continue
        if not current:
            raise ValueError("a context fact cannot fit within the page budgets")
        pages.append(_page(meta, len(pages), current, facts))
        current = [ref]
        if not _fits(meta, len(pages), current, facts, byte_limit, token_limit):
            raise ValueError("a context fact cannot fit within the page budgets")
    if current:
        pages.append(_page(meta, len(pages), current, facts))
    return pages


def _fits(meta: Mapping[str, Any], part: int, refs: Sequence[str], facts: Mapping[str, Any],
          byte_limit: int, token_limit: int) -> bool:
    size = len(_materialized(meta, part, refs, facts))
    return size <= byte_limit and size <= token_limit


def _page(meta: Mapping[str, Any], part: int, refs: Sequence[str],
          facts: Mapping[str, Any]) -> dict[str, Any]:
    encoded = _materialized(meta, part, refs, facts)
    identity = _canonical({**meta, "part_index": part, "fact_refs": list(refs)})
    return {**meta, "part_index": part,
            "page_id": f"page-{hashlib.sha256(identity).hexdigest()[:24]}",
            "fact_refs": list(refs), "materialized_bytes": len(encoded),
            "estimated_tokens": len(encoded),
            "materialized_sha256": hashlib.sha256(encoded).hexdigest()}


def _materialized(meta: Mapping[str, Any], part: int, refs: Sequence[str],
                  facts: Mapping[str, Any]) -> bytes:
    return _canonical({**meta, "part_index": part,
                       "facts": [{"sha256": ref, **facts[ref]} for ref in refs]})


def _add_fact(store: dict[str, dict[str, Any]], kind: str, payload: Mapping[str, Any]) -> str:
    fact = {"kind": kind, "payload": dict(payload)}
    digest = hashlib.sha256(_canonical(fact)).hexdigest()
    store.setdefault(digest, fact)
    return digest


paginate_context_pages = build_context_pages

__all__ = ["build_context_pages", "paginate_context_pages"]
