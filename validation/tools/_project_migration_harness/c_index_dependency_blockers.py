from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def dependency_blocker(
    unit: Mapping[str, Any],
    kind: str,
    offset: int,
    *,
    source_path: str | None = None,
    source_sha256: str | None = None,
    directive_sha256: str | None = None,
) -> dict[str, Any]:
    result = {
        "unit_id": str(unit["unit_id"]),
        "kind": kind,
        "byte_offset": int(offset),
        "source_path": source_path or str(unit["path"]),
        "source_sha256": source_sha256 or str(unit["sha256"]),
    }
    if directive_sha256 is not None:
        result["directive_sha256"] = directive_sha256
    return result


__all__ = ["dependency_blocker"]
