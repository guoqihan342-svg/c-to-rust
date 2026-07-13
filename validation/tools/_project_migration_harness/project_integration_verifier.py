from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import content_sha256
from .gate_candidate_sets import current_candidate_members
from .integration_generation import GenerationCommitError, recover_current_generation
from .integration_validation import existing_state, read_bounded
from .ledger import ProjectLedger
from .project_host_gates import record_host_project_observation


def verify_integrated_project(
    *, ledger: ProjectLedger, run_id: str, project_root: Path,
    out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    candidate_set = ledger.bind_current_candidate_set(run_id=run_id)
    expected = _expected_groups(ledger, run_id)
    diagnostics: list[str] = []
    manifest_sha = hashlib.sha256(b"").hexdigest()
    project_sha = manifest_sha
    matched = False
    try:
        generation = recover_current_generation(project_root)
        source = generation or project_root.resolve(strict=True)
        state, managed = existing_state(source)
        if managed:
            raw = read_bounded(
                source / cargo_project.LAST_GOOD_MANIFEST,
                128_000,
            )
            manifest = json.loads(raw.decode("utf-8"))
            actual = _actual_groups(manifest)
            manifest_sha = hashlib.sha256(raw).hexdigest()
            project_sha = content_sha256({
                "generation_state": state,
                "files": manifest.get("files"),
            })
            matched = actual == expected and state == manifest_sha
            if not matched:
                diagnostics.append("integration_candidate_set_mismatch")
        else:
            diagnostics.append("integration_generation_unmanaged")
    except (
        GenerationCommitError, OSError, UnicodeError, ValueError,
        json.JSONDecodeError, cargo_project.ProjectInputError,
    ):
        diagnostics.append("integration_generation_invalid")
    observation = {
        "managed_project_unchanged": matched,
        "candidate_count": len(expected),
        "manifest_sha256": manifest_sha,
        "project_sha256": project_sha,
    }
    recorded = record_host_project_observation(
        ledger=ledger,
        out_root=out_root,
        out_root_rel=out_root_rel,
        run_id=run_id,
        gate_kind="integration",
        candidate_set_sha256=candidate_set,
        observation=observation,
        diagnostic_codes=diagnostics,
    )
    return {
        **recorded,
        "verification": {
            "adapter": "managed-generation-v1",
            "expected_group_count": len(expected),
            "matched_candidate_set": matched,
        },
    }


def _expected_groups(ledger: ProjectLedger, run_id: str) -> dict[str, str]:
    states = {str(item["unit_id"]): item for item in ledger.unit_states(run_id)}
    with ledger.connect() as connection:
        members = current_candidate_members(connection, run_id)
    result: dict[str, str] = {}
    for member in members:
        state = states.get(member["unit_id"])
        group_id = state.get("group_id") if isinstance(state, dict) else None
        if not isinstance(group_id, str) or group_id in result:
            raise ValueError("candidate set cannot be projected to unique migration groups")
        result[group_id] = member["content_sha256"]
    return result


def _actual_groups(manifest: Any) -> dict[str, str]:
    groups = manifest.get("accepted_groups") if isinstance(manifest, dict) else None
    if not isinstance(groups, list):
        raise ValueError("managed project accepted groups are missing")
    result: dict[str, str] = {}
    for group in groups:
        source = group.get("source") if isinstance(group, dict) else None
        group_id = group.get("group_id") if isinstance(group, dict) else None
        digest = source.get("sha256") if isinstance(source, dict) else None
        if (
            not isinstance(group_id, str)
            or not isinstance(digest, str)
            or group_id in result
        ):
            raise ValueError("managed project accepted group is invalid")
        result[group_id] = digest
    return result


__all__ = ["verify_integrated_project"]
