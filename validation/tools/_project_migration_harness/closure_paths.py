from __future__ import annotations

from pathlib import Path
from typing import Any

from .build_facts import is_linklike, repository_path, resolve_repository_path
from .closure_directory_digest import directory_digest, file_digest


MAX_BOUND_FILE_BYTES = 512 * 1024 * 1024


def bind_repository_artifact(
    repo_root: Path,
    value: str | Path,
    *,
    base: Path | None = None,
    kind: str,
) -> dict[str, Any]:
    path = resolve_repository_path(repo_root, value, base=base)
    if kind == "file":
        if not path.is_file() or is_linklike(path):
            raise ValueError("artifact_missing")
        size = path.stat().st_size
        if size > MAX_BOUND_FILE_BYTES:
            raise ValueError("file_byte_limit_exceeded")
        digest = file_digest(path)
        return {
            "path": repository_path(repo_root, path),
            "sha256": digest,
            "size_bytes": size,
            "kind": "file",
        }
    if kind != "directory":
        raise ValueError("artifact_kind_invalid")
    if not path.is_dir() or is_linklike(path):
        raise ValueError("artifact_missing")
    digest, entries, size = directory_digest(path)
    return {
        "path": repository_path(repo_root, path),
        "sha256": digest,
        "size_bytes": size,
        "entry_count": entries,
        "kind": "directory",
    }


def verify_repository_artifact(
    repo_root: Path, binding: dict[str, Any]
) -> dict[str, Any] | None:
    path = binding.get("path")
    kind = binding.get("kind")
    expected = binding.get("sha256")
    if not isinstance(path, str) or kind not in {"file", "directory"}:
        return {"kind": "artifact_binding_invalid", "path": str(path)}
    try:
        current = bind_repository_artifact(repo_root, path, kind=kind)
    except (OSError, ValueError) as error:
        return {
            "kind": _path_error_kind(error),
            "path": _safe_blocker_path(error, path),
        }
    if current["sha256"] != expected:
        return {"kind": "artifact_sha256_drift", "path": path}
    return None


def path_error_blocker(error: Exception, *, role: str, path: str) -> dict[str, str]:
    return {
        "kind": f"{role}_{_path_error_kind(error)}",
        "path": _safe_blocker_path(error, path),
    }


def _path_error_kind(error: Exception) -> str:
    reason = str(error)
    if reason in {
        "foreign_absolute_path",
        "path_outside_repository",
        "linked_path_component",
    }:
        return reason
    return "missing"


def _safe_blocker_path(error: Exception, path: str) -> str:
    if str(error) in {"foreign_absolute_path", "path_outside_repository"}:
        return "<external-path>"
    return path


__all__ = [
    "bind_repository_artifact",
    "path_error_blocker",
    "verify_repository_artifact",
]
