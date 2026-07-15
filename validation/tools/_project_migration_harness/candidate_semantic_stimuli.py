from __future__ import annotations

import hashlib

from .artifacts import content_sha256
from .candidate_semantic_backend_contract import ScalarFunction, ScalarType


HELD_OUT_CASE_COUNT = 32
_SIGNED_ANCHORS = (-3, -1, 0, 1, 3, 7)
_UNSIGNED_ANCHORS = (0, 1, 3, 7, 15, 31)
_TYPE_BITS = {
    "i8": 8, "u8": 8,
    "i16": 16, "u16": 16,
    "i32": 32, "u32": 32,
    "i64": 64, "u64": 64,
}


def held_out_scalar_cases(
    function: ScalarFunction, verifier_nonce: bytes,
) -> tuple[tuple[int, ...], ...]:
    if not isinstance(verifier_nonce, bytes) or len(verifier_nonce) != 32:
        raise ValueError("semantic verifier nonce must be 32 bytes")
    if not function.parameters:
        return ((),)

    rows: list[tuple[int, ...]] = []
    seen: set[tuple[int, ...]] = set()
    for index in range(max(len(_SIGNED_ANCHORS), len(_UNSIGNED_ANCHORS))):
        row = tuple(
            _anchor(kind, index + parameter_index)
            for parameter_index, kind in enumerate(function.parameters)
        )
        if row not in seen:
            rows.append(row)
            seen.add(row)

    counter = 0
    while len(rows) < HELD_OUT_CASE_COUNT and counter < 4096:
        row = tuple(
            _nonce_value(verifier_nonce, counter, parameter_index, kind)
            for parameter_index, kind in enumerate(function.parameters)
        )
        counter += 1
        if row in seen:
            continue
        rows.append(row)
        seen.add(row)
    if len(rows) != HELD_OUT_CASE_COUNT:
        raise ValueError("semantic held-out stimulus space exhausted")
    return tuple(rows)


def stimulus_binding(
    verifier_nonce: bytes, cases: tuple[tuple[int, ...], ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "strategy": "post-candidate-host-nonce-v1",
        "nonce_sha256": hashlib.sha256(verifier_nonce).hexdigest(),
        "cases_sha256": content_sha256([list(row) for row in cases]),
        "case_count": len(cases),
    }


def rust_negative_source(
    function: ScalarFunction, cases: tuple[tuple[int, ...], ...],
) -> str:
    lines = ["#[path = \"candidate.rs\"]", "mod candidate;", "fn main() {"]
    for index, values in enumerate(cases):
        arguments = ", ".join(
            _rust_literal(kind, value)
            for kind, value in zip(function.parameters, values, strict=True)
        )
        expression = f"candidate::{function.symbol}({arguments})"
        if index == 0:
            expression = f"({expression}).wrapping_add(1{function.result.rust_name})"
        cast = "i128" if function.result.signed else "u128"
        lines.append(f'    println!("{index}:{{}}", ({expression}) as {cast});')
    lines.extend(("}", ""))
    return "\n".join(lines)


def _anchor(kind: ScalarType, index: int) -> int:
    values = _SIGNED_ANCHORS if kind.signed else _UNSIGNED_ANCHORS
    return values[index % len(values)]


def _nonce_value(
    nonce: bytes, counter: int, parameter_index: int, kind: ScalarType,
) -> int:
    digest = hashlib.sha256(
        b"candidate-semantic-held-out-v1\0"
        + nonce
        + counter.to_bytes(4, "big")
        + parameter_index.to_bytes(2, "big")
        + kind.rust_name.encode("ascii")
    ).digest()
    raw = int.from_bytes(digest[:8], "big")
    bits = _TYPE_BITS[kind.rust_name]
    if kind.signed:
        bound = min((1 << (bits - 1)) - 1, 4095)
        return raw % (2 * bound + 1) - bound
    bound = min((1 << bits) - 1, 8191)
    return raw % (bound + 1)


def _rust_literal(kind: ScalarType, value: int) -> str:
    return f"{value}{kind.rust_name}"


__all__ = [
    "HELD_OUT_CASE_COUNT", "held_out_scalar_cases", "rust_negative_source",
    "stimulus_binding",
]
