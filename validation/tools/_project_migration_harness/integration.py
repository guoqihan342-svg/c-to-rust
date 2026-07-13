from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from . import cargo_project
from . import integration_generation as generations
from . import integration_validation as validation
from .rust_project_cargo import reconstruct_cargo_project_from_ir

def integrate_rust_project_ir(
    rust_project_ir: Mapping[str, Any], artifact_root: Path, project_root: Path,
    *, max_source_bytes: int = cargo_project.MAX_SOURCE_BYTES,
) -> dict[str, Any]:
    """Publish an authoritative generation only after reopening RustProjectIR."""
    stage: Path | None = None
    previous_managed = False
    previous_preserved = True
    try:
        trusted_root = validation.trusted_root(artifact_root)
        target = validation.project_target(project_root, trusted_root)
        current = generations.recover_current_generation(target)
        previous_state, previous_managed = validation.existing_state(current or target)
        plan = reconstruct_cargo_project_from_ir(
            rust_project_ir, trusted_root, max_source_bytes=max_source_bytes,
        )
        if plan.last_good_manifest.get("rust_project_ir_scope") != "full-project":
            raise cargo_project.ProjectInputError(
                "rust_project_ir_scope_not_full_project", "rust_project_ir",
            )
        stage = generations.create_generation_stage(target)
        _write_stage(stage, plan.files)
        staged_state, staged_managed = validation.existing_state(stage)
        if not staged_managed or staged_state == "absent":
            raise cargo_project.ProjectInputError("staged_project_invalid", "atomic_write")
        generation = generations.publish_generation(stage, target, previous_state)
        stage = None
        manifest_bytes = plan.files[cargo_project.LAST_GOOD_MANIFEST]
        return {
            "schema_version": 1, "status": "integrated",
            "integrated_group_ids": list(plan.accepted_group_ids),
            "rust_project_ir_sha256": rust_project_ir["ir_sha256"],
            "rust_project_interface_sha256": rust_project_ir["interface_sha256"],
            "rust_project_ir_completeness": dict(
                rust_project_ir["interface_completeness"]
            ),
            "last_good_manifest": {
                "path": cargo_project.LAST_GOOD_MANIFEST,
                "sha256": validation.digest(manifest_bytes),
            },
            "unsafe_policy": plan.last_good_manifest["unsafe_policy"],
            "last_good_updated": True,
            "generation": {"id": generation.name, "current_pointer": generations.CURRENT,
                           "immutable": True},
            "cargo_executed": False, "diagnostics": [],
        }
    except cargo_project.ProjectInputError as error:
        return _failure(error.code, error.stage, error.group_id,
                        previous_managed, previous_preserved)
    except generations.GenerationCommitError as error:
        previous_preserved = error.preserved
        return _failure(error.code, "generation_publish", None,
                        previous_managed, previous_preserved)
    except OSError:
        return _failure("integration_io_failure", "filesystem", None,
                        previous_managed, previous_preserved)
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


integrate_project = integrate_rust_project_ir


def _write_stage(stage: Path, files: Mapping[str, bytes]) -> None:
    for relative, data in sorted(files.items()):
        path = stage.joinpath(*validation.generated_path(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, data)


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _failure(
    code: str, stage: str, group_id: str | None,
    previous_managed: bool, previous_preserved: bool,
) -> dict[str, Any]:
    diagnostic = {"code": code[:96], "stage": stage[:48]}
    if isinstance(group_id, str) and group_id:
        diagnostic["group_id"] = group_id[:128]
    return {
        "schema_version": 1,
        "status": "failed",
        "integrated_group_ids": [],
        "last_good_preserved": previous_managed and previous_preserved,
        "cargo_executed": False,
        "diagnostics": [diagnostic],
    }
