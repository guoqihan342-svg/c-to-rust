from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .rust_cargo_target_link_trace import parse_rust_cargo_target_link_trace


def parse_required_target_link_trace(
    data: bytes, expectation: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not expectation.get("targets"):
        return None
    try:
        return parse_rust_cargo_target_link_trace(data)
    except (TypeError, ValueError):
        return None


__all__ = ["parse_required_target_link_trace"]
