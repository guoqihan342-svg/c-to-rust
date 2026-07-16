from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePath
import stat

from .bounded_artifact_io import read_bounded_artifact


@dataclass
class DirectoryAnchor:
    path: Path
    descriptor: int | None
    device: int
    inode: int

    def close(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None


def open_directory_anchor(path: Path) -> DirectoryAnchor:
    lexical = Path(os.path.abspath(path))
    if _is_linklike(lexical):
        raise ValueError("anchored_directory_link_rejected")
    if os.name == "posix" and hasattr(os, "O_DIRECTORY"):
        flags = (
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            descriptor = os.open(lexical, flags)
            metadata = os.fstat(descriptor)
        except OSError as error:
            raise ValueError("anchored_directory_unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode):
            os.close(descriptor)
            raise ValueError("anchored_directory_invalid")
        anchor = DirectoryAnchor(
            lexical, descriptor, metadata.st_dev, metadata.st_ino,
        )
    else:
        try:
            metadata = lexical.stat(follow_symlinks=False)
        except OSError as error:
            raise ValueError("anchored_directory_unavailable") from error
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("anchored_directory_invalid")
        anchor = DirectoryAnchor(lexical, None, metadata.st_dev, metadata.st_ino)
    validate_directory_anchor(anchor)
    return anchor


def validate_directory_anchor(anchor: DirectoryAnchor) -> None:
    if not isinstance(anchor, DirectoryAnchor) or _is_linklike(anchor.path):
        raise ValueError("anchored_directory_identity_drift")
    try:
        by_path = anchor.path.stat(follow_symlinks=False)
        by_handle = (
            os.fstat(anchor.descriptor)
            if anchor.descriptor is not None else by_path
        )
    except OSError as error:
        raise ValueError("anchored_directory_identity_drift") from error
    expected = (anchor.device, anchor.inode)
    if (
        not stat.S_ISDIR(by_path.st_mode)
        or not stat.S_ISDIR(by_handle.st_mode)
        or (by_path.st_dev, by_path.st_ino) != expected
        or (by_handle.st_dev, by_handle.st_ino) != expected
    ):
        raise ValueError("anchored_directory_identity_drift")


def read_anchored_artifact(
    anchor: DirectoryAnchor, relative: PurePath, limit: int,
) -> bytes:
    if (
        relative.is_absolute() or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
        or type(limit) is not int or limit <= 0
    ):
        raise ValueError("anchored_artifact_contract_invalid")
    validate_directory_anchor(anchor)
    if anchor.descriptor is None:
        data = read_bounded_artifact(
            anchor.path, anchor.path.joinpath(*relative.parts), limit,
        )
    else:
        data = _read_posix(anchor, relative, limit)
    validate_directory_anchor(anchor)
    return data


def _read_posix(
    anchor: DirectoryAnchor, relative: PurePath, limit: int,
) -> bytes:
    if anchor.descriptor is None:
        raise ValueError("anchored_directory_descriptor_missing")
    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = (
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    current = os.dup(anchor.descriptor)
    try:
        for part in relative.parts[:-1]:
            metadata = os.stat(part, dir_fd=current, follow_symlinks=False)
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("anchored_artifact_link_rejected")
            child = os.open(part, directory_flags, dir_fd=current)
            if not _same_entry(metadata, os.fstat(child)):
                os.close(child)
                raise ValueError("anchored_artifact_directory_drift")
            os.close(current)
            current = child
        name = relative.parts[-1]
        metadata = os.stat(name, dir_fd=current, follow_symlinks=False)
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("anchored_artifact_link_rejected")
        descriptor = os.open(name, file_flags, dir_fd=current)
        try:
            data = _read_file(descriptor, metadata, limit)
            current_path = os.stat(name, dir_fd=current, follow_symlinks=False)
            if not _same_file(metadata, current_path):
                raise ValueError("anchored_artifact_file_drift")
            return data
        finally:
            os.close(descriptor)
    except OSError as error:
        raise ValueError("anchored_artifact_unavailable") from error
    finally:
        os.close(current)


def _read_file(descriptor: int, metadata: os.stat_result, limit: int) -> bytes:
    before = os.fstat(descriptor)
    if (
        not stat.S_ISREG(before.st_mode) or not _same_file(metadata, before)
        or before.st_size > limit
    ):
        raise ValueError("anchored_artifact_file_invalid")
    chunks = bytearray()
    while True:
        chunk = os.read(descriptor, min(1024 * 1024, limit + 1 - len(chunks)))
        if not chunk:
            break
        chunks.extend(chunk)
        if len(chunks) > limit:
            raise ValueError("anchored_artifact_size_limit")
    after = os.fstat(descriptor)
    if not _same_file(before, after) or len(chunks) != after.st_size:
        raise ValueError("anchored_artifact_file_drift")
    return bytes(chunks)


def _same_entry(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, stat.S_IFMT(left.st_mode)) == (
        right.st_dev, right.st_ino, stat.S_IFMT(right.st_mode),
    )


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    return _same_entry(left, right) and (
        left.st_size, left.st_mtime_ns
    ) == (
        right.st_size, right.st_mtime_ns
    )


def _is_linklike(path: Path) -> bool:
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(callable(junction) and junction())


__all__ = [
    "DirectoryAnchor", "open_directory_anchor", "read_anchored_artifact",
    "validate_directory_anchor",
]
