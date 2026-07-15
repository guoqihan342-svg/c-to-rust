from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
from typing import BinaryIO

from .make_dry_run_cas import validated_make_output_root


MAX_SNAPSHOT_FILES = 100_000
MAX_SNAPSHOT_DIRECTORIES = 100_000
MAX_SNAPSHOT_FILE_BYTES = 64 * 1024 * 1024
MAX_SNAPSHOT_TOTAL_BYTES = 16 * 1024 * 1024 * 1024


def snapshot_repository_files(
    root: Path, *, collector_output_root: str, destination: Path | None,
) -> tuple[str, list[str], list[dict[str, object]], int]:
    out_root = validated_make_output_root(collector_output_root)
    exclusions = [".git", out_root]
    files: list[dict[str, object]] = []
    state = {"directories": 0, "bytes": 0}
    if os.name == "posix" and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW"):
        _scan_posix_root(root, destination, exclusions, files, state)
    else:
        _scan_path_directory(root, root, destination, exclusions, files, state)
    return out_root, exclusions, sorted(files, key=lambda item: str(item["path"])), state["bytes"]


def _scan_posix_root(
    root: Path, destination: Path | None, exclusions: list[str],
    files: list[dict[str, object]], state: dict[str, int],
) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(root, flags)
    try:
        _scan_posix_directory(
            descriptor, (), destination, exclusions, files, state,
        )
    finally:
        os.close(descriptor)


def _scan_posix_directory(
    descriptor: int, relative: tuple[str, ...], destination: Path | None,
    exclusions: list[str], files: list[dict[str, object]],
    state: dict[str, int],
) -> None:
    before = os.fstat(descriptor)
    if not stat.S_ISDIR(before.st_mode):
        raise ValueError("make_snapshot_directory_unreadable")
    _count_directory(state)
    _make_destination_directory(destination, relative)
    try:
        with os.scandir(descriptor) as iterator:
            names = sorted(entry.name for entry in iterator)
    except OSError as error:
        raise ValueError("make_snapshot_directory_unreadable") from error
    for name in names:
        if not name or name in {".", ".."} or "/" in name:
            raise ValueError("make_snapshot_entry_name_invalid")
        parts = (*relative, name)
        if _is_excluded(parts, exclusions):
            continue
        try:
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as error:
            raise ValueError("make_snapshot_entry_unreadable") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("make_snapshot_linked_path_rejected")
        if stat.S_ISDIR(metadata.st_mode):
            _scan_posix_child(
                descriptor, name, metadata, parts, destination,
                exclusions, files, state,
            )
        elif stat.S_ISREG(metadata.st_mode):
            _bind_posix_file(
                descriptor, name, metadata, parts, destination, files, state,
            )
        else:
            raise ValueError("make_snapshot_special_file_rejected")
    if _directory_state(before) != _directory_state(os.fstat(descriptor)):
        raise ValueError("make_snapshot_directory_drift")


def _scan_posix_child(
    parent: int, name: str, metadata: os.stat_result, relative: tuple[str, ...],
    destination: Path | None, exclusions: list[str],
    files: list[dict[str, object]], state: dict[str, int],
) -> None:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        child = os.open(name, flags, dir_fd=parent)
    except OSError as error:
        raise ValueError("make_snapshot_linked_path_rejected") from error
    try:
        if not _same_entry(metadata, os.fstat(child)):
            raise ValueError("make_snapshot_directory_identity_drift")
        _scan_posix_directory(
            child, relative, destination, exclusions, files, state,
        )
    finally:
        os.close(child)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not _same_entry(metadata, current):
        raise ValueError("make_snapshot_directory_identity_drift")


def _bind_posix_file(
    parent: int, name: str, metadata: os.stat_result, relative: tuple[str, ...],
    destination: Path | None, files: list[dict[str, object]],
    state: dict[str, int],
) -> None:
    _check_file_budget(metadata, files, state)
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent)
    except OSError as error:
        raise ValueError("make_snapshot_file_unreadable") from error
    try:
        reference = _read_file_descriptor(
            descriptor, metadata, relative, destination,
        )
        current = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if not _same_file(metadata, current):
            raise ValueError("make_snapshot_file_identity_drift")
    finally:
        os.close(descriptor)
    files.append(reference)
    state["bytes"] += int(reference["size_bytes"])


