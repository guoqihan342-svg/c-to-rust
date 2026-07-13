from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


def canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def budget(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 256:
        raise ValueError(f"{label} budget must be an integer of at least 256")
    return value


def mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def objects(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be an array")
    if not all(isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} entries must be objects")
    return list(value)


def required_string(value: Mapping[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"{key} must be a non-empty string")
    return result


def string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError("expected an array of strings")
    if not all(isinstance(item, str) and item for item in value):
        raise ValueError("expected non-empty strings")
    return sorted(set(value))


def safe_blockers(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in objects(value, "blockers"):
        current = {
            "unit_id": str(item.get("unit_id", "")),
            "kind": str(item.get("kind", "unknown")),
        }
        if isinstance(item.get("byte_offset"), int):
            current["byte_offset"] = item["byte_offset"]
        if isinstance(item.get("occurrence_count"), int):
            current["occurrence_count"] = item["occurrence_count"]
        if isinstance(item.get("evidence_set_sha256"), str):
            current["evidence_set_sha256"] = item["evidence_set_sha256"]
        result.append(current)
    return sorted(
        result,
        key=lambda item: (item["unit_id"], item["kind"], item.get("byte_offset", -1)),
    )


def source_ref(source: Mapping[str, Any], *, include_content: bool) -> dict[str, Any]:
    span = mapping(source.get("span"), "source.span")
    result = {
        "path": required_string(source, "path"),
        "sha256": required_string(source, "sha256"),
        "span": {
            "byte_start": span.get("byte_start"),
            "byte_end": span.get("byte_end"),
            "sha256": span.get("sha256"),
        },
    }
    if isinstance(source.get("encoding"), str):
        result["encoding"] = source["encoding"]
    if include_content:
        result["content"] = source.get("content")
    return result


def split_text(value: str, max_bytes: int) -> list[str]:
    chunks: list[str] = []
    current = ""
    size = 0
    for char in value:
        width = len(char.encode("utf-8"))
        if current and size + width > max_bytes:
            chunks.append(current)
            current, size = "", 0
        current += char
        size += width
    if current or not chunks:
        chunks.append(current)
    return chunks


__all__ = [
    "budget",
    "canonical",
    "mapping",
    "objects",
    "required_string",
    "safe_blockers",
    "source_ref",
    "split_text",
    "string_list",
]
