from __future__ import annotations

from typing import Any

from .context_compiler_headers import (
    compiler_header_declaration,
    is_compiler_header_candidate,
)


def compiler_header_declaration_status(
    boundary_payload: dict[str, Any],
    declared: list[Any],
    context: dict[str, Any],
) -> str:
    candidates = [item for item in declared if is_compiler_header_candidate(item)]
    actual = context.get("declarations", [])
    if not isinstance(actual, list):
        return "invalid"
    expected = []
    signatures = boundary_payload.get("signatures")
    try:
        for item in candidates:
            if not isinstance(item, dict):
                return "invalid"
            expected.append(compiler_header_declaration(item, signatures))
    except ValueError:
        return "invalid"
    if actual != expected:
        return "invalid"
    if expected and context.get("status") not in {"bound", "partial"}:
        return "incomplete"

    declaration_names = {item["callee"] for item in expected}
    blocks = context.get("blocks", [])
    if not isinstance(blocks, list):
        return "invalid"
    if any(
        isinstance(item, dict) and item.get("callee") in declaration_names
        for item in blocks
    ):
        return "invalid"
    blocked = context.get("blocked", [])
    if not isinstance(blocked, list):
        return "invalid"
    if any(
        isinstance(item, dict) and item.get("callee") in declaration_names
        for item in blocked
    ):
        return "incomplete"
    return "ready"


__all__ = ["compiler_header_declaration_status"]
