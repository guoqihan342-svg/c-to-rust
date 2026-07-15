from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .native_link_actual_paths import (
    normalize_native_guest_roots,
    reopen_mapped_native_artifact_path,
)
from .native_link_actual_validation import validate_native_link_actual_resolution
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_trace import validate_cargo_linker_trace
from .native_object_symbols import extract_native_object_symbols


def extract_native_link_symbol_reports(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    actual_resolution: Mapping[str, Any],
    *,
    guest_roots: Mapping[str, Path] | None = None,
) -> dict[str, dict[str, Any]]:
    """Extract path-free symbol reports for every observed native artifact."""
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    actual = validate_native_link_actual_resolution(
        actual_resolution, normalized_trace, context, candidate,
    )
    roots = normalize_native_guest_roots(guest_roots)
    reports = {}
    for item in actual["requirements"]:
        if item["status"] != "passed":
            continue
        inspection = item["inspection"]
        if not isinstance(inspection, Mapping):
            raise ValueError("native_link_symbol_report_inspection_missing")
        guest_path = _unique_guest_path(normalized_trace, item)
        requirement = next(
            value for value in context["requirements"]
            if value["requirement_id"] == item["requirement_id"]
        )
        path = reopen_mapped_native_artifact_path(
            guest_path, requirement["library_format"], roots, inspection,
        )
        report = extract_native_object_symbols(path)
        if any(
            report[field] != inspection[field] for field in (
                "object_format", "object_kind", "member_count",
                "file_sha256", "size_bytes",
            )
        ):
            raise ValueError("native_link_symbol_report_object_drift")
        reports[item["requirement_id"]] = report
    return reports


def _unique_guest_path(
    trace: Mapping[str, Any], item: Mapping[str, Any],
) -> str:
    ordinals = set(item["trace_ordinals"])
    paths = {
        str(entry["path"]) for entry in trace["entries"]
        if entry["ordinal"] in ordinals
        and PurePosixPath(str(entry["path"])).name == item["file_name"]
    }
    if len(paths) != 1:
        raise ValueError("native_link_symbol_report_trace_path_invalid")
    return next(iter(paths))


__all__ = ["extract_native_link_symbol_reports"]
