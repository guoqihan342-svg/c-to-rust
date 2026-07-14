from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any


def hash_stable_file(
    path: Path, *, executable: bool, limit: int,
) -> dict[str, Any]:
    data, identity = read_stable_file(path, limit, executable=executable)
    return {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": identity["size_bytes"],
    }


def read_stable_file(
    path: Path, limit: int, *, executable: bool = False,
) -> tuple[bytes, dict[str, Any]]:
    try:
        resolved = path.resolve(strict=True)
        path_before = resolved.stat()
        with resolved.open("rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
                raise ValueError("stable_file_invalid")
            if executable and os.name != "nt" and not os.access(resolved, os.X_OK):
                raise ValueError("stable_file_not_executable")
            data = handle.read(limit + 1)
            after = os.fstat(handle.fileno())
        path_after = resolved.stat()
    except OSError as error:
        raise ValueError("stable_file_unavailable") from error
    if len(data) > limit or _stat_identity(path_before) != _stat_identity(before):
        raise ValueError("stable_file_invalid")
    if (
        _stat_identity(before) != _stat_identity(after)
        or _stat_identity(after) != _stat_identity(path_after)
    ):
        raise ValueError("stable_file_changed_while_reading")
    return data, {
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns


__all__ = ["hash_stable_file", "read_stable_file"]
