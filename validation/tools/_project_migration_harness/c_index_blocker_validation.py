from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, NoReturn

from .artifacts import checked_relative_path


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_CATALOG_FIELDS = {
    "blockers", "blocker_evidence_facts", "blocker_evidence_sets",
}
_BLOCKER_REQUIRED = {
    "unit_id", "kind", "occurrence_count", "evidence_set_sha256",
}
_BLOCKER_OPTIONAL = {"byte_offset"}
_FACT_REQUIRED = {"kind", "source_path", "source_sha256"}
_FACT_OPTIONAL = {"byte_offset", "directive_sha256"}
_SET_FIELDS = {"evidence_count", "evidence_refs"}


class CIndexBlockerValidationError(ValueError):
    pass


def validate_blocker_catalog(value: Mapping[str, Any]) -> None:
    """Validate the complete content-addressed output of build_blocker_catalog."""
    if not isinstance(value, Mapping) or set(value) != _CATALOG_FIELDS:
        _fail("blocker_catalog_schema_invalid")
    validate_blocker_evidence(
        value["blockers"],
        value["blocker_evidence_facts"],
        value["blocker_evidence_sets"],
    )


def validate_blocker_evidence(
    blockers: Any,
    blocker_evidence_facts: Any,
    blocker_evidence_sets: Any,
) -> None:
    """Recompute blocker evidence bindings without reading project files."""
    facts = _validated_facts(blocker_evidence_facts)
    evidence_sets = _validated_sets(blocker_evidence_sets, facts)
    if not isinstance(blockers, list):
        _fail("blockers_not_array")

    identities: list[tuple[str, str]] = []
    seen_identities: set[tuple[str, str]] = set()
    referenced_sets: set[str] = set()
    for raw_blocker in blockers:
        if not isinstance(raw_blocker, Mapping):
            _fail("blocker_not_object")
        fields = set(raw_blocker)
        if not _exact_fields(fields, _BLOCKER_REQUIRED, _BLOCKER_OPTIONAL):
            _fail("blocker_schema_invalid")
        unit_id = _nonempty_text(raw_blocker.get("unit_id"), "blocker_unit_id_invalid")
        kind = _nonempty_text(raw_blocker.get("kind"), "blocker_kind_invalid")
        identity = (unit_id, kind)
        if identity in seen_identities:
            _fail("duplicate_blocker_identity")
        seen_identities.add(identity)
        identities.append(identity)

        set_sha256 = _sha256(
            raw_blocker.get("evidence_set_sha256"), "blocker_evidence_set_ref_invalid"
        )
        evidence_set = evidence_sets.get(set_sha256)
        if evidence_set is None:
            _fail("dangling_blocker_evidence_set")
        referenced_sets.add(set_sha256)
        occurrence_count = _non_negative_int(
            raw_blocker.get("occurrence_count"), "blocker_occurrence_count_invalid"
        )
        if occurrence_count != evidence_set["evidence_count"]:
            _fail("blocker_occurrence_count_mismatch")

        bound_facts = [facts[ref] for ref in evidence_set["evidence_refs"]]
        if any(fact["kind"] != kind for fact in bound_facts):
            _fail("blocker_kind_evidence_mismatch")
        offsets = [fact["byte_offset"] for fact in bound_facts if "byte_offset" in fact]
        if "byte_offset" in raw_blocker:
            offset = _non_negative_int(
                raw_blocker["byte_offset"], "blocker_byte_offset_invalid"
            )
            if not offsets or offset != min(offsets):
                _fail("blocker_byte_offset_mismatch")
        elif offsets:
            _fail("blocker_byte_offset_missing")

    if identities != sorted(identities):
        _fail("blockers_not_canonical")
    if referenced_sets != set(evidence_sets):
        _fail("unreferenced_blocker_evidence_set")
    referenced_facts = {
        ref
        for set_sha256 in referenced_sets
        for ref in evidence_sets[set_sha256]["evidence_refs"]
    }
    if referenced_facts != set(facts):
        _fail("unreferenced_blocker_evidence_fact")


def _validated_facts(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        _fail("blocker_evidence_facts_not_object")
    result: dict[str, dict[str, Any]] = {}
    for digest, raw_fact in value.items():
        fact_sha256 = _sha256(digest, "blocker_evidence_fact_key_invalid")
        if not isinstance(raw_fact, Mapping):
            _fail("blocker_evidence_fact_not_object")
        if not _exact_fields(set(raw_fact), _FACT_REQUIRED, _FACT_OPTIONAL):
            _fail("blocker_evidence_fact_schema_invalid")
        fact = dict(raw_fact)
        _nonempty_text(fact.get("kind"), "blocker_evidence_fact_kind_invalid")
        source_path = _nonempty_text(
            fact.get("source_path"), "blocker_evidence_fact_source_path_invalid"
        )
        try:
            checked_relative_path(source_path)
        except (IndexError, ValueError):
            _fail("blocker_evidence_fact_source_path_invalid")
        _sha256(
            fact.get("source_sha256"), "blocker_evidence_fact_source_sha256_invalid"
        )
        if "byte_offset" in fact:
            _non_negative_int(
                fact["byte_offset"], "blocker_evidence_fact_byte_offset_invalid"
            )
        if "directive_sha256" in fact:
            _sha256(
                fact["directive_sha256"],
                "blocker_evidence_fact_directive_sha256_invalid",
            )
        if _content_sha256(fact) != fact_sha256:
            _fail("blocker_evidence_fact_sha256_mismatch")
        result[fact_sha256] = fact
    return result


def _validated_sets(
    value: Any,
    facts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, Mapping):
        _fail("blocker_evidence_sets_not_object")
    result: dict[str, dict[str, Any]] = {}
    for digest, raw_set in value.items():
        set_sha256 = _sha256(digest, "blocker_evidence_set_key_invalid")
        if not isinstance(raw_set, Mapping) or set(raw_set) != _SET_FIELDS:
            _fail("blocker_evidence_set_schema_invalid")
        refs = raw_set.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            _fail("blocker_evidence_refs_invalid")
        normalized_refs = [
            _sha256(ref, "blocker_evidence_ref_invalid") for ref in refs
        ]
        if len(normalized_refs) != len(set(normalized_refs)):
            _fail("duplicate_blocker_evidence_ref")
        if normalized_refs != sorted(normalized_refs):
            _fail("blocker_evidence_refs_not_canonical")
        if any(ref not in facts for ref in normalized_refs):
            _fail("dangling_blocker_evidence_fact")
        count = _non_negative_int(
            raw_set.get("evidence_count"), "blocker_evidence_count_invalid"
        )
        if count != len(normalized_refs):
            _fail("blocker_evidence_count_mismatch")
        if _content_sha256(normalized_refs) != set_sha256:
            _fail("blocker_evidence_set_sha256_mismatch")
        result[set_sha256] = {
            "evidence_count": count,
            "evidence_refs": normalized_refs,
        }
    return result


def _content_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _exact_fields(
    fields: set[str],
    required: set[str],
    optional: set[str],
) -> bool:
    return required <= fields <= required | optional


def _nonempty_text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(code)
    return value


def _non_negative_int(value: Any, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(code)
    return value


def _sha256(value: Any, code: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail(code)
    return value


def _fail(code: str) -> NoReturn:
    raise CIndexBlockerValidationError(code)


__all__ = [
    "CIndexBlockerValidationError",
    "validate_blocker_catalog",
    "validate_blocker_evidence",
]
