from __future__ import annotations

import hashlib

from .artifacts import content_sha256
from .candidate_semantic_backend_contract import ScalarFunction, ScalarType
from .candidate_semantic_integer_literals import source_integer_magnitudes
from .candidate_semantic_scalar_render import rust_scalar_literal


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
    function_source: str | bytes | None = None,
    *, signed_wrapping: bool = False,
) -> tuple[tuple[int, ...], ...]:
    if not isinstance(verifier_nonce, bytes) or len(verifier_nonce) != 32:
        raise ValueError("semantic verifier nonce must be 32 bytes")
    if type(signed_wrapping) is not bool:
        raise ValueError("semantic signed wrapping mode must be boolean")
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

    magnitudes = _prioritized_magnitudes(function_source)
    signed_parameter = any(kind.signed for kind in function.parameters)
    for magnitude in magnitudes[:3]:
        signs = (1, -1) if signed_parameter and magnitude else (1,)
        for sign in signs:
            for delta in (0, -1, 1):
                _append_source_boundary(
                    rows, seen, function.parameters, sign * magnitude + delta,
                )
    for boundary_index in range(4):
        _append_row(rows, seen, tuple(
            _type_boundaries(kind, signed_wrapping)[boundary_index]
            for kind in function.parameters
        ))
    for power_index in range(2):
        _append_row(rows, seen, tuple(
            _type_powers(kind, signed_wrapping)[power_index]
            for kind in function.parameters
        ))

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
    *, signed_wrapping: bool = False,
) -> dict[str, object]:
    if type(signed_wrapping) is not bool:
        raise ValueError("semantic signed wrapping mode must be boolean")
    return {
        "schema_version": 1,
        "strategy": "source-boundaries-plus-host-nonce-v2",
        "nonce_sha256": hashlib.sha256(verifier_nonce).hexdigest(),
        "cases_sha256": content_sha256([list(row) for row in cases]),
        "case_count": len(cases),
        "signed_extrema_enabled": signed_wrapping,
    }


def rust_negative_source(
    function: ScalarFunction, cases: tuple[tuple[int, ...], ...],
) -> str:
    lines = ["#[path = \"candidate.rs\"]", "mod candidate;", "fn main() {"]
    for index, values in enumerate(cases):
        arguments = ", ".join(
            rust_scalar_literal(kind, value)
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


def _prioritized_magnitudes(source: str | bytes | None) -> tuple[int, ...]:
    anchors = set(_SIGNED_ANCHORS) | set(_UNSIGNED_ANCHORS)
    values = source_integer_magnitudes(source)
    return tuple(sorted(
        (value for value in values if value not in anchors),
        key=lambda value: (-value.bit_length(), -value),
    ))


def _append_source_boundary(
    rows: list[tuple[int, ...]], seen: set[tuple[int, ...]],
    parameters: tuple[ScalarType, ...], value: int,
) -> None:
    row = []
    accepted = False
    for index, kind in enumerate(parameters):
        lower, upper = _type_range(kind)
        if lower <= value <= upper:
            row.append(value)
            accepted = True
        else:
            row.append(_anchor(kind, index))
    if accepted:
        _append_row(rows, seen, tuple(row))


def _append_row(
    rows: list[tuple[int, ...]], seen: set[tuple[int, ...]], row: tuple[int, ...],
) -> None:
    if len(rows) < HELD_OUT_CASE_COUNT and row not in seen:
        rows.append(row)
        seen.add(row)


def _type_range(kind: ScalarType) -> tuple[int, int]:
    bits = _TYPE_BITS[kind.rust_name]
    if kind.signed:
        return -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    return 0, (1 << bits) - 1


def _type_boundaries(
    kind: ScalarType, signed_wrapping: bool,
) -> tuple[int, int, int, int]:
    lower, upper = _type_range(kind)
    if kind.signed and not signed_wrapping:
        bits = _TYPE_BITS[kind.rust_name]
        bound = min(4095, (1 << max(1, bits - 3)) - 1)
        return -bound, -1, 1, bound
    return lower, lower + 1, upper - 1, upper


def _type_powers(kind: ScalarType, signed_wrapping: bool) -> tuple[int, int]:
    bits = _TYPE_BITS[kind.rust_name]
    if kind.signed and not signed_wrapping:
        return 1 << min(12, max(1, bits // 4)), 1 << min(12, bits // 2)
    return 1 << max(1, bits // 2), 1 << (bits - (2 if kind.signed else 1))


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


__all__ = [
    "HELD_OUT_CASE_COUNT", "held_out_scalar_cases", "rust_negative_source",
    "stimulus_binding",
]
