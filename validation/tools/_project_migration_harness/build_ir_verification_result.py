from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .build_ir_external_dependencies import NATIVE_DEPENDENCY_KIND


def build_ir_verification_result(
    payload: Mapping[str, Any] | None,
    reference: Mapping[str, Any],
    blockers: list[dict[str, Any]],
    verified_bindings: int,
) -> dict[str, Any]:
    claim = payload.get("claim_boundary") if payload else {}
    if not isinstance(claim, Mapping):
        claim = {}
    dependencies = payload.get("external_dependencies", []) if payload else []
    unresolved_native = sum(
        isinstance(item, Mapping) and item.get("kind") == NATIVE_DEPENDENCY_KIND
        for item in dependencies
    )
    return {
        "schema_version": 1,
        "status": "verified" if not blockers else "blocked",
        "build_ir_sha256": reference.get("sha256"),
        "semantic_sha256": payload.get("semantic_sha256") if payload else None,
        "toolchain_profile": claim.get("toolchain_profile"),
        "native_link_config_resolved": not unresolved_native if payload else None,
        "unresolved_native_dependency_count": unresolved_native if payload else None,
        "verified_binding_count": verified_bindings,
        "blockers": blockers,
    }


__all__ = ["build_ir_verification_result"]
