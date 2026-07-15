from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .c2rust_project_baseline import run_c2rust_project_baseline
from .project_cli_runtime import target_path


def add_c2rust_baseline_parser(commands: Any) -> None:
    parser = commands.add_parser(
        "c2rust-baseline",
        help="Run a whole-project C2Rust execution baseline with bound evidence.",
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--compile-database", type=Path, required=True)
    parser.add_argument("--c2rust-transpile", type=Path, required=True)
    parser.add_argument("--cargo", type=Path, required=True)
    parser.add_argument("--rustc", type=Path, required=True)
    parser.add_argument("--out-root", default="target/c2rust-project-baseline")
    parser.add_argument("--cargo-toolchain")
    parser.add_argument("--cargo-home", type=Path)
    parser.add_argument("--rustup-home", type=Path)
    parser.add_argument("--rustc-bootstrap", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=300)


def run_c2rust_baseline_command(
    args: argparse.Namespace, *, harness_root: Path,
) -> dict[str, Any]:
    output = target_path(args.out_root, "out-root", repo_root=harness_root)
    overrides = {}
    if args.cargo_home is not None:
        overrides["CARGO_HOME"] = str(args.cargo_home)
    if args.rustup_home is not None:
        overrides["RUSTUP_HOME"] = str(args.rustup_home)
    if args.rustc_bootstrap:
        overrides["RUSTC_BOOTSTRAP"] = "1"
    run = run_c2rust_project_baseline(
        repo_root=args.repo_root,
        compile_commands=args.compile_database,
        c2rust_transpile=args.c2rust_transpile,
        out_root=output,
        cargo=args.cargo,
        rustc=args.rustc,
        timeout_seconds=args.timeout_seconds,
        cargo_toolchain=args.cargo_toolchain,
        environment_overrides=overrides,
    )
    return {
        "schema_version": 1,
        "status": run.report["status"],
        "run_id": run.report["run_id"],
        "blockers": run.report["blockers"],
        "source_count": len(run.report["inputs"]["source_bindings"]),
        "wrapper_count": len(run.report["generated"]["wrappers"]),
        "report": {
            **run.report_ref,
            "path": f"{Path(args.out_root).as_posix()}/{run.report_ref['path']}",
        },
        "semantic_gate": False,
    }


__all__ = ["add_c2rust_baseline_parser", "run_c2rust_baseline_command"]
