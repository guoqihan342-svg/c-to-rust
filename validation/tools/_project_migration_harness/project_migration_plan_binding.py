from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .context_frontier_reference import context_frontier_reference
from .ledger_schema import SCHEMA_VERSION as LEDGER_SCHEMA_VERSION
from .project_cli_runtime import target_path


def load_next_frontier_bindings(
    args: argparse.Namespace, *, harness_root: Path,
) -> tuple[Any, ...]:
    root = harness_root.resolve(strict=True)
    plan_path = target_path(args.plan, "plan", repo_root=root, must_exist=True)
    plan = _load_object(plan_path)
    ledger_value, out_root_rel = output_binding(
        plan, plan_path=plan_path, harness_root=root,
    )

    def artifact(name: str) -> dict[str, Any]:
        artifacts = plan.get("artifacts")
        value = artifacts.get(name) if isinstance(artifacts, dict) else None
        if not isinstance(value, dict):
            raise SystemExit(f"plan {name} artifact binding is missing")
        try:
            local = value.get("path")
            if not isinstance(local, str):
                raise ValueError("plan artifact path is not a string")
            path = (out_root_rel / PurePosixPath(local)).as_posix()
            return context_frontier_reference({**value, "path": path})
        except ValueError as error:
            raise SystemExit(f"plan {name} artifact binding is invalid") from error

    references = {name: artifact(name) for name in ("portfolio", "context_pages")}
    latest_path = target_path(
        args.latest_dag_path, "latest-dag", repo_root=root, must_exist=True,
    )
    latest_reference = context_frontier_reference({
        "path": latest_path.relative_to(root).as_posix(),
        "sha256": args.latest_dag_sha256,
        "size_bytes": args.latest_dag_size_bytes,
    })
    return (
        plan, ledger_value, out_root_rel, references, latest_path, latest_reference,
    )


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


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path.name}")
    return value


__all__ = ["load_next_frontier_bindings", "output_binding"]
