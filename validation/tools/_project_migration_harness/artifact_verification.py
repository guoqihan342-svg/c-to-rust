from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_metadata
from .build_facts import is_linklike


def verify_artifact_reference(
    root: Path, reference: Mapping[str, Any], *, max_bytes: int,
) -> None:
    path, expected, expected_size = _artifact_binding(
        root, reference, max_bytes=max_bytes,
    )
    with path.open("rb") as stream:
        _verify_stream(stream, expected, expected_size, max_bytes=max_bytes)


def read_verified_json_object(
    root: Path, reference: Mapping[str, Any], *, max_bytes: int,
) -> dict[str, Any]:
    path, expected, expected_size = _artifact_binding(
        root, reference, max_bytes=max_bytes,
    )
    with path.open("rb") as stream:
        _verify_stream(stream, expected, expected_size, max_bytes=max_bytes)
        stream.seek(0)
        text = io.TextIOWrapper(stream, encoding="utf-8")
        try:
            value = json.load(text)
        finally:
            text.detach()
    if not isinstance(value, dict):
        raise ValueError("verified JSON artifact must be an object")
    digest, size = canonical_json_metadata(value)
    if digest != expected or size != expected_size:
        raise ValueError("verified JSON artifact is not canonical")
    return value


def _artifact_binding(
    root: Path, reference: Mapping[str, Any], *, max_bytes: int,
) -> tuple[Path, str, int]:
    relative = reference.get("path")
    expected = reference.get("sha256")
    expected_size = reference.get("size_bytes")
    if (
        not isinstance(relative, str) or not isinstance(expected, str)
        or isinstance(expected_size, bool) or not isinstance(expected_size, int)
        or expected_size < 0 or max_bytes < 1
    ):
        raise ValueError("artifact verification binding is incomplete")
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or "\\" in relative:
        raise ValueError("artifact verification path is unsafe")
    base = root.resolve(strict=True)
    current = base
    for part in path.parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("artifact verification path contains a link")
    resolved = current.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise ValueError("artifact verification path escapes the root") from error
    if expected_size > max_bytes:
        raise ValueError("artifact verification size is invalid")
    return resolved, expected, expected_size


def _verify_stream(
    stream: Any, expected: str, expected_size: int, *, max_bytes: int,
) -> None:
    if os.fstat(stream.fileno()).st_size != expected_size:
        raise ValueError("artifact verification size is invalid")
    digest = hashlib.sha256()
    read = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        read += len(chunk)
        if read > max_bytes:
            raise ValueError("artifact verification exceeds the read limit")
        digest.update(chunk)
    if read != expected_size or digest.hexdigest() != expected:
        raise ValueError("artifact verification SHA-256 drifted")


__all__ = ["read_verified_json_object", "verify_artifact_reference"]
