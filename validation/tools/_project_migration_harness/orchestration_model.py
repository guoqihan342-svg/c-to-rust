from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .artifacts import content_sha256
from .context_index_store import materialize_context_indexes


def portfolio_dag(
    graph: Mapping[str, Any],
    contexts: Mapping[str, Mapping[str, Any]],
    *,
    run_id: str,
    project_key: str,
) -> dict[str, Any]:
    raw_sccs = graph.get("sccs")
    raw_waves = graph.get("waves")
    if not isinstance(raw_sccs, list) or not isinstance(raw_waves, list):
        raise ValueError("migration graph SCC/wave contract is invalid")
    groups = []
    for raw in raw_sccs:
        if not isinstance(raw, Mapping):
            raise ValueError("migration graph SCC entry is invalid")
        group_id = str(raw.get("scc_id", ""))
        context = contexts.get(group_id)
        classification = raw.get("classification")
        dependencies = list(raw.get("dependency_scc_ids", []))
        group = {
            "group_id": group_id,
            "node_ids": list(raw.get("node_ids", [])),
            "classification": classification,
            "structural_reasons": list(raw.get("structural_reasons", [])),
            "dependencies": dependencies,
            "structurally_eligible": classification in {"independent", "context_group"},
            "context_pack": dict(context) if context else None,
        }
        if isinstance(raw.get("target_scope"), Mapping):
            group["source_unit_ids"] = list(raw.get("source_unit_ids", []))
            group["target_scope"] = dict(raw["target_scope"])
        group["content_sha256"] = content_sha256(group)
        groups.append(group)
    waves = [
        {"wave_index": int(item["wave_index"]), "group_ids": list(item["scc_ids"])}
        for item in raw_waves
        if isinstance(item, Mapping)
    ]
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "project_key": project_key,
        "groups": groups,
        "waves": waves,
        "claim_boundary": {"semantic_gate": False, "translation_coverage_numerator": 0},
    }
    payload["dag_sha256"] = content_sha256(payload)
    return payload


def ledger_units(portfolio_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    wave_by_group = {
        group_id: int(wave["wave_index"])
        for wave in portfolio_input["waves"]
        for group_id in wave["group_ids"]
    }
    return [
        {
            "unit_id": group["group_id"],
            "group_id": group["group_id"],
            "wave_index": wave_by_group[group["group_id"]],
            "status": "pending" if group["structurally_eligible"] else "blocked",
            "resumable_status": "ready" if group["structurally_eligible"] else "terminal",
            "content_sha256": group["content_sha256"],
        }
        for group in portfolio_input["groups"]
    ]


__all__ = ["ledger_units", "materialize_context_indexes", "portfolio_dag"]
