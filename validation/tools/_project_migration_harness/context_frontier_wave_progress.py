from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .context_frontier_cas import read_bound_frontier_cas_json
from .context_frontier_reference import context_frontier_reference as reference
from .context_frontier_refresh_reopen import (
    reopen_context_frontier_overlay_dependencies,
)
from .context_frontier_state import (
    ContextFrontierProjection, FRONTIER_PENDING, FRONTIER_READY,
)
from .context_frontier_wave_event import pending_wave_artifact_sha256


def classify_context_frontier_wave_progress(
    ledger: Any, *, harness_root: Path, wave: Mapping[str, Any],
    wave_reference: Mapping[str, Any],
    selection_references: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    run_id = wave.get("run_id")
    unit_ids = wave.get("next_unit_ids")
    units = wave.get("units")
    if (
        not isinstance(run_id, str)
        or not isinstance(unit_ids, list)
        or not isinstance(units, list)
    ):
        raise ValueError("context frontier wave progress input is invalid")
    expected = set(unit_ids)
    if set(selection_references) != expected:
        raise ValueError("context frontier wave selection set drifted")
    unit_inputs = {
        str(item.get("unit_id")): item for item in units
        if isinstance(item, Mapping)
    }
    query_epochs = {
        str(item.get("unit_id")): item.get("query_epoch")
        for item in wave.get("expansion_queries", [])
        if isinstance(item, Mapping)
    }
    states = {
        item["unit_id"]: item for item in ledger.context_frontier_states(run_id)
        if item.get("unit_id") in expected
    }
    if set(states) != expected or set(unit_inputs) != expected:
        raise ValueError("context frontier wave projection set drifted")
    wave_ref = reference(wave_reference)
    fresh: dict[str, ContextFrontierProjection] = {}
    pending: list[str] = []
    ready: dict[str, dict[str, Any]] = {}
    for unit_id in unit_ids:
        state = states[unit_id]
        if state["status"] == FRONTIER_PENDING:
            _require_query_epoch(state, query_epochs.get(unit_id), pending=True)
            _require_pending_binding(
                ledger, state, unit_inputs[unit_id], wave_ref,
            )
            pending.append(unit_id)
        elif state["status"] == FRONTIER_READY and _matches_ready_wave(
            state, harness_root=harness_root, wave_reference=wave_ref,
            selection_reference=selection_references[unit_id],
            unit_input=unit_inputs[unit_id],
        ):
            _require_query_epoch(state, query_epochs.get(unit_id), pending=True)
            ready[unit_id] = state
        elif state["status"] == FRONTIER_READY:
            _require_query_epoch(state, query_epochs.get(unit_id), pending=False)
            fresh[unit_id] = ContextFrontierProjection(
                state["status"], state["state_version"],
                state["head"], state["head_sha256"],
            )
        else:
            raise ValueError("context frontier wave projection status is invalid")
    if fresh and (pending or ready):
        raise ValueError("context frontier wave invalidation is partially applied")
    if fresh and set(fresh) != expected:
        raise ValueError("context frontier fresh wave set is incomplete")
    return {"fresh": fresh, "pending": pending, "ready": ready}


def _require_query_epoch(
    state: Mapping[str, Any], query_epoch: Any, *, pending: bool,
) -> None:
    if query_epoch is None:
        return
    current = state["head"].get("query_epoch")
    expected = current if pending else current + 1
    if isinstance(query_epoch, bool) or query_epoch != expected:
        raise ValueError("context frontier expansion query epoch drifted")


def _require_pending_binding(
    ledger: Any, state: Mapping[str, Any], unit: Mapping[str, Any],
    wave_reference: Mapping[str, Any],
) -> None:
    head = state["head"]
    binding = head.get("input_binding")
    expected = {
        "dag_sha256": unit.get("dag_sha256"),
        "group_sha256": unit.get("group_sha256"),
        "failure_fact_set_sha256": unit.get("failure_fact_set_sha256"),
        "selection_seed_sha256": unit.get("selection_seed_sha256"),
    }
    if (
        pending_wave_artifact_sha256(ledger, state) != wave_reference["sha256"]
        or not isinstance(binding, Mapping)
        or any(binding.get(key) != value for key, value in expected.items())
        or head.get("selection_input_sha256") != content_sha256(binding)
    ):
        raise ValueError("context frontier pending wave binding drifted")


def _matches_ready_wave(
    state: Mapping[str, Any], *, harness_root: Path,
    wave_reference: Mapping[str, Any],
    selection_reference: Mapping[str, Any], unit_input: Mapping[str, Any],
) -> bool:
    head = state["head"]
    overlay_ref = head.get("context_overlay")
    if overlay_ref is None:
        return False
    overlay = read_bound_frontier_cas_json(
        harness_root, reference(overlay_ref), "context-frontier-overlay",
    )
    refresh = reopen_context_frontier_overlay_dependencies(
        overlay, harness_root=harness_root,
    )
    wave = refresh.get("wave")
    return bool(
        refresh.get("schema_version") == 2
        and isinstance(wave, Mapping)
        and wave.get("input") == reference(wave_reference)
        and wave.get("selection") == reference(selection_reference)
        and head.get("input_binding", {}).get("selection_seed_sha256")
        == unit_input.get("selection_seed_sha256")
    )


__all__ = ["classify_context_frontier_wave_progress"]
