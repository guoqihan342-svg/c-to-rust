from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .native_link_context import (
    model_native_link_context,
    validate_native_link_context,
)
from .native_link_model import (
    NATIVE_LINK_RESPONSE_KIND,
    build_native_link_candidate,
    validate_native_link_proposal,
)
from .rust_project_ir import bind_native_link_candidate


NATIVE_LINK_PLAN_SECTION = "native_link_plans"
_PLAN_SET_ID = re.compile(r"native-link-plan-set-[0-9a-f]{24}\Z")


def normalize_native_link_operation(value: Mapping[str, Any]) -> dict[str, Any]:
    if (
        set(value) != {"section", "action", "record_id", "changes"}
        or value.get("section") != NATIVE_LINK_PLAN_SECTION
        or value.get("action") != "bind"
        or not isinstance(value.get("record_id"), str)
        or _PLAN_SET_ID.fullmatch(value["record_id"]) is None
    ):
        raise ValueError("native link repair operation fields are invalid")
    changes = value.get("changes")
    if not isinstance(changes, Mapping) or set(changes) != {"proposals"}:
        raise ValueError("native link repair proposals are invalid")
    proposals = changes.get("proposals")
    if not isinstance(proposals, list) or not proposals:
        raise ValueError("native link repair proposals are invalid")
    normalized = sorted(
        (validate_native_link_proposal(item) for item in proposals),
        key=lambda item: item["requirement_id"],
    )
    return {
        "section": NATIVE_LINK_PLAN_SECTION,
        "action": "bind",
        "record_id": value["record_id"],
        "changes": {"proposals": normalized},
    }


def apply_native_link_operation(
    base_ir: Mapping[str, Any], context: Mapping[str, Any],
    operations: list[Mapping[str, Any]],
    native_link_context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    planning = context.get("native_link_planning")
    if (
        context.get("schema_version") != 3
        or not isinstance(planning, Mapping)
        or len(operations) != 1
        or native_link_context is None
    ):
        raise ValueError("native link repair binding is unavailable")
    validate_native_link_context(native_link_context)
    operation = operations[0]
    if (
        operation.get("section") != NATIVE_LINK_PLAN_SECTION
        or operation.get("record_id") != planning.get("plan_set_id")
        or model_native_link_context(native_link_context)
        != planning.get("context")
        or base_ir["native_link_requirements"]
        != native_link_context["requirements"]
        or base_ir["native_link_plans"]
    ):
        raise ValueError("native link repair changed its host binding")
    response = {
        "schema_version": 1,
        "artifact_kind": NATIVE_LINK_RESPONSE_KIND,
        "context_sha256": native_link_context["context_sha256"],
        "proposals": operation["changes"]["proposals"],
    }
    candidate = build_native_link_candidate(native_link_context, response)
    return bind_native_link_candidate(base_ir, native_link_context, candidate)


__all__ = [
    "NATIVE_LINK_PLAN_SECTION", "apply_native_link_operation",
    "normalize_native_link_operation",
]
