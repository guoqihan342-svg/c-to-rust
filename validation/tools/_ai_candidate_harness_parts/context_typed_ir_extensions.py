from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TARGET_ABI_FIELDS = (
    "triple_or_abi",
    "endianness",
    "char_width",
    "short_width",
    "int_width",
    "long_width",
    "long_long_width",
    "pointer_width",
    "char_align",
    "short_align",
    "int_align",
    "long_align",
    "long_long_align",
    "pointer_align",
    "plain_char_signed",
)


def validate_record_memset(
    payload: dict[str, Any],
    issues: list[str],
    *,
    budget: list[int],
    depth: int,
    validate_expression: Callable[..., None],
    append_issue: Callable[[list[str], str], None],
) -> None:
    validate_expression(
        payload.get("destination"), issues, budget=budget, depth=depth + 1
    )
    byte = payload.get("byte")
    write_len = payload.get("write_len_bytes")
    layout = record_layout_summary(payload.get("layout"))
    if not _integer(byte, minimum=0, maximum=255):
        append_issue(issues, "record_memset_byte_invalid")
    if not _integer(write_len, minimum=1):
        append_issue(issues, "record_memset_write_len_invalid")
    if not layout:
        append_issue(issues, "record_memset_layout_invalid")
    elif write_len != layout["size_bytes"]:
        append_issue(issues, "record_memset_layout_size_mismatch")


def summarize_record_memset(
    payload: dict[str, Any],
    *,
    budget: list[int],
    depth: int,
    summarize_expression: Callable[..., Any],
) -> dict[str, Any]:
    return _without_empty(
        {
            "kind": "RecordMemset",
            "destination": summarize_expression(
                payload.get("destination"), budget=budget, depth=depth + 1
            ),
            "byte": payload.get("byte"),
            "write_len_bytes": payload.get("write_len_bytes"),
            "layout": record_layout_summary(payload.get("layout")),
        }
    )


def validate_mutable_void_pointer_address(
    payload: dict[str, Any],
    issues: list[str],
    *,
    budget: list[int],
    depth: int,
    validate_expression: Callable[..., None],
    append_issue: Callable[[list[str], str], None],
) -> None:
    validate_expression(payload.get("operand"), issues, budget=budget, depth=depth + 1)
    source = pointer_contract_summary(payload.get("source_pointer"))
    target = pointer_contract_summary(payload.get("target"))
    if not _mutable_pointer_to(source, "integer"):
        append_issue(issues, "mutable_void_address_source_pointer_invalid")
    if not _mutable_pointer_to(target, "void"):
        append_issue(issues, "mutable_void_address_target_pointer_invalid")


def summarize_mutable_void_pointer_address(
    payload: dict[str, Any],
    *,
    budget: list[int],
    depth: int,
    summarize_expression: Callable[..., Any],
) -> dict[str, Any]:
    return _without_empty(
        {
            "kind": "mutable_void_pointer_address",
            "operand": summarize_expression(
                payload.get("operand"), budget=budget, depth=depth + 1
            ),
            "source_pointer": pointer_contract_summary(payload.get("source_pointer")),
            "target_pointer": pointer_contract_summary(payload.get("target")),
        }
    )


def record_layout_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    record_type = value.get("record_type")
    size = value.get("size_bytes")
    align = value.get("align_bytes")
    sha_fields = (
        "compile_arguments_sha256",
        "compile_database_sha256",
        "diagnostics_sha256",
        "dump_sha256",
    )
    target = target_abi_summary(value.get("target_abi"))
    if (
        not isinstance(record_type, str)
        or not record_type.strip()
        or not _integer(size, minimum=1)
        or not _integer(align, minimum=1)
        or not all(_sha256(value.get(field)) for field in sha_fields)
        or not target
    ):
        return {}
    return {
        "record_type": record_type,
        "size_bytes": size,
        "align_bytes": align,
        **{field: value[field] for field in sha_fields},
        "target_abi": target,
    }


def target_abi_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(TARGET_ABI_FIELDS):
        return {}
    triple = value.get("triple_or_abi")
    endianness = value.get("endianness")
    pointer_width = value.get("pointer_width")
    if (
        not isinstance(triple, str)
        or not triple.strip()
        or endianness not in {"little", "big"}
        or not _integer(pointer_width, minimum=1)
    ):
        return {}
    integer_fields = (
        "char_width",
        "short_width",
        "int_width",
        "long_width",
        "long_long_width",
        "pointer_width",
        "char_align",
        "short_align",
        "int_align",
        "long_align",
        "long_long_align",
        "pointer_align",
    )
    if not all(_integer(value.get(field), minimum=1) for field in integer_fields):
        return {}
    if not isinstance(value.get("plain_char_signed"), bool):
        return {}
    return {field: value[field] for field in TARGET_ABI_FIELDS}


def pointer_contract_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    kind = value.get("kind")
    pointer = kind.get("Pointer") if isinstance(kind, dict) else None
    pointee = pointer.get("pointee") if isinstance(pointer, dict) else None
    if not isinstance(pointee, dict):
        return {}
    pointee_kind = pointee.get("kind")
    if isinstance(pointee_kind, dict) and isinstance(pointee_kind.get("Integer"), dict):
        integer = pointee_kind["Integer"]
        width = integer.get("width")
        if not isinstance(integer.get("signed"), bool) or not _integer(
            width, minimum=1
        ):
            return {}
        if pointee.get("width_bits") != width:
            return {}
        pointee_summary = {
            **type_identity(pointee),
            "kind": "integer",
            "signed": integer["signed"],
            "width_bits": width,
        }
    elif pointee_kind == "Void":
        pointee_summary = {**type_identity(pointee), "kind": "void"}
    else:
        return {}
    return {
        **type_identity(value),
        "kind": "pointer",
        "pointee": pointee_summary,
    }


def type_identity(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value[key]
        for key in ("spelled", "canonical", "is_const")
        if isinstance(value.get(key), (str, bool))
    }


def _mutable_pointer_to(value: dict[str, Any], pointee_kind: str) -> bool:
    pointee = value.get("pointee") if isinstance(value, dict) else None
    return (
        value.get("kind") == "pointer"
        and value.get("is_const") is False
        and isinstance(pointee, dict)
        and pointee.get("kind") == pointee_kind
        and pointee.get("is_const") is False
    )


def _integer(value: Any, *, minimum: int, maximum: int | None = None) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= minimum
        and (maximum is None or value <= maximum)
    )


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _without_empty(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item not in (None, {}, [])}


__all__ = [
    "summarize_mutable_void_pointer_address",
    "summarize_record_memset",
    "validate_mutable_void_pointer_address",
    "validate_record_memset",
]
