from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .context_contracts import canonical
from .context_selection import select_deferred_context
from .context_selection_index import ContextSelectionIndex


DEFERRED_FACT_KINDS = frozenset({
    "header_source", "header_source_binding", "include_binding",
    "top_level_source", "translation_unit_function_spans",
    "translation_unit_uncovered_ranges",
})
AddFact = Callable[[str, Mapping[str, Any]], str]


def partition_context_refs(
    scc_id: str,
    refs: Sequence[str],
    facts: Mapping[str, Mapping[str, Any]],
    add_fact: AddFact,
    *,
    max_selected_bytes: int,
    identifier_cache: dict[str, frozenset[str]],
    selection_index: ContextSelectionIndex,
) -> tuple[
    list[str], dict[str, Any] | None, dict[str, Any] | None,
    dict[str, dict[str, Any]],
]:
    visible: list[str] = []
    deferred: list[str] = []
    for digest in refs:
        fact = facts.get(digest)
        if not isinstance(fact, Mapping) or not isinstance(fact.get("kind"), str):
            raise ValueError("context fact reference is invalid")
        if fact["kind"] in DEFERRED_FACT_KINDS:
            deferred.append(digest)
        else:
            visible.append(digest)
    if not deferred:
        return visible, None, None, {}
    selection = select_deferred_context(
        scc_id, visible, deferred, facts,
        max_selected_bytes=max_selected_bytes,
        identifier_cache=identifier_cache,
        selection_index=selection_index,
    )
    selected = selection["selected_fact_refs"]
    omitted = selection["omitted_fact_refs"]
    segments = _segments(omitted, facts)
    segment_refs = sorted(segments)
    set_sha256 = hashlib.sha256(canonical(segment_refs)).hexdigest()
    binding = _with_receipt({
        **_binding_for(scc_id, set_sha256, omitted, facts),
        **selection["binding"],
    })
    summary = add_fact("context_retrieval_summary", _summary_payload(binding))
    return visible + selected + [summary], binding, {
        "fact_count": len(omitted),
        "segment_count": len(segment_refs),
        "segment_refs": segment_refs,
    }, segments


