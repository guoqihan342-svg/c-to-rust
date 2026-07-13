from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .context_security import logical_path, sha256_path
from .context_source import path_hash_match_mode


@dataclass(frozen=True)
class BoundSourceFile:
    source_root: Path
    path: Path
    actual_sha256: str
    declared_sha256: str
    hash_match_mode: str
    size_bytes: int
    text: str


def read_hash_bound_utf8_source(
    source_root: Path,
    relative_path: str,
    declared_sha256: str,
    *,
    max_bytes: int,
) -> BoundSourceFile:
    resolved_root = source_root.resolve()
    resolved = (resolved_root / PurePosixPath(relative_path)).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("source_path_outside_root") from error
    if not resolved.is_file():
        raise ValueError("source_file_missing")
    size_bytes = resolved.stat().st_size
    if size_bytes > max_bytes:
        raise ValueError("source_file_exceeds_limit")

    actual_sha256 = sha256_path(resolved)
    match_mode = path_hash_match_mode(
        resolved,
        declared_sha256,
        actual_sha256=actual_sha256,
    )
    if match_mode is None:
        raise ValueError("source_file_sha256_mismatch")
    try:
        text = resolved.read_text(encoding="utf-8-sig")
    except UnicodeError as error:
        raise ValueError("source_file_not_utf8") from error
    if sha256_path(resolved) != actual_sha256:
        raise ValueError("source_file_changed_during_read")
    return BoundSourceFile(
        source_root=resolved_root,
        path=resolved,
        actual_sha256=actual_sha256,
        declared_sha256=declared_sha256,
        hash_match_mode=match_mode,
        size_bytes=size_bytes,
        text=text,
    )


def source_file_descriptor(value: BoundSourceFile) -> dict[str, object]:
    return {
        "path": logical_path(value.source_root, value.path),
        "sha256": value.actual_sha256,
        "declared_sha256": value.declared_sha256,
        "hash_match_mode": value.hash_match_mode,
        "size_bytes": value.size_bytes,
    }


def ensure_bound_source_unchanged(value: BoundSourceFile) -> None:
    if sha256_path(value.path) != value.actual_sha256:
        raise ValueError("source_file_changed_during_read")


__all__ = [
    "BoundSourceFile",
    "ensure_bound_source_unchanged",
    "read_hash_bound_utf8_source",
    "source_file_descriptor",
]
