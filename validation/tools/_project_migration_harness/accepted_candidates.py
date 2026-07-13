from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from .ledger import LedgerError, ProjectLedger


def accepted_candidate_descriptors(
    ledger: ProjectLedger, *, run_id: str, out_root_rel: str
) -> list[dict[str, Any]]:
    root = PurePosixPath(out_root_rel)
    states = ledger.unit_states(run_id)
    if not states:
        raise LedgerError("project run has no migration units")
    if any(
        item["resumable_status"] != "last_good"
        or not isinstance(item.get("last_good_artifact_id"), str)
        for item in states
    ):
        raise LedgerError("all migration units require host-verified last-good candidates")
    rows = ledger.orchestration_rows(run_id)["artifacts"]
    by_id = {
        (str(item["unit_id"]), str(item["artifact_id"])): item for item in rows
    }
    descriptors: list[dict[str, Any]] = []
    for state in states:
        unit_id = str(state["unit_id"])
        artifact_id = str(state["last_good_artifact_id"])
        artifact = by_id.get((unit_id, artifact_id))
        if artifact is None or artifact["kind"] != "rust-candidate":
            raise LedgerError("last-good pointer does not reference a Rust candidate")
        path = PurePosixPath(str(artifact["repo_rel_path"]))
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise LedgerError("last-good candidate is outside the project output root") from error
        metadata = _metadata(artifact.get("metadata_json"))
        descriptors.append({
            "group_id": str(state["group_id"]),
            "status": "accepted",
            "source_path": relative.as_posix(),
            "sha256": str(artifact["content_sha256"]),
            "public_symbols": _strings(metadata.get("public_symbols"), "public_symbols"),
            "required_symbols": _strings(metadata.get("required_symbols"), "required_symbols"),
            "unsafe_count": _count(metadata.get("unsafe_count"), "unsafe_count"),
        })
    return sorted(descriptors, key=lambda item: item["group_id"])


def _metadata(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, str):
        raise LedgerError("candidate metadata is missing")
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise LedgerError("candidate metadata is invalid JSON") from error
    if not isinstance(payload, Mapping):
        raise LedgerError("candidate metadata must be an object")
    return payload


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise LedgerError(f"candidate {label} metadata is invalid")
    return list(value)


def _count(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise LedgerError(f"candidate {label} metadata is invalid")
    return value


__all__ = ["accepted_candidate_descriptors"]
