from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any


MAX_SOURCE_MACROS = 4096
MAX_MACRO_REPLACEMENT_BYTES = 16 * 1024
_DIRECTIVE = re.compile(r"^\s*#\s*([A-Za-z_]\w*)\b(.*)$", re.DOTALL)
_DEFINE = re.compile(
    r"^\s*([A-Za-z_]\w*)(?:\(([^)]*)\))?\s*(.*?)\s*$",
    re.DOTALL,
)
_IDENT = re.compile(r"[A-Za-z_]\w*")


def source_macro_definitions(unit: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = bytes(unit["raw"])
    result: list[dict[str, Any]] = []
    depth = 0
    for logical in logical_directives(raw):
        kind = logical["kind"]
        if kind in {"endif"}:
            depth = max(0, depth - 1)
        if kind == "define":
            parsed = _DEFINE.fullmatch(logical["body"])
            if parsed is not None:
                name, parameters_text, replacement = parsed.groups()
                encoded = replacement.encode("latin-1")
                if len(encoded) <= MAX_MACRO_REPLACEMENT_BYTES:
                    parameters = None
                    if parameters_text is not None:
                        parameters = [
                            item.strip() for item in parameters_text.split(",")
                            if item.strip()
                        ]
                        if any(_IDENT.fullmatch(item) is None for item in parameters):
                            parameters = []
                    result.append({
                        "name": name,
                        "parameters": parameters,
                        "replacement": replacement,
                        "byte_offset": logical["byte_offset"],
                        "directive_sha256": logical["sha256"],
                        "source_path": unit["path"],
                        "source_sha256": unit["sha256"],
                        "conditional_depth": depth,
                        "activation_status": (
                            "unconditional" if depth == 0 else "conditional_unknown"
                        ),
                    })
        if kind in {"if", "ifdef", "ifndef"}:
            depth += 1
        if len(result) > MAX_SOURCE_MACROS:
            raise ValueError("translation unit source macro limit exceeded")
    return sorted(result, key=lambda item: (item["name"], item["byte_offset"]))


def function_like_macro_names(raw: bytes) -> set[str]:
    result: set[str] = set()
    for logical in logical_directives(raw):
        if logical["kind"] != "define":
            continue
        parsed = _DEFINE.fullmatch(logical["body"])
        if parsed is not None and parsed.group(2) is not None:
            result.add(parsed.group(1))
        if len(result) > MAX_SOURCE_MACROS:
            raise ValueError("translation unit function-like macro limit exceeded")
    return result


def conditional_ranges(raw: bytes) -> list[tuple[int, int]]:
    stack: list[int] = []
    ranges: list[tuple[int, int]] = []
    end = len(raw)
    for logical in logical_directives(raw):
        kind = logical["kind"]
        if kind in {"if", "ifdef", "ifndef"}:
            stack.append(logical["byte_offset"])
        elif kind == "endif" and stack:
            start = stack.pop()
            ranges.append((start, logical["byte_end"]))
    ranges.extend((start, end) for start in stack)
    return sorted(ranges)


def span_is_unconditional(
    start: int, end: int, ranges: Sequence[tuple[int, int]],
) -> bool:
    return all(end <= left or start >= right for left, right in ranges)


def logical_directives(raw: bytes) -> list[dict[str, Any]]:
    text = raw.decode("latin-1")
    result = []
    offset = 0
    while offset < len(text):
        end = text.find("\n", offset)
        end = len(text) if end < 0 else end + 1
        while end < len(text) and text[offset:end].rstrip("\r\n").endswith("\\"):
            following = text.find("\n", end)
            end = len(text) if following < 0 else following + 1
        logical = text[offset:end]
        matched = _DIRECTIVE.match(logical)
        if matched:
            result.append({
                "kind": matched.group(1).lower(),
                "body": matched.group(2).strip(),
                "byte_offset": offset,
                "byte_end": end,
                "sha256": hashlib.sha256(raw[offset:end]).hexdigest(),
            })
        offset = end
    return result


__all__ = [
    "conditional_ranges",
    "function_like_macro_names",
    "logical_directives",
    "source_macro_definitions",
    "span_is_unconditional",
]
