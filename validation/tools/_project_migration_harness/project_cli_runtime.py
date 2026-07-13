from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_facts import is_linklike
from .ledger import ProjectLedger


def reference(path: str, sha256: str) -> dict[str, str]:
    return {"path": path, "sha256": sha256}


def repo_relative(value: str, *, repo_root: Path) -> Path:
    target = target_path(value, "out-root", repo_root=repo_root)
    target.mkdir(parents=True, exist_ok=True)
    return target


def ledger(value: str | Path, *, repo_root: Path) -> ProjectLedger:
    return ProjectLedger(ledger_path(value, repo_root=repo_root))


def ledger_path(value: str | Path, *, repo_root: Path) -> Path:
    target = target_path(value, "ledger", repo_root=repo_root)
    if target.name != "project-migration.sqlite3" or target.parent.name != "state":
        raise SystemExit("ledger must use the fixed project migration state path")
    return target


def target_path(
    value: str | Path, label: str, *, repo_root: Path, must_exist: bool = False,
) -> Path:
    if not isinstance(value, (str, Path)) or not str(value):
        raise SystemExit(f"{label} path is missing")
    relative = Path(value)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or relative.parts[0] != "target"
    ):
        raise SystemExit(f"{label} must stay under the repository target directory")
    root = repo_root.resolve(strict=True)
    current = root
    for part in relative.parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise SystemExit(f"{label} contains a linked path component")
    try:
        target = current.resolve(strict=must_exist)
        target.relative_to(root)
    except (OSError, ValueError) as error:
        raise SystemExit(f"{label} escapes the repository") from error
    return target


def target_relative(value: str | Path, label: str, *, repo_root: Path) -> str:
    target = target_path(value, label, repo_root=repo_root)
    return target.relative_to(repo_root.resolve(strict=True)).as_posix()


def exit_code(result: dict[str, Any]) -> int:
    successful = {
        "completed", "dispatched", "integrated", "last-good", "materialized",
        "passed", "planned", "ready", "recorded", "waiting",
    }
    if result.get("status") not in successful:
        return 1
    if result.get("gate_status") not in {None, "passed"}:
        return 1
    if result.get("next_status") in {
        "blocked", "failed", "manual-reconcile", "rejected", "retry-ready",
    }:
        return 1
    return 0


def display_result(command: str, result: dict[str, Any]) -> dict[str, Any]:
    portfolio = result.get("portfolio")
    if command != "plan" or not isinstance(portfolio, dict):
        return result
    assignments = portfolio.get("assignments", [])
    units = portfolio.get("ledger_units", [])
    blocked = portfolio.get("blocked_groups", [])
    artifacts = result.get("artifacts")
    full_payload = artifacts.get("portfolio") if isinstance(artifacts, dict) else None
    summary = {
        "schema_version": portfolio.get("schema_version"),
        "status": portfolio.get("status"),
        "run_id": portfolio.get("run_id"),
        "dag_sha256": portfolio.get("dag_sha256"),
        "plan_sha256": portfolio.get("plan_sha256"),
        "assignment_count": len(assignments) if isinstance(assignments, list) else None,
        "unit_count": len(units) if isinstance(units, list) else None,
        "blocked_group_count": len(blocked) if isinstance(blocked, list) else None,
        "full_payload": full_payload,
    }
    return {**result, "portfolio": summary}


__all__ = [
    "display_result", "exit_code", "ledger", "ledger_path", "reference", "repo_relative",
    "target_path", "target_relative",
]
