from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from .native_object_inspection import inspect_native_object


GUEST_ROOTS = ("/lib64", "/usr", "/lib")
_EXPECTED_OBJECT = {
    "shared-library": ("elf", "shared-object"),
    "static-archive": ("unix-ar", "static-archive"),
}


def normalize_native_guest_roots(
    guest_roots: Mapping[str, Path] | None,
) -> dict[str, Path]:
    if guest_roots is None:
        return {guest: Path(guest).resolve(strict=False) for guest in GUEST_ROOTS}
    if not isinstance(guest_roots, Mapping) or set(guest_roots) != set(GUEST_ROOTS):
        raise ValueError("native_link_guest_roots_invalid")
    roots = dict(guest_roots)
    if any(
        not isinstance(value, Path) or not value.is_absolute()
        for value in roots.values()
    ):
        raise ValueError("native_link_guest_roots_invalid")
    return roots


def inspect_mapped_native_artifact(
    guest_path: str,
    library_format: str,
    roots: Mapping[str, Path],
) -> tuple[str, dict[str, Any] | None]:
    guest_root = next(
        (
            root for root in GUEST_ROOTS
            if guest_path == root or guest_path.startswith(root + "/")
        ),
        None,
    )
    if guest_root is None:
        return "native_link_guest_root_unsupported", None
    relative = PurePosixPath(guest_path).relative_to(guest_root)
    host_path = roots[guest_root].joinpath(*relative.parts)
    try:
        roots_before = _resolved_roots(roots)
        resolved_before = host_path.resolve(strict=True)
    except FileNotFoundError:
        return "native_link_actual_artifact_missing", None
    except (OSError, RuntimeError):
        return "native_link_actual_artifact_unavailable", None
    if not _inside_any_root(resolved_before, roots_before):
        return "native_link_actual_artifact_path_escape", None
    try:
        before = resolved_before.stat()
    except OSError:
        return "native_link_actual_artifact_unavailable", None
    if not stat.S_ISREG(before.st_mode):
        return "native_link_actual_artifact_not_regular", None
    try:
        inspection = inspect_native_object(resolved_before)
    except (OSError, RuntimeError, TypeError, ValueError):
        return "native_link_actual_artifact_inspection_failed", None
    try:
        roots_after = _resolved_roots(roots)
        resolved_after = host_path.resolve(strict=True)
        after = resolved_after.stat()
    except (OSError, RuntimeError):
        return "native_link_actual_artifact_unstable", None
    if (
        roots_before != roots_after
        or resolved_before != resolved_after
        or not _inside_any_root(resolved_after, roots_after)
        or not stat.S_ISREG(after.st_mode)
        or _stat_identity(before) != _stat_identity(after)
        or inspection.get("size_bytes") != after.st_size
    ):
        return "native_link_actual_artifact_unstable", None
    expected_format, expected_kind = _EXPECTED_OBJECT[library_format]
    if (
        inspection.get("object_format") != expected_format
        or inspection.get("object_kind") != expected_kind
    ):
        return "native_link_actual_artifact_type_mismatch", dict(inspection)
    return "native_link_actual_artifact_observed", dict(inspection)


def reopen_mapped_native_artifact_path(
    guest_path: str,
    library_format: str,
    roots: Mapping[str, Path],
    expected_inspection: Mapping[str, Any],
) -> Path:
    """Return a host-only path after recomputing the path-free inspection."""
    reason, inspection = inspect_mapped_native_artifact(
        guest_path, library_format, roots,
    )
    if (
        reason != "native_link_actual_artifact_observed"
        or inspection != dict(expected_inspection)
    ):
        raise ValueError("native_link_actual_artifact_reopen_drift")
    guest_root = next(
        root for root in GUEST_ROOTS
        if guest_path == root or guest_path.startswith(root + "/")
    )
    relative = PurePosixPath(guest_path).relative_to(guest_root)
    resolved = roots[guest_root].joinpath(*relative.parts).resolve(strict=True)
    if not _inside_any_root(resolved, _resolved_roots(roots)):
        raise ValueError("native_link_actual_artifact_reopen_escape")
    return resolved


def _resolved_roots(roots: Mapping[str, Path]) -> tuple[Path, ...]:
    return tuple(roots[root].resolve(strict=False) for root in GUEST_ROOTS)


def _inside_any_root(path: Path, roots: tuple[Path, ...]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev, value.st_ino, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns,
    )


__all__ = [
    "GUEST_ROOTS", "inspect_mapped_native_artifact",
    "normalize_native_guest_roots", "reopen_mapped_native_artifact_path",
]