def validate_retrieval_bundle(
    bundle: Mapping[str, Any],
    facts: Mapping[str, Any],
    pages: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    raw_sets = bundle.get("retrieval_sets", {})
    raw_segments = bundle.get("retrieval_segments", {})
    raw_bindings = bundle.get("retrieval_bindings", [])
    if (
        not isinstance(raw_sets, Mapping) or not isinstance(raw_segments, Mapping)
        or not isinstance(raw_bindings, list)
    ):
        raise ValueError("context retrieval index shape is invalid")
    segments = _validated_segments(raw_segments, facts)
    sets = _validated_sets(raw_sets, segments)
    seed_by_scc: dict[str, set[str]] = {}
    for page in pages:
        scc_id, refs = page.get("scc_id"), page.get("fact_refs")
        if not isinstance(scc_id, str) or not _string_list(refs):
            raise ValueError("context retrieval page binding is invalid")
        seed_by_scc.setdefault(scc_id, set()).update(refs)
    result: dict[str, dict[str, Any]] = {}
    used_sets: set[str] = set()
    identifier_cache: dict[str, frozenset[str]] = {}
    selection_index = ContextSelectionIndex(facts)
    for binding in raw_bindings:
        if not isinstance(binding, Mapping):
            raise ValueError("context retrieval binding is invalid")
        scc_id = binding.get("scc_id")
        set_sha256 = binding.get("retrieval_set_sha256")
        if not isinstance(scc_id, str) or scc_id in result or scc_id not in seed_by_scc:
            raise ValueError("context retrieval SCC binding is invalid")
        if not isinstance(set_sha256, str) or set_sha256 not in sets:
            raise ValueError("context retrieval set binding is invalid")
        refs = [
            digest for segment in sets[set_sha256]
            for digest in segments[segment]
        ]
        if len(refs) != len(set(refs)):
            raise ValueError("context retrieval set contains duplicate facts")
        if any(ref not in facts or ref in seed_by_scc[scc_id] for ref in refs):
            raise ValueError("context retrieval facts are missing or already visible")
        seed_refs = seed_by_scc[scc_id]
        required_refs = [
            ref for ref in seed_refs
            if facts[ref].get("kind") not in DEFERRED_FACT_KINDS
            and facts[ref].get("kind") != "context_retrieval_summary"
        ]
        selected_refs = [
            ref for ref in seed_refs
            if facts[ref].get("kind") in DEFERRED_FACT_KINDS
        ]
        selection = select_deferred_context(
            scc_id, required_refs, [*selected_refs, *refs], facts,
            max_selected_bytes=binding.get("selection_byte_budget"),
            identifier_cache=identifier_cache,
            selection_index=selection_index,
        )
        expected = _with_receipt({
            **_binding_for(scc_id, set_sha256, refs, facts),
            **selection["binding"],
        })
        if dict(binding) != expected:
            raise ValueError("context retrieval binding does not match its facts")
        summary_payload = _summary_payload(expected)
        if not _summary_visible(seed_by_scc[scc_id], facts, summary_payload):
            raise ValueError("context retrieval summary is not bound to a visible page")
        result[scc_id] = {**expected, "fact_refs": list(refs)}
        used_sets.add(set_sha256)
    if used_sets != set(raw_sets):
        raise ValueError("context retrieval sets must be referenced exactly")
    used_segments = {
        segment for set_sha256 in used_sets for segment in sets[set_sha256]
    }
    if used_segments != set(raw_segments):
        raise ValueError("context retrieval segments must be referenced exactly")
    return result


def _segments(
    refs: Sequence[str], facts: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    grouped: dict[tuple[str, str], list[str]] = {}
    for digest in refs:
        fact = facts[digest]
        kind = str(fact["kind"])
        payload = fact.get("payload")
        if not isinstance(payload, Mapping):
            raise ValueError("context retrieval fact payload is invalid")
        owner = payload.get("owner_id", payload.get("unit_id"))
        if not isinstance(owner, str) or not owner:
            raise ValueError("context retrieval fact owner is invalid")
        grouped.setdefault((kind, owner), []).append(digest)
    result: dict[str, dict[str, Any]] = {}
    for segment_refs in grouped.values():
        digest = hashlib.sha256(canonical(segment_refs)).hexdigest()
        record = {"fact_count": len(segment_refs), "fact_refs": segment_refs}
        if digest in result and result[digest] != record:
            raise ValueError("context retrieval segment identity collision")
        result[digest] = record
    return result


def _validated_segments(
    raw: Mapping[str, Any], facts: Mapping[str, Any]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for digest, record in raw.items():
        if not isinstance(digest, str) or not isinstance(record, Mapping):
            raise ValueError("context retrieval segment is invalid")
        refs = record.get("fact_refs")
        if not _string_list(refs) or hashlib.sha256(canonical(refs)).hexdigest() != digest:
            raise ValueError("context retrieval segment SHA-256 is invalid")
        if record.get("fact_count") != len(refs):
            raise ValueError("context retrieval segment count is invalid")
        if any(ref not in facts for ref in refs):
            raise ValueError("context retrieval segment references missing facts")
        result[digest] = list(refs)
    return result


def _validated_sets(
    raw: Mapping[str, Any], segments: Mapping[str, Sequence[str]]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for digest, record in raw.items():
        if not isinstance(digest, str) or not isinstance(record, Mapping):
            raise ValueError("context retrieval set is invalid")
        refs = record.get("segment_refs")
        if not _string_list(refs) or hashlib.sha256(canonical(refs)).hexdigest() != digest:
            raise ValueError("context retrieval set SHA-256 is invalid")
        if any(ref not in segments for ref in refs):
            raise ValueError("context retrieval set references missing segments")
        if record.get("segment_count") != len(refs):
            raise ValueError("context retrieval set segment count is invalid")
        count = sum(len(segments[ref]) for ref in refs)
        if record.get("fact_count") != count:
            raise ValueError("context retrieval set count is invalid")
        result[digest] = list(refs)
    return result


def _binding_for(
    scc_id: str, set_sha256: str, refs: Sequence[str], facts: Mapping[str, Any]
) -> dict[str, Any]:
    kinds = Counter(str(facts[ref]["kind"]) for ref in refs)
    return {
        "scc_id": scc_id,
        "retrieval_set_sha256": set_sha256,
        "omitted_fact_count": len(refs),
        "omitted_kind_counts": [
            {"kind": kind, "count": count} for kind, count in sorted(kinds.items())
        ],
    }


def _with_receipt(binding: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(binding)
    return {
        **payload,
        "selection_receipt_sha256": hashlib.sha256(canonical(payload)).hexdigest(),
    }


def _summary_payload(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: binding[key] for key in (
            "scc_id", "omitted_fact_count", "selected_fact_count",
            "selection_status", "selection_receipt_sha256",
        )
    } | {"visibility": "host_retrieval_required"}


def _summary_visible(
    refs: set[str], facts: Mapping[str, Any], payload: Mapping[str, Any]
) -> bool:
    return any(
        isinstance(facts.get(ref), Mapping)
        and facts[ref].get("kind") == "context_retrieval_summary"
        and facts[ref].get("payload") == payload
        for ref in refs
    )


def _string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item for item in value)


__all__ = [
    "DEFERRED_FACT_KINDS", "partition_context_refs", "validate_retrieval_bundle",
]
