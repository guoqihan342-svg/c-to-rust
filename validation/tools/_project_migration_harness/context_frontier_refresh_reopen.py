from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path, content_sha256
from .context_frontier_binding import validate_context_against_frontier
from .context_frontier_cas import read_bound_frontier_cas_json
from .context_frontier_overlay import (
    resolve_effective_context, validate_context_frontier_overlay,
)
from .context_frontier_refresh_artifacts import reopen_context_catalog
from .context_frontier_refresh_permit import _host_context_refresh_binding
from .context_frontier_state import (
    ContextFrontierProjection, context_frontier_schedule_binding,
    validate_context_frontier_head,
)
from .orchestration_facts import read_artifact_reference


_REFRESH_INPUT_KIND = "context-frontier-refresh-input"
_OVERLAY_KIND = "context-frontier-overlay"


def reopen_host_context_refresh_permit(
    permit: Any, *, harness_root: Path,
) -> dict[str, Any]:
    binding = _host_context_refresh_binding(permit)
    portfolio = read_canonical_reference(harness_root, binding["portfolio"])
    if (
        portfolio.get("run_id") != binding.get("run_id")
        or portfolio.get("plan_sha256") != binding.get("plan_sha256")
    ):
        raise ValueError("context refresh permit portfolio binding drifted")
    refresh_input = read_bound_frontier_cas_json(
        harness_root, binding["refresh_input"], _REFRESH_INPUT_KIND,
    )
    overlay = validate_context_frontier_overlay(read_bound_frontier_cas_json(
        harness_root, binding["overlay"], _OVERLAY_KIND,
    ))
    _validate_refresh_input(refresh_input, binding, overlay)
    assignments = unit_assignments(portfolio, str(binding["unit_id"]))
    target = validate_context_frontier_head(binding["target_head"])
    if (
        target.get("run_id") != binding.get("run_id")
        or target.get("unit_id") != binding.get("unit_id")
        or target.get("status") != "ready"
        or target.get("context_overlay") != binding.get("overlay")
        or overlay.get("base_frontier") != {
            "state_version": binding.get("expected_version"),
            "head_sha256": binding.get("expected_head_sha256"),
            "catalog": refresh_input.get("base_catalog"),
        }
    ):
        raise ValueError("context refresh target or base frontier drifted")
    projection = ContextFrontierProjection(
        target["status"], int(binding["expected_version"]) + 1,
        target, content_sha256(target),
    )
    frontier = context_frontier_schedule_binding(projection)
    effective = overlay["effective_context"]
    validate_context_against_frontier(frontier, effective)
    for assignment in assignments:
        if resolve_effective_context(assignment, frontier, overlay) != effective:
            raise ValueError("context refresh overlay resolved inconsistent context")
    catalog = reopen_context_catalog(
        harness_root, effective["catalog"], unit_id=str(binding["unit_id"]),
    )
    _reopen_refresh_artifacts(
        harness_root, refresh_input, overlay, effective, catalog,
    )
    read_canonical_reference(harness_root, refresh_input["context_bundle"])
    reopen_context_catalog(
        harness_root, refresh_input["base_catalog"],
        unit_id=str(binding["unit_id"]),
        require_materialized_pages=False,
    )
    return {**binding, "portfolio_payload": portfolio, "overlay_payload": overlay}


def unit_assignments(
    portfolio: Mapping[str, Any], unit_id: str,
) -> list[dict[str, Any]]:
    values = portfolio.get("assignments")
    if not isinstance(values, list):
        raise ValueError("context refresh portfolio assignments are invalid")
    matches = [dict(item) for item in values if isinstance(item, Mapping)
               and item.get("unit_id") == unit_id]
    if not matches:
        raise ValueError("context refresh SCC has no assignments")
    return sorted(
        matches, key=lambda item: (str(item.get("role")), str(item.get("worker_id"))),
    )


def read_canonical_reference(
    root: Path, value: Mapping[str, Any],
) -> dict[str, Any]:
    data = _read_reference_bytes(root, reference(value))
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("context refresh artifact is not UTF-8 JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        raise ValueError("context refresh artifact is not canonical JSON")
    return payload


def reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {"path", "sha256", "size_bytes"}:
        raise ValueError("context refresh reference is invalid")
    path = checked_relative_path(str(value.get("path", "")))
    digest, size = value.get("sha256"), value.get("size_bytes")
    if (not isinstance(digest, str) or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or isinstance(size, bool) or not isinstance(size, int) or size < 0):
        raise ValueError("context refresh reference binding is invalid")
    return {"path": path, "sha256": digest, "size_bytes": size}


def _validate_refresh_input(
    value: Mapping[str, Any], binding: Mapping[str, Any], overlay: Mapping[str, Any],
) -> None:
    if set(value) != {
        "schema_version", "artifact_kind", "run_id", "unit_id", "portfolio",
        "context_bundle", "base_catalog", "artifacts", "claim_boundary",
    } or value.get("schema_version") != 1:
        raise ValueError("context refresh input contract is invalid")
    if (
        value.get("run_id") != binding.get("run_id")
        or value.get("unit_id") != binding.get("unit_id")
        or value.get("portfolio") != binding.get("portfolio")
        or overlay.get("refresh_bundle") != binding.get("refresh_input")
        or overlay.get("plan_sha256") != binding.get("plan_sha256")
        or value.get("claim_boundary") != {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        }
    ):
        raise ValueError("context refresh input identity drifted")


def _reopen_refresh_artifacts(
    root: Path, refresh: Mapping[str, Any], overlay: Mapping[str, Any],
    context: Mapping[str, Any], catalog: Mapping[str, Any],
) -> None:
    artifacts = refresh.get("artifacts")
    if not isinstance(artifacts, Mapping) or set(artifacts) != {
        "selection_receipt", "catalog", "group", "pages",
    }:
        raise ValueError("context refresh artifact set is invalid")
    if artifacts["catalog"] != context.get("catalog"):
        raise ValueError("context refresh catalog reference drifted")
    pages = artifacts["pages"]
    actual = [
        (item.get("path"), item.get("sha256"), item.get("size_bytes"))
        for item in pages if isinstance(item, Mapping)
    ] if isinstance(pages, list) else []
    expected = [
        (item.get("path"), item.get("sha256"), item.get("byte_count"))
        for item in context.get("pages", []) if isinstance(item, Mapping)
    ]
    if actual != expected:
        raise ValueError("context refresh page artifact set drifted")
    receipt = reference(artifacts["selection_receipt"])
    _read_reference_bytes(root, receipt)
    if receipt["sha256"] != overlay["selection_receipt_sha256"]:
        raise ValueError("context refresh receipt artifact drifted")
    expected_group = {
        "schema_version": 1, "scc_id": overlay["unit_id"],
        "catalog": context["catalog"], "retrieval": context["retrieval"],
        "pages": [
            {"page_id": page["page_id"], **page["reference"]}
            for page in catalog["pages"]
        ],
        "model_input_policy": catalog["model_input_policy"],
        "claim_boundary": catalog["claim_boundary"],
    }
    if read_canonical_reference(root, artifacts["group"]) != expected_group:
        raise ValueError("context refresh group artifact drifted")


def _read_reference_bytes(root: Path, ref: Mapping[str, Any]) -> bytes:
    data = read_artifact_reference(root, ref)
    if len(data) != ref.get("size_bytes"):
        raise ValueError("context refresh artifact size drifted")
    return data


__all__: list[str] = []
