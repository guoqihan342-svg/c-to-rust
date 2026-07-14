from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifact_write_once import write_once_bytes_artifact
from .artifacts import canonical_json_bytes, content_sha256
from .context_catalog import prepare_context_catalog, validate_context_catalog
from .context_contracts import canonical
from .context_index_store import prepare_context_indexes
from .context_required_facts import context_retrieval_ready
from .context_selection_materialization import (
    bind_selection_materialization, require_selection_materialization,
)
from .orchestration_facts import read_artifact_reference
from .portfolio_integrity import bind_context


def prepare_single_scc_refresh_artifacts(
    context_bundle: Mapping[str, Any], *, run_id: str, unit_id: str,
    assignment_context: Mapping[str, Any], out_root: Path, out_root_rel: str,
    context_page_limit: int,
) -> dict[str, Any]:
    _contexts, _payloads, prepared = prepare_context_indexes(
        context_bundle, out_root_rel=out_root_rel,
    )
    by_scc = prepared.get("by_scc")
    retrievals = prepared.get("retrieval")
    if not isinstance(by_scc, Mapping) or not isinstance(retrievals, Mapping):
        raise ValueError("context refresh prepared store is invalid")
    entries = by_scc.get(unit_id)
    retrieval = retrievals.get(unit_id)
    if not isinstance(entries, list) or not entries or not isinstance(retrieval, Mapping):
        raise ValueError("context refresh bundle has no host-retrieval SCC")
    receipt = _write_selection_receipt(out_root, retrieval)

    refreshed_entries = []
    page_payloads: dict[str, bytes] = {}
    for entry in sorted(entries, key=lambda item: int(item["page_metadata"]["part_index"])):
        payload = bytes(entry["payload"])
        reference = _write_cas_bytes(out_root, "pages", payload)
        prefixed = _prefix(reference, out_root_rel)
        page_payloads[prefixed["path"]] = payload
        refreshed_entries.append({
            **dict(entry), "relative_path": reference["path"],
            "local_reference": reference, "reference": prefixed,
        })
    refreshed_retrieval = bind_selection_materialization(
        retrieval, refreshed_entries,
    )
    public_retrieval = {
        key: value for key, value in refreshed_retrieval.items()
        if key != "fact_refs"
    }
    if not context_retrieval_ready({"retrieval": public_retrieval}):
        raise ValueError("context refresh selection is not ready")

    catalog = prepare_context_catalog(
        unit_id, refreshed_entries, refreshed_retrieval,
        out_root_rel=out_root_rel,
        model_input_policy=prepared.get("model_input_policy"),
        claim_boundary=prepared.get("claim_boundary"),
    )
    catalog_ref = _prefix(
        _write_cas_bytes(out_root, "catalogs", bytes(catalog["payload"])),
        out_root_rel,
    )
    local_pages = [
        {"page_id": entry["page_id"], **entry["local_reference"]}
        for entry in refreshed_entries
    ]
    group_payload = {
        "schema_version": 1,
        "scc_id": unit_id,
        "catalog": catalog_ref,
        "retrieval": public_retrieval,
        "pages": local_pages,
        "model_input_policy": prepared.get("model_input_policy"),
        "claim_boundary": prepared.get("claim_boundary"),
    }
    group_ref = _prefix(
        _write_cas_bytes(out_root, "groups", canonical_json_bytes(group_payload)),
        out_root_rel,
    )
    raw_context = {
        "path": group_ref["path"],
        "pages": [
            {
                "page_id": entry["page_id"], **entry["reference"],
                "estimated_tokens": entry["reference"]["size_bytes"],
            }
            for entry in refreshed_entries
        ],
        "page_count": len(refreshed_entries),
        "byte_count": sum(item["size_bytes"] for item in local_pages),
        "token_count": sum(item["size_bytes"] for item in local_pages),
        "catalog": catalog_ref,
        "retrieval": public_retrieval,
    }
    byte_budget = _positive(assignment_context.get("byte_budget"), "byte budget")
    token_budget = _positive(assignment_context.get("token_budget"), "token budget")
    if len(refreshed_entries) > context_page_limit:
        raise ValueError("context refresh page limit exceeded")
    effective = bind_context(
        raw_context, page_payloads=page_payloads, page_root=None,
        max_page_bytes=byte_budget,
    )
    if effective["byte_count"] > byte_budget or effective["token_count"] > token_budget:
        raise ValueError("context refresh group budget exceeded")
    effective = {
        **effective, "byte_budget": byte_budget, "token_budget": token_budget,
    }
    return {
        "run_id": run_id,
        "unit_id": unit_id,
        "effective_context": effective,
        "selection_receipt": _prefix(receipt, out_root_rel),
        "catalog": catalog_ref,
        "group": group_ref,
        "pages": [_prefix(entry["local_reference"], out_root_rel) for entry in refreshed_entries],
        "selection_receipt_sha256": public_retrieval["selection_receipt_sha256"],
        "materialized_page_set_sha256": public_retrieval["materialized_page_set_sha256"],
        "selection_materialization_sha256": public_retrieval[
            "selection_materialization_sha256"
        ],
        "context_sha256": content_sha256(effective),
    }


