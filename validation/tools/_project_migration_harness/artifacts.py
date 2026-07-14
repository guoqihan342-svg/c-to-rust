from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from typing import Any


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def canonical_json_metadata(value: Any) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    for chunk in _canonical_json_chunks(value, level=0):
        encoded = chunk.encode("utf-8")
        digest.update(encoded)
        size += len(encoded)
    digest.update(b"\n")
    return digest.hexdigest(), size + 1


def _canonical_json_chunks(value: Any, *, level: int):
    if isinstance(value, str):
        yield from _quoted_chunks(value)
    elif value is None:
        yield "null"
    elif value is True:
        yield "true"
    elif value is False:
        yield "false"
    elif isinstance(value, int):
        yield str(value)
    elif isinstance(value, float):
        yield json.dumps(value, ensure_ascii=True)
    elif isinstance(value, (list, tuple)):
        if not value:
            yield "[]"
            return
        yield "[\n"
        for index, item in enumerate(value):
            if index:
                yield ",\n"
            yield " " * (2 * (level + 1))
            yield from _canonical_json_chunks(item, level=level + 1)
        yield "\n" + " " * (2 * level) + "]"
    elif isinstance(value, dict):
        if not value:
            yield "{}"
            return
        yield "{\n"
        for index, (key, item) in enumerate(sorted(value.items())):
            if index:
                yield ",\n"
            yield " " * (2 * (level + 1))
            yield from _quoted_chunks(_json_key(key))
            yield ": "
            yield from _canonical_json_chunks(item, level=level + 1)
        yield "\n" + " " * (2 * level) + "}"
    else:
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_key(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return json.dumps(value, ensure_ascii=True)
    raise TypeError(f"keys must be JSON scalar values, not {type(value).__name__}")


def _quoted_chunks(value: str):
    yield '"'
    for offset in range(0, len(value), 64 * 1024):
        encoded = json.encoder.encode_basestring_ascii(value[offset:offset + 64 * 1024])
        yield encoded[1:-1]
    yield '"'


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
    "canonical_json_bytes", "canonical_json_metadata",
    "checked_relative_path",
    "content_sha256",
    "write_bytes_artifact",
    "write_json_artifact",
]
