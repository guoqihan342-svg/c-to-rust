from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest import mock
from typing import Any

from validation.tools._project_migration_harness.project_cargo_verifier import (
    verify_project_cargo,
)


def verify_project_compile_intake(
    *, ledger: Any, run_id: str, project_root: Path,
    harness_root: Path, out_root: Path, cargo_execution: dict[str, Any],
) -> dict[str, Any]:
    failed_check = deepcopy(cargo_execution["checks"][0])
    failed_check.update({
        "status": "failed",
        "returncode": 1,
        "diagnostics": [{
            "code": "e0432", "stage": "cargo-check",
            "message": "unresolved import `shared_api`",
            "file": "src/lib.rs", "line": 1, "column": 1,
            "level": "error", "origin": "rustc-compiler-message",
        }],
    })
    failed_execution = {
        **deepcopy(cargo_execution),
        "status": "failed",
        "checks": [failed_check],
    }
    with mock.patch(
        "validation.tools._project_migration_harness.project_cargo_verifier."
        "run_cargo_project_gates",
        return_value=failed_execution,
    ):
        return verify_project_cargo(
            ledger=ledger, run_id=run_id, project_root=project_root,
            runtime_root=harness_root / "target/cargo-runtime-project-error",
            out_root=out_root, out_root_rel="target/run",
        )


__all__ = ["verify_project_compile_intake"]