def reopen_context_catalog(
    harness_root: Path, reference: Mapping[str, Any], *, unit_id: str,
    require_materialized_pages: bool = True,
) -> dict[str, Any]:
    data = read_artifact_reference(harness_root, reference)
    if reference.get("size_bytes") != len(data):
        raise ValueError("context refresh catalog size drifted")
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("context refresh catalog is not JSON") from error
    if canonical_json_bytes(raw) != data:
        raise ValueError("context refresh catalog is not canonical JSON")
    catalog = validate_context_catalog(raw)
    if catalog["scc_id"] != unit_id:
        raise ValueError("context refresh catalog SCC binding drifted")
    prefix = _artifact_prefix(str(reference.get("path", "")))
    page_facts = []
    for page in catalog["pages"]:
        local = page["reference"]
        if require_materialized_pages:
            bound = {
                **local,
                "path": (prefix / PurePosixPath(local["path"])).as_posix(),
            }
            payload = read_artifact_reference(harness_root, bound)
            if canonical_json_bytes(page["payload"]) != payload:
                raise ValueError("context refresh catalog page payload drifted")
        page_facts.append({"page_id": page["page_id"], **local})
    retrieval = catalog.get("retrieval")
    if isinstance(retrieval, Mapping):
        _require_selection_receipt(retrieval)
        require_selection_materialization(retrieval, page_facts)
    return catalog


def _write_selection_receipt(
    out_root: Path, retrieval: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        key: value for key, value in retrieval.items()
        if key not in {
            "fact_refs", "selection_receipt_sha256",
            "materialized_page_set_sha256", "selection_materialization_sha256",
        }
    }
    encoded = canonical(payload)
    if hashlib.sha256(encoded).hexdigest() != retrieval.get("selection_receipt_sha256"):
        raise ValueError("context refresh selection receipt drifted")
    return _write_cas_bytes(out_root, "receipts", encoded)


def _require_selection_receipt(retrieval: Mapping[str, Any]) -> None:
    payload = {
        key: value for key, value in retrieval.items()
        if key not in {
            "selection_receipt_sha256", "materialized_page_set_sha256",
            "selection_materialization_sha256",
        }
    }
    if hashlib.sha256(canonical(payload)).hexdigest() != retrieval.get(
        "selection_receipt_sha256"
    ):
        raise ValueError("context refresh catalog selection receipt drifted")


def _write_cas_bytes(out_root: Path, kind: str, data: bytes) -> dict[str, Any]:
    digest = hashlib.sha256(data).hexdigest()
    return write_once_bytes_artifact(
        out_root,
        f"context/frontier-cas/{kind}/sha256/{digest[:2]}/{digest}.json",
        data,
    )


def _prefix(reference: Mapping[str, Any], root: str) -> dict[str, Any]:
    return {**dict(reference), "path": f"{root}/{reference['path']}"}


def _artifact_prefix(path: str) -> PurePosixPath:
    value = PurePosixPath(path)
    parts = value.parts
    try:
        index = parts.index("context")
    except ValueError as error:
        raise ValueError("context refresh catalog path is invalid") from error
    return PurePosixPath(*parts[:index])


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"context refresh {label} is invalid")
    return value


__all__ = ["prepare_single_scc_refresh_artifacts", "reopen_context_catalog"]
