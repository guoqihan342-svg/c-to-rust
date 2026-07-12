from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .context_source import bytes_hash_match_mode


MAX_SOURCE_FILE_BYTES = 32 * 1024 * 1024


def extract_strict_span(
    path: Path,
    descriptor: dict[str, Any],
    expected_sha256: str,
    *,
    max_span_bytes: int,
) -> tuple[bytes, dict[str, int], str]:
    if path.stat().st_size > MAX_SOURCE_FILE_BYTES:
        raise ValueError("source_file_too_large")
    raw = path.read_bytes()
    byte_start = descriptor.get("byte_start")
    byte_end = descriptor.get("byte_end")
    line_start = descriptor.get("line_start")
    line_end = descriptor.get("line_end")
    bytes_declared = "byte_start" in descriptor or "byte_end" in descriptor
    lines_declared = "line_start" in descriptor or "line_end" in descriptor
    has_bytes = (
        isinstance(byte_start, int)
        and not isinstance(byte_start, bool)
        and isinstance(byte_end, int)
        and not isinstance(byte_end, bool)
        and 0 <= byte_start < byte_end
        and byte_end - byte_start <= max_span_bytes
    )
    has_lines = (
        isinstance(line_start, int)
        and not isinstance(line_start, bool)
        and isinstance(line_end, int)
        and not isinstance(line_end, bool)
        and 1 <= line_start <= line_end
    )
    if (bytes_declared and not has_bytes) or (lines_declared and not has_lines):
        raise ValueError("source_span_declared_coordinates_invalid")
    if has_bytes:
        variants = newline_variants(raw)
        for variant_name, variant in variants:
            if byte_end > len(variant):
                continue
            if has_lines:
                line_range = line_span_byte_range(variant, line_start, line_end)
                if line_range is None or byte_start != line_range[0] or byte_end not in line_range[1]:
                    continue
            elif variant_name != "exact":
                continue
            declared_data = variant[byte_start:byte_end]
            if hashlib.sha256(declared_data).hexdigest() != expected_sha256:
                continue
            actual_data = declared_data
            if variant_name != "exact":
                actual_range = line_span_byte_range(raw, line_start, line_end)
                declared_range = line_span_byte_range(variant, line_start, line_end)
                if actual_range is None or declared_range is None:
                    continue
                includes_newline = len(declared_range[1]) > 1 and byte_end == max(declared_range[1])
                actual_end = max(actual_range[1]) if includes_newline else min(actual_range[1])
                actual_data = raw[actual_range[0]:actual_end]
                if bytes_hash_match_mode(
                    actual_data,
                    expected_sha256,
                    actual_sha256=hashlib.sha256(actual_data).hexdigest(),
                ) is None:
                    continue
            coordinates = {"byte_start": byte_start, "byte_end": byte_end}
            if has_lines:
                coordinates.update({"line_start": line_start, "line_end": line_end})
            return actual_data, coordinates, variant_name
    if has_lines and not has_bytes:
        line_range = line_span_byte_range(raw, line_start, line_end)
        if line_range is not None:
            for actual_end in sorted(line_range[1]):
                data = raw[line_range[0]:actual_end]
                mode = bytes_hash_match_mode(
                    data,
                    expected_sha256,
                    actual_sha256=hashlib.sha256(data).hexdigest(),
                )
                if mode is not None:
                    return data, {"line_start": line_start, "line_end": line_end}, mode
    raise ValueError("source_span_coordinates_or_hash_mismatch")


def newline_variants(raw: bytes) -> tuple[tuple[str, bytes], ...]:
    variants = (
        ("exact", raw),
        ("newline_equivalent", raw.replace(b"\r\n", b"\n")),
        ("newline_equivalent", raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")),
    )
    unique: list[tuple[str, bytes]] = []
    seen: set[bytes] = set()
    for name, value in variants:
        if value not in seen:
            seen.add(value)
            unique.append((name, value))
    return tuple(unique)


def line_span_byte_range(raw: bytes, line_start: int, line_end: int) -> tuple[int, set[int]] | None:
    if not raw:
        return None
    starts = [0]
    starts.extend(index + 1 for index, byte in enumerate(raw) if byte == 0x0A and index + 1 < len(raw))
    if line_end > len(starts):
        return None
    byte_start = starts[line_start - 1]
    final_start = starts[line_end - 1]
    newline_at = raw.find(b"\n", final_start)
    if newline_at < 0:
        return byte_start, {len(raw)}
    without_newline = newline_at - (1 if newline_at > final_start and raw[newline_at - 1] == 0x0D else 0)
    return byte_start, {without_newline, newline_at + 1}


__all__ = ["extract_strict_span"]
