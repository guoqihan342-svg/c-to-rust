from __future__ import annotations

import re
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
READY_SOURCE_SPAN_STATUSES = frozenset(
    {"real_source_bound", "inline_slice_spec", "inline_translation_carrier_bound"}
)
BLOCKED_SOURCE_SPAN_STATUSES = frozenset(
    {
        "blocked_path_outside_source_root",
        "source_file_missing",
        "blocked_source_hash_mismatch",
        "source_span_too_large",
        "source_span_empty",
        "source_span_coordinates_missing",
        "blocked_span_hash_mismatch",
        "omitted_too_large",
        "unsupported_source_encoding",
        "source_span_unavailable",
        "blocked_translation_carrier_contract",
        "source_binding_incomplete",
        "source_root_not_ready",
        "source_file_changed_during_read",
    }
)


def evaluate_provider_readiness(context_pack: dict[str, Any]) -> dict[str, str]:
    """Return a bounded source-span admission result before provider invocation."""
    source_root = context_pack.get("source_root") if isinstance(context_pack, dict) else None
    source_root_status = source_root.get("status") if isinstance(source_root, dict) else None
    source = context_pack.get("source") if isinstance(context_pack, dict) else None
    span = source.get("span") if isinstance(source, dict) else None
    raw_status = span.get("status") if isinstance(span, dict) else None
    if raw_status == "inline_slice_spec" and source_root_status == "unavailable" and inline_span_is_bound(span):
        return {"status": "ready", "source_span_status": raw_status}
    if (
        raw_status in {"real_source_bound", "inline_translation_carrier_bound"}
        and source_root_status in {"explicit", "slice_spec_relative"}
        and bound_project_span_is_complete(source, span)
    ):
        return {"status": "ready", "source_span_status": raw_status}
    if raw_status in READY_SOURCE_SPAN_STATUSES:
        reason = (
            "source_root_not_ready"
            if source_root_status not in {"unavailable", "explicit", "slice_spec_relative"}
            else "source_binding_incomplete"
        )
        return {"status": "blocked", "source_span_status": reason}
    source_span_status = (
        raw_status if raw_status in BLOCKED_SOURCE_SPAN_STATUSES else "invalid_context_shape"
    )
    return {"status": "blocked", "source_span_status": source_span_status}


def inline_span_is_bound(span: dict[str, Any]) -> bool:
    return is_sha256(span.get("sha256")) and isinstance(span.get("content"), str)


def bound_project_span_is_complete(source: Any, span: dict[str, Any]) -> bool:
    source_input = source.get("input") if isinstance(source, dict) else None
    if not isinstance(source_input, dict) or not isinstance(span.get("content"), str):
        return False
    if not all(
        is_sha256(source_input.get(field))
        for field in ("sha256", "declared_sha256")
    ) or source_input.get("hash_match_mode") not in {"exact", "newline_equivalent"}:
        return False
    if not all(is_sha256(span.get(field)) for field in ("sha256", "declared_sha256")):
        return False
    if raw_hash_mode_invalid(span):
        return False
    if span.get("status") == "inline_translation_carrier_bound":
        fragment = span.get("real_source_fragment")
        return (
            isinstance(fragment, dict)
            and all(is_sha256(fragment.get(field)) for field in ("sha256", "declared_sha256"))
            and fragment.get("sha256") == fragment.get("declared_sha256")
            and isinstance(fragment.get("content"), str)
        )
    return True


def raw_hash_mode_invalid(span: dict[str, Any]) -> bool:
    return span.get("hash_match_mode") not in {"exact", "newline_equivalent"}


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


__all__ = [
    "BLOCKED_SOURCE_SPAN_STATUSES",
    "READY_SOURCE_SPAN_STATUSES",
    "evaluate_provider_readiness",
]
