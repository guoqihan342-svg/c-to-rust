from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .make_build_ir_adapter import reproject_make_build_ir
from .make_build_ir_projection import MAKE_RAW_ROLE


def accepted_make_raw_roles(roles: list[Any]) -> bool:
    return roles == [MAKE_RAW_ROLE]


def accepted_make_provenance_role(role: Any) -> bool:
    return role == MAKE_RAW_ROLE


def reproject_bound_make_build_ir(
    repo_root: str | Path, payload: Mapping[str, Any],
    attachments: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    roles = sorted(attachments)
    if not accepted_make_raw_roles(roles):
        raise ValueError("build_ir_make_raw_fact_refs_invalid")
    references = payload.get("raw_fact_refs")
    if not isinstance(references, list) or len(references) != 1:
        raise ValueError("build_ir_make_raw_fact_refs_invalid")
    return reproject_make_build_ir(
        repo_root, attachments[MAKE_RAW_ROLE], references[0],
    )


__all__ = [
    "accepted_make_provenance_role", "accepted_make_raw_roles",
    "reproject_bound_make_build_ir",
]
