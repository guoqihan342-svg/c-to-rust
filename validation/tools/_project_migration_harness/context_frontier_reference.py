from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import checked_relative_path


def context_frontier_reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("context frontier reference is invalid")
    path = checked_relative_path(str(value.get("path", "")))
    digest, size = value.get("sha256"), value.get("size_bytes")
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
    ):
        raise ValueError("context frontier reference binding is invalid")
    return {"path": path, "sha256": digest, "size_bytes": size}


__all__ = ["context_frontier_reference"]
