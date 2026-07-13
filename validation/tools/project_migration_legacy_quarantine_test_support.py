from __future__ import annotations

import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness import cargo_project
from validation.tools._project_migration_harness import integration_validation as validation
from validation.tools._project_migration_harness.quarantine_filesystem import (
    detached_root, ensure_store, present, publish, remove_tree,
    trusted_candidate_root, verify_generation, write_stage,
)
from validation.tools._project_migration_harness.quarantine_manifest import (
    QUARANTINE_MANIFEST, candidate_set, generation_files,
)
from validation.tools.project_migration_legacy_cargo_test_support import (
    reconstruct_cargo_project,
)


def materialize_quarantine_generation(
    migration_manifest: Mapping[str, Any],
    candidate_descriptors: Sequence[Mapping[str, Any]], candidate_root: Path,
    quarantine_root: Path, candidate_set_sha256: str,
    candidate_set_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    stage: Path | None = None
    count = 0
    try:
        candidates = trusted_candidate_root(candidate_root)
        quarantine = detached_root(quarantine_root, candidates)
        members, bindings = candidate_set(
            candidate_descriptors, candidate_set_sha256, candidate_set_manifest,
        )
        count = len(members)
        plan = reconstruct_cargo_project(
            migration_manifest, candidate_descriptors, candidates,
        )
        if len(plan.accepted_group_ids) != count:
            _fail("quarantine_candidate_set_incomplete", "candidate")
        files = generation_files(
            plan, candidate_set_sha256, candidate_set_manifest, members, bindings,
        )
        store = ensure_store(quarantine)
        stage = Path(tempfile.mkdtemp(prefix=".staging.", dir=store))
        write_stage(stage, files)
        state = verify_generation(stage, files, "quarantine_stage_invalid")
        generation = publish(stage, store, state, files)
        stage = None
        manifest = files[QUARANTINE_MANIFEST]
        generation_manifest = files[cargo_project.LAST_GOOD_MANIFEST]
        relative = f"generations/{generation.name}"
        return {
            "schema_version": 1, "status": "materialized",
            "candidate_set": {"sha256": candidate_set_sha256, "member_count": count},
            "candidate_count": count,
            "generation": {"sha256": state, "path": relative, "immutable": True},
            "manifest_ref": {"path": f"{relative}/{QUARANTINE_MANIFEST}",
                             "sha256": validation.digest(manifest),
                             "size_bytes": len(manifest)},
            "generation_manifest_ref": {
                "path": f"{relative}/{cargo_project.LAST_GOOD_MANIFEST}",
                "sha256": validation.digest(generation_manifest),
                "size_bytes": len(generation_manifest)},
            "immutable": True, "last_good_updated": False,
            "cargo_executed": False, "diagnostics": [],
        }
    except cargo_project.ProjectInputError as error:
        return _failure(error.code, error.stage, count)
    except (OSError, TypeError, ValueError):
        return _failure("quarantine_io_failure", "filesystem", count)
    finally:
        if stage is not None and present(stage):
            remove_tree(stage)


def _fail(code: str, stage: str) -> None:
    raise cargo_project.ProjectInputError(code, stage)


def _failure(code: str, stage: str, count: int) -> dict[str, Any]:
    return {"schema_version": 1, "status": "failed", "candidate_set": None,
            "candidate_count": count, "generation": None, "manifest_ref": None,
            "immutable": False, "last_good_updated": False, "cargo_executed": False,
            "generation_manifest_ref": None,
            "diagnostics": [{"code": code[:96], "stage": stage[:48]}]}


__all__ = ["QUARANTINE_MANIFEST", "materialize_quarantine_generation"]
