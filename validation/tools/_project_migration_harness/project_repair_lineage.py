from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256


def derive_project_repair_diagnostic_lineage(
    diagnostic: Mapping[str, Any], rust_project_ir: Mapping[str, Any],
) -> tuple[str, str]:
    modules = {
        str(value["module_id"]): value
        for value in rust_project_ir.get("modules", [])
        if isinstance(value, Mapping) and isinstance(value.get("module_id"), str)
    }

    def module_anchor(module_id: str) -> dict[str, str]:
        module = modules.get(module_id)
        if module is None:
            return {"kind": "unresolved-module", "identity": module_id}
        return {
            "kind": "module",
            "unit_id": str(module.get("unit_id", "")),
            "rust_path": str(module.get("rust_path", "")),
        }

    entity_anchors: list[dict[str, str]] = []
    for identity in diagnostic.get("entity_ids", []):
        text = str(identity)
        entity_anchors.append(
            module_anchor(text) if text in modules else {
                "kind": "entity", "identity": text,
            }
        )
    module_anchors = [
        module_anchor(str(value))
        for value in diagnostic.get("affected_module_ids", [])
    ]
    projection = {
        "schema_version": 1,
        "diagnostic_code": str(diagnostic.get("code", "")),
        "entity_anchors": sorted(entity_anchors, key=content_sha256),
        "module_anchors": sorted(module_anchors, key=content_sha256),
    }
    projection_sha256 = content_sha256(projection)
    return f"project-repair-lineage-{projection_sha256[:32]}", projection_sha256


__all__ = ["derive_project_repair_diagnostic_lineage"]
