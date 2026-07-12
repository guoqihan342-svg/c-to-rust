"""Validate run-bound clang record-layout provenance in lowering reports."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from validation.tools.native_build_context import resolve_native_build_context


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECORD_TYPE = re.compile(r"^struct [A-Za-z_][A-Za-z0-9_]*$")
_TARGET_FIELDS = (
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


def validate_record_layout_evidence(
    spec: Mapping[str, Any],
    clang_report: Mapping[str, Any],
    repo_root: str | Path,
) -> None:
    """Fail closed when persisted record-layout provenance is inconsistent."""

    lowering = clang_report.get("lowering_report")
    if not isinstance(lowering, Mapping):
        return
    evidence = lowering.get("record_layout_evidence")
    if evidence is None:
        return
    if not isinstance(evidence, Mapping):
        _fail("must be an object")

    status = evidence.get("status")
    if status == "unavailable":
        _validate_unavailable(evidence)
        return
    if status != "captured":
        _fail("status must be captured or unavailable")

    hashes = {
        field: _required_sha(evidence, field)
        for field in (
            "dump_sha256",
            "diagnostics_sha256",
            "compile_arguments_sha256",
            "compile_database_sha256",
        )
    }
    if evidence.get("error") is not None:
        _fail("captured evidence cannot contain an error")

    context = resolve_native_build_context(spec, repo_root)
    if context is None:
        _fail("captured evidence requires a verified native build closure")
    expected_database_sha = context["compile_database"]["sha256"]
    if hashes["compile_database_sha256"] != expected_database_sha:
        _fail("compile_database_sha256 drifted from verified native build closure")

    target = _required_mapping(evidence, "target_abi")
    _validate_target_abi(target, spec, context)
    arguments = evidence.get("arguments")
    if not isinstance(arguments, list) or not all(isinstance(item, str) for item in arguments):
        _fail("arguments must be a string array")
    _validate_arguments(arguments)

    ambiguous = evidence.get("ambiguous_records")
    if not isinstance(ambiguous, list) or not all(
        isinstance(item, str) and _RECORD_TYPE.fullmatch(item) for item in ambiguous
    ):
        _fail("ambiguous_records must contain canonical named struct types")
    if len(set(ambiguous)) != len(ambiguous):
        _fail("ambiguous_records contains duplicates")

    layouts = evidence.get("used_layouts")
    if not isinstance(layouts, list):
        _fail("used_layouts must be an array")
    used_names: set[str] = set()
    for index, layout in enumerate(layouts):
        if not isinstance(layout, Mapping):
            _fail(f"used_layouts[{index}] must be an object")
        record_type = layout.get("record_type")
        if not isinstance(record_type, str) or not _RECORD_TYPE.fullmatch(record_type):
            _fail(f"used_layouts[{index}].record_type is not a canonical named struct")
        if record_type in used_names:
            _fail(f"used_layouts contains duplicate record {record_type}")
        if record_type in ambiguous:
            _fail(f"used layout {record_type} is also marked ambiguous")
        used_names.add(record_type)
        _validate_layout_dimensions(layout, index)
        for field, expected in hashes.items():
            if layout.get(field) != expected:
                _fail(f"used_layouts[{index}].{field} drifted from top-level evidence")
        if layout.get("target_abi") != target:
            _fail(f"used_layouts[{index}].target_abi drifted from top-level evidence")


def _validate_unavailable(evidence: Mapping[str, Any]) -> None:
    for field in (
        "dump_sha256",
        "diagnostics_sha256",
        "compile_arguments_sha256",
        "compile_database_sha256",
        "target_abi",
    ):
        if evidence.get(field) is not None:
            _fail(f"unavailable evidence must set {field} to null")
    for field in ("arguments", "used_layouts", "ambiguous_records"):
        if evidence.get(field) != []:
            _fail(f"unavailable evidence must set {field} to an empty array")
    if not isinstance(evidence.get("error"), str) or not evidence["error"].strip():
        _fail("unavailable evidence requires a non-empty error")


def _validate_arguments(arguments: list[str]) -> None:
    layout_pairs = sum(
        arguments[index : index + 2] == ["-Xclang", "-fdump-record-layouts-complete"]
        for index in range(max(0, len(arguments) - 1))
    )
    if layout_pairs != 1:
        _fail("arguments require exactly one clang record-layout frontend action")
    if "-ast-dump=json" in arguments:
        _fail("record-layout invocation must be isolated from JSON AST dumping")
    if any("\x00" in item or "\r" in item or "\n" in item for item in arguments):
        _fail("arguments contain control characters")


def _validate_target_abi(
    target: Mapping[str, Any],
    spec: Mapping[str, Any],
    context: Mapping[str, Any],
) -> None:
    if set(target) != set(_TARGET_FIELDS):
        _fail("target_abi fields do not match the complete translator ABI profile")
    for field in _TARGET_FIELDS:
        value = target[field]
        if field.endswith("_width") or field.endswith("_align"):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                _fail(f"target_abi.{field} must be a positive integer")
    if target["endianness"] not in {"little", "big"}:
        _fail("target_abi.endianness must be little or big")
    if not isinstance(target["triple_or_abi"], str) or not target["triple_or_abi"].strip():
        _fail("target_abi.triple_or_abi must be non-empty")
    if not isinstance(target["plain_char_signed"], bool):
        _fail("target_abi.plain_char_signed must be boolean")

    declared = dict((spec.get("build_profile") or {}).get("target") or {})
    closure_target = dict(context.get("target_abi") or {})
    closure_target["triple_or_abi"] = closure_target.pop("triple", None)
    for source_name, expected in (("slice spec", declared), ("native build closure", closure_target)):
        for field, value in expected.items():
            if field in target and value not in (None, "", 0) and target[field] != value:
                _fail(f"target_abi.{field} conflicts with {source_name}")


def _validate_layout_dimensions(layout: Mapping[str, Any], index: int) -> None:
    size = layout.get("size_bytes")
    align = layout.get("align_bytes")
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        _fail(f"used_layouts[{index}].size_bytes must be a positive integer")
    if not isinstance(align, int) or isinstance(align, bool) or align <= 0:
        _fail(f"used_layouts[{index}].align_bytes must be a positive integer")
    if align & (align - 1):
        _fail(f"used_layouts[{index}].align_bytes must be a power of two")
    if size % align:
        _fail(f"used_layouts[{index}] size must be a multiple of alignment")


def _required_sha(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not _SHA256.fullmatch(result):
        _fail(f"{field} must be a lowercase sha256")
    return result


def _required_mapping(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    result = value.get(field)
    if not isinstance(result, Mapping):
        _fail(f"{field} must be an object")
    return result


def _fail(message: str) -> None:
    raise SystemExit(f"clang record-layout evidence {message}")


__all__ = ["validate_record_layout_evidence"]
