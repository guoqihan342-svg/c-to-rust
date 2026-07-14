from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .artifacts import checked_relative_path, content_sha256
from .context_required_facts import context_retrieval_ready


FRONTIER_PENDING = "pending_retrieval"
FRONTIER_READY = "ready"
FRONTIER_STATUSES = frozenset({FRONTIER_PENDING, FRONTIER_READY})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_HEAD_KEYS = {
    "schema_version", "run_id", "unit_id", "status", "mode", "query_epoch",
    "input_binding", "selection_input_sha256", "catalog",
    "selection_receipt_sha256", "materialized_page_set_sha256",
    "selection_materialization_sha256",
}
_INPUT_KEYS = {
    "dag_sha256", "group_sha256", "failure_fact_set_sha256",
    "selection_seed_sha256", "limits",
}
_LIMIT_KEYS = {
    "context_byte_budget", "context_token_budget", "context_page_limit",
}


@dataclass(frozen=True, slots=True)
class ContextFrontierProjection:
    status: str
    version: int
    head: dict[str, Any]
    head_sha256: str


def build_initial_context_frontier(
    *, run_id: str, unit_id: str, dag_sha256: str, group_sha256: str,
    context: Mapping[str, Any], limits: Mapping[str, Any],
) -> dict[str, Any]:
    catalog = _reference(context.get("catalog"), "catalog")
    retrieval = context.get("retrieval")
    host_retrieval = isinstance(retrieval, Mapping)
    ready = host_retrieval and context_retrieval_ready(context) and all(
        _sha(retrieval.get(key)) for key in (
            "selection_receipt_sha256", "materialized_page_set_sha256",
            "selection_materialization_sha256",
        )
    )
    status = FRONTIER_READY if not host_retrieval or ready else FRONTIER_PENDING
    seed = _selection_seed(retrieval if host_retrieval else None, unit_id)
    input_binding = {
        "dag_sha256": dag_sha256,
        "group_sha256": group_sha256,
        "failure_fact_set_sha256": content_sha256([]),
        "selection_seed_sha256": content_sha256(seed),
        "limits": {key: limits.get(key) for key in sorted(_LIMIT_KEYS)},
    }
    head = {
        "schema_version": 1,
        "run_id": run_id,
        "unit_id": unit_id,
        "status": status,
        "mode": "host_retrieval" if host_retrieval else "static_context",
        "query_epoch": 0,
        "input_binding": input_binding,
        "selection_input_sha256": content_sha256(input_binding),
        "catalog": catalog,
        "selection_receipt_sha256": (
            retrieval.get("selection_receipt_sha256") if ready else None
        ),
        "materialized_page_set_sha256": (
            retrieval.get("materialized_page_set_sha256")
            if ready else (_static_page_set(context) if not host_retrieval else None)
        ),
        "selection_materialization_sha256": (
            retrieval.get("selection_materialization_sha256") if ready else None
        ),
    }
    normalized = validate_context_frontier_head(head)
    return {
        "unit_id": unit_id,
        "group_id": unit_id,
        "initial_status": normalized["status"],
        "initial_head": normalized,
        "initial_head_sha256": content_sha256(normalized),
    }


def validate_context_frontier_head(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _HEAD_KEYS:
        raise ValueError("context frontier head shape is invalid")
    run_id = _text(value, "run_id")
    unit_id = _text(value, "unit_id")
    status = value.get("status")
    mode = value.get("mode")
    epoch = value.get("query_epoch")
    if (
        value.get("schema_version") != 1 or status not in FRONTIER_STATUSES
        or mode not in {"static_context", "host_retrieval"}
        or isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0
    ):
        raise ValueError("context frontier head header is invalid")
    binding = _input_binding(value.get("input_binding"))
    if value.get("selection_input_sha256") != content_sha256(binding):
        raise ValueError("context frontier selection input SHA-256 drifted")
    catalog = _reference(value.get("catalog"), "catalog")
    receipt = value.get("selection_receipt_sha256")
    pages = value.get("materialized_page_set_sha256")
    materialization = value.get("selection_materialization_sha256")
    if status == FRONTIER_PENDING:
        if mode != "host_retrieval" or any(
            item is not None for item in (receipt, pages, materialization)
        ):
            raise ValueError("pending context frontier carries ready output")
    elif mode == "host_retrieval":
        if not all(_sha(item) for item in (receipt, pages, materialization)):
            raise ValueError("ready retrieval frontier output is incomplete")
    elif receipt is not None or materialization is not None or not _sha(pages):
        raise ValueError("static context frontier output is invalid")
    return {
        **dict(value), "run_id": run_id, "unit_id": unit_id,
        "input_binding": binding, "catalog": catalog,
    }


def context_frontier_head_sha256(value: Mapping[str, Any]) -> str:
    return content_sha256(validate_context_frontier_head(value))


def _input_binding(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _INPUT_KEYS:
        raise ValueError("context frontier input binding shape is invalid")
    hashes = {key: value.get(key) for key in _INPUT_KEYS - {"limits"}}
    if not all(_sha(item) for item in hashes.values()):
        raise ValueError("context frontier input binding SHA-256 is invalid")
    limits = value.get("limits")
    if not isinstance(limits, Mapping) or set(limits) != _LIMIT_KEYS:
        raise ValueError("context frontier limits shape is invalid")
    if any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in limits.values()
    ):
        raise ValueError("context frontier limits are invalid")
    return {**hashes, "limits": {key: limits[key] for key in sorted(limits)}}


def _selection_seed(retrieval: Mapping[str, Any] | None, unit_id: str) -> dict[str, Any]:
    if retrieval is None:
        return {"policy": "static-context-v1", "unit_id": unit_id}
    keys = (
        "selection_policy", "query_seed_sha256", "required_fact_query_policy",
        "required_fact_query_sha256", "required_fact_set_sha256",
        "retrieval_set_sha256", "selection_byte_budget",
    )
    return {key: retrieval.get(key) for key in keys}


def _static_page_set(context: Mapping[str, Any]) -> str:
    pages = context.get("pages")
    if (
        not isinstance(pages, list)
        or any(not isinstance(page, Mapping) for page in pages)
    ):
        raise ValueError("static context pages are invalid")
    return content_sha256([
        {
            "page_id": page.get("page_id"), "path": page.get("path"),
            "sha256": page.get("sha256"), "byte_count": page.get("byte_count"),
        }
        for page in pages
    ])


def _reference(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}:
        raise ValueError(f"context frontier {label} reference shape is invalid")
    path = checked_relative_path(str(value.get("path", "")))
    size = value.get("size_bytes")
    if not _sha(value.get("sha256")) or isinstance(size, bool) or not isinstance(size, int) or size < 0:
        raise ValueError(f"context frontier {label} reference is invalid")
    return {"path": path, "sha256": value["sha256"], "size_bytes": size}


def _sha(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _text(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"context frontier {key} is invalid")
    return result


__all__ = [
    "ContextFrontierProjection", "FRONTIER_PENDING", "FRONTIER_READY",
    "build_initial_context_frontier", "context_frontier_head_sha256",
    "validate_context_frontier_head",
]
