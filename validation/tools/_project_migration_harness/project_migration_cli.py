from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any, Sequence

from .ledger_schema import SCHEMA_VERSION as LEDGER_SCHEMA_VERSION


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generic whole-project, AI-first C-to-Rust migration orchestration."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--repo-root", type=Path, required=True)
    plan.add_argument("--compile-database", type=Path)
    plan.add_argument("--out-root", default="target/project-migration")
    plan.add_argument("--run-id")
    plan.add_argument("--source-commit", default="unversioned")
    plan.add_argument("--max-units", type=int, default=10_000)
    plan.add_argument("--max-concurrency", type=int, default=4)
    plan.add_argument("--max-attempts", type=int, default=5)
    plan.add_argument("--context-page-bytes", type=int, default=16_384)
    plan.add_argument("--context-page-tokens", type=int, default=4_096)
    plan.add_argument("--context-group-pages", type=int, default=32)
    plan.add_argument(
        "--build-closure-policy",
        choices=("required", "bounded-source"),
        default="required",
    )

    dispatch = commands.add_parser("dispatch")
    dispatch.add_argument("--plan", type=Path, required=True)
    dispatch.add_argument("--lease-ttl-seconds", type=int, default=900)

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
    complete.add_argument("--logical-model", default="GLM-5.1")
    complete.add_argument("--resolved-model", default="zai/glm-5.1")
    complete.add_argument("--timeout-seconds", type=int, default=300)
    complete.add_argument("--preflight-timeout-seconds", type=int, default=60)

    status = commands.add_parser("status")
    status.add_argument("--db", type=Path, required=True)
    status.add_argument("--run-id", required=True)
    return parser.parse_args(argv)


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


def output_binding(
    plan: dict[str, Any], *, plan_path: Path, harness_root: Path,
) -> tuple[str, PurePosixPath]:
    ledger = plan.get("ledger")
    path = ledger.get("path") if isinstance(ledger, dict) else None
    if (
        not isinstance(path, str)
        or not isinstance(ledger, dict)
        or set(ledger) != {"path", "resume_policy", "schema_version", "status"}
        or ledger.get("schema_version") != LEDGER_SCHEMA_VERSION
        or ledger.get("status") != "bound"
        or ledger.get("resume_policy") != "create_or_verify_immutable_inputs"
    ):
        raise SystemExit("plan ledger binding is invalid")
    ledger_path = PurePosixPath(path)
    if (
        not path
        or "\\" in path
        or ledger_path.is_absolute()
        or ".." in ledger_path.parts
        or ledger_path.as_posix() != path
        or ledger_path.name != "project-migration.sqlite3"
        or ledger_path.parent.name != "state"
    ):
        raise SystemExit("plan ledger.path is not canonical")
    root = harness_root.resolve(strict=True)
    resolved_plan = plan_path.resolve(strict=True)
    try:
        relative_plan = PurePosixPath(resolved_plan.relative_to(root).as_posix())
    except ValueError as error:
        raise SystemExit("plan must stay inside the harness repository") from error
    if (
        relative_plan.name != "project-migration-plan.json"
        or not relative_plan.parts
        or relative_plan.parts[0] != "target"
        or relative_plan.parent == PurePosixPath("target")
    ):
        raise SystemExit("plan must be a generated target artifact")
    out_root = relative_plan.parent
    if ledger_path != out_root / "state" / "project-migration.sqlite3":
        raise SystemExit("plan ledger.path is not bound to the plan output root")
    portfolio = plan.get("portfolio")
    if (
        plan.get("schema_version") != 1
        or plan.get("status") != "planned"
        or not isinstance(plan.get("run_id"), str)
        or not isinstance(portfolio, dict)
        or portfolio.get("run_id") != plan.get("run_id")
        or portfolio.get("status") != "planned"
    ):
        raise SystemExit("plan orchestration binding is invalid")
    return path, out_root


def _reference_args(parser: argparse.ArgumentParser, name: str) -> None:
    parser.add_argument(f"--{name}-path", required=True)
    parser.add_argument(f"--{name}-sha256", required=True)


__all__ = ["load_array", "load_object", "output_binding", "parse_args"]
