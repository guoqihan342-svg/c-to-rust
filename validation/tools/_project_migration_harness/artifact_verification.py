from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .build_facts import is_linklike


def verify_artifact_reference(
    root: Path, reference: Mapping[str, Any], *, max_bytes: int,
) -> None:
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
    if resolved.stat().st_size != expected_size or expected_size > max_bytes:
        raise ValueError("artifact verification size is invalid")
    digest = hashlib.sha256()
    read = 0
    with resolved.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            read += len(chunk)
            if read > max_bytes:
                raise ValueError("artifact verification exceeds the read limit")
            digest.update(chunk)
    if read != expected_size or digest.hexdigest() != expected:
        raise ValueError("artifact verification SHA-256 drifted")


__all__ = ["verify_artifact_reference"]
