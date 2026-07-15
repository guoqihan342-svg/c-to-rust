from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .build_facts import is_linklike
from .build_ir import is_sha256
from .rust_project_ir_validation import RustProjectIRError


MAX_BOUND_ARTIFACT_BYTES = 64 * 1024 * 1024


def strict_json(data: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, item in items:
            if key in result:
                fail(f"bound {label} contains duplicate keys")
            result[key] = item
        return result
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise RustProjectIRError(f"bound {label} is invalid JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != data:
        fail(f"bound {label} is not canonical JSON")
    return payload


def read_reference(root: Path, reference: Mapping[str, Any]) -> bytes:
    relative, expected_sha, size = artifact_identity(reference)
    try:
        resolved_root = root.resolve(strict=True)
        current = resolved_root
        for part in PurePosixPath(relative).parts:
            current /= part
            if current.exists() and is_linklike(current):
                fail("bound artifact linked path is forbidden")
        target = current.resolve(strict=True)
        target.relative_to(resolved_root)
        if target.stat().st_size != size:
            fail("bound artifact content drifted")
        data = target.read_bytes()
    except RustProjectIRError:
        raise
    except (OSError, ValueError) as error:
        raise RustProjectIRError("bound artifact cannot be reopened") from error
    if hashlib.sha256(data).hexdigest() != expected_sha:
        fail("bound artifact content drifted")
    return data


def artifact_identity(value: Any) -> tuple[str, str, int]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        fail("bound artifact reference schema is invalid")
    try:
        path = checked_relative_path(value.get("path"))
    except ValueError as error:
        raise RustProjectIRError("bound artifact path is invalid") from error
    digest, size = value.get("sha256"), value.get("size_bytes")
    if not is_sha256(digest):
        fail("bound artifact sha256 is invalid")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_BOUND_ARTIFACT_BYTES:
        fail("bound artifact size is invalid")
    return path, digest, size


def fail(message: str) -> None:
    raise RustProjectIRError(message)


__all__ = [
    "MAX_BOUND_ARTIFACT_BYTES", "artifact_identity", "fail", "read_reference",
    "strict_json",
]
