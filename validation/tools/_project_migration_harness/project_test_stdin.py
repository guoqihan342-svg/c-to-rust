from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import is_linklike, resolve_repository_path


MAX_PROJECT_TEST_STDIN_BYTES = 1024 * 1024


def normalize_stdin_file(
    value: Any, *, repo_root: Path, base: Path,
) -> dict[str, str]:
    if (
        not isinstance(value, str) or not value or "\x00" in value
        or "\r" in value or "\n" in value
        or len(value.encode("utf-8")) > 4096
    ):
        raise ValueError("project_test_stdin_path_invalid")
    try:
        path = resolve_repository_path(repo_root, value, base=base)
        metadata = path.stat(follow_symlinks=False)
    except (OSError, ValueError) as error:
        raise ValueError("project_test_stdin_path_invalid") from error
    if (
        not path.is_file() or is_linklike(path)
        or not 0 <= metadata.st_size <= MAX_PROJECT_TEST_STDIN_BYTES
    ):
        raise ValueError("project_test_stdin_file_invalid")
    return {
        "kind": "repo-path",
        "path": path.relative_to(repo_root.resolve()).as_posix(),
    }


def stdin_repo_path(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != {"kind", "path"}:
        raise ValueError("project_test_stdin_binding_invalid")
    path = value.get("path")
    if value.get("kind") != "repo-path" or not isinstance(path, str) or not path:
        raise ValueError("project_test_stdin_binding_invalid")
    return path


def read_snapshot_stdin(
    root: Path, value: Any, snapshot: Mapping[str, Any],
) -> bytes:
    relative = stdin_repo_path(value)
    if relative is None:
        return b""
    binding = _snapshot_file_binding(snapshot, relative)
    try:
        path = resolve_repository_path(root, relative)
        before = path.stat(follow_symlinks=False)
    except (OSError, ValueError) as error:
        raise ValueError("project_test_stdin_snapshot_invalid") from error
    if (
        not path.is_file() or is_linklike(path)
        or not 0 <= before.st_size <= MAX_PROJECT_TEST_STDIN_BYTES
    ):
        raise ValueError("project_test_stdin_snapshot_invalid")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_PROJECT_TEST_STDIN_BYTES + 1)
        after = path.stat(follow_symlinks=False)
    except OSError as error:
        raise ValueError("project_test_stdin_snapshot_invalid") from error
    if (
        len(data) > MAX_PROJECT_TEST_STDIN_BYTES
        or _stable_stat(before) != _stable_stat(after)
        or len(data) != before.st_size
        or len(data) != binding["size_bytes"]
        or hashlib.sha256(data).hexdigest() != binding["sha256"]
    ):
        raise ValueError("project_test_stdin_snapshot_drifted")
    return data


def _stable_stat(value: Any) -> tuple[int, int, int, int, int]:
    return (
        int(value.st_dev), int(value.st_ino), int(value.st_mode),
        int(value.st_size), int(value.st_mtime_ns),
    )


def _snapshot_file_binding(
    snapshot: Mapping[str, Any], relative: str,
) -> Mapping[str, Any]:
    files, required = snapshot.get("files"), snapshot.get("required_inputs")
    if (
        snapshot.get("schema_version") != 1
        or snapshot.get("artifact_kind") != "project-test-input-snapshot"
        or not isinstance(files, list) or not isinstance(required, list)
        or relative not in required
        or snapshot.get("snapshot_sha256") != content_sha256({
            key: item for key, item in snapshot.items()
            if key != "snapshot_sha256"
        })
    ):
        raise ValueError("project_test_stdin_snapshot_invalid")
    matches = [item for item in files
               if isinstance(item, Mapping) and item.get("path") == relative]
    if len(matches) != 1:
        raise ValueError("project_test_stdin_snapshot_invalid")
    binding = matches[0]
    if (
        set(binding) != {"path", "sha256", "size_bytes", "mode"}
        or not _sha256(binding.get("sha256"))
        or type(binding.get("size_bytes")) is not int
        or not 0 <= binding["size_bytes"] <= MAX_PROJECT_TEST_STDIN_BYTES
    ):
        raise ValueError("project_test_stdin_snapshot_invalid")
    return binding


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__ = [
    "MAX_PROJECT_TEST_STDIN_BYTES", "normalize_stdin_file",
    "read_snapshot_stdin", "stdin_repo_path",
]
