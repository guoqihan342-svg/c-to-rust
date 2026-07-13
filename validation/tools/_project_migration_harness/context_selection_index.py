from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SOURCE_KINDS = frozenset({"header_source", "top_level_source"})
_MAX_DEFINITION_REFS = 4


class ContextSelectionIndex:
    """Invocation-local inverted index for deferred source fact selection."""

    def __init__(self, facts: Mapping[str, Mapping[str, Any]]) -> None:
        groups: dict[tuple[str, str], list[tuple[int, str, str]]] = defaultdict(list)
        for digest, fact in facts.items():
            kind = fact.get("kind")
            payload = fact.get("payload")
            if kind not in _SOURCE_KINDS or not isinstance(payload, Mapping):
                continue
            owner = payload.get("owner_id")
            index = payload.get("chunk_index")
            content = payload.get("content")
            if not isinstance(owner, str) or not isinstance(index, int) \
                    or not isinstance(content, str):
                raise ValueError("context selection source fact is invalid")
            groups[(str(kind), owner)].append((index, digest, content))

        self._metadata: dict[str, tuple[str, str]] = {}
        self._neighbors: dict[str, tuple[str | None, str | None]] = {}
        self._content: dict[str, str] = {}
        by_token: dict[str, set[str]] = defaultdict(set)
        for (kind, owner), chunks in groups.items():
            ordered = sorted(chunks)
            indexes = [item[0] for item in ordered]
            if indexes != list(range(len(ordered))):
                raise ValueError("context selection source chunks are not contiguous")
            for position, (_index, digest, content) in enumerate(ordered):
                self._metadata[digest] = (kind, owner)
                self._content[digest] = content
                self._neighbors[digest] = (
                    ordered[position - 1][1] if position > 0 else None,
                    ordered[position + 1][1]
                    if position + 1 < len(ordered) else None,
                )
                for token in set(_IDENTIFIER.findall(content)):
                    by_token[token].add(digest)
        self._by_token = {
            token: frozenset(refs) for token, refs in by_token.items()
        }

    def matching_refs(
        self,
        identifiers: Sequence[str],
        candidate_refs: Sequence[str],
        own_units: set[str],
        header_owners: set[str],
    ) -> set[str]:
        candidates = set(candidate_refs)
        result: set[str] = set()
        for token in identifiers:
            hits = sorted(
                ref for ref in self._by_token.get(token, ())
                if ref in candidates and self._allowed(ref, own_units, header_owners)
            )
            if not hits:
                continue
            scored = [(self._definition_score(token, ref), ref) for ref in hits]
            best_score = min(item[0] for item in scored)
            limit = _MAX_DEFINITION_REFS if best_score < 4 else 1
            chosen = [ref for score, ref in scored if score == best_score][:limit]
            result.update(chosen)
            for ref in chosen:
                result.update(self._boundary_neighbors(token, ref, candidates))
        return result

    def _definition_score(self, token: str, ref: str) -> int:
        content = self._content[ref]
        escaped = re.escape(token)
        if re.search(rf"(?m)^\s*#\s*define\s+{escaped}\b", content):
            return 0
        if re.search(rf"\btypedef\b[\s\S]{{0,768}}\b{escaped}\b", content):
            return 1
        if re.search(
            rf"\b(?:struct|union|enum)\s+{escaped}\s*\{{", content
        ):
            return 1
        if re.search(rf"\b{escaped}\s*\([^;{{}}]*\)\s*;", content):
            return 2
        if re.search(rf"\b{escaped}\b[^;{{}}]*;", content):
            return 3
        return 4

    def _boundary_neighbors(
        self, token: str, ref: str, candidates: set[str]
    ) -> set[str]:
        content = self._content[ref]
        position = content.find(token)
        if position < 0:
            return set()
        previous, following = self._neighbors.get(ref, (None, None))
        selected: set[str] = set()
        if position < 128 and previous is not None:
            selected.add(previous)
        if len(content) - position - len(token) < 128 and following is not None:
            selected.add(following)
        return {
            neighbor for neighbor in selected
            if neighbor in candidates
        }

    def _allowed(
        self, ref: str, own_units: set[str], header_owners: set[str]
    ) -> bool:
        metadata = self._metadata.get(ref)
        if metadata is None:
            return False
        kind, owner = metadata
        return (
            kind == "header_source" and owner in header_owners
        ) or (
            kind == "top_level_source" and owner in own_units
        )


__all__ = ["ContextSelectionIndex"]
