from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any, Mapping

from .gate_candidate_sets import candidate_set_members
from .ledger import LedgerError, ProjectLedger


def accepted_candidate_descriptors(
    ledger: ProjectLedger, *, run_id: str, out_root_rel: str
) -> list[dict[str, Any]]:
    states = ledger.unit_states(run_id)
    if not states:
        raise LedgerError("project run has no migration units")
    if any(
        item["resumable_status"] != "last_good"
        or not isinstance(item.get("last_good_artifact_id"), str)
        for item in states
    ):
        raise LedgerError("all migration units require host-verified last-good candidates")
    members = [{
        "unit_id": str(item["unit_id"]),
        "artifact_id": str(item["last_good_artifact_id"]),
        "content_sha256": "",
    } for item in states]
    return candidate_descriptors_for_members(
        ledger, run_id=run_id, out_root_rel=out_root_rel, members=members,
        require_member_sha=False,
    )


def candidate_set_descriptors(
    ledger: ProjectLedger, *, run_id: str, out_root_rel: str,
    candidate_set_sha256: str,
) -> list[dict[str, Any]]:
    with ledger.connect() as connection:
        members = candidate_set_members(connection, run_id, candidate_set_sha256)
    return candidate_descriptors_for_members(
        ledger, run_id=run_id, out_root_rel=out_root_rel, members=members,
    )


def candidate_descriptors_for_members(
    ledger: ProjectLedger, *, run_id: str, out_root_rel: str,
    members: list[dict[str, str]], require_member_sha: bool = True,
) -> list[dict[str, Any]]:
    root = PurePosixPath(out_root_rel)
    states = {str(item["unit_id"]): item for item in ledger.unit_states(run_id)}
    rows = ledger.orchestration_rows(run_id)["artifacts"]
    by_id = {
        (str(item["unit_id"]), str(item["artifact_id"])): item for item in rows
    }
    descriptors: list[dict[str, Any]] = []
    for member in members:
        unit_id = str(member["unit_id"])
        artifact_id = str(member["artifact_id"])
        state = states.get(unit_id)
        if state is None:
            raise LedgerError("candidate set references an unknown migration unit")
        artifact = by_id.get((unit_id, artifact_id))
        if artifact is None or artifact["kind"] != "rust-candidate":
            raise LedgerError("candidate set member does not reference a Rust candidate")
        if require_member_sha and artifact["content_sha256"] != member["content_sha256"]:
            raise LedgerError("candidate set member content binding drifted")
        path = PurePosixPath(str(artifact["repo_rel_path"]))
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise LedgerError("candidate is outside the project output root") from error
        metadata = _metadata(artifact.get("metadata_json"))
        descriptors.append({
            "unit_id": unit_id,
            "artifact_id": artifact_id,
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


__all__ = [
    "accepted_candidate_descriptors", "candidate_descriptors_for_members",
    "candidate_set_descriptors",
]
