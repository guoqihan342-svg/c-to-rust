from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .context_frontier_cas import (
    read_bound_frontier_cas_json, write_frontier_cas_json,
)
from .context_frontier_overlay import build_context_frontier_overlay
from .context_frontier_refresh_artifacts import (
    prepare_single_scc_refresh_artifacts, reopen_context_catalog,
)
from .context_frontier_refresh_permit import _issue_host_context_refresh_permit
from .context_frontier_refresh_reopen import (
    read_canonical_reference, unit_assignments,
)
from .context_frontier_reference import context_frontier_reference as reference
from .context_frontier_state import FRONTIER_PENDING, validate_context_frontier_head
from .context_frontier_wave_event import pending_wave_artifact_sha256


_REFRESH_INPUT_KIND = "context-frontier-refresh-input"
_OVERLAY_KIND = "context-frontier-overlay"


def refresh_single_scc_context(
    portfolio: Mapping[str, Any], *, portfolio_reference: Mapping[str, Any],
    context_bundle_reference: Mapping[str, Any], ledger: Any,
    harness_root: Path, out_root: Path, out_root_rel: str, unit_id: str,
    wave_input_reference: Mapping[str, Any] | None = None,
    wave_selection_reference: Mapping[str, Any] | None = None,
    wave_selection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _text(portfolio.get("run_id"), "run_id")
    unit_id = _text(unit_id, "unit_id")
    binding = ledger.require_portfolio_binding(portfolio)
    if read_canonical_reference(harness_root, portfolio_reference) != dict(portfolio):
        raise ValueError("context refresh portfolio artifact drifted")
    bundle = read_canonical_reference(harness_root, context_bundle_reference)
    assignments = unit_assignments(portfolio, unit_id)
    assignment_context = _shared_assignment_context(assignments)
    current = _pending_frontier(ledger, run_id, unit_id)
    current["wave_input_artifact_sha256"] = pending_wave_artifact_sha256(
        ledger, current,
    )
    wave_binding = _wave_refresh_binding(
        harness_root=harness_root,
        run_id=run_id,
        unit_id=unit_id,
        current=current,
        wave_input_reference=wave_input_reference,
        wave_selection_reference=wave_selection_reference,
        wave_selection=wave_selection,
    )
    reopen_context_catalog(
        harness_root, current["head"]["catalog"], unit_id=unit_id,
        require_materialized_pages=False,
    )
    limits = current["head"]["input_binding"]["limits"]
    artifacts = prepare_single_scc_refresh_artifacts(
        bundle, run_id=run_id, unit_id=unit_id,
        assignment_context=assignment_context, out_root=out_root,
        out_root_rel=out_root_rel,
        context_page_limit=int(limits["context_page_limit"]),
        wave_selection=wave_selection,
        wave_selection_reference=wave_selection_reference,
    )
    refresh_input = {
        "schema_version": 2 if wave_binding is not None else 1,
        "artifact_kind": _REFRESH_INPUT_KIND,
        "run_id": run_id,
        "unit_id": unit_id,
        "portfolio": reference(portfolio_reference),
        "context_bundle": reference(context_bundle_reference),
        "base_catalog": dict(current["head"]["catalog"]),
        "artifacts": {
            key: artifacts[key]
            for key in ("selection_receipt", "catalog", "group", "pages")
        },
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    if wave_binding is not None:
        refresh_input["wave"] = {
            **wave_binding,
            "materialization": artifacts["wave_selection_materialization"],
        }
    refresh_ref = _prefix(
        write_frontier_cas_json(out_root, _REFRESH_INPUT_KIND, refresh_input),
        out_root_rel,
    )
    base_frontier = {
        **current["head"],
        "state_version": current["state_version"],
        "head_sha256": current["head_sha256"],
    }
    overlay = build_context_frontier_overlay(
        assignments, base_frontier, plan_sha256=str(binding["plan_sha256"]),
        refresh_bundle=refresh_ref,
        effective_context=artifacts["effective_context"],
    )
    overlay_ref = _prefix(
        write_frontier_cas_json(out_root, _OVERLAY_KIND, overlay),
        out_root_rel,
    )
    target_head = validate_context_frontier_head({
        **current["head"],
        "schema_version": 2,
        "status": "ready",
        "catalog": artifacts["catalog"],
        "context_overlay": overlay_ref,
        "selection_receipt_sha256": artifacts["selection_receipt_sha256"],
        "materialized_page_set_sha256": artifacts["materialized_page_set_sha256"],
        "selection_materialization_sha256": artifacts[
            "selection_materialization_sha256"
        ],
    })
    permit = _issue_host_context_refresh_permit({
        "schema_version": 1,
        "run_id": run_id,
        "unit_id": unit_id,
        "plan_sha256": binding["plan_sha256"],
        "portfolio": reference(portfolio_reference),
        "refresh_input": refresh_ref,
        "overlay": overlay_ref,
        "expected_status": current["status"],
        "expected_version": current["state_version"],
        "expected_head_sha256": current["head_sha256"],
        "target_head": target_head,
    })
    committed = ledger._commit_context_refresh(
        permit, harness_root=harness_root,
    )
    return {
        "schema_version": 1,
        "status": "ready",
        "run_id": run_id,
        "unit_id": unit_id,
        "refresh_input": refresh_ref,
        "context_overlay": overlay_ref,
        "ledger": committed,
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }


def _pending_frontier(ledger: Any, run_id: str, unit_id: str) -> dict[str, Any]:
    matches = [
        item for item in ledger.context_frontier_states(run_id)
        if item.get("unit_id") == unit_id
    ]
    if len(matches) != 1 or matches[0].get("status") != FRONTIER_PENDING:
        raise ValueError("context refresh requires one pending SCC frontier")
    return matches[0]


def _wave_refresh_binding(
    *, harness_root: Path, run_id: str, unit_id: str,
    current: Mapping[str, Any],
    wave_input_reference: Mapping[str, Any] | None,
    wave_selection_reference: Mapping[str, Any] | None,
    wave_selection: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    values = (wave_input_reference, wave_selection_reference, wave_selection)
    if all(value is None for value in values):
        if current.get("wave_input_artifact_sha256") is not None:
            raise ValueError("context refresh wave binding is required")
        return None
    if any(value is None for value in values):
        raise ValueError("context refresh wave binding is incomplete")
    wave_ref = reference(wave_input_reference)
    selection_ref = reference(wave_selection_reference)
    wave = read_bound_frontier_cas_json(
        harness_root, wave_ref, "context-frontier-wave-input",
    )
    reopened_selection = read_bound_frontier_cas_json(
        harness_root, selection_ref,
        "context-frontier-wave-selection-directives",
    )
    if reopened_selection != dict(wave_selection):
        raise ValueError("context refresh wave selection artifact drifted")
    units = wave.get("units")
    matches = [
        item for item in units if isinstance(item, Mapping)
        and item.get("unit_id") == unit_id
    ] if isinstance(units, list) else []
    head = current["head"]
    selection_inputs = reopened_selection.get("input_bindings")
    if (
        current.get("wave_input_artifact_sha256") != wave_ref["sha256"]
        or
        wave.get("run_id") != run_id
        or len(matches) != 1
        or reopened_selection.get("run_id") != run_id
        or reopened_selection.get("unit_id") != unit_id
        or not isinstance(selection_inputs, Mapping)
        or selection_inputs.get("wave_selection_seed_sha256")
        != matches[0].get("selection_seed_sha256")
        or head["input_binding"]["selection_seed_sha256"]
        != matches[0].get("selection_seed_sha256")
    ):
        raise ValueError("context refresh wave selection binding drifted")
    return {"input": wave_ref, "selection": selection_ref}


def _shared_assignment_context(assignments: list[dict[str, Any]]) -> dict[str, Any]:
    contexts = [item.get("context") for item in assignments]
    if not isinstance(contexts[0], Mapping) or any(value != contexts[0] for value in contexts):
        raise ValueError("context refresh assignments have inconsistent context")
    return dict(contexts[0])


def _prefix(reference: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(reference), "path": f"{root}/{reference['path']}"}


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"context refresh {label} is invalid")
    return value


__all__ = ["refresh_single_scc_context"]
