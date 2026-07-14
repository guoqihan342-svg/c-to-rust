from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .context_contracts import canonical


_ISSUER = object()
_KIND = "host-context-group-closure-set"
_ARTIFACT_PROFILE = "json-ascii-indent-2-sort-keys-lf-v1"
_LOGICAL_PROFILE = "json-utf8-compact-sort-keys-v1"


class _HostContextGroupProof:
    __slots__ = ("_authority", "_record")

    def __init__(self, authority: object, record: Mapping[str, Any]) -> None:
        if authority is not _ISSUER:
            raise TypeError("context group proofs are host-issued")
        self._authority = authority
        self._record = dict(record)


class _HostContextPageProofSet:
    __slots__ = ("_authority", "_records", "_binding_sha256")

    def __init__(
        self, authority: object, records: tuple[Mapping[str, Any], ...],
        binding_sha256: str,
    ) -> None:
        if authority is not _ISSUER:
            raise TypeError("context closure sets are host-issued")
        self._authority = authority
        self._records = records
        self._binding_sha256 = binding_sha256


class _VerifiedContextClosures:
    __slots__ = ("_authority", "_groups")

    def __init__(self, groups: Mapping[str, Mapping[str, Any]]) -> None:
        self._authority = _ISSUER
        self._groups = MappingProxyType(dict(groups))


class _VerifiedContextGroup:
    __slots__ = ("_authority", "_group_id", "_pages")

    def __init__(self, group_id: str, pages: Mapping[str, Mapping[str, Any]]) -> None:
        self._authority = _ISSUER
        self._group_id = group_id
        self._pages = MappingProxyType(dict(pages))


def _issue_host_context_group_proof(
    group_id: str, context: Mapping[str, Any],
    entries: Sequence[Mapping[str, Any]],
) -> _HostContextGroupProof:
    if not isinstance(group_id, str) or not group_id:
        raise ValueError("context group proof identity is invalid")
    pages = [_page_record(entry) for entry in entries]
    expected_pages = [
        {
            "page_id": page["page_id"], "path": page["path"],
            "sha256": page["sha256"], "size_bytes": page["size_bytes"],
            "estimated_tokens": page["size_bytes"],
        }
        for page in pages
    ]
    if context.get("pages") != expected_pages:
        raise ValueError("context group proof pages drifted")
    record = {
        "group_id": group_id,
        "context_path": checked_relative_path(context.get("path")),
        "context_binding_sha256": content_sha256(context),
        "artifact_canonical_profile": _ARTIFACT_PROFILE,
        "logical_canonical_profile": _LOGICAL_PROFILE,
        "pages": pages,
    }
    return _HostContextGroupProof(_ISSUER, record)


def _issue_host_context_page_proof_set(
    groups: Sequence[_HostContextGroupProof],
) -> _HostContextPageProofSet:
    records = []
    for group in groups:
        if type(group) is not _HostContextGroupProof or group._authority is not _ISSUER:
            raise TypeError("context closure set requires host-issued groups")
        records.append(_validate_group_record(group._record))
    records.sort(key=lambda item: item["group_id"])
    _require_unique_closure_records(records)
    payload = _binding_payload(records)
    return _HostContextPageProofSet(
        _ISSUER, tuple(records), content_sha256(payload),
    )


def _open_host_context_page_proof_set(value: Any) -> _VerifiedContextClosures:
    if (
        type(value) is not _HostContextPageProofSet
        or value._authority is not _ISSUER
    ):
        raise TypeError("context closure set is not host-issued")
    records = [_validate_group_record(item) for item in value._records]
    if records != sorted(records, key=lambda item: item["group_id"]):
        raise ValueError("context closure set order drifted")
    _require_unique_closure_records(records)
    if content_sha256(_binding_payload(records)) != value._binding_sha256:
        raise ValueError("context closure set binding drifted")
    return _VerifiedContextClosures({
        item["group_id"]: MappingProxyType(dict(item)) for item in records
    })


def _verified_context_group(
    proofs: Any, group_id: str, context: Mapping[str, Any],
) -> _VerifiedContextGroup:
    verified = _require_verified_set(proofs)
    record = verified._groups.get(group_id)
    if record is None:
        raise ValueError(f"context group proof is unavailable: {group_id}")
    if (
        record["context_path"] != context.get("path")
        or record["context_binding_sha256"] != content_sha256(context)
    ):
        raise ValueError(f"context group proof binding drifted: {group_id}")
    pages = {
        item["page_id"]: MappingProxyType(dict(item))
        for item in record["pages"]
    }
    return _VerifiedContextGroup(group_id, pages)


