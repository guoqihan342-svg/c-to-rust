from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import (
    canonical_json_bytes, checked_relative_path, content_sha256,
)
from .build_facts import is_linklike
from .artifact_write_once import (
    write_once_bytes_artifact, write_once_json_artifact,
)
from .context_catalog import validate_context_catalog
from .context_selection_materialization import require_selection_materialization
from .context_frontier_binding import validate_context_against_frontier
from .context_frontier_state import static_context_page_set_sha256
from .orchestration_facts import read_artifact_reference


def materialize_scheduled_contexts(
    schedule: Mapping[str, Any], *, harness_root: Path, out_root: Path,
    out_root_rel: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ready = schedule.get("ready")
    if not isinstance(ready, list):
        raise ValueError("context frontier schedule.ready is invalid")
    contexts: dict[str, dict[str, Any]] = {}
    frontiers: dict[str, dict[str, Any]] = {}
    assignments: list[dict[str, Any]] = []
    for item in ready:
        assignment = item.get("assignment") if isinstance(item, Mapping) else None
        if not isinstance(assignment, Mapping):
            raise ValueError("context frontier assignment is invalid")
        group_id = assignment.get("group_id")
        context = assignment.get("context")
        if not isinstance(group_id, str) or not isinstance(context, Mapping):
            raise ValueError("context frontier assignment binding is invalid")
        previous = contexts.setdefault(group_id, dict(context))
        if previous != context:
            raise ValueError("context frontier group has conflicting context bindings")
        frontier = validate_context_against_frontier(
            item.get("context_frontier"), context,
        )
        previous_frontier = frontiers.setdefault(group_id, frontier)
        if previous_frontier != frontier:
            raise ValueError("context frontier group has conflicting ledger heads")
        assignments.append({
            "worker_id": assignment.get("worker_id"),
            "role": assignment.get("role"),
            "group_id": group_id,
            "assignment_sha256": content_sha256(assignment),
        })
    page_refs: list[dict[str, Any]] = []
    group_bindings: list[dict[str, Any]] = []
    for group_id, context in sorted(contexts.items()):
        catalog = _load_catalog(
            context, harness_root=harness_root, group_id=group_id,
        )
        refs = _materialize_group(
            catalog, context, out_root=out_root, out_root_rel=out_root_rel,
        )
        page_refs.extend(refs)
        retrieval = context.get("retrieval")
        group_bindings.append({
            "group_id": group_id,
            "catalog_sha256": context["catalog"]["sha256"],
            "selection_receipt_sha256": (
                retrieval.get("selection_receipt_sha256")
                if isinstance(retrieval, Mapping) else None
            ),
            "materialized_page_set_sha256": (
                retrieval.get("materialized_page_set_sha256")
                if isinstance(retrieval, Mapping)
                else static_context_page_set_sha256(context)
            ),
            "selection_materialization_sha256": (
                retrieval.get("selection_materialization_sha256")
                if isinstance(retrieval, Mapping) else None
            ),
            "context_frontier": frontiers[group_id],
            "pages": refs,
        })
    report = {
        "schema_version": 1,
        "artifact_kind": "context-frontier-materialization",
        "policy": "scheduled-frontier-only",
        "write_policy": "content-addressed-write-once-idempotent",
        "selected_group_ids": sorted(contexts),
        "selected_group_count": len(contexts),
        "assignments": sorted(
            assignments,
            key=lambda item: (str(item["group_id"]), str(item["worker_id"])),
        ),
        "groups": group_bindings,
        "materialized_page_count": len(page_refs),
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    digest = content_sha256(report)
    reference = write_once_json_artifact(
        out_root,
        f"context/materializations/frontier-{digest[:24]}.json",
        report,
    )
    return page_refs, reference


def _load_catalog(
    context: Mapping[str, Any], *, harness_root: Path, group_id: str,
) -> dict[str, Any]:
    reference = context.get("catalog")
    if not isinstance(reference, Mapping):
        raise ValueError("context frontier catalog reference is missing")
    data = read_artifact_reference(harness_root, reference)
    if reference.get("size_bytes") != len(data):
        raise ValueError("context frontier catalog size drifted")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("context frontier catalog is not JSON") from error
    if canonical_json_bytes(raw) != data:
        raise ValueError("context frontier catalog is not canonical JSON")
    catalog = validate_context_catalog(raw)
    if catalog["scc_id"] != group_id:
        raise ValueError("context frontier catalog changed its group binding")
    return catalog


def _materialize_group(
    catalog: Mapping[str, Any], context: Mapping[str, Any], *,
    out_root: Path, out_root_rel: str,
) -> list[dict[str, Any]]:
    group_id = str(catalog["scc_id"])
    if catalog.get("retrieval") != context.get("retrieval"):
        raise ValueError("context frontier retrieval receipt drifted")
    expected_pages = context.get("pages")
    if not isinstance(expected_pages, list) or len(expected_pages) != len(catalog["pages"]):
        raise ValueError("context frontier page count drifted")
    by_id = {
        page.get("page_id"): page for page in expected_pages
        if isinstance(page, Mapping) and isinstance(page.get("page_id"), str)
    }
    if len(by_id) != len(expected_pages):
        raise ValueError("context frontier page identities are invalid")
    prepared: list[tuple[dict[str, Any], bytes]] = []
    stable_pages: list[dict[str, Any]] = []
    for page in catalog["pages"]:
        page_id = str(page["page_id"])
        expected = by_id.get(page_id)
        reference = dict(page["reference"])
        encoded = canonical_json_bytes(page["payload"])
        if expected is None or not _page_matches(
            expected, reference, out_root_rel=out_root_rel,
        ):
            raise ValueError("context frontier page binding drifted")
        prepared.append((reference, encoded))
        stable_pages.append({"page_id": page_id, **reference})
    retrieval = catalog.get("retrieval")
    if isinstance(retrieval, Mapping):
        require_selection_materialization(retrieval, stable_pages)
    group_relative = _output_relative(
        str(context.get("path", "")), out_root_rel=out_root_rel,
    )
    if group_relative != f"context/groups/{group_id}.json":
        raise ValueError("context frontier group path drifted")
    group_target = out_root.joinpath(*PurePosixPath(group_relative).parts)
    group_payload = {
        "schema_version": 1,
        "scc_id": group_id,
        "catalog": dict(context["catalog"]),
        "retrieval": dict(retrieval) if isinstance(retrieval, Mapping) else None,
        "pages": stable_pages,
        "model_input_policy": catalog.get("model_input_policy"),
        "claim_boundary": catalog.get("claim_boundary"),
    }
    page_targets = [
        out_root.joinpath(*PurePosixPath(item[0]["path"]).parts)
        for item in prepared
    ]
    if any(
        _contains_link(out_root, path) for path in [*page_targets, group_target]
    ):
        raise ValueError("context frontier materialization path contains a link")
    present = [path.exists() for path in [*page_targets, group_target]]
    if any(present):
        if not all(present):
            raise ValueError("context frontier materialization is incomplete")
        for target, (_reference, encoded) in zip(page_targets, prepared):
            if not target.is_file() or target.read_bytes() != encoded:
                raise ValueError("context frontier materialized page drifted")
        _validate_existing_group(group_target, group_payload)
        return stable_pages
    for reference, encoded in prepared:
        actual = write_once_bytes_artifact(
            out_root, str(reference["path"]), encoded,
        )
        if actual != reference:
            raise ValueError("context frontier page materialization drifted")
    write_once_json_artifact(out_root, group_relative, group_payload)
    return stable_pages


def _page_matches(
    expected: Mapping[str, Any], reference: Mapping[str, Any], *,
    out_root_rel: str,
) -> bool:
    return (
        expected.get("path") == f"{out_root_rel}/{reference.get('path')}"
        and expected.get("sha256") == reference.get("sha256")
        and expected.get("byte_count") == reference.get("size_bytes")
        and expected.get("token_count") == reference.get("size_bytes")
    )


def _validate_existing_group(
    path: Path, expected: Mapping[str, Any],
) -> None:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise ValueError("context frontier group index is invalid") from error
    if data != canonical_json_bytes(expected):
        raise ValueError("context frontier group index drifted")


def _output_relative(path: str, *, out_root_rel: str) -> str:
    checked_relative_path(path)
    prefix = PurePosixPath(out_root_rel)
    candidate = PurePosixPath(path)
    try:
        relative = candidate.relative_to(prefix)
    except ValueError as error:
        raise ValueError("context frontier path escapes output root") from error
    return checked_relative_path(relative.as_posix())


def _contains_link(root: Path, target: Path) -> bool:
    base = root.resolve(strict=True)
    current = root
    try:
        relative = target.relative_to(root)
    except ValueError:
        return True
    for part in relative.parts:
        current /= part
        if current.exists() and is_linklike(current):
            return True
    try:
        target.resolve(strict=False).relative_to(base)
    except ValueError:
        return True
    return False


__all__ = ["materialize_scheduled_contexts"]
