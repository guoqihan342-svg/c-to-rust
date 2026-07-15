from __future__ import annotations

from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_trace import validate_cargo_linker_trace
from .native_object_validation import validate_native_object_inspection


_TOP_KEYS = {
    "schema_version", "context_sha256", "candidate_sha256",
    "trace_entry_set_sha256", "status", "requirements", "unverified_gates",
    "semantic_gate", "resolution_gate", "artifact_sha256",
}
_ITEM_KEYS = {
    "requirement_id", "status", "reason_code", "file_name",
    "trace_ordinals", "trace_entry_set_sha256", "inspection",
}
_BLOCKED_REASONS = {
    "native_link_strategy_not_rustc_link_lib",
    "native_link_linux_format_unsupported",
    "native_link_portable_name_unsupported",
    "native_link_proposal_name_mismatch",
    "native_link_proposal_kind_mismatch",
    "native_link_trace_match_missing",
    "native_link_trace_match_ambiguous",
    "native_link_guest_root_unsupported",
    "native_link_actual_artifact_missing",
    "native_link_actual_artifact_unavailable",
    "native_link_actual_artifact_path_escape",
    "native_link_actual_artifact_not_regular",
    "native_link_actual_artifact_inspection_failed",
    "native_link_actual_artifact_unstable",
    "native_link_actual_artifact_type_mismatch",
}
_PREMATCH_REASONS = {
    "native_link_strategy_not_rustc_link_lib",
    "native_link_linux_format_unsupported",
    "native_link_portable_name_unsupported",
    "native_link_proposal_name_mismatch",
    "native_link_proposal_kind_mismatch",
    "native_link_trace_match_missing",
}
_PATH_FAILURE_REASONS = _BLOCKED_REASONS - _PREMATCH_REASONS - {
    "native_link_trace_match_ambiguous",
    "native_link_actual_artifact_type_mismatch",
}


def validate_native_link_actual_resolution(
    value: Any,
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """Reopen observed native artifacts and enforce all non-semantic bounds."""
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    if not isinstance(value, Mapping) or set(value) != _TOP_KEYS:
        raise ValueError("native_link_actual_resolution_schema_invalid")
    requirements = value.get("requirements")
    if not isinstance(requirements, list):
        raise ValueError("native_link_actual_resolution_requirements_invalid")
    expected_ids = [
        item["requirement_id"] for item in sorted(
            context["requirements"], key=lambda item: item["requirement_id"],
        )
    ]
    normalized = [
        _validate_item(item, requirement_id, normalized_trace)
        for item, requirement_id in zip(requirements, expected_ids)
    ]
    if len(requirements) != len(expected_ids):
        raise ValueError("native_link_actual_resolution_coverage_invalid")
    expected_status = (
        "observed"
        if normalized and all(item["status"] == "passed" for item in normalized)
        else "blocked"
    )
    if (
        value.get("schema_version") != 1
        or value.get("context_sha256") != context["context_sha256"]
        or value.get("candidate_sha256") != candidate["candidate_sha256"]
        or value.get("trace_entry_set_sha256")
        != normalized_trace["entry_set_sha256"]
        or value.get("status") != expected_status
        or value.get("unverified_gates") != ["symbols", "target-triple"]
        or value.get("semantic_gate") is not False
        or value.get("resolution_gate") is not False
    ):
        raise ValueError("native_link_actual_resolution_summary_invalid")
    result = {**dict(value), "requirements": normalized}
    claimed = result.pop("artifact_sha256")
    if claimed != content_sha256(result):
        raise ValueError("native_link_actual_resolution_sha256_drift")
    return {**result, "artifact_sha256": claimed}


def _validate_item(
    value: Any, requirement_id: str, trace: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _ITEM_KEYS:
        raise ValueError("native_link_actual_resolution_item_schema_invalid")
    result = dict(value)
    ordinals = result.get("trace_ordinals")
    if (
        result.get("requirement_id") != requirement_id
        or result.get("trace_entry_set_sha256") != trace["entry_set_sha256"]
        or not isinstance(ordinals, list)
        or any(type(item) is not int or item < 0 for item in ordinals)
        or ordinals != sorted(set(ordinals))
    ):
        raise ValueError("native_link_actual_resolution_item_binding_invalid")
    entries = {item["ordinal"]: item for item in trace["entries"]}
    if any(ordinal not in entries for ordinal in ordinals):
        raise ValueError("native_link_actual_resolution_item_ordinal_invalid")
    file_name = result.get("file_name")
    if file_name is not None and (
        not isinstance(file_name, str)
        or not file_name
        or len(file_name.encode("utf-8")) > 255
        or PurePosixPath(file_name).name != file_name
        or "\\" in file_name
        or not ordinals
        or any(
            PurePosixPath(entries[ordinal]["path"]).name != file_name
            for ordinal in ordinals
        )
    ):
        raise ValueError("native_link_actual_resolution_item_file_invalid")
    inspection = result.get("inspection")
    normalized_inspection = (
        None if inspection is None
        else validate_native_object_inspection(inspection)
    )
    status = result.get("status")
    reason = result.get("reason_code")
    if status == "passed":
        valid_state = (
            reason == "native_link_actual_artifact_observed"
            and file_name is not None and bool(ordinals)
            and normalized_inspection is not None
        )
    elif status == "blocked":
        valid_state = (
            reason in _BLOCKED_REASONS
            and _blocked_state_valid(
                reason, file_name, ordinals, normalized_inspection,
            )
        )
    else:
        valid_state = False
    if not valid_state:
        raise ValueError("native_link_actual_resolution_item_state_invalid")
    return {**result, "inspection": normalized_inspection}


def _blocked_state_valid(
    reason: Any, file_name: Any, ordinals: list[int], inspection: Any,
) -> bool:
    if reason in _PREMATCH_REASONS:
        return file_name is None and not ordinals and inspection is None
    if reason == "native_link_trace_match_ambiguous":
        return file_name is None and bool(ordinals) and inspection is None
    if reason in _PATH_FAILURE_REASONS:
        return file_name is not None and bool(ordinals) and inspection is None
    if reason == "native_link_actual_artifact_type_mismatch":
        return file_name is not None and bool(ordinals) and inspection is not None
    return False


__all__ = ["validate_native_link_actual_resolution"]
