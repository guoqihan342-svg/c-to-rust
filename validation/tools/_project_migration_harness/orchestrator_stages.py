from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import re
from typing import Any

from .artifacts import content_sha256, write_json_artifact


_ERROR_CODE = re.compile(r"[a-z][a-z0-9_]{0,127}\Z", re.ASCII)


def run_stage(
    name: str,
    operation: Callable[[], dict[str, Any]],
) -> dict[str, Any] | None:
    try:
        return operation()
    except (OSError, UnicodeError, ValueError):
        _ = name
        return None


def contract_error(stage: str, error: BaseException) -> dict[str, Any]:
    message = str(error)
    if isinstance(error, ValueError) and _ERROR_CODE.fullmatch(message) is not None:
        kind = message
    elif isinstance(error, UnicodeError):
        kind = f"{stage}_unicode_error"
    elif isinstance(error, OSError):
        kind = f"{stage}_io_error"
    elif isinstance(error, TypeError):
        kind = f"{stage}_type_error"
    else:
        kind = f"{stage}_contract_error"
    return {
        "schema_version": 1,
        "status": "blocked",
        "stage": stage,
        "kind": kind,
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }


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


__all__ = ["blocked_plan", "contract_error", "run_stage"]
