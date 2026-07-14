from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .build_ir_projection import RAW_ROLES, project_build_ir
from .generated_closure import verify_generated_build_closure
from .make_build_ir_adapter import reproject_make_build_ir
from .make_build_ir_projection import MAKE_RAW_ROLE


def accepted_raw_roles(roles: list[Any]) -> bool:
    return roles == sorted(RAW_ROLES) or roles == [MAKE_RAW_ROLE]


def accepted_provenance_role(role: Any) -> bool:
    return role in RAW_ROLES or role == MAKE_RAW_ROLE


def reproject_bound_build_ir(
    repo_root: str | Path, payload: Mapping[str, Any],
    attachments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    roles = sorted(attachments)
    if roles == [MAKE_RAW_ROLE]:
        references = payload.get("raw_fact_refs")
        if not isinstance(references, list) or len(references) != 1:
            raise ValueError("build_ir_make_raw_fact_refs_invalid")
        return reproject_make_build_ir(
            repo_root, attachments[MAKE_RAW_ROLE], references[0],
        )
    if roles != sorted(RAW_ROLES):
        raise ValueError("build_ir_raw_fact_refs_invalid")
    discovery = attachments["discovery"]
    closure = attachments["generated-build-closure"]
    stored = attachments["generated-build-closure-verification"]
    current = verify_generated_build_closure(repo_root, dict(closure))
    if current != stored:
        raise ValueError("build_ir_generated_closure_drift")
    return project_build_ir(
        discovery, closure, stored, list(payload["raw_fact_refs"]),
    )


__all__ = [
    "accepted_provenance_role", "accepted_raw_roles",
    "reproject_bound_build_ir",
]
