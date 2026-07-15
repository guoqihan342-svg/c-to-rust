from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import shutil
from typing import Any

from validation.tools._project_migration_harness.integration_generation import (
    create_generation_stage,
    publish_generation,
    recover_current_generation,
)
from validation.tools._project_migration_harness.integration_validation import (
    existing_state,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    reconstruct_cargo_project_from_ir,
)


def materialize_candidate_generation(
    rust_project_ir: Mapping[str, Any], artifact_root: Path, target: Path,
    *, publish_current: bool = False,
) -> Path:
    """Materialize a test-only candidate tree, optionally with a test CURRENT."""
    plan = reconstruct_cargo_project_from_ir(rust_project_ir, artifact_root)
    root = Path(target)
    if publish_current:
        current = recover_current_generation(root)
        previous, _managed = existing_state(current or root)
        stage = create_generation_stage(root)
        try:
            _write_files(stage, plan.files)
            return publish_generation(stage, root, previous)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    _write_files(root, plan.files)
    return root


def _write_files(root: Path, files: Mapping[str, bytes]) -> None:
    for relative, data in files.items():
        path = root.joinpath(*PurePosixPath(relative).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


__all__ = ["materialize_candidate_generation"]
