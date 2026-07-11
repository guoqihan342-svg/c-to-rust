from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from .context_security import redact_text, sha256_bytes


MAX_CARRIER_SOURCE_BYTES = 32_000
SUPPORTED_CARRIER_KIND = "exact_source_fragment_wrapper"
SUPPORTED_FRAGMENT_HASH_MODE = "normalized_line_span_with_newline"
CONDITIONAL_OPEN_RE = re.compile(r"^\s*#\s*(?:if|ifdef|ifndef)\b")
CONDITIONAL_CLOSE_RE = re.compile(r"^\s*#\s*endif\b")


def build_translation_carrier_context(
    spec: dict[str, Any],
    *,
    source_path: Path,
    source_file: str,
    input_binding: dict[str, Any],
    base: dict[str, Any],
    known_roots: tuple[str, ...],
) -> dict[str, Any] | None:
    carrier = spec.get("translation_carrier")
    if carrier is None:
        return None
    if not isinstance(carrier, dict):
        return blocked_context(base, input_binding, "invalid_contract_shape")
    inline_source = spec.get("c_source")
    if not isinstance(inline_source, str) or not inline_source:
        return blocked_context(base, input_binding, "carrier_source_missing")
    normalized_carrier = normalize_newlines(inline_source)
    carrier_bytes = normalized_carrier.encode("utf-8")
    if len(carrier_bytes) > MAX_CARRIER_SOURCE_BYTES:
        return blocked_context(base, input_binding, "carrier_source_too_large")
    if not carrier_contract_is_supported(carrier, spec):
        return blocked_context(base, input_binding, "unsupported_contract")
    carrier_sha = sha256_bytes(carrier_bytes)
    if carrier.get("carrier_source_sha256") != carrier_sha:
        return blocked_context(base, input_binding, "carrier_source_hash_mismatch")

    real_source = carrier.get("real_source")
    fragment = real_source.get("fragment") if isinstance(real_source, dict) else None
    if (
        not isinstance(real_source, dict)
        or real_source.get("file") != Path(source_file).as_posix()
        or not isinstance(fragment, dict)
    ):
        return blocked_context(base, input_binding, "real_source_binding_invalid")
    containing_failure = validate_containing_function(source_path, real_source, fragment)
    if containing_failure is not None:
        return blocked_context(base, input_binding, containing_failure)
    fragment_result = read_real_fragment(source_path, fragment)
    if isinstance(fragment_result, str):
        return blocked_context(base, input_binding, fragment_result)
    fragment_text, fragment_bytes = fragment_result
    if normalized_carrier.count(fragment_text) != 1:
        return blocked_context(base, input_binding, "fragment_embedding_count_mismatch")
    fragment_offset = normalized_carrier.index(fragment_text)
    if offset_is_inside_c_comment(normalized_carrier, fragment_offset):
        return blocked_context(base, input_binding, "fragment_inside_comment")
    if fragment_is_inside_preprocessor_conditional(
        normalized_carrier,
        fragment_offset,
    ):
        return blocked_context(base, input_binding, "fragment_inside_preprocessor_conditional")

    return {
        **base,
        "input": input_binding,
        "span": {
            "status": "inline_translation_carrier_bound",
            "sha256": carrier_sha,
            "declared_sha256": carrier["carrier_source_sha256"],
            "hash_match_mode": "exact",
            "size_bytes": len(carrier_bytes),
            "content": redact_text(normalized_carrier, known_roots),
            "carrier_kind": SUPPORTED_CARRIER_KIND,
            "carrier_function": carrier["carrier_function"],
            "embedding_mode": "verbatim_once",
            "real_source_fragment": {
                "file": Path(source_file).as_posix(),
                "line_start": fragment["line_start"],
                "line_end": fragment["line_end"],
                "sha256": sha256_bytes(fragment_bytes),
                "declared_sha256": fragment["sha256"],
                "hash_mode": SUPPORTED_FRAGMENT_HASH_MODE,
                "content": redact_text(fragment_text, known_roots),
            },
        },
    }


def carrier_contract_is_supported(carrier: dict[str, Any], spec: dict[str, Any]) -> bool:
    claim = carrier.get("claim_boundary")
    return (
        carrier.get("kind") == SUPPORTED_CARRIER_KIND
        and carrier.get("embedding_mode") == "verbatim_once"
        and carrier.get("source_text_normalization") == "utf8_universal_newlines"
        and carrier.get("source_file_hash_mode") == "raw_bytes"
        and carrier.get("artifact_source_hash_mode") == "lf_stable_text"
        and carrier.get("frontend_contract") == "live_clang_slice_source"
        and isinstance(carrier.get("carrier_function"), str)
        and carrier.get("carrier_function") == spec.get("function_name")
        and isinstance(claim, dict)
        and claim.get("scope") == "source_fragment_only"
        and claim.get("whole_function_semantics_verified") is False
        and claim.get("external_callee_semantics_verified") is False
    )


