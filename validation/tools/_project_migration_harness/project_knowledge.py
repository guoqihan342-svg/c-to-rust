from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .project_knowledge_payload import (
    KINDS,
    knowledge_authority as _authority,
    knowledge_kind as _kind,
    safe_knowledge_payload as _safe_payload,
)


STORE_AUTHORITY = "host-knowledge-store"
MAX_ENTRY_BYTES = 8_192
MAX_BUNDLE_BYTES = 131_072
MAX_ENTRIES = 64
SUBJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def knowledge_entry(
    *, kind: str, authority: str, subjects: Sequence[str],
    payload: Mapping[str, Any], evidence_sha256s: Sequence[str],
) -> dict[str, Any]:
    normalized_kind = _kind(kind)
    core = {
        "kind": normalized_kind,
        "authority": _authority(authority),
        "subjects": _subjects(subjects),
        "payload": _safe_payload(normalized_kind, payload),
        "evidence_sha256s": _hashes(evidence_sha256s),
    }
    if not core["evidence_sha256s"]:
        raise ValueError("knowledge entry requires host evidence")
    if len(canonical_json_bytes(core)) > MAX_ENTRY_BYTES:
        raise ValueError("knowledge entry exceeds its bounded size")
    return {"sha256": content_sha256(core), **core}


def build_project_knowledge(
    entries: Sequence[Mapping[str, Any]], *, subject_refs: Sequence[str],
    kinds: Sequence[str] | None = None, max_entries: int = 16,
    max_bytes: int = 65_536,
) -> dict[str, Any]:
    subjects = _subjects(subject_refs)
    if not subjects:
        raise ValueError("knowledge query requires at least one subject")
    selected_kinds = sorted({_kind(value) for value in (kinds or sorted(KINDS))})
    entry_limit = _bounded(max_entries, 1, MAX_ENTRIES, "max_entries")
    byte_limit = _bounded(max_bytes, 1_024, MAX_BUNDLE_BYTES, "max_bytes")
    normalized: dict[str, dict[str, Any]] = {}
    for raw in entries:
        entry = validate_knowledge_entry(raw)
        normalized.setdefault(entry["sha256"], entry)
    subject_set = set(subjects)
    eligible = [
        entry for entry in normalized.values()
        if entry["kind"] in selected_kinds and subject_set.intersection(entry["subjects"])
    ]
    eligible.sort(key=lambda entry: (
        -len(subject_set.intersection(entry["subjects"])), entry["kind"], entry["sha256"],
    ))
    query = {
        "subject_refs": subjects,
        "kinds": selected_kinds,
        "max_entries": entry_limit,
        "max_bytes": byte_limit,
    }
    chosen: list[dict[str, Any]] = []
    for entry in eligible:
        if len(chosen) >= entry_limit:
            break
        candidate = _bundle_payload(query, chosen + [entry])
        if len(canonical_json_bytes({**candidate, "bundle_sha256": content_sha256(candidate)})) <= byte_limit:
            chosen.append(entry)
    payload = _bundle_payload(query, chosen)
    return {**payload, "bundle_sha256": content_sha256(payload)}


def validate_project_knowledge(value: Any) -> dict[str, Any]:
    required = {
        "schema_version", "authority", "query", "entries", "entry_count",
        "bundle_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("project knowledge bundle fields are invalid")
    query = value.get("query")
    if not isinstance(query, Mapping) or set(query) != {
        "subject_refs", "kinds", "max_entries", "max_bytes",
    }:
        raise ValueError("project knowledge query fields are invalid")
    subjects = _subjects(query.get("subject_refs"))
    kinds = [_kind(item) for item in _strings(query.get("kinds"), "query kinds")]
    if kinds != sorted(set(kinds)) or not subjects:
        raise ValueError("project knowledge query must be canonical")
    max_entries = _bounded(query.get("max_entries"), 1, MAX_ENTRIES, "max_entries")
    max_bytes = _bounded(query.get("max_bytes"), 1_024, MAX_BUNDLE_BYTES, "max_bytes")
    raw_entries = value.get("entries")
    if not isinstance(raw_entries, list) or len(raw_entries) > max_entries:
        raise ValueError("project knowledge entries exceed their bound")
    entries = [validate_knowledge_entry(item) for item in raw_entries]
    if len({entry["sha256"] for entry in entries}) != len(entries):
        raise ValueError("project knowledge entries must be unique")
    subject_set = set(subjects)
    if any(entry["kind"] not in kinds or not subject_set.intersection(entry["subjects"]) for entry in entries):
        raise ValueError("project knowledge entry is irrelevant to its query")
    payload = _bundle_payload({
        "subject_refs": subjects,
        "kinds": kinds,
        "max_entries": max_entries,
        "max_bytes": max_bytes,
    }, entries)
    if (
        value.get("schema_version") != 1
        or value.get("authority") != STORE_AUTHORITY
        or value.get("entry_count") != len(entries)
        or value.get("bundle_sha256") != content_sha256(payload)
        or len(canonical_json_bytes(dict(value))) > max_bytes
    ):
        raise ValueError("project knowledge bundle binding is invalid")
    return dict(value)


def validate_knowledge_entry(value: Any) -> dict[str, Any]:
    required = {"sha256", "kind", "authority", "subjects", "payload", "evidence_sha256s"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("knowledge entry fields are invalid")
    normalized = knowledge_entry(
        kind=value.get("kind"),
        authority=value.get("authority"),
        subjects=value.get("subjects"),
        payload=value.get("payload"),
        evidence_sha256s=value.get("evidence_sha256s"),
    )
    if dict(value) != normalized:
        raise ValueError("knowledge entry is not canonical or hash-bound")
    return normalized


def validate_knowledge_reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}:
        raise ValueError("project knowledge reference fields are invalid")
    path = checked_relative_path(value.get("path"))
    digest = value.get("sha256")
    size = value.get("size_bytes")
    if not isinstance(digest, str) or SHA256_RE.fullmatch(digest) is None:
        raise ValueError("project knowledge reference SHA-256 is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_BUNDLE_BYTES:
        raise ValueError("project knowledge reference size is invalid")
    return {"path": path, "sha256": digest, "size_bytes": size}


def _bundle_payload(query: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "authority": STORE_AUTHORITY,
        "query": dict(query),
        "entries": [dict(entry) for entry in entries],
        "entry_count": len(entries),
    }


def _subjects(values: Any) -> list[str]:
    result = _strings(values, "subjects")
    if any(SUBJECT_RE.fullmatch(item) is None for item in result):
        raise ValueError("knowledge subjects must be portable identifiers")
    if result != sorted(set(result)):
        raise ValueError("knowledge subjects must be sorted and unique")
    return result


def _strings(values: Any, label: str) -> list[str]:
    if not isinstance(values, (list, tuple)) or not all(isinstance(item, str) for item in values):
        raise ValueError(f"{label} must be an array of strings")
    return list(values)


def _hashes(values: Any) -> list[str]:
    result = _strings(values, "evidence_sha256s")
    if result != sorted(set(result)) or any(SHA256_RE.fullmatch(item) is None for item in result):
        raise ValueError("knowledge evidence SHAs must be canonical")
    return result


def _bounded(value: Any, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{label} is outside its bound")
    return value


__all__ = [
    "build_project_knowledge", "knowledge_entry", "validate_knowledge_entry",
    "validate_knowledge_reference", "validate_project_knowledge",
]
