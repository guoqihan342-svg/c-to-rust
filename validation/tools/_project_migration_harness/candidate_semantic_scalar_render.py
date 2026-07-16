from __future__ import annotations

import json

from .candidate_semantic_backend_contract import ScalarType


def rust_scalar_literal(kind: ScalarType, value: int) -> str:
    bits = int(kind.rust_name[1:])
    if kind.signed and value == -(1 << (bits - 1)):
        return f"{kind.rust_name}::MIN"
    return f"{value}{kind.rust_name}"


def c_scalar_literal(kind: ScalarType, value: int) -> str:
    bits = int(kind.rust_name[1:])
    if kind.signed and value == -(1 << (bits - 1)):
        upper = (1 << (bits - 1)) - 1
        suffix = "LL" if bits == 64 else ""
        return f"(-{upper}{suffix} - 1{suffix})"
    return str(value)


def rust_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


__all__ = ["c_scalar_literal", "rust_scalar_literal", "rust_string"]
