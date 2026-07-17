from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .build_ir import BUILD_IR_SCHEMA_VERSION
from .make_build_ir_adapter import reproject_make_build_ir
from .make_build_ir_projection import MAKE_RAW_ROLE
from .build_ir_toolchains import make_tool_requests, merge_tool_requests
from .c_toolchain_reopen import C_TOOLCHAIN_RAW_ROLE, reopen_c_toolchain_evidence


def accepted_make_raw_roles(roles: list[Any]) -> bool:
    return roles in (
        [MAKE_RAW_ROLE],
        sorted([MAKE_RAW_ROLE, C_TOOLCHAIN_RAW_ROLE]),
    )


def accepted_make_provenance_role(role: Any) -> bool:
    return role in {MAKE_RAW_ROLE, C_TOOLCHAIN_RAW_ROLE}


def reproject_bound_make_build_ir(
    repo_root: str | Path, payload: Mapping[str, Any],
    attachments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    roles = sorted(attachments)
    if not accepted_make_raw_roles(roles):
        raise ValueError("build_ir_make_raw_fact_refs_invalid")
    references = payload.get("raw_fact_refs")
    if not isinstance(references, list) or len(references) != len(roles):
        raise ValueError("build_ir_make_raw_fact_refs_invalid")
    references_by_role = {
        item.get("role"): item for item in references if isinstance(item, Mapping)
    }
    if set(references_by_role) != set(roles):
        raise ValueError("build_ir_make_raw_fact_refs_invalid")
    toolchain = None
    toolchain_reference = None
    if C_TOOLCHAIN_RAW_ROLE in attachments:
        evidence = attachments[C_TOOLCHAIN_RAW_ROLE]
        if evidence.get("requests") != merge_tool_requests(
            make_tool_requests(attachments[MAKE_RAW_ROLE])
        ):
            raise ValueError("build_ir_c_toolchain_request_drift")
        toolchain = reopen_c_toolchain_evidence(
            evidence,
        )
        toolchain_reference = references_by_role.get(C_TOOLCHAIN_RAW_ROLE)
    schema_version = payload.get("schema_version")
    if schema_version != BUILD_IR_SCHEMA_VERSION:
        raise ValueError("build_ir_schema_version_invalid")
    return reproject_make_build_ir(
        repo_root,
        attachments[MAKE_RAW_ROLE],
        references_by_role[MAKE_RAW_ROLE],
        toolchain,
        toolchain_reference,
    )


__all__ = [
    "accepted_make_provenance_role", "accepted_make_raw_roles",
    "reproject_bound_make_build_ir",
]
