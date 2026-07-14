from __future__ import annotations

import os
from pathlib import Path, PurePath
import stat

from .meson_paths import MesonPathError
from .meson_safe_io import read_bounded as _read_bounded


class BoundedArtifactIOError(ValueError):
    pass


def read_bounded_artifact(root: Path, path: Path, limit: int) -> bytes:
    try:
        return _read_bounded(root, path, limit)
    except (OSError, MesonPathError) as error:
        raise BoundedArtifactIOError("bounded artifact is not safely readable") from error


def write_immutable_artifact(
    root: Path, relative: PurePath, data: bytes, limit: int,
) -> Path:
    if (
        relative.is_absolute() or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or len(data) > limit
    ):
        raise BoundedArtifactIOError("bounded artifact write contract is invalid")
    lexical_root = Path(os.path.abspath(root))
    lexical_root.mkdir(parents=True, exist_ok=True)
    target = lexical_root.joinpath(*relative.parts)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = _exclusive_descriptor(lexical_root, target, relative)
    except FileExistsError:
        if read_bounded_artifact(lexical_root, target, limit) != data:
            raise BoundedArtifactIOError("content-addressed artifact is immutable")
        return target
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size != 0:
            raise BoundedArtifactIOError("bounded artifact target is not a new file")
        _write_all(descriptor, data)
        os.fsync(descriptor)
        after = os.fstat(descriptor)
        if not stat.S_ISREG(after.st_mode) or after.st_size != len(data):
            raise BoundedArtifactIOError("bounded artifact write drifted")
    finally:
        os.close(descriptor)
    if read_bounded_artifact(lexical_root, target, limit) != data:
        raise BoundedArtifactIOError("bounded artifact verification failed")
    return target


def _exclusive_descriptor(root: Path, target: Path, relative: PurePath) -> int:
    if os.name == "posix" and hasattr(os, "O_NOFOLLOW"):
        return _openat_exclusive(root, relative)
    _reject_linklike_components(root, target.parent)
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(target, flags, 0o600)
    try:
        _validate_open_target(root, target, descriptor)
    except Exception:
        os.close(descriptor)
        raise
    return descriptor


def _openat_exclusive(root: Path, relative: PurePath) -> int:
    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    current = os.open(root, directory_flags)
    try:
        for part in relative.parts[:-1]:
            child = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = child
        return os.open(relative.parts[-1], file_flags, 0o600, dir_fd=current)
    finally:
        os.close(current)


def _validate_open_target(root: Path, target: Path, descriptor: int) -> None:
    _reject_linklike_components(root, target)
    try:
        target.resolve(strict=True).relative_to(root.resolve(strict=True))
        by_path = target.lstat()
        by_handle = os.fstat(descriptor)
    except (OSError, ValueError) as error:
        raise BoundedArtifactIOError("bounded artifact escaped its root") from error
    if _identity(by_path) != _identity(by_handle):
        raise BoundedArtifactIOError("bounded artifact handle identity drifted")


def _reject_linklike_components(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise BoundedArtifactIOError("bounded artifact escaped its root") from error
    current = root
    for part in relative.parts:
        current /= part
        junction = getattr(current, "is_junction", None)
        if current.is_symlink() or bool(callable(junction) and junction()):
            raise BoundedArtifactIOError("bounded artifact path contains a link")


def _write_all(descriptor: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise BoundedArtifactIOError("bounded artifact write made no progress")
        view = view[written:]


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


__all__ = [
    "BoundedArtifactIOError", "read_bounded_artifact",
    "write_immutable_artifact",
]
