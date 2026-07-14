from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import write_json_artifact
from .native_link_context import build_native_link_context


def prepare_native_link_plan(
    build_ir: Mapping[str, Any], build_ir_reference: Mapping[str, Any], *,
    profile: str, output: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    context = build_native_link_context(
        build_ir, build_ir_reference, profile=profile,
    )
    reference = write_json_artifact(
        output, "plan/native-link-context.json", context,
    )
    return context, reference


def native_link_execution_summary(
    context: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "native_link_planning_status": context["status"],
        "native_link_requirement_count": context["requirement_count"],
        "native_link_dependency_count": context["dependency_count"],
    }


__all__ = ["native_link_execution_summary", "prepare_native_link_plan"]
