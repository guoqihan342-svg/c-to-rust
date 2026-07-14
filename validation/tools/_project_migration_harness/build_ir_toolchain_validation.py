from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def validate_toolchain_references(
    units: list[Mapping[str, Any]],
    targets: list[Mapping[str, Any]],
    abi: list[Mapping[str, Any]],
    toolchain_ids: list[str],
    *,
    require_target_refs: bool,
) -> None:
    identifiers = set(toolchain_ids)
    if identifiers:
        for item in [*units, *abi]:
            if item.get("toolchain_id") not in identifiers:
                raise ValueError("build_ir_toolchain_reference_invalid")
    for target in targets:
        if (
            require_target_refs
            and target.get("kind") in {"object", "link", "archive"}
            and "toolchain_id" not in target
        ):
            raise ValueError("build_ir_toolchain_reference_invalid")
        if "toolchain_id" in target:
            toolchain_id = target.get("toolchain_id")
            if not isinstance(toolchain_id, str) or toolchain_id not in identifiers:
                raise ValueError("build_ir_toolchain_reference_invalid")
        auxiliary = target.get("auxiliary_toolchain_ids", [])
        if (
            not isinstance(auxiliary, list)
            or any(not isinstance(item, str) for item in auxiliary)
            or auxiliary != sorted(set(auxiliary))
            or any(item not in identifiers for item in auxiliary)
        ):
            raise ValueError("build_ir_toolchain_reference_invalid")


__all__ = ["validate_toolchain_references"]