def _verified_context_page_reference(
    group: Any, page_id: str, path: str, *, max_page_bytes: int,
) -> dict[str, Any]:
    verified = _require_verified_group(group)
    reference = verified._pages.get(page_id)
    if reference is None or reference["path"] != path:
        raise ValueError(
            f"context page proof is unavailable: {verified._group_id}:{page_id}"
        )
    if reference["size_bytes"] > max_page_bytes:
        raise ValueError(f"context page exceeds byte budget: {path}")
    return dict(reference)


def _require_context_page_proof_coverage(
    proofs: Any, used_group_ids: Sequence[str],
) -> None:
    verified = _require_verified_set(proofs)
    if len(used_group_ids) != len(set(used_group_ids)):
        raise ValueError("context group proof consumption is duplicated")
    expected, actual = set(verified._groups), set(used_group_ids)
    if actual != expected:
        raise ValueError("context group proof coverage drifted")


def _page_record(entry: Mapping[str, Any]) -> dict[str, Any]:
    payload = entry.get("payload")
    metadata = entry.get("page_metadata")
    reference = entry.get("reference")
    if not isinstance(payload, bytes) or not isinstance(metadata, Mapping):
        raise ValueError("context group proof page payload is invalid")
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("context group proof page JSON is invalid") from error
    if canonical_json_bytes(value) != payload:
        raise ValueError("context group proof page JSON is not canonical")
    logical_sha256 = hashlib.sha256(canonical(value)).hexdigest()
    page_id = metadata.get("page_id")
    if (
        not isinstance(page_id, str) or not page_id
        or metadata.get("materialized_sha256") != logical_sha256
        or not isinstance(reference, Mapping)
    ):
        raise ValueError("context group proof page metadata drifted")
    expected = {
        "path": checked_relative_path(reference.get("path")),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    if dict(reference) != expected:
        raise ValueError("context group proof page reference drifted")
    return {
        "page_id": page_id, **expected,
        "logical_sha256": logical_sha256,
    }


def _validate_group_record(value: Any) -> dict[str, Any]:
    keys = {
        "group_id", "context_path", "context_binding_sha256",
        "artifact_canonical_profile", "logical_canonical_profile", "pages",
    }
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError("context group proof shape is invalid")
    record = dict(value)
    if (
        not isinstance(record["group_id"], str) or not record["group_id"]
        or checked_relative_path(record["context_path"]) != record["context_path"]
        or not _sha256(record["context_binding_sha256"])
        or record["artifact_canonical_profile"] != _ARTIFACT_PROFILE
        or record["logical_canonical_profile"] != _LOGICAL_PROFILE
        or not isinstance(record["pages"], list)
    ):
        raise ValueError("context group proof header is invalid")
    pages = []
    for page in record["pages"]:
        if not isinstance(page, Mapping) or set(page) != {
            "page_id", "path", "sha256", "size_bytes", "logical_sha256",
        }:
            raise ValueError("context group proof page shape is invalid")
        normalized = dict(page)
        if (
            not isinstance(normalized["page_id"], str) or not normalized["page_id"]
            or checked_relative_path(normalized["path"]) != normalized["path"]
            or not _sha256(normalized["sha256"])
            or not _sha256(normalized["logical_sha256"])
            or isinstance(normalized["size_bytes"], bool)
            or not isinstance(normalized["size_bytes"], int)
            or normalized["size_bytes"] < 0
        ):
            raise ValueError("context group proof page is invalid")
        pages.append(normalized)
    return {**record, "pages": pages}


def _require_unique_closure_records(records: Sequence[Mapping[str, Any]]) -> None:
    group_ids = [item["group_id"] for item in records]
    page_ids = [page["page_id"] for item in records for page in item["pages"]]
    paths = [page["path"] for item in records for page in item["pages"]]
    if (
        len(group_ids) != len(set(group_ids))
        or len(page_ids) != len(set(page_ids))
        or len(paths) != len(set(paths))
    ):
        raise ValueError("context closure set identity is duplicated")


def _require_verified_set(value: Any) -> _VerifiedContextClosures:
    if type(value) is not _VerifiedContextClosures or value._authority is not _ISSUER:
        raise TypeError("context closures are not host-verified")
    return value


def _require_verified_group(value: Any) -> _VerifiedContextGroup:
    if type(value) is not _VerifiedContextGroup or value._authority is not _ISSUER:
        raise TypeError("context group proof is not host-verified")
    return value


def _binding_payload(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1, "artifact_kind": _KIND,
        "groups": [dict(item) for item in records],
    }


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__: list[str] = []
