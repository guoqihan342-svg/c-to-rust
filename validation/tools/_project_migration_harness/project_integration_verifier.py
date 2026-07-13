from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from . import cargo_project
from .artifacts import content_sha256
from .gate_candidate_sets import current_candidate_members
from .integration_generation import GenerationCommitError, recover_current_generation
from .integration_validation import MAX_MANIFEST_BYTES, existing_state, read_bounded
from .ledger import ProjectLedger
from .project_host_gates import record_host_project_observation
from .rust_project_cargo import (
    GENERATOR, RUST_PROJECT_IR_FILE, reconstruct_cargo_project_from_ir,
)
from .rust_project_ir import canonical_rust_project_ir_bytes


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
    interface_complete = False
    try:
        generation = recover_current_generation(project_root)
        source = generation or project_root.resolve(strict=True)
        state, managed = existing_state(source)
        if managed:
            raw = read_bounded(
                source / cargo_project.LAST_GOOD_MANIFEST,
                MAX_MANIFEST_BYTES,
            )
            manifest = json.loads(raw.decode("utf-8"))
            actual = _actual_groups(manifest)
            manifest_sha = hashlib.sha256(raw).hexdigest()
            project_sha = content_sha256({
                "generation_state": state,
                "files": manifest.get("files"),
            })
            ir_matched = _verified_ir_generation(
                source, out_root, raw, manifest,
            )
            completeness = manifest.get("rust_project_ir_completeness")
            interface_complete = (
                isinstance(completeness, dict)
                and completeness.get("status") == "complete"
            )
            matched = actual == expected and state == manifest_sha and ir_matched
            if not matched:
                diagnostics.append("integration_candidate_set_mismatch")
            if not interface_complete:
                diagnostics.append("integration_interface_incomplete")
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
        "interface_complete": interface_complete,
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
            "interface_complete": interface_complete,
        },
    }


def _verified_ir_generation(
    generation_root: Path, artifact_root: Path, manifest_raw: bytes,
    manifest: dict[str, Any],
) -> bool:
    if manifest.get("generator") != GENERATOR:
        return False
    try:
        ir_raw = read_bounded(generation_root / RUST_PROJECT_IR_FILE, 2 * 1024 * 1024)
        ir = json.loads(ir_raw.decode("utf-8"))
        if not isinstance(ir, dict) or canonical_rust_project_ir_bytes(ir) != ir_raw:
            return False
        if (
            manifest.get("rust_project_ir_sha256") != ir.get("ir_sha256")
            or manifest.get("rust_project_interface_sha256") != ir.get("interface_sha256")
            or manifest.get("rust_project_ir_completeness")
            != ir.get("interface_completeness")
        ):
            return False
        expected = reconstruct_cargo_project_from_ir(ir, artifact_root)
        if expected.files[cargo_project.LAST_GOOD_MANIFEST] != manifest_raw:
            return False
        for relative, data in expected.files.items():
            if read_bounded(generation_root / relative, max(len(data), 1)) != data:
                return False
        return True
    except (
        OSError, UnicodeError, ValueError, json.JSONDecodeError,
        cargo_project.ProjectInputError,
    ):
        return False


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
