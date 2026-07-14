from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .context_frontier_cas import write_frontier_cas_json
from .context_frontier_bundle_binding import require_context_bundle_binding
from .context_frontier_refresh import refresh_single_scc_context
from .context_frontier_wave import (
    derive_context_frontier_wave_input,
)
from .context_frontier_wave_inputs import (
    expansion_query_map, failure_evidence_map,
    validate_context_frontier_wave_inputs,
)
from .context_frontier_wave_permit import (
    _issue_host_context_frontier_wave_permit,
)
from .context_frontier_wave_progress import classify_context_frontier_wave_progress
from .context_frontier_wave_selection import (
    derive_context_frontier_wave_selection,
)
from .context_frontier_wave_materialization import (
    materialize_context_frontier_wave_selection,
)
from .context_index_store import prepare_context_indexes


_WAVE_KIND = "context-frontier-wave-input"
_SELECTION_KIND = "context-frontier-wave-selection-directives"
_CLAIM_BOUNDARY = {"semantic_gate": False, "translation_coverage_numerator": 0}


def prepare_next_context_frontier_wave(
    portfolio: Mapping[str, Any], *,
    portfolio_reference: Mapping[str, Any],
    latest_dag: Mapping[str, Any], latest_dag_reference: Mapping[str, Any],
    context_bundle: Mapping[str, Any], context_bundle_reference: Mapping[str, Any],
    completed_wave_index: int,
    failure_evidence: Sequence[Mapping[str, Any]],
    expansion_queries: Sequence[Mapping[str, Any]],
    ledger: Any, harness_root: Path, out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    binding, runtime_dag = validate_context_frontier_wave_inputs(
        portfolio,
        portfolio_reference=portfolio_reference,
        latest_dag=latest_dag,
        latest_dag_reference=latest_dag_reference,
        context_bundle=context_bundle,
        context_bundle_reference=context_bundle_reference,
        completed_wave_index=completed_wave_index,
        ledger=ledger,
        harness_root=harness_root,
    )
    wave = derive_context_frontier_wave_input(
        runtime_dag,
        completed_wave_index=completed_wave_index,
        failure_evidence=failure_evidence,
        expansion_queries=expansion_queries,
    )
    if (
        wave["run_id"] != portfolio.get("run_id")
        or wave["project_key"] != portfolio.get("project_key")
        or wave["dag_sha256"] != binding["dag_sha256"]
    ):
        raise ValueError("context frontier wave portfolio/DAG binding drifted")
    wave_local = write_frontier_cas_json(out_root, _WAVE_KIND, wave)
    wave_reference = _prefix(wave_local, out_root_rel)
    failures = failure_evidence_map(failure_evidence)
    queries = expansion_query_map(expansion_queries)
    contexts, _payloads, prepared = prepare_context_indexes(
        context_bundle, out_root_rel=out_root_rel,
    )
    require_context_bundle_binding(
        contexts, portfolio, wave["next_unit_ids"],
    )
    selection_records = []
    for unit in wave["units"]:
        unit_id = unit["unit_id"]
        query = queries.get(unit_id)
        unit_failures = [failures[digest] for digest in unit["failure_evidence_sha256s"]]
        selection = derive_context_frontier_wave_selection(
            unit,
            expansion_query=query,
            failed_verifier_evidence=unit_failures,
            context_bundle=context_bundle,
        )
        selection_ref = _prefix(
            write_frontier_cas_json(out_root, _SELECTION_KIND, selection),
            out_root_rel,
        )
        selection_records.append({
            "unit_id": unit_id,
            "selection": selection_ref,
            "payload": selection,
        })
        _preflight_materialization(
            prepared, unit_id=unit_id, selection=selection,
            selection_reference=selection_ref, context_bundle=context_bundle,
        )
    selections = {item["unit_id"]: item["selection"] for item in selection_records}
    progress = classify_context_frontier_wave_progress(
        ledger, harness_root=harness_root, wave=wave,
        wave_reference=wave_reference, selection_references=selections,
    )
    permits = [
        _issue_host_context_frontier_wave_permit(
            wave, wave_reference, progress["fresh"][unit_id],
        )
        for unit_id in wave["next_unit_ids"]
        if unit_id in progress["fresh"]
    ]
    committed = ledger._commit_context_wave_invalidations(
        permits, harness_root=harness_root,
    ) if permits else []
    pending = set(wave["next_unit_ids"] if permits else progress["pending"])
    refreshes = []
    for item in selection_records:
        if item["unit_id"] in pending:
            refreshes.append(refresh_single_scc_context(
                portfolio,
                portfolio_reference=portfolio_reference,
                context_bundle_reference=context_bundle_reference,
                ledger=ledger,
                harness_root=harness_root,
                out_root=out_root,
                out_root_rel=out_root_rel,
                unit_id=item["unit_id"],
                wave_input_reference=wave_reference,
                wave_selection_reference=item["selection"],
                wave_selection=item["payload"],
            ))
        else:
            refreshes.append({
                "status": "ready", "unit_id": item["unit_id"],
                "resumed": True,
                "context_overlay": progress["ready"][item["unit_id"]]["head"][
                    "context_overlay"
                ],
            })
    return {
        "schema_version": 1,
        "status": "ready",
        "run_id": wave["run_id"],
        "completed_wave_index": wave["completed_wave_index"],
        "next_wave_index": wave["next_wave_index"],
        "wave_input": wave_reference,
        "selection_directives": [
            {
                "unit_id": item["unit_id"],
                "selection": item["selection"],
                "selection_ready": True,
                "requires_host_recompute": False,
            }
            for item in selection_records
        ],
        "ledger": {"invalidations": committed, "refreshes": refreshes},
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    }


def _preflight_materialization(
    prepared: Mapping[str, Any], *, unit_id: str,
    selection: Mapping[str, Any], selection_reference: Mapping[str, Any],
    context_bundle: Mapping[str, Any],
) -> None:
    groups, retrievals = prepared.get("by_scc"), prepared.get("retrieval")
    if not isinstance(groups, Mapping) or not isinstance(retrievals, Mapping):
        raise ValueError("context frontier prepared selection store is invalid")
    entries, retrieval = groups.get(unit_id), retrievals.get(unit_id)
    if not isinstance(entries, list) or not isinstance(retrieval, Mapping):
        raise ValueError("context frontier wave selection group is missing")
    _entries, _retrieval, materialization = (
        materialize_context_frontier_wave_selection(
            selection,
            directives_reference=selection_reference,
            context_bundle=context_bundle,
            entries=entries,
            retrieval=retrieval,
        )
    )
    if materialization["selection_ready"] is not True:
        raise ValueError("context frontier wave selection remains blocked")


def _prefix(value: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(value), "path": f"{root}/{value['path']}"}


__all__ = ["prepare_next_context_frontier_wave"]
