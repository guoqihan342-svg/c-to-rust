from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .artifacts import content_sha256, write_json_artifact


def run_stage(
    name: str,
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        return operation()
    except (OSError, UnicodeError, ValueError):
        _ = name
        return None


def blocked_plan(
    output: Path,
    artifacts: dict[str, dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    result = {
        "schema_version": 1,
        "status": "blocked",
        "blockers": [reason],
        "artifacts": artifacts,
        "execution": {"model_launched": False, "cargo_executed": False},
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "proof_class": "project-plan-only",
        },
    }
    result["plan_sha256"] = content_sha256(result)
    write_json_artifact(output, "project-migration-plan.json", result)
    return result


__all__ = ["blocked_plan", "run_stage"]
