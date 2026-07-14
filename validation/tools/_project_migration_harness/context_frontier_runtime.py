from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .orchestration_facts import read_artifact_reference
from .context_frontier_binding import validate_context_against_frontier
from .context_frontier_state import FRONTIER_READY


def validate_request_context_materialization(
    request: Mapping[str, Any], *, harness_root: Path,
) -> dict[str, Any]:
    reference = request.get("context_materialization")
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("worker context materialization reference is invalid")
    data = read_artifact_reference(harness_root, reference)
    if reference.get("size_bytes") != len(data):
        raise ValueError("worker context materialization size drifted")
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("worker context materialization is not UTF-8 JSON") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValueError("worker context materialization is not canonical JSON")
    _validate_report(value)
    _validate_assignment(value, request)
    _validate_group(value, request, _output_prefix(str(reference["path"])))
    return value


def _validate_report(report: Mapping[str, Any]) -> None:
    if (
        report.get("schema_version") != 1
        or report.get("artifact_kind") != "context-frontier-materialization"
        or report.get("policy") != "scheduled-frontier-only"
    ):
        raise ValueError("worker context materialization contract is invalid")
    selected = report.get("selected_group_ids")
    groups = report.get("groups")
    assignments = report.get("assignments")
    if not all(isinstance(value, list) for value in (
        selected, groups, assignments,
    )):
        raise ValueError("worker context materialization collections are invalid")
    if (
        report.get("write_policy")
        != "content-addressed-write-once-idempotent"
        or not all(isinstance(group_id, str) and group_id for group_id in selected)
    ):
        raise ValueError("worker context materialization write policy is invalid")
    group_ids = [
        group.get("group_id") for group in groups if isinstance(group, Mapping)
    ]
    if (
        len(group_ids) != len(groups)
        or any(not isinstance(group_id, str) for group_id in group_ids)
        or selected != sorted(set(selected))
        or group_ids != selected
        or report.get("selected_group_count") != len(selected)
    ):
        raise ValueError("worker context materialization group set drifted")
    assignment_keys = []
    for item in assignments:
        if (
            not isinstance(item, Mapping)
            or set(item) != {
                "worker_id", "role", "group_id", "assignment_sha256",
            }
            or not all(isinstance(item.get(key), str) and item.get(key) for key in (
                "worker_id", "role", "group_id", "assignment_sha256",
            ))
            or item.get("group_id") not in selected
        ):
            raise ValueError("worker context materialization assignments are invalid")
        assignment_keys.append((item["worker_id"], item["role"], item["group_id"]))
    if len(set(assignment_keys)) != len(assignment_keys):
        raise ValueError("worker context materialization assignments are duplicated")
    page_count = sum(
        len(group.get("pages", [])) for group in groups
        if isinstance(group, Mapping) and isinstance(group.get("pages"), list)
    )
    if page_count != report.get("materialized_page_count"):
        raise ValueError("worker context materialization page count drifted")
    boundary = report.get("claim_boundary")
    if not isinstance(boundary, Mapping) or (
        boundary.get("semantic_gate") is not False
        or boundary.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("worker context materialization claim boundary is invalid")


def _validate_assignment(
    report: Mapping[str, Any], request: Mapping[str, Any],
) -> None:
    binding = request.get("assignment_binding")
    if not isinstance(binding, Mapping):
        raise ValueError("worker context assignment binding is invalid")
    expected = {
        "worker_id": request.get("worker_id"),
        "role": request.get("role"),
        "group_id": request.get("group_id"),
        "assignment_sha256": binding.get("assignment_sha256"),
    }
    matches = [
        item for item in report["assignments"]
        if isinstance(item, Mapping) and dict(item) == expected
    ]
    if len(matches) != 1:
        raise ValueError("worker context materialization assignment drifted")


def _validate_group(
    report: Mapping[str, Any], request: Mapping[str, Any], prefix: PurePosixPath,
) -> None:
    context = request.get("context")
    if not isinstance(context, Mapping):
        raise ValueError("worker context binding is invalid")
    group_id = request.get("group_id")
    matches = [
        item for item in report["groups"]
        if isinstance(item, Mapping) and item.get("group_id") == group_id
    ]
    if len(matches) != 1:
        raise ValueError("worker context materialization group binding drifted")
    group = matches[0]
    frontier = validate_context_against_frontier(
        request.get("context_frontier"), context,
    )
    if group.get("context_frontier") != frontier or frontier["status"] != FRONTIER_READY:
        raise ValueError("worker context frontier ledger binding drifted")
    catalog = context.get("catalog")
    if not isinstance(catalog, Mapping):
        raise ValueError("worker context catalog binding is invalid")
    if (
        group.get("catalog_sha256") != catalog.get("sha256")
        or frontier.get("catalog") != catalog
    ):
        raise ValueError("worker context materialization catalog drifted")
    if any(
        group.get(key) != frontier.get(key)
        for key in (
            "selection_receipt_sha256", "materialized_page_set_sha256",
            "selection_materialization_sha256",
        )
    ):
        raise ValueError("worker context materialization frontier output drifted")
    _validate_pages(group.get("pages"), context.get("pages"), prefix)


def _validate_pages(
    receipt_pages: Any, request_pages: Any, prefix: PurePosixPath,
) -> None:
    if not isinstance(receipt_pages, list) or not isinstance(request_pages, list):
        raise ValueError("worker context materialization pages are invalid")
    requested: dict[str, Mapping[str, Any]] = {}
    for page in request_pages:
        page_id = page.get("page_id") if isinstance(page, Mapping) else None
        if not isinstance(page_id, str) or page_id in requested:
            raise ValueError("worker context request page identities are invalid")
        requested[page_id] = page
    seen: set[str] = set()
    for page in receipt_pages:
        page_id = page.get("page_id") if isinstance(page, Mapping) else None
        local_path = page.get("path") if isinstance(page, Mapping) else None
        if not isinstance(page_id, str) or page_id in seen or not isinstance(local_path, str):
            raise ValueError("worker context receipt page identities are invalid")
        expected = requested.get(page_id)
        full_path = (prefix / checked_relative_path(local_path)).as_posix()
        if expected is None or (
            expected.get("path") != full_path
            or expected.get("sha256") != page.get("sha256")
            or expected.get("byte_count") != page.get("size_bytes")
            or expected.get("token_count") != page.get("size_bytes")
        ):
            raise ValueError("worker context materialization page binding drifted")
        seen.add(page_id)
    if seen != set(requested):
        raise ValueError("worker context materialization page set drifted")


def _output_prefix(reference_path: str) -> PurePosixPath:
    path = PurePosixPath(checked_relative_path(reference_path))
    if path.parent.name != "materializations" or path.parent.parent.name != "context":
        raise ValueError("worker context materialization path is invalid")
    return path.parent.parent.parent


__all__ = ["validate_request_context_materialization"]
