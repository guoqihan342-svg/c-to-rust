from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def content_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def checked_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact path must be a non-empty POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.parts[0].startswith("~"):
        raise ValueError("artifact path must stay relative")
    if ":" in path.parts[0] or path.as_posix() != value:
        raise ValueError("artifact path is not canonical POSIX relative")
    return value


def write_json_artifact(out_root: Path, relative: str, payload: Any) -> dict[str, Any]:
    return write_bytes_artifact(out_root, relative, canonical_json_bytes(payload))


def write_bytes_artifact(
    out_root: Path, relative: str, data: bytes
) -> dict[str, Any]:
    relative = checked_relative_path(relative)
    if not isinstance(data, bytes):
        raise TypeError("artifact data must be bytes")
    root = out_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = (root / Path(*PurePosixPath(relative).parts)).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise ValueError("artifact target escapes out_root") from error
    _atomic_write(target, data)
    return {
        "path": relative,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "canonical_json_bytes",
    "checked_relative_path",
    "content_sha256",
    "write_bytes_artifact",
    "write_json_artifact",
]
