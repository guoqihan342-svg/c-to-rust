from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path
from typing import Any, Iterable

from .artifacts import content_sha256
from .build_facts import is_linklike


MAX_SNAPSHOT_FILES = 100_000
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024


def copy_bounded_repository_snapshot(
    source: Path, destination: Path, *, excludes: Iterable[Path] = (),
) -> dict[str, Any]:
    root = Path(source).resolve(strict=True)
    target = Path(destination)
    if not root.is_dir() or target.exists() or is_linklike(root):
        raise ValueError("project_test_snapshot_root_invalid")
    excluded = _excluded_relatives(root, excludes)
    root_metadata = root.stat(follow_symlinks=False)
    target.mkdir(parents=True, mode=0o700)
    target.chmod(root_metadata.st_mode & 0o777)
    files: list[dict[str, Any]] = []
    directory_records: list[dict[str, Any]] = [{
        "path": ".", "mode": root_metadata.st_mode & 0o777,
    }]
    total = 0
    stack = [(root, target, ())]
    while stack:
        current, output, relative_parts = stack.pop()
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError as error:
            raise ValueError("project_test_snapshot_directory_unreadable") from error
        child_directories = []
        for entry in entries:
            relative = (*relative_parts, entry.name)
            if _excluded(relative, excluded) or entry.name == ".git":
                continue
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ValueError("project_test_snapshot_entry_unreadable") from error
            if entry.is_symlink() or stat.S_ISLNK(metadata.st_mode):
                raise ValueError("project_test_snapshot_link_forbidden")
            destination_path = output / entry.name
            if stat.S_ISDIR(metadata.st_mode):
                destination_path.mkdir(mode=0o700)
                destination_path.chmod(metadata.st_mode & 0o777)
                directory_records.append({
                    "path": "/".join(relative),
                    "mode": metadata.st_mode & 0o777,
                })
                child_directories.append((Path(entry.path), destination_path, relative))
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError("project_test_snapshot_special_file_forbidden")
            if len(files) >= MAX_SNAPSHOT_FILES:
                raise ValueError("project_test_snapshot_file_limit_exceeded")
            total += metadata.st_size
            if total > MAX_SNAPSHOT_BYTES:
                raise ValueError("project_test_snapshot_byte_limit_exceeded")
            digest = copy_stable_file(Path(entry.path), destination_path, metadata)
            files.append({
                "path": "/".join(relative), "sha256": digest,
                "size_bytes": metadata.st_size,
                "executable": bool(metadata.st_mode & 0o111),
            })
        stack.extend(reversed(child_directories))
    payload = {
        "schema_version": 2, "artifact_kind": "project-test-source-snapshot",
        "file_count": len(files), "directory_count": len(directory_records),
        "size_bytes": total, "files": files,
        "directories": sorted(directory_records, key=lambda item: item["path"]),
        "exclusion_policy": {
            "git_metadata": "excluded", "links": "forbidden",
            "special_files": "forbidden",
            "explicit_excludes": ["/".join(item) for item in excluded],
        },
    }
    payload["snapshot_sha256"] = content_sha256(payload)
    return payload


def copy_stable_file(
    source: Path, destination: Path, before: os.stat_result,
) -> str:
    digest = hashlib.sha256()
    observed = 0
    try:
        with source.open("rb") as reader, destination.open("xb") as writer:
            while chunk := reader.read(1024 * 1024):
                observed += len(chunk)
                writer.write(chunk)
                digest.update(chunk)
        after = source.stat(follow_symlinks=False)
        identity_before = (
            before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
        )
        if observed != before.st_size or identity_before != identity_after:
            raise ValueError("project_test_snapshot_source_drifted")
        destination.chmod(before.st_mode & 0o777)
    except (OSError, ValueError) as error:
        destination.unlink(missing_ok=True)
        if isinstance(error, ValueError):
            raise
        raise ValueError("project_test_snapshot_file_unreadable") from error
    return digest.hexdigest()


def _excluded_relatives(
    root: Path, values: Iterable[Path],
) -> tuple[tuple[str, ...], ...]:
    result = []
    for value in values:
        try:
            relative = Path(value).resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        if relative.parts:
            result.append(relative.parts)
    return tuple(sorted(set(result)))


def _excluded(
    relative: tuple[str, ...], excluded: tuple[tuple[str, ...], ...],
) -> bool:
    return any(relative[:len(item)] == item for item in excluded)


__all__ = ["copy_bounded_repository_snapshot", "copy_stable_file"]