def validate_containing_function(
    path: Path,
    real_source: dict[str, Any],
    fragment: dict[str, Any],
) -> str | None:
    containing = real_source.get("containing_function")
    if not isinstance(containing, dict):
        return "containing_function_contract_invalid"
    line_start = containing.get("line_start")
    line_end = containing.get("line_end")
    declaration = containing.get("declaration_text")
    if (
        not isinstance(containing.get("name"), str)
        or not isinstance(line_start, int)
        or isinstance(line_start, bool)
        or not isinstance(line_end, int)
        or isinstance(line_end, bool)
        or not 1 <= line_start <= line_end
        or containing.get("hash_mode") != "trimmed_normalized_span"
        or not isinstance(containing.get("sha256"), str)
        or not isinstance(declaration, str)
        or not declaration
    ):
        return "containing_function_contract_invalid"
    fragment_start = fragment.get("line_start")
    fragment_end = fragment.get("line_end")
    if (
        not isinstance(fragment_start, int)
        or not isinstance(fragment_end, int)
        or not line_start <= fragment_start <= fragment_end <= line_end
    ):
        return "fragment_outside_containing_function"
    containing_bytes = read_normalized_line_span(path, line_start, line_end)
    if isinstance(containing_bytes, str):
        return containing_bytes
    if sha256_bytes(containing_bytes.strip()) != containing["sha256"]:
        return "containing_function_hash_mismatch"
    try:
        containing_text = containing_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "containing_function_encoding_unsupported"
    if declaration not in containing_text:
        return "containing_function_declaration_missing"
    return None


def read_real_fragment(path: Path, fragment: dict[str, Any]) -> tuple[str, bytes] | str:
    line_start = fragment.get("line_start")
    line_end = fragment.get("line_end")
    if (
        not isinstance(line_start, int)
        or isinstance(line_start, bool)
        or not isinstance(line_end, int)
        or isinstance(line_end, bool)
        or not 1 <= line_start <= line_end
        or fragment.get("hash_mode") != SUPPORTED_FRAGMENT_HASH_MODE
        or not isinstance(fragment.get("sha256"), str)
    ):
        return "fragment_contract_invalid"
    fragment_bytes = read_normalized_line_span(path, line_start, line_end)
    if isinstance(fragment_bytes, str):
        return fragment_bytes.replace("line_span", "fragment")
    if sha256_bytes(fragment_bytes) != fragment["sha256"]:
        return "fragment_hash_mismatch"
    try:
        fragment_text = fragment_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return "fragment_encoding_unsupported"
    declared_text = fragment.get("text")
    if not isinstance(declared_text, str) or normalize_newlines(declared_text) != fragment_text:
        return "fragment_text_mismatch"
    return fragment_text, fragment_bytes


def read_normalized_line_span(path: Path, line_start: int, line_end: int) -> bytes | str:
    selected: list[bytes] = []
    total = 0
    with path.open("rb") as stream:
        for number, line in enumerate(stream, start=1):
            if number < line_start:
                continue
            if number > line_end:
                break
            normalized = line.replace(b"\r\n", b"\n")
            total += len(normalized)
            if total > MAX_CARRIER_SOURCE_BYTES:
                return "line_span_too_large"
            selected.append(normalized)
    if not selected:
        return "line_span_empty"
    return b"".join(selected)


def blocked_context(
    base: dict[str, Any],
    input_binding: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        **base,
        "input": input_binding,
        "span": {
            "status": "blocked_translation_carrier_contract",
            "reason": reason,
        },
    }


def fragment_is_inside_preprocessor_conditional(carrier_source: str, fragment_offset: int) -> bool:
    depth = 0
    for line in carrier_source[:fragment_offset].splitlines():
        if CONDITIONAL_OPEN_RE.match(line):
            depth += 1
        elif CONDITIONAL_CLOSE_RE.match(line):
            depth = max(0, depth - 1)
    return depth > 0


def offset_is_inside_c_comment(source: str, offset: int) -> bool:
    state = "code"
    index = 0
    while index < offset:
        char = source[index]
        next_char = source[index + 1] if index + 1 < offset else ""
        if state == "code":
            if char == "/" and next_char == "*":
                state = "block_comment"
                index += 2
                continue
            if char == "/" and next_char == "/":
                state = "line_comment"
                index += 2
                continue
            if char == '"':
                state = "string"
            elif char == "'":
                state = "character"
        elif state == "block_comment":
            if char == "*" and next_char == "/":
                state = "code"
                index += 2
                continue
        elif state == "line_comment":
            if char == "\n":
                state = "code"
        elif state in {"string", "character"}:
            if char == "\\":
                index += 2
                continue
            if (state == "string" and char == '"') or (
                state == "character" and char == "'"
            ):
                state = "code"
        index += 1
    return state in {"block_comment", "line_comment"}


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


__all__ = ["MAX_CARRIER_SOURCE_BYTES", "build_translation_carrier_context"]
