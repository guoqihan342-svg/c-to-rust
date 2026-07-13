from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes
from .artifact_write_once import write_once_bytes_artifact


CATALOG_SCHEMA_VERSION = 1


def prepare_context_catalog(
    scc_id: str,
    entries: Sequence[Mapping[str, Any]],
    retrieval: Mapping[str, Any] | None,
    *,
    out_root_rel: str,
    model_input_policy: Any,
    claim_boundary: Any,
) -> dict[str, Any]:
    if not isinstance(scc_id, str) or not scc_id:
        raise ValueError("context catalog SCC identity is invalid")
    pages = []
    for entry in entries:
        try:
            payload = json.loads(bytes(entry["payload"]).decode("utf-8"))
        except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("context catalog page payload is invalid") from error
        encoded = canonical_json_bytes(payload)
        reference = dict(entry.get("local_reference", {}))
        if (
            encoded != entry.get("payload")
            or reference.get("sha256") != hashlib.sha256(encoded).hexdigest()
            or reference.get("size_bytes") != len(encoded)
        ):
            raise ValueError("context catalog page binding drifted")
        pages.append({
            "page_id": entry.get("page_id"),
            "metadata": dict(entry.get("page_metadata", {})),
            "reference": reference,
            "payload": payload,
        })
    payload = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "artifact_kind": "host-context-group-catalog",
        "scc_id": scc_id,
        "pages": pages,
        "retrieval": _public_retrieval(retrieval),
        "model_input_policy": model_input_policy,
        "claim_boundary": claim_boundary,
    }
    encoded = canonical_json_bytes(payload)
    relative = f"context/catalog/groups/{scc_id}.json"
    local = {
        "path": relative,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }
    return {
        "payload": encoded,
        "local_reference": local,
        "reference": {**local, "path": f"{out_root_rel}/{relative}"},
    }


def persist_context_catalogs(
    catalogs: Mapping[str, Mapping[str, Any]], *, out_root: Path,
) -> list[dict[str, Any]]:
    references = []
    for scc_id in sorted(catalogs):
        catalog = catalogs[scc_id]
        relative = str(catalog["local_reference"]["path"])
        payload = bytes(catalog["payload"])
        reference = write_once_bytes_artifact(out_root, relative, payload)
        if reference != catalog["local_reference"]:
            raise ValueError("context catalog materialization drifted")
        references.append({"scc_id": scc_id, **reference})
    return references


def validate_context_catalog(value: Any) -> dict[str, Any]:
    required = {
        "schema_version", "artifact_kind", "scc_id", "pages", "retrieval",
        "model_input_policy", "claim_boundary",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("context catalog shape is invalid")
    if (
        value.get("schema_version") != CATALOG_SCHEMA_VERSION
        or value.get("artifact_kind") != "host-context-group-catalog"
        or not isinstance(value.get("scc_id"), str)
        or not value["scc_id"]
        or not isinstance(value.get("pages"), list)
    ):
        raise ValueError("context catalog header is invalid")
    pages = []
    page_ids: set[str] = set()
    for page in value["pages"]:
        if not isinstance(page, Mapping) or set(page) != {
            "page_id", "metadata", "reference", "payload",
        }:
            raise ValueError("context catalog page shape is invalid")
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id or page_id in page_ids:
            raise ValueError("context catalog page identity is invalid")
        page_ids.add(page_id)
        metadata = page.get("metadata")
        reference = page.get("reference")
        if not isinstance(metadata, Mapping) or metadata.get("page_id") != page_id:
            raise ValueError("context catalog page metadata is invalid")
        encoded = canonical_json_bytes(page.get("payload"))
        if not _reference_matches(reference, encoded):
            raise ValueError("context catalog page reference is invalid")
        pages.append({
            "page_id": page_id,
            "metadata": dict(metadata),
            "reference": dict(reference),
            "payload": page["payload"],
        })
    retrieval = value.get("retrieval")
    if retrieval is not None and not isinstance(retrieval, Mapping):
        raise ValueError("context catalog retrieval binding is invalid")
    return {**dict(value), "pages": pages, "retrieval": (
        dict(retrieval) if isinstance(retrieval, Mapping) else None
    )}


def _public_retrieval(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {key: item for key, item in value.items() if key != "fact_refs"}


def _reference_matches(value: Any, encoded: bytes) -> bool:
    return (
        isinstance(value, Mapping)
        and set(value) == {"path", "sha256", "size_bytes"}
        and isinstance(value.get("path"), str)
        and value.get("sha256") == hashlib.sha256(encoded).hexdigest()
        and value.get("size_bytes") == len(encoded)
    )


__all__ = [
    "persist_context_catalogs", "prepare_context_catalog",
    "validate_context_catalog",
]
