from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .build_ir_projection import HOST_BOUND_RAW_ROLES, RAW_ROLES, project_build_ir
from .build_ir_tool_selections import bound_standard_tool_requests
from .build_ir_toolchains import merge_tool_requests
from .c_toolchain_reopen import C_TOOLCHAIN_RAW_ROLE, reopen_c_toolchain_evidence
from .generated_closure import verify_generated_build_closure
from .make_build_ir_reopen import (
    accepted_make_provenance_role,
    accepted_make_raw_roles,
    reproject_bound_make_build_ir,
)


def accepted_raw_roles(roles: list[Any]) -> bool:
    return roles in (sorted(RAW_ROLES), sorted(HOST_BOUND_RAW_ROLES)) or (
        accepted_make_raw_roles(roles)
    )


def accepted_provenance_role(role: Any) -> bool:
    return (
        role in HOST_BOUND_RAW_ROLES or accepted_make_provenance_role(role)
    )


def reproject_bound_build_ir(
    repo_root: str | Path,
    payload: Mapping[str, Any],
    attachments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    roles = sorted(attachments)
    if accepted_make_raw_roles(roles):
        return reproject_bound_make_build_ir(repo_root, payload, attachments)
    if roles not in (sorted(RAW_ROLES), sorted(HOST_BOUND_RAW_ROLES)):
        raise ValueError("build_ir_raw_fact_refs_invalid")
    discovery = attachments["discovery"]
    closure = attachments["generated-build-closure"]
    stored = attachments["generated-build-closure-verification"]
    current = verify_generated_build_closure(repo_root, dict(closure))
    if current != stored:
        raise ValueError("build_ir_generated_closure_drift")
    toolchain = None
    if C_TOOLCHAIN_RAW_ROLE in attachments:
        evidence = attachments[C_TOOLCHAIN_RAW_ROLE]
        expected_requests = merge_tool_requests(
            bound_standard_tool_requests(repo_root, discovery, closure)
        )
        if evidence.get("requests") != expected_requests:
            raise ValueError("build_ir_c_toolchain_request_drift")
        toolchain = reopen_c_toolchain_evidence(
            evidence,
        )
    return project_build_ir(
        discovery,
        closure,
        stored,
        list(payload["raw_fact_refs"]),
        toolchain,
    )


__all__ = [
    "accepted_provenance_role",
    "accepted_raw_roles",
    "reproject_bound_build_ir",
]
