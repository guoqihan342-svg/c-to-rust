from __future__ import annotations
import argparse
import json
from pathlib import Path
from typing import Any, Sequence

from .build_adapter import BuildInputSelection, MAKE_REPORT_INPUT_KIND
from .c2rust_project_baseline_cli import add_c2rust_baseline_parser
from .make_dry_run_cli import add_collect_make_parser
from .project_migration_plan_binding import (
    load_next_frontier_bindings,
    output_binding,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generic whole-project, AI-first C-to-Rust migration orchestration."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add_collect_make_parser(commands)
    add_c2rust_baseline_parser(commands)

    plan = commands.add_parser("plan")
    _add_plan_arguments(plan)

    migrate = commands.add_parser("migrate")
    _add_plan_arguments(migrate)
    _add_completion_runtime_arguments(migrate)

    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("--plan", type=Path, required=True)
    dispatch.add_argument("--lease-ttl-seconds", type=int, default=900)

    frontier = commands.add_parser("prepare-next-context-frontier-wave")
    frontier.add_argument("--plan", type=Path, required=True)
    frontier.add_argument("--latest-dag-path", required=True)
    frontier.add_argument("--latest-dag-sha256", required=True)
    frontier.add_argument("--latest-dag-size-bytes", type=int, required=True)
    frontier.add_argument("--completed-wave-index", type=int, required=True)
    frontier.add_argument("--failure-evidence", type=Path, required=True)
    frontier.add_argument("--expansion-queries", type=Path, required=True)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--out-root", default="target/project-migration")
    preflight.add_argument("--run-id", required=True)
    preflight.add_argument("--logical-model", default="GLM-5.1")
    preflight.add_argument("--resolved-model", default="zai/glm-5.1")
    preflight.add_argument("--timeout-seconds", type=int, default=60)

    worker = commands.add_parser("run-worker")
    _reference_args(worker, "request")
    _reference_args(worker, "preflight")
    worker.add_argument("--db", type=Path, required=True)
    worker.add_argument("--logical-model", default="GLM-5.1")
    worker.add_argument("--resolved-model", default="zai/glm-5.1")
    worker.add_argument("--timeout-seconds", type=int, default=300)

    ingest = commands.add_parser("ingest")
    ingest.add_argument("--db", type=Path, required=True)
    ingest.add_argument("--run-id", required=True)
    ingest.add_argument("--worker-id", required=True)
    ingest.add_argument("--attempt-id", required=True)
    ingest.add_argument("--fencing-token", type=int, required=True)
    ingest.add_argument("--response", type=Path, required=True)

    gate = commands.add_parser("record-candidate-gate")
    gate.add_argument("--db", type=Path, required=True)
    gate.add_argument("--out-root", required=True)
    gate.add_argument("--run-id", required=True)
    gate.add_argument("--unit-id", required=True)
    gate.add_argument("--candidate-artifact-id", required=True)
    gate.add_argument("--record-id", required=True)
    gate.add_argument("--gate-family", required=True)
    gate.add_argument("--diagnostics", type=Path, required=True)

    promote = commands.add_parser("promote")
    promote.add_argument("--db", type=Path, required=True)
    promote.add_argument("--run-id", required=True)
    promote.add_argument("--unit-id", required=True)
    promote.add_argument("--candidate-artifact-id", required=True)

    verified = commands.add_parser("integrate-verified")
    verified.add_argument("--manifest", type=Path, required=True)
    verified.add_argument("--db", type=Path, required=True)
    verified.add_argument("--run-id", required=True)
    verified.add_argument("--candidate-root", type=Path, required=True)
    verified.add_argument("--candidate-root-rel", required=True)
    verified.add_argument("--project-root", type=Path, required=True)

    cargo = commands.add_parser("cargo-verify")
    cargo.add_argument("--project-root", type=Path, required=True)
    cargo.add_argument("--runtime-root", type=Path, required=True)
    cargo.add_argument("--cargo-command", default="cargo")
    cargo.add_argument("--timeout-seconds", type=int, default=300)

    integration_gate = commands.add_parser("verify-integration")
    integration_gate.add_argument("--db", type=Path, required=True)
    integration_gate.add_argument("--run-id", required=True)
    integration_gate.add_argument("--out-root", required=True)
    integration_gate.add_argument("--project-root", type=Path, required=True)

    cargo_gate = commands.add_parser("verify-cargo")
    cargo_gate.add_argument("--db", type=Path, required=True)
    cargo_gate.add_argument("--run-id", required=True)
    cargo_gate.add_argument("--out-root", required=True)
    cargo_gate.add_argument("--project-root", type=Path, required=True)
    cargo_gate.add_argument("--runtime-root", type=Path, required=True)
    cargo_gate.add_argument("--timeout-seconds", type=int, default=300)

    candidate_compile = commands.add_parser("verify-candidate-compile")
    candidate_compile.add_argument("--db", type=Path, required=True)
    candidate_compile.add_argument("--run-id", required=True)
    candidate_compile.add_argument("--unit-id", required=True)
    candidate_compile.add_argument("--candidate-artifact-id", required=True)
    candidate_compile.add_argument("--candidate-root", type=Path, required=True)
    candidate_compile.add_argument("--quarantine-root", type=Path, required=True)
    candidate_compile.add_argument("--runtime-root", type=Path, required=True)
    candidate_compile.add_argument("--out-root", required=True)
    candidate_compile.add_argument("--timeout-seconds", type=int, default=300)

    candidate_final = commands.add_parser("verify-candidate-final")
    candidate_final.add_argument("--db", type=Path, required=True)
    candidate_final.add_argument("--run-id", required=True)
    candidate_final.add_argument("--unit-id", required=True)
    candidate_final.add_argument("--candidate-artifact-id", required=True)
    candidate_final.add_argument("--out-root", required=True)

    project_gate = commands.add_parser("record-project-gate")
    project_gate.add_argument("--db", type=Path, required=True)
    project_gate.add_argument("--out-root", required=True)
    project_gate.add_argument("--run-id", required=True)
    project_gate.add_argument("--record-id", required=True)
    project_gate.add_argument("--gate-kind", required=True)
    project_gate.add_argument("--source-evidence", type=Path, required=True)

    complete = commands.add_parser("complete")
    complete.add_argument("--db", type=Path, required=True)
    complete.add_argument("--run-id", required=True)
    complete.add_argument("--repo-root", type=Path)
    complete.add_argument("--logical-model", default="GLM-5.1")
    complete.add_argument("--resolved-model", default="zai/glm-5.1")
    complete.add_argument("--timeout-seconds", type=int, default=300)
    complete.add_argument("--preflight-timeout-seconds", type=int, default=60)

    run = commands.add_parser("run-to-completion")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--repo-root", type=Path, required=True)
    _add_completion_runtime_arguments(run)

    status = commands.add_parser("status")
    status.add_argument("--db", type=Path, required=True)
    status.add_argument("--run-id", required=True)
    parsed = parser.parse_args(argv)
    if parsed.command in {"plan", "migrate"}:
        make_values = (
            parsed.make_report, parsed.make_report_sha256,
            parsed.make_report_size_bytes,
        )
        if any(value is not None for value in make_values):
            if parsed.compile_database is not None or any(
                value is None for value in make_values
            ):
                parser.error(
                    "--make-report, --make-report-sha256, and "
                    "--make-report-size-bytes are exclusive with --compile-database"
                )
            try:
                parsed.make_report = BuildInputSelection(
                    MAKE_REPORT_INPUT_KIND, *make_values,
                )
            except ValueError as error:
                parser.error(str(error))
    return parsed


def _add_plan_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--profile", choices=("development", "competition"),
        default="competition",
    )
    parser.add_argument("--compile-database", type=Path)
    parser.add_argument("--make-report", type=Path)
    parser.add_argument("--make-report-sha256")
    parser.add_argument("--make-report-size-bytes", type=int)
    parser.add_argument("--out-root", default="target/project-migration")
    parser.add_argument("--run-id")
    parser.add_argument("--source-commit", default="unversioned")
    parser.add_argument("--max-units", type=int, default=10_000)
    parser.add_argument("--max-concurrency", type=int, default=4)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--context-page-bytes", type=int, default=16_384)
    parser.add_argument("--context-page-tokens", type=int, default=4_096)
    parser.add_argument("--context-group-pages", type=int, default=32)
    parser.add_argument(
        "--build-closure-policy",
        choices=("required", "bounded-source"),
        default="required",
    )


def _add_completion_runtime_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--logical-model", default="GLM-5.1")
    parser.add_argument("--resolved-model", default="zai/glm-5.1")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--preflight-timeout-seconds", type=int, default=60)
    parser.add_argument("--lease-ttl-seconds", type=int, default=900)
    parser.add_argument("--max-cycles", type=int, default=256)


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path.name}")
    return value


def load_array(path: Path) -> list[Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise SystemExit(f"expected JSON array: {path.name}")
    return value


def _reference_args(parser: argparse.ArgumentParser, name: str) -> None:
    parser.add_argument(f"--{name}-path", required=True)
    parser.add_argument(f"--{name}-sha256", required=True)


__all__ = [
    "load_array", "load_next_frontier_bindings", "load_object", "output_binding",
    "parse_args",
]
