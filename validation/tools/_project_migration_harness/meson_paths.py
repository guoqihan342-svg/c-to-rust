from __future__ import annotations

import hashlib
import os
from pathlib import Path
import stat
from typing import Any

from .build_facts import is_absolute_any_platform, is_linklike


FILE_LIMITS = {
    "build_ninja": 16 * 1024 * 1024,
    "info": 256 * 1024,
    "targets": 8 * 1024 * 1024,
    "buildoptions": 2 * 1024 * 1024,
    "dependencies": 4 * 1024 * 1024,
    "compilers": 2 * 1024 * 1024,
    "buildsystem_files": 2 * 1024 * 1024,
}
MAX_SNAPSHOT_BYTES = 36 * 1024 * 1024
MAX_REFERENCED_BYTES = 512 * 1024 * 1024
MAX_REFERENCED_FILE_BYTES = 256 * 1024 * 1024
INFO_FILES = {
    "info": "meson-info.json",
    "targets": "intro-targets.json",
    "buildoptions": "intro-buildoptions.json",
    "dependencies": "intro-dependencies.json",
    "compilers": "intro-compilers.json",
    "buildsystem_files": "intro-buildsystem_files.json",
}


class MesonPathError(ValueError):
    pass


def fixed_paths(build_root: Path) -> dict[str, Path]:
    info_root = build_root / "meson-info"
    paths = {"build_ninja": build_root / "build.ninja"}
    paths.update({name: info_root / filename for name, filename in INFO_FILES.items()})
    return paths


def meson_signal(root: Path, build_root: Path) -> dict[str, bool]:
    return {
        "meson_info_manifest": path_present(build_root / "meson-info/meson-info.json"),
        "meson_info_path": path_present(build_root / "meson-info"),
        "meson_private_path": path_present(build_root / "meson-private"),
        "meson_ninja_header": _meson_ninja_header(root, build_root / "build.ninja"),
    }


def path_present(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except OSError:
        return False


def read_snapshot_files(
    root: Path, paths: dict[str, Path],
) -> tuple[dict[str, bytes], list[dict[str, Any]]]:
    raw_files: dict[str, bytes] = {}
    bindings: list[dict[str, Any]] = []
    total = 0
    for name, path in paths.items():
        raw = read_bounded(root, path, FILE_LIMITS[name])
        total += len(raw)
        if total > MAX_SNAPSHOT_BYTES:
            raise MesonPathError("meson_snapshot_size_limit_exceeded")
        raw_files[name] = raw
        bindings.append(file_binding(root, path, raw))
    return raw_files, bindings


def recheck_snapshot_files(
    root: Path, paths: dict[str, Path], expected: dict[str, bytes],
) -> None:
    for name, path in paths.items():
        if read_bounded(root, path, FILE_LIMITS[name]) != expected[name]:
            raise MesonPathError("meson_snapshot_drift_during_read")


def configured_directory(root: Path, value: str, role: str) -> Path:
    path = confined_path(root, value)
    if not path.is_dir():
        raise MesonPathError(f"meson_{role}_directory_missing")
    return path


def configured_file(root: Path, value: str) -> Path:
    path = confined_path(root, value)
    if not path.is_file():
        raise MesonPathError("meson_referenced_file_missing")
    return path


def declared_file(root: Path, value: str) -> tuple[Path, bool]:
    path = confined_path(root, value)
    if not path_present(path):
        return path, False
    if not path.is_file():
        raise MesonPathError("meson_declared_output_not_regular_file")
    return path, True


def confined_path(root: Path, value: str) -> Path:
    root = Path(os.path.abspath(root)).resolve()
    if not is_absolute_any_platform(value):
        raise MesonPathError("meson_path_not_absolute")
    candidate = Path(value)
    if not candidate.is_absolute():
        raise MesonPathError("meson_foreign_absolute_path")
    lexical = Path(os.path.abspath(candidate))
    _reject_reparse_absolute(lexical)
    canonical = lexical.resolve(strict=False)
    try:
        canonical.relative_to(root)
    except ValueError as error:
        raise MesonPathError("meson_path_outside_repository") from error
    _reject_reparse_components(root, canonical)
    return canonical


def repository_lexical_path(root: Path, path: Path) -> str:
    relative = Path(os.path.abspath(path)).resolve(strict=False).relative_to(
        Path(os.path.abspath(root)).resolve()
    )
    return "." if not relative.parts else relative.as_posix()


def read_bounded(root: Path, path: Path, limit: int) -> bytes:
    from .meson_safe_io import read_bounded as read

    return read(root, path, limit)


def hash_binding(root: Path, path: Path, limit: int) -> dict[str, Any]:
    from .meson_safe_io import hash_binding as bind

    return bind(root, path, limit)


def file_binding(root: Path, path: Path, raw: bytes) -> dict[str, Any]:
    return {
        "path": repository_lexical_path(root, path),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "kind": "file",
    }


def _reject_reparse_components(root: Path, path: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise MesonPathError("meson_path_outside_repository") from error
    current = root
    if path_present(current) and _is_reparse(current):
        raise MesonPathError("meson_reparse_path")
    for part in relative.parts:
        current /= part
        if path_present(current) and _is_reparse(current):
            raise MesonPathError("meson_reparse_path")


def _reject_reparse_absolute(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if path_present(current) and _is_reparse(current):
            raise MesonPathError("meson_reparse_path")


def _is_reparse(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except OSError:
        attributes = 0
    marker = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return is_linklike(path) or bool(attributes & marker)


def _meson_ninja_header(root: Path, path: Path) -> bool:
    from .meson_safe_io import meson_ninja_header

    return meson_ninja_header(root, path)


__all__ = [
    "FILE_LIMITS", "INFO_FILES", "MAX_REFERENCED_BYTES",
    "MAX_REFERENCED_FILE_BYTES", "MAX_SNAPSHOT_BYTES", "MesonPathError",
    "configured_directory", "configured_file", "confined_path", "declared_file",
    "fixed_paths", "hash_binding", "meson_signal", "path_present",
    "read_snapshot_files", "recheck_snapshot_files", "repository_lexical_path",
]
