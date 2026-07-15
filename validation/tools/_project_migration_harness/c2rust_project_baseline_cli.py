from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from .build_facts import file_binding
from .c2rust_project_baseline import run_c2rust_project_baseline
from .c2rust_project_baseline_unit_transpile import (
    run_c2rust_build_ir_unit_baseline,
)
from .project_cli_runtime import target_path


def add_c2rust_baseline_parser(commands: Any) -> None:
    parser = commands.add_parser(
        "c2rust-baseline",
        help="Run a whole-project C2Rust execution baseline with bound evidence.",
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--compile-database", type=Path, required=True)
    parser.add_argument("--build-ir", type=Path)
    parser.add_argument("--build-ir-artifact-root", type=Path)
    parser.add_argument("--execution-contract", type=Path)
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
    build_ir_mode = args.build_ir is not None
    if build_ir_mode != (args.build_ir_artifact_root is not None):
        raise ValueError("c2rust_build_ir_arguments_incomplete")
    if build_ir_mode:
        if args.execution_contract is not None or args.cargo_toolchain is not None:
            raise ValueError("c2rust_build_ir_mode_option_unsupported")
        artifact_root = args.build_ir_artifact_root.resolve(strict=True)
        build_ir_reference = file_binding(
            artifact_root, args.build_ir,
        )
        run = run_c2rust_build_ir_unit_baseline(
            repo_root=args.repo_root,
            compile_commands=args.compile_database,
            build_ir_artifact_root=artifact_root,
            build_ir_reference=build_ir_reference,
            c2rust_transpile=args.c2rust_transpile,
            out_root=output,
            cargo=args.cargo,
            rustc=args.rustc,
            timeout_seconds=args.timeout_seconds,
            environment_overrides=overrides,
        )
    else:
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
            execution_contract=args.execution_contract,
        )
    generated = run.report.get("generated", {})
    units = run.report.get("unit_transpiles", [])
    return {
        "schema_version": 1,
        "status": run.report["status"],
        "run_id": run.report["run_id"],
        "blockers": run.report["blockers"],
        "source_count": len(run.report["inputs"]["source_bindings"]),
        "wrapper_count": len(generated.get("wrappers", [])),
        "unit_count": len(units),
        "scenario_count": (
            generated.get("execution_plan") or {}
        ).get("scenario_count", 0),
        "report": {
            **run.report_ref,
            "path": f"{Path(args.out_root).as_posix()}/{run.report_ref['path']}",
        },
        "semantic_gate": False,
    }


__all__ = ["add_c2rust_baseline_parser", "run_c2rust_baseline_command"]
