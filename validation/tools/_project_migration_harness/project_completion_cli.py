from __future__ import annotations

from pathlib import Path
from typing import Any

from . import project_cli_runtime
from .ledger import ProjectLedger
from .project_completion_coordinator import resume_project_completion
from .project_migration_cli import load_object, output_binding
from .project_run_to_completion import run_project_to_completion


def run_completion_cli_command(
    command: str, args: Any, *, harness_root: Path,
) -> dict[str, Any]:
    if command == "complete":
        return resume_project_completion(
            ledger=project_cli_runtime.ledger(args.db, repo_root=harness_root),
            run_id=args.run_id, harness_root=harness_root,
            repo_root=args.repo_root, logical_model=args.logical_model,
            resolved_model=args.resolved_model,
            timeout_seconds=args.timeout_seconds,
            preflight_timeout_seconds=args.preflight_timeout_seconds,
        )
    if command != "run-to-completion":
        raise ValueError("project completion CLI command is invalid")
    plan_path = project_cli_runtime.target_path(
        args.plan, "plan", repo_root=harness_root, must_exist=True,
    )
    plan = load_object(plan_path)
    ledger_path, out_rel = output_binding(
        plan, plan_path=plan_path, harness_root=harness_root,
    )
    out_root = harness_root.joinpath(*out_rel.parts)
    ledger = ProjectLedger(project_cli_runtime.ledger_path(
        ledger_path, repo_root=harness_root,
    ))
    return run_project_to_completion(
        project_cli_runtime.load_bound_portfolio(plan, out_root),
        ledger=ledger, harness_root=harness_root, repo_root=args.repo_root,
        out_root=out_root, out_root_rel=out_rel.as_posix(),
        logical_model=args.logical_model, resolved_model=args.resolved_model,
        timeout_seconds=args.timeout_seconds,
        preflight_timeout_seconds=args.preflight_timeout_seconds,
        lease_ttl_seconds=args.lease_ttl_seconds, max_cycles=args.max_cycles,
    )


__all__ = ["run_completion_cli_command"]
