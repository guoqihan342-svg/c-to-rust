from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
import hashlib
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from .artifacts import checked_relative_path
from .artifact_verification import verify_artifact_reference
from .artifact_write_once import write_once_bytes_artifact
from .context_catalog import prepare_context_catalog
from .context_page_binding import context_group_binding, prepare_context_page
from .context_page_proof import (
    _issue_host_context_group_proof,
    _issue_host_context_page_proof_set,
)
from .context_retrieval import validate_retrieval_bundle
from .context_selection_materialization import bind_selection_materialization


def prepare_plan_context_indexes(
    context_bundle: Mapping[str, Any], *, out_root: Path, out_root_rel: str,
    max_page_bytes: int,
) -> tuple[dict[str, dict[str, Any]], Any, dict[str, int]]:
    """Stage catalogs one group at a time and retain only page proofs."""
    facts = context_bundle.get("shared_facts")
    pages = context_bundle.get("pages")
    if not isinstance(facts, Mapping) or not isinstance(pages, list):
        raise ValueError("context bundle facts/pages contract is invalid")
    pages_by_scc = _pages_by_scc(pages)
    retrieval = validate_retrieval_bundle(context_bundle, facts, pages)
    page_budget = _positive(max_page_bytes, "context page byte budget")
    contexts: dict[str, dict[str, Any]] = {}
    group_proofs = []
    catalog_references: list[dict[str, Any]] = []
    page_ids: set[str] = set()
    out_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".context-catalog-stage-", dir=out_root.parent,
    ) as temporary:
        staging = Path(temporary)
        for scc_id in sorted(pages_by_scc):
            entries = [
                prepare_context_page(
                    page, facts, out_root_rel, max_payload_bytes=page_budget,
                )
                for page in pages_by_scc[scc_id]
            ]
            for entry in entries:
                page_id = entry["page_id"]
                if page_id in page_ids:
                    raise ValueError("context page IDs must be unique")
                page_ids.add(page_id)
            group_retrieval = retrieval.get(scc_id)
            if group_retrieval is not None:
                group_retrieval = bind_selection_materialization(
                    group_retrieval, entries,
                )
            catalog = prepare_context_catalog(
                scc_id, entries, group_retrieval,
                out_root_rel=out_root_rel,
                model_input_policy=context_bundle.get("model_input_policy"),
                claim_boundary=context_bundle.get("claim_boundary"),
            )
            context = context_group_binding(
                scc_id, entries, out_root_rel, group_retrieval,
                catalog["reference"],
            )
            group_proofs.append(_issue_host_context_group_proof(
                scc_id, context, entries,
            ))
            _stage_catalog(staging, catalog)
            catalog_references.append(dict(catalog["local_reference"]))
            contexts[scc_id] = context
        proof_set = _issue_host_context_page_proof_set(group_proofs)
        _publish_staged_catalogs(
            staging, out_root=out_root, references=catalog_references,
        )
    return contexts, proof_set, {
        "logical_page_count": len(pages),
        "logical_group_count": len(pages_by_scc),
    }


def _pages_by_scc(pages: list[Any]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for page in pages:
        if (
            not isinstance(page, Mapping)
            or not isinstance(page.get("scc_id"), str)
            or not page["scc_id"]
        ):
            raise ValueError("context page SCC binding is invalid")
        result[page["scc_id"]].append(page)
    return dict(result)


def _positive(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _publish_staged_catalogs(
    staging: Path, *, out_root: Path,
    references: list[dict[str, Any]],
) -> None:
    if out_root.exists():
        for reference in references:
            relative = PurePosixPath(reference["path"])
            if out_root.joinpath(*relative.parts).exists():
                verify_artifact_reference(
                    out_root, reference, max_bytes=reference["size_bytes"],
                )
    for reference in references:
        relative = reference["path"]
        data = staging.joinpath(*PurePosixPath(relative).parts).read_bytes()
        if (
            len(data) != reference["size_bytes"]
            or hashlib.sha256(data).hexdigest() != reference["sha256"]
        ):
            raise ValueError("staged context catalog drifted")
        if write_once_bytes_artifact(out_root, relative, data) != reference:
            raise ValueError("staged context catalog publication drifted")


def _stage_catalog(staging: Path, catalog: Mapping[str, Any]) -> None:
    reference = catalog.get("local_reference")
    data = catalog.get("payload")
    if not isinstance(reference, Mapping) or not isinstance(data, bytes):
        raise ValueError("staged context catalog is invalid")
    relative = checked_relative_path(reference.get("path"))
    if (
        len(data) != reference.get("size_bytes")
        or hashlib.sha256(data).hexdigest() != reference.get("sha256")
    ):
        raise ValueError("staged context catalog binding drifted")
    target = staging.joinpath(*PurePosixPath(relative).parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


__all__ = ["prepare_plan_context_indexes"]
