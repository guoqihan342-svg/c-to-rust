from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from .artifacts import canonical_json_bytes, canonical_json_metadata


_PATH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def prepare_context_page(
    page: Any, facts: Mapping[str, Any], out_root_rel: str,
    *, max_payload_bytes: int | None = None,
) -> dict[str, Any]:
    if not isinstance(page, Mapping) or not valid_context_path_id(
        page.get("scc_id")
    ):
        raise ValueError("context page SCC binding is invalid")
    page_id = page.get("page_id")
    if not valid_context_path_id(page_id):
        raise ValueError("context page identity is invalid")
    fact_refs = page.get("fact_refs")
    if (
        not isinstance(fact_refs, list) or not fact_refs
        or len(fact_refs) != len(set(fact_refs))
        or any(not _sha256(digest) or digest not in facts for digest in fact_refs)
    ):
        raise ValueError("context page references an unknown shared fact")
    fields = (
        "wave_index", "scc_id", "classification", "dependency_count",
        "dependency_set_sha256", "part_index",
    )
    materialized = {
        **{key: page.get(key) for key in fields},
        "facts": [{"sha256": digest, **facts[digest]} for digest in fact_refs],
    }
    artifact_sha256, artifact_size = canonical_json_metadata(materialized)
    if max_payload_bytes is not None and (
        isinstance(max_payload_bytes, bool)
        or not isinstance(max_payload_bytes, int)
        or max_payload_bytes < 1
        or artifact_size > max_payload_bytes
    ):
        raise ValueError("context page exceeds byte budget")
    compact = json.dumps(
        materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if (
        page.get("materialized_sha256") != hashlib.sha256(compact).hexdigest()
        or page.get("materialized_bytes") != len(compact)
        or page.get("estimated_tokens") != len(compact)
    ):
        raise ValueError("context page materialized metadata drift")
    payload = canonical_json_bytes(materialized)
    if (
        hashlib.sha256(payload).hexdigest() != artifact_sha256
        or len(payload) != artifact_size
    ):
        raise ValueError("context page canonical metadata drift")
    relative = f"context/pages/{page_id}.json"
    local = {
        "path": relative,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    metadata = {**dict(page), "estimated_tokens": len(payload)}
    return {
        "scc_id": str(page["scc_id"]), "page_id": page_id,
        "fact_refs": list(fact_refs), "payload": payload,
        "relative_path": relative, "local_reference": local,
        "reference": {**local, "path": f"{out_root_rel}/{relative}"},
        "page_metadata": metadata,
    }


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def valid_context_path_id(value: Any) -> bool:
    return isinstance(value, str) and _PATH_ID.fullmatch(value) is not None


def context_group_binding(
    scc_id: str, entries: list[dict[str, Any]], out_root_rel: str,
    retrieval: Mapping[str, Any] | None,
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    entries.sort(key=lambda item: int(item["page_metadata"]["part_index"]))
    pages = [
        {"page_id": entry["page_id"], **entry["reference"]}
        for entry in entries
    ]
    result = {
        "path": f"{out_root_rel}/context/groups/{scc_id}.json",
        "byte_count": sum(int(item["size_bytes"]) for item in pages),
        "token_count": sum(int(item["size_bytes"]) for item in pages),
        "page_count": len(pages),
        "pages": [
            {**item, "estimated_tokens": item["size_bytes"]} for item in pages
        ],
        "catalog": dict(catalog),
    }
    if retrieval is not None:
        result["retrieval"] = {
            key: value for key, value in retrieval.items() if key != "fact_refs"
        }
    return result


__all__ = [
    "context_group_binding", "prepare_context_page", "valid_context_path_id",
]