def _scan_path_directory(
    root: Path, current: Path, destination: Path | None,
    exclusions: list[str], files: list[dict[str, object]], state: dict[str, int],
) -> None:
    before = current.stat(follow_symlinks=False)
    _count_directory(state)
    relative_directory = current.relative_to(root)
    _make_destination_directory(destination, relative_directory.parts)
    try:
        entries = sorted(os.scandir(current), key=lambda item: item.name)
    except OSError as error:
        raise ValueError("make_snapshot_directory_unreadable") from error
    for entry in entries:
        path = Path(entry.path)
        relative = path.relative_to(root)
        parts = PurePosixPath(relative.as_posix()).parts
        if _is_excluded(parts, exclusions):
            continue
        if entry.is_symlink() or _is_junction(path):
            raise ValueError("make_snapshot_linked_path_rejected")
        try:
            metadata = path.stat(follow_symlinks=False)
            path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as error:
            raise ValueError("make_snapshot_entry_unreadable") from error
        if stat.S_ISDIR(metadata.st_mode):
            _scan_path_directory(
                root, path, destination, exclusions, files, state,
            )
        elif stat.S_ISREG(metadata.st_mode):
            _check_file_budget(metadata, files, state)
            reference = _bind_path_file(path, metadata, parts, destination)
            files.append(reference)
            state["bytes"] += int(reference["size_bytes"])
        else:
            raise ValueError("make_snapshot_special_file_rejected")
    after = current.stat(follow_symlinks=False)
    if _directory_state(before) != _directory_state(after):
        raise ValueError("make_snapshot_directory_drift")


def _bind_path_file(
    path: Path, metadata: os.stat_result, relative: tuple[str, ...],
    destination: Path | None,
) -> dict[str, object]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ValueError("make_snapshot_file_unreadable") from error
    try:
        reference = _read_file_descriptor(
            descriptor, metadata, relative, destination,
        )
        if not _same_file(metadata, path.stat(follow_symlinks=False)):
            raise ValueError("make_snapshot_file_identity_drift")
    finally:
        os.close(descriptor)
    return reference


def _read_file_descriptor(
    descriptor: int, metadata: os.stat_result, relative: tuple[str, ...],
    destination: Path | None,
) -> dict[str, object]:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode) or not _same_file(metadata, before):
        raise ValueError("make_snapshot_file_identity_drift")
    digest = hashlib.sha256()
    size = 0
    target = destination.joinpath(*relative) if destination is not None else None
    output: BinaryIO | None = None
    try:
        if target is not None:
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            output = target.open("xb")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SNAPSHOT_FILE_BYTES:
                raise ValueError("make_snapshot_file_size_limit_exceeded")
            digest.update(chunk)
            if output is not None:
                output.write(chunk)
        after = os.fstat(descriptor)
        if not _same_file(before, after) or after.st_size != size:
            raise ValueError("make_snapshot_file_content_drift")
    finally:
        if output is not None:
            output.close()
    if target is not None and os.name == "posix":
        target.chmod(0o400 | (stat.S_IMODE(metadata.st_mode) & 0o111))
    return {
        "path": PurePosixPath(*relative).as_posix(),
        "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _check_file_budget(
    metadata: os.stat_result, files: list[dict[str, object]],
    state: dict[str, int],
) -> None:
    if len(files) >= MAX_SNAPSHOT_FILES:
        raise ValueError("make_snapshot_file_limit_exceeded")
    if metadata.st_size > MAX_SNAPSHOT_FILE_BYTES:
        raise ValueError("make_snapshot_file_size_limit_exceeded")
    if state["bytes"] + metadata.st_size > MAX_SNAPSHOT_TOTAL_BYTES:
        raise ValueError("make_snapshot_total_size_limit_exceeded")


def _count_directory(state: dict[str, int]) -> None:
    state["directories"] += 1
    if state["directories"] > MAX_SNAPSHOT_DIRECTORIES:
        raise ValueError("make_snapshot_directory_limit_exceeded")


def _make_destination_directory(
    destination: Path | None, relative: tuple[str, ...],
) -> None:
    if destination is not None:
        destination.joinpath(*relative).mkdir(exist_ok=True, mode=0o700)


def _is_excluded(parts: tuple[str, ...], exclusions: list[str]) -> bool:
    return any(
        tuple(parts[:len(excluded)]) == excluded
        for excluded in (PurePosixPath(value).parts for value in exclusions)
    )


def _same_entry(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev, left.st_ino, stat.S_IFMT(left.st_mode)
    ) == (
        right.st_dev, right.st_ino, stat.S_IFMT(right.st_mode)
    )


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_entry(left, right) and (
        left.st_size, left.st_mtime_ns
    ) == (
        right.st_size, right.st_mtime_ns
    )


def _directory_state(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev, value.st_ino, stat.S_IFMT(value.st_mode), value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


def _is_junction(path: Path) -> bool:
    predicate = getattr(path, "is_junction", None)
    return bool(callable(predicate) and predicate())


__all__ = [
    "MAX_SNAPSHOT_DIRECTORIES", "MAX_SNAPSHOT_FILES",
    "MAX_SNAPSHOT_FILE_BYTES", "MAX_SNAPSHOT_TOTAL_BYTES",
    "snapshot_repository_files",
]
