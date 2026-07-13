from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any

from .artifacts import canonical_json_bytes, checked_relative_path
from .build_facts import is_linklike


def write_once_json_artifact(
    out_root: Path, relative: str, payload: Any,
) -> dict[str, Any]:
    return write_once_bytes_artifact(
        out_root, relative, canonical_json_bytes(payload),
    )


def write_once_bytes_artifact(
    out_root: Path, relative: str, data: bytes,
) -> dict[str, Any]:
    relative = checked_relative_path(relative)
    if not isinstance(data, bytes):
        raise TypeError("write-once artifact data must be bytes")
    root = out_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    if is_linklike(root):
        raise ValueError("write-once artifact root must not be a link")
    lexical = root.joinpath(*PurePosixPath(relative).parts)
    lexical.parent.mkdir(parents=True, exist_ok=True)
    _reject_link_components(root, lexical)
    parent = lexical.parent.resolve(strict=True)
    try:
        parent.relative_to(root)
    except ValueError as error:
        raise ValueError("write-once artifact target escapes out_root") from error
    target = parent / lexical.name
    expected = hashlib.sha256(data).hexdigest()
    reference = {"path": relative, "sha256": expected, "size_bytes": len(data)}
    if target.exists():
        _require_existing(target, data)
        return reference
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            _require_existing(target, data)
        _require_existing(target, data)
    finally:
        temporary.unlink(missing_ok=True)
    return reference


def _reject_link_components(root: Path, target: Path) -> None:
    current = root
    for part in target.relative_to(root).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise ValueError("write-once artifact path contains a link")


def _require_existing(path: Path, expected: bytes) -> None:
    if is_linklike(path) or not path.is_file():
        raise ValueError("write-once artifact target is not a regular file")
    if path.stat().st_size != len(expected) or path.read_bytes() != expected:
        raise ValueError("write-once artifact drifted")


__all__ = ["write_once_bytes_artifact", "write_once_json_artifact"]
