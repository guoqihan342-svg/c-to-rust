from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .native_link_context import (
    model_native_link_context,
    validate_model_native_link_context,
    validate_native_link_context,
)


NATIVE_LINK_FIELD = "native_link_planning"


def native_link_planning(
    rust_project_ir: Mapping[str, Any], diagnostic: Mapping[str, Any],
    native_link_context: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if diagnostic.get("code") != "rust_project_ir_native_link_plan_missing":
        if native_link_context is not None:
            raise ValueError("native link context is unexpected for this repair")
        return None
    if native_link_context is None:
        raise ValueError("native link planning context is missing")
    validate_native_link_context(native_link_context)
    model_context = model_native_link_context(native_link_context)
    if (
        model_context["requirements"]
        != rust_project_ir["native_link_requirements"]
        or rust_project_ir["native_link_plans"]
        or len(diagnostic.get("entity_ids", [])) != 1
        or diagnostic.get("affected_module_ids") != []
    ):
        raise ValueError("native link planning context does not bind the repair")
    return {
        "plan_set_id": diagnostic["entity_ids"][0],
        "context": model_context,
    }


def validate_native_link_planning(value: Mapping[str, Any]) -> None:
    planning = value.get(NATIVE_LINK_FIELD)
    diagnostic = value.get("diagnostic")
    if (
        not isinstance(planning, Mapping)
        or set(planning) != {"plan_set_id", "context"}
        or not isinstance(diagnostic, Mapping)
        or diagnostic.get("code")
        != "rust_project_ir_native_link_plan_missing"
        or diagnostic.get("entity_ids") != [planning.get("plan_set_id")]
        or diagnostic.get("affected_module_ids") != []
    ):
        raise ValueError("native link planning repair binding is invalid")
    validate_model_native_link_context(planning.get("context"))


def context_allowed_output(native: bool) -> dict[str, Any]:
    return {
        "kind": "native-link-plan-set",
        "sections": ["native_link_plans"],
        "max_operations": 1,
        "may_change_evidence": False,
        "may_change_candidate_sources": False,
        "may_generate_glue": False,
    } if native else {
        "kind": "bounded-rust-project-ir-operations",
        "sections": [
            "modules", "public_api", "shared_types", "global_ownership",
            "initialization", "ffi_boundaries", "cfgs", "features",
            "unsafe_obligations",
        ],
        "max_operations": 32,
        "may_change_evidence": False,
        "may_change_candidate_sources": False,
        "may_generate_glue": False,
    }


__all__ = [
    "NATIVE_LINK_FIELD", "context_allowed_output", "native_link_planning",
    "validate_native_link_planning",
]
