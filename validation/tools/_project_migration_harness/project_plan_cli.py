from __future__ import annotations

from pathlib import Path
from typing import Any

from . import project_cli_runtime
from .orchestrator import plan_project


def run_plan_cli_command(args: Any, *, harness_root: Path) -> dict[str, Any]:
    out_root_rel = project_cli_runtime.target_relative(
        args.out_root, "out-root", repo_root=harness_root,
    )
    return plan_project(
        args.repo_root,
        harness_root=harness_root,
        out_root=out_root_rel,
        compile_database=args.compile_database,
        make_report=args.make_report,
        run_id=args.run_id,
        source_commit=args.source_commit,
        max_units=args.max_units,
        max_concurrency=args.max_concurrency,
        max_attempts=args.max_attempts,
        context_page_bytes=args.context_page_bytes,
        context_page_tokens=args.context_page_tokens,
        context_group_pages=args.context_group_pages,
        require_build_closure=args.build_closure_policy == "required",
        profile=args.profile,
    )


__all__ = ["run_plan_cli_command"]
