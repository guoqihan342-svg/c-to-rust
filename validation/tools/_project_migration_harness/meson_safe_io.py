from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any

from . import meson_paths as paths


def read_bounded(root: Path, path: Path, limit: int) -> bytes:
    fd = _open_read_fd(root, path)
    try:
        before = _regular_stat(fd, limit)
        raw = bytearray()
        while True:
            chunk = os.read(fd, min(1024 * 1024, limit + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > limit:
                raise paths.MesonPathError("meson_file_size_limit_exceeded")
        _validate_open_file(root, path, fd, before, len(raw))
        return bytes(raw)
    finally:
        os.close(fd)


def hash_binding(root: Path, path: Path, limit: int) -> dict[str, Any]:
    fd = _open_read_fd(root, path)
    digest = hashlib.sha256()
    total = 0
    try:
        before = _regular_stat(fd, limit)
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise paths.MesonPathError("meson_referenced_file_size_limit_exceeded")
            digest.update(chunk)
        _validate_open_file(root, path, fd, before, total)
    finally:
        os.close(fd)
    return {
        "path": paths.repository_lexical_path(root, path),
        "sha256": digest.hexdigest(),
        "size_bytes": total,
        "kind": "file",
    }


def meson_ninja_header(root: Path, path: Path) -> bool:
    if not paths.path_present(path):
        return False
    try:
        fd = _open_read_fd(root, path)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                return False
            prefix = os.read(fd, 64 * 1024)
            after = os.fstat(fd)
            if _identity(before) != _identity(after):
                return False
            if os.name == "nt":
                _validate_windows_handle(root, path, fd)
            return b"meson build system" in prefix.lower()
        finally:
            os.close(fd)
    except (OSError, paths.MesonPathError):
        return False


def _open_read_fd(root: Path, path: Path) -> int:
    confined = paths.confined_path(root, str(path))
    try:
        if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
            return _openat_read_fd(Path(os.path.abspath(root)), confined)
        paths._reject_reparse_components(Path(os.path.abspath(root)), confined)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        fd = os.open(confined, flags)
        _validate_windows_handle(root, confined, fd)
        return fd
    except paths.MesonPathError:
        raise
    except OSError as error:
        raise paths.MesonPathError("meson_file_unreadable") from error


def _openat_read_fd(root: Path, path: Path) -> int:
    relative = path.relative_to(root)
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(
        os, "O_CLOEXEC", 0
    )
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    current = os.open(root, directory_flags)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = child
        return os.open(relative.parts[-1], file_flags, dir_fd=current)
    finally:
        os.close(current)


def _regular_stat(fd: int, limit: int) -> os.stat_result:
    try:
        value = os.fstat(fd)
    except OSError as error:
        raise paths.MesonPathError("meson_file_unreadable") from error
    if not stat.S_ISREG(value.st_mode):
        raise paths.MesonPathError("meson_file_not_regular")
    if value.st_size > limit:
        raise paths.MesonPathError("meson_file_size_limit_exceeded")
    return value


def _validate_open_file(
    root: Path, path: Path, fd: int, before: os.stat_result, bytes_read: int,
) -> None:
    after = os.fstat(fd)
    if _identity(before) != _identity(after) or bytes_read != after.st_size:
        raise paths.MesonPathError("meson_file_drift_during_read")
    if os.name == "nt":
        _validate_windows_handle(root, path, fd)


def _validate_windows_handle(root: Path, path: Path, fd: int) -> None:
    if os.name != "nt":
        return
    paths._reject_reparse_components(Path(os.path.abspath(root)), path)
    try:
        by_path = path.lstat()
        by_handle = os.fstat(fd)
    except OSError as error:
        raise paths.MesonPathError("meson_file_unreadable") from error
    if paths._is_reparse(path) or _identity(by_path) != _identity(by_handle):
        raise paths.MesonPathError("meson_file_identity_mismatch")


def _identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


__all__ = ["hash_binding", "meson_ninja_header", "read_bounded"]
