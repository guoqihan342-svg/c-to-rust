from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .artifacts import (
    canonical_json_bytes, content_sha256,
)
from .artifact_write_once import (
    write_once_bytes_artifact, write_once_json_artifact,
)
from .context_catalog import persist_context_catalogs, prepare_context_catalog
from .context_retrieval import validate_retrieval_bundle
from .context_selection_materialization import (
    bind_selection_materialization as _bind_selection_materialization,
    prepared_page_facts as _prepared_page_facts,
    require_selection_materialization as _require_selection_materialization,
)


def prepare_context_indexes(
    context_bundle: Mapping[str, Any], *, out_root_rel: str
) -> tuple[
    dict[str, dict[str, Any]], dict[str, bytes], dict[str, Any]
]:
    facts = context_bundle.get("shared_facts")
    pages = context_bundle.get("pages")
    if not isinstance(facts, Mapping) or not isinstance(pages, list):
        raise ValueError("context bundle facts/pages contract is invalid")
    by_scc: dict[str, list[dict[str, Any]]] = defaultdict(list)
    page_payloads: dict[str, bytes] = {}
    page_ids: set[str] = set()
    for page in pages:
        prepared = _prepare_page(page, facts, out_root_rel)
        page_id = prepared["page_id"]
        if page_id in page_ids:
            raise ValueError("context page IDs must be unique")
        page_ids.add(page_id)
        path = prepared["reference"]["path"]
        page_payloads[path] = prepared["payload"]
        by_scc[prepared["scc_id"]].append(prepared)
    retrieval = validate_retrieval_bundle(context_bundle, facts, pages)
    retrieval = {
        scc_id: _bind_selection_materialization(binding, by_scc[scc_id])
        for scc_id, binding in retrieval.items()
    }
    catalogs = {
        scc_id: prepare_context_catalog(
            scc_id, entries, retrieval.get(scc_id),
            out_root_rel=out_root_rel,
            model_input_policy=context_bundle.get("model_input_policy"),
            claim_boundary=context_bundle.get("claim_boundary"),
        )
        for scc_id, entries in sorted(by_scc.items())
    }
    contexts = {
        scc_id: _context_binding(
            scc_id, entries, out_root_rel, retrieval.get(scc_id),
            catalogs[scc_id]["reference"],
        )
        for scc_id, entries in sorted(by_scc.items())
    }
    prepared_store = {
        "facts": facts,
        "by_scc": dict(by_scc),
        "model_input_policy": context_bundle.get("model_input_policy"),
        "claim_boundary": context_bundle.get("claim_boundary"),
        "logical_page_count": len(pages),
        "logical_group_count": len(by_scc),
        "retrieval": retrieval,
        "catalogs": catalogs,
    }
    return contexts, page_payloads, prepared_store


def materialize_prepared_context_catalogs(
    prepared: Mapping[str, Any], *, out_root: Path,
) -> list[dict[str, Any]]:
    catalogs = prepared.get("catalogs")
    if not isinstance(catalogs, Mapping):
        raise ValueError("prepared context catalogs are invalid")
    return persist_context_catalogs(catalogs, out_root=out_root)


