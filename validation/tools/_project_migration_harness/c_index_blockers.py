from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


def build_blocker_catalog(
    blockers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Content-address blocker evidence and deduplicate repeated closure facts."""
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    facts: dict[str, dict[str, Any]] = {}
    for blocker in blockers:
        unit_id = str(blocker.get("unit_id", ""))
        kind = str(blocker.get("kind", ""))
        if not unit_id or not kind:
            raise ValueError("parser blocker identity is invalid")
        source_path = blocker.get("source_path")
        source_sha256 = blocker.get("source_sha256")
        if not isinstance(source_path, str) or not source_path:
            raise ValueError("parser blocker source path is invalid")
        if not isinstance(source_sha256, str) or len(source_sha256) != 64:
            raise ValueError("parser blocker source SHA-256 is invalid")
        normalized = {
            "kind": kind,
            "source_path": source_path,
            "source_sha256": source_sha256,
        }
        offset = blocker.get("byte_offset")
        if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0:
            normalized["byte_offset"] = offset
        directive = blocker.get("directive_sha256")
        if isinstance(directive, str):
            normalized["directive_sha256"] = directive
        encoded = _canonical(normalized)
        evidence_sha256 = hashlib.sha256(encoded).hexdigest()
        facts.setdefault(evidence_sha256, normalized)
        grouped[(unit_id, kind)].append(evidence_sha256)

    result: list[dict[str, Any]] = []
    sets: dict[str, dict[str, Any]] = {}
    for (unit_id, kind), refs in sorted(grouped.items()):
        ordered = sorted(set(refs))
        set_sha256 = hashlib.sha256(_canonical(ordered)).hexdigest()
        sets.setdefault(set_sha256, {
            "evidence_count": len(ordered), "evidence_refs": ordered,
        })
        summary: dict[str, Any] = {
            "unit_id": unit_id,
            "kind": kind,
            "occurrence_count": len(ordered),
            "evidence_set_sha256": set_sha256,
        }
        offsets = [
            facts[digest]["byte_offset"] for digest in ordered
            if "byte_offset" in facts[digest]
        ]
        if offsets:
            summary["byte_offset"] = min(offsets)
        result.append(summary)
    return {
        "blockers": result,
        "blocker_evidence_facts": {key: facts[key] for key in sorted(facts)},
        "blocker_evidence_sets": {key: sets[key] for key in sorted(sets)},
    }


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")


__all__ = ["build_blocker_catalog"]
