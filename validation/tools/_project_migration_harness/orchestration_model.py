from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .artifacts import content_sha256, write_json_artifact


def materialize_context_indexes(
    context_bundle: Mapping[str, Any],
    *,
    out_root: Path,
    out_root_rel: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    facts = context_bundle.get("shared_facts")
    pages = context_bundle.get("pages")
    if not isinstance(facts, Mapping) or not isinstance(pages, list):
        raise ValueError("context bundle facts/pages contract is invalid")
    shared_ref = write_json_artifact(out_root, "context/shared-facts.json", {
        "schema_version": 1,
        "facts": facts,
        "model_input_policy": context_bundle.get("model_input_policy"),
    })
    by_scc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    page_refs: list[dict[str, Any]] = []
    for page in pages:
        if not isinstance(page, Mapping) or not isinstance(page.get("scc_id"), str):
            raise ValueError("context page SCC binding is invalid")
        for digest in page.get("fact_refs", []):
            if digest not in facts:
                raise ValueError("context page references an unknown shared fact")
        expected = page.get("materialized_sha256")
        materialized = {
            **{
                key: page[key]
                for key in (
                    "wave_index", "scc_id", "classification", "dependency_count",
                    "dependency_set_sha256", "part_index",
                )
            },
            "facts": [{"sha256": digest, **facts[digest]} for digest in page["fact_refs"]],
        }
        materialized_sha = hashlib.sha256(json.dumps(
            materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        if expected != materialized_sha:
            raise ValueError("context page materialized SHA drift")
        relative = f"context/pages/{page['page_id']}.json"
        page_ref = write_json_artifact(out_root, relative, materialized)
        bound = {**page_ref, **dict(page)}
        by_scc[str(page["scc_id"])].append(bound)
        page_refs.append(bound)

    contexts: dict[str, dict[str, Any]] = {}
    for scc_id, entries in sorted(by_scc.items()):
        entries.sort(key=lambda item: int(item["part_index"]))
        index_payload = {
            "schema_version": 1,
            "scc_id": scc_id,
            "shared_facts": shared_ref,
            "pages": entries,
            "model_input_policy": context_bundle.get("model_input_policy"),
            "claim_boundary": context_bundle.get("claim_boundary"),
        }
        index_ref = write_json_artifact(
            out_root,
            f"context/groups/{scc_id}.json",
            index_payload,
        )
        contexts[scc_id] = {
            "path": f"{out_root_rel}/{index_ref['path']}",
            "sha256": index_ref["sha256"],
            "byte_count": sum(int(item["size_bytes"]) for item in entries),
            "token_count": sum(int(item["size_bytes"]) for item in entries),
            "page_count": len(entries),
            "pages": [
                {
                    "path": f"{out_root_rel}/{item['path']}",
                    "sha256": item["sha256"],
                    "size_bytes": item["size_bytes"],
                    "estimated_tokens": item["size_bytes"],
                }
                for item in entries
            ],
        }
    return contexts, page_refs


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