def materialize_selected_context_indexes(
    prepared: Mapping[str, Any], *, out_root: Path,
    selected_scc_ids: Sequence[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_scc = prepared.get("by_scc")
    facts = prepared.get("facts")
    if not isinstance(by_scc, Mapping) or not isinstance(facts, Mapping):
        raise ValueError("prepared context store is invalid")
    selected = sorted(set(selected_scc_ids))
    if any(scc_id not in by_scc for scc_id in selected):
        raise ValueError("selected context group is unknown")
    selected_fact_ids = {
        digest
        for scc_id in selected
        for entry in by_scc[scc_id]
        for digest in entry["fact_refs"]
    }
    retrieval = prepared.get("retrieval", {})
    if not isinstance(retrieval, Mapping):
        raise ValueError("prepared context retrieval index is invalid")
    selected_retrieval = {
        scc_id: retrieval[scc_id] for scc_id in selected if scc_id in retrieval
    }
    for scc_id, binding in selected_retrieval.items():
        _require_selection_materialization(
            binding, _prepared_page_facts(by_scc[scc_id])
        )
    retrieval_fact_ids = {
        digest for binding in selected_retrieval.values()
        for digest in binding["fact_refs"]
    }
    shared_payload = {
        "schema_version": 1,
        "facts": {digest: facts[digest] for digest in sorted(selected_fact_ids)},
        "model_input_policy": prepared.get("model_input_policy"),
    }
    shared_ref = _write_named_json(out_root, "shared-facts", shared_payload)
    retrieval_facts_payload = {
            "schema_version": 1,
            "facts": {digest: facts[digest] for digest in sorted(retrieval_fact_ids)},
            "model_input": False,
    }
    retrieval_facts_ref = _write_named_json(
        out_root, "retrieval-facts", retrieval_facts_payload,
    )
    retrieval_index_payload = {
            "schema_version": 1,
            "bindings": [
                {key: value for key, value in selected_retrieval[scc_id].items()
                 if key != "fact_refs"}
                for scc_id in sorted(selected_retrieval)
            ],
            "fact_store": retrieval_facts_ref,
            "policy": "host_bounded_on_demand_only",
    }
    retrieval_index_ref = _write_named_json(
        out_root, "retrieval-index", retrieval_index_payload,
    )
    page_refs: list[dict[str, Any]] = []
    for scc_id in selected:
        entries = by_scc[scc_id]
        materialized = []
        for entry in entries:
            reference = write_once_bytes_artifact(
                out_root, entry["relative_path"], entry["payload"]
            )
            if reference != entry["local_reference"]:
                raise ValueError("context page materialization drifted")
            bound = {**entry["page_metadata"], **reference}
            page_refs.append(bound)
            materialized.append(bound)
        if scc_id in selected_retrieval:
            _require_selection_materialization(
                selected_retrieval[scc_id], materialized
            )
        write_once_json_artifact(out_root, f"context/groups/{scc_id}.json", {
            "schema_version": 1,
            "scc_id": scc_id,
            "shared_facts": shared_ref,
            "retrieval": {
                **{key: value for key, value in selected_retrieval.get(scc_id, {}).items()
                   if key != "fact_refs"},
                "index": retrieval_index_ref,
            } if scc_id in selected_retrieval else None,
            "pages": materialized,
            "model_input_policy": prepared.get("model_input_policy"),
            "claim_boundary": prepared.get("claim_boundary"),
        })
    report = {
        "schema_version": 1,
        "policy": "assignment_context_pages_only",
        "logical_group_count": int(prepared["logical_group_count"]),
        "selected_group_ids": selected,
        "selected_group_count": len(selected),
        "logical_page_count": int(prepared["logical_page_count"]),
        "materialized_page_count": len(page_refs),
        "omitted_blocked_page_count": int(prepared["logical_page_count"]) - len(page_refs),
        "selected_shared_fact_count": len(selected_fact_ids),
        "selected_retrieval_fact_count": len(retrieval_fact_ids),
        "selected_retrieval_group_count": len(selected_retrieval),
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    digest = content_sha256(report)
    return page_refs, write_once_json_artifact(
        out_root, f"context/materializations/materialization-{digest[:24]}.json",
        report,
    )


def materialize_context_indexes(
    context_bundle: Mapping[str, Any], *, out_root: Path, out_root_rel: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    contexts, _payloads, prepared = prepare_context_indexes(
        context_bundle, out_root_rel=out_root_rel
    )
    page_refs, _report = materialize_selected_context_indexes(
        prepared, out_root=out_root, selected_scc_ids=sorted(contexts)
    )
    return contexts, page_refs


def _prepare_page(
    page: Any, facts: Mapping[str, Any], out_root_rel: str
) -> dict[str, Any]:
    if not isinstance(page, Mapping) or not isinstance(page.get("scc_id"), str):
        raise ValueError("context page SCC binding is invalid")
    fact_refs = page.get("fact_refs")
    if not isinstance(fact_refs, list) or any(digest not in facts for digest in fact_refs):
        raise ValueError("context page references an unknown shared fact")
    fields = (
        "wave_index", "scc_id", "classification", "dependency_count",
        "dependency_set_sha256", "part_index",
    )
    materialized = {
        **{key: page[key] for key in fields},
        "facts": [{"sha256": digest, **facts[digest]} for digest in fact_refs],
    }
    compact = json.dumps(
        materialized, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    if page.get("materialized_sha256") != hashlib.sha256(compact).hexdigest():
        raise ValueError("context page materialized SHA drift")
    payload = canonical_json_bytes(materialized)
    page_id = str(page.get("page_id", ""))
    relative = f"context/pages/{page_id}.json"
    local = {
        "path": relative,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_bytes": len(payload),
    }
    metadata = {**dict(page), "estimated_tokens": len(payload)}
    return {
        "scc_id": str(page["scc_id"]), "page_id": page_id,
        "fact_refs": list(fact_refs), "payload": payload,
        "relative_path": relative, "local_reference": local,
        "reference": {**local, "path": f"{out_root_rel}/{relative}"},
        "page_metadata": metadata,
    }


def _context_binding(
    scc_id: str, entries: list[dict[str, Any]], out_root_rel: str,
    retrieval: Mapping[str, Any] | None,
    catalog: Mapping[str, Any],
) -> dict[str, Any]:
    entries.sort(key=lambda item: int(item["page_metadata"]["part_index"]))
    pages = [
        {"page_id": entry["page_id"], **entry["reference"]}
        for entry in entries
    ]
    result = {
        "path": f"{out_root_rel}/context/groups/{scc_id}.json",
        "byte_count": sum(int(item["size_bytes"]) for item in pages),
        "token_count": sum(int(item["size_bytes"]) for item in pages),
        "page_count": len(pages),
        "pages": [
            {**item, "estimated_tokens": item["size_bytes"]} for item in pages
        ],
        "catalog": dict(catalog),
    }
    if retrieval is not None:
        result["retrieval"] = {
            key: value for key, value in retrieval.items() if key != "fact_refs"
        }
    return result


def _write_named_json(
    out_root: Path, name: str, payload: Mapping[str, Any],
) -> dict[str, Any]:
    digest = content_sha256(payload)
    return write_once_json_artifact(
        out_root, f"context/indexes/{name}-{digest[:24]}.json", payload,
    )


__all__ = [
    "materialize_context_indexes", "materialize_selected_context_indexes",
    "materialize_prepared_context_catalogs", "prepare_context_indexes",
]
