from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .artifacts import content_sha256


def bind_selection_materialization(
    retrieval: Mapping[str, Any], entries: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    bound = selection_materialization(retrieval, prepared_page_facts(entries))
    return {**dict(retrieval), **bound}


def prepared_page_facts(
    entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {"page_id": item["page_id"], **item["local_reference"]}
        for item in entries
    ]


def selection_materialization(
    retrieval: Mapping[str, Any], pages: Sequence[Mapping[str, Any]]
) -> dict[str, str]:
    receipt = retrieval.get("selection_receipt_sha256")
    if not _sha256(receipt):
        raise ValueError("context selection receipt SHA-256 is invalid")
    stable_pages: list[dict[str, Any]] = []
    page_ids: set[str] = set()
    for page in pages:
        page_id = page.get("page_id")
        digest = page.get("sha256")
        size = page.get("size_bytes")
        if (
            not isinstance(page_id, str) or not page_id or page_id in page_ids
            or not _sha256(digest) or isinstance(size, bool)
            or not isinstance(size, int) or size < 0
        ):
            raise ValueError("context materialized page fact is invalid")
        page_ids.add(page_id)
        stable_pages.append({
            "page_id": page_id, "sha256": digest, "size_bytes": size,
        })
    page_set = content_sha256(sorted(
        stable_pages, key=lambda item: item["page_id"]
    ))
    materialization = content_sha256({
        "materialized_page_set_sha256": page_set,
        "selection_receipt_sha256": receipt,
    })
    return {
        "materialized_page_set_sha256": page_set,
        "selection_materialization_sha256": materialization,
    }


def require_selection_materialization(
    retrieval: Mapping[str, Any], pages: Sequence[Mapping[str, Any]]
) -> None:
    expected = selection_materialization(retrieval, pages)
    if any(retrieval.get(key) != value for key, value in expected.items()):
        raise ValueError("context selection materialization drifted")


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__ = [
    "bind_selection_materialization", "prepared_page_facts",
    "require_selection_materialization", "selection_materialization",
]
