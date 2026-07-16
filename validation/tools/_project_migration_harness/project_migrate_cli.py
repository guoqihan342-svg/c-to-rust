from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath
from typing import Any

from . import project_cli_runtime
from .project_completion_cli import run_completion_cli_command
from .project_plan_cli import run_plan_cli_command


def run_migrate_cli_command(
    args: argparse.Namespace, *, harness_root: Path,
) -> dict[str, Any]:
    plan = run_plan_cli_command(args, harness_root=harness_root)
    if plan.get("status") != "planned":
        return plan

    out_root_rel = project_cli_runtime.target_relative(
        args.out_root, "out-root", repo_root=harness_root,
    )
    completion_values = dict(vars(args))
    completion_values["plan"] = Path(
        (PurePosixPath(out_root_rel) / "project-migration-plan.json").as_posix()
    )
    completion_args = argparse.Namespace(**completion_values)
    return run_completion_cli_command(
        "run-to-completion", completion_args, harness_root=harness_root,
    )


__all__ = ["run_migrate_cli_command"]
