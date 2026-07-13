from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


BUILD_MARKERS = {
    "CMakeLists.txt": "cmake",
    "GNUmakefile": "make",
    "Makefile": "make",
    "makefile": "make",
    "meson.build": "meson",
}
MAX_BUILD_DIRECTORIES = 4_096
MAX_BUILD_MARKERS = 256
MAX_BUILD_MARKER_BYTES = 1024 * 1024
MAX_BUILD_MARKER_TOTAL_BYTES = 8 * 1024 * 1024


def is_absolute_any_platform(value: str) -> bool:
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or (callable(is_junction) and is_junction())


def repository_path(repo_root: Path, path: Path) -> str:
    relative = path.resolve().relative_to(repo_root.resolve())
    return "." if not relative.parts else relative.as_posix()


def resolve_repository_path(
    repo_root: Path,
    value: str | Path,
    *,
    base: Path | None = None,
    reject_links: bool = True,
) -> Path:
    root = repo_root.resolve()
    raw = str(value)
    if is_absolute_any_platform(raw) and not Path(raw).is_absolute():
        raise ValueError("foreign_absolute_path")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = (base or root) / candidate
    lexical = Path(os.path.abspath(candidate))
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise ValueError("path_outside_repository") from error
    if reject_links:
        current = Path(lexical.anchor)
        for part in lexical.parts[1:]:
            current /= part
            if current.exists() and is_linklike(current):
                raise ValueError("linked_path_component")
    return resolved


def sha256_file(path: Path, *, max_bytes: int | None = None) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise ValueError("file_size_limit_exceeded")
            digest.update(chunk)
    return digest.hexdigest()


def file_binding(
    repo_root: Path, path: Path, *, max_bytes: int | None = None
) -> dict[str, Any]:
    resolved = resolve_repository_path(repo_root, path)
    if not resolved.is_file() or is_linklike(resolved):
        raise ValueError("not_regular_file")
    size = resolved.stat().st_size
    if max_bytes is not None and size > max_bytes:
        raise ValueError("file_size_limit_exceeded")
    return {
        "path": repository_path(repo_root, resolved),
        "sha256": sha256_file(resolved, max_bytes=max_bytes),
        "size_bytes": size,
    }


def json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compiler_name(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1].removesuffix(".exe")


def summarize_path(
    value: str, repo_root: Path, working_directory: Path
) -> dict[str, Any]:
    try:
        resolved = resolve_repository_path(
            repo_root, value, base=working_directory, reject_links=False
        )
    except (OSError, ValueError):
        return {"path": "<external-path>", "scope": "external"}
    return {"path": repository_path(repo_root, resolved), "scope": "repository"}


def is_source_argument(
    argument: str,
    repo_root: Path,
    working_directory: Path,
    source_path: Path,
) -> bool:
    if argument.startswith("-"):
        return False
    try:
        return resolve_repository_path(
            repo_root, argument, base=working_directory, reject_links=False
        ) == source_path
    except (OSError, ValueError):
        return False


def normalize_response_files(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    files = report.get("files") if isinstance(report, dict) else None
    if not isinstance(files, list):
        return []
    normalized = []
    for item in files:
        if not isinstance(item, dict):
            continue
        current = dict(item)
        path = current.get("path")
        if isinstance(path, str) and path.startswith("<source-root>/"):
            current["path"] = path[len("<source-root>/"):]
        normalized.append(current)
    return sorted(normalized, key=lambda item: str(item.get("path", "")))


def rejection(
    entry_index: int,
    entry_sha256: str,
    reason: str,
    blocking: bool,
    **details: Any,
) -> dict[str, Any]:
    return {
        "entry_index": entry_index,
        "entry_sha256": entry_sha256,
        "reason": reason,
        "blocking": blocking,
        **details,
    }


def detect_build_system_facts(repo_root: Path) -> dict[str, Any]:
    root = repo_root.resolve()
    markers: list[dict[str, Any]] = []
    blockers: list[str] = []
    directory_count = 0
    marker_bytes = 0
    for current_text, directories, files in os.walk(root, topdown=True, followlinks=False):
        directory_count += 1
        if directory_count > MAX_BUILD_DIRECTORIES:
            blockers.append("build_fact_directory_limit_exceeded")
            directories[:] = []
            break
        current = Path(current_text)
        directories[:] = sorted(
            name
            for name in directories
            if name != ".git" and not is_linklike(current / name)
        )
        for name in sorted(files):
            build_system = BUILD_MARKERS.get(name)
            path = current / name
            if build_system is None or is_linklike(path):
                continue
            try:
                size = path.stat().st_size
                if size > MAX_BUILD_MARKER_BYTES:
                    blockers.append("build_marker_size_limit_exceeded")
                    continue
                if marker_bytes + size > MAX_BUILD_MARKER_TOTAL_BYTES:
                    blockers.append("build_marker_total_size_limit_exceeded")
                    directories[:] = []
                    break
                if len(markers) >= MAX_BUILD_MARKERS:
                    blockers.append("build_marker_count_limit_exceeded")
                    directories[:] = []
                    break
                binding = file_binding(root, path, max_bytes=MAX_BUILD_MARKER_BYTES)
            except (OSError, ValueError):
                continue
            marker_bytes += binding["size_bytes"]
            markers.append({"build_system": build_system, **binding})
        if blockers and blockers[-1] in {
            "build_marker_total_size_limit_exceeded",
            "build_marker_count_limit_exceeded",
        }:
            break
    markers.sort(key=lambda item: (item["path"], item["build_system"]))
    systems = sorted({item["build_system"] for item in markers})
    return {
        "status": "blocked" if blockers else ("detected" if markers else "not_detected"),
        "systems": systems,
        "markers": markers,
        "blockers": sorted(set(blockers)),
        "scan_limits": {
            "max_directories": MAX_BUILD_DIRECTORIES,
            "max_markers": MAX_BUILD_MARKERS,
            "max_marker_bytes": MAX_BUILD_MARKER_BYTES,
            "max_total_marker_bytes": MAX_BUILD_MARKER_TOTAL_BYTES,
        },
        "build_commands_executed": False,
    }


def detect_generated_build_facts(
    repo_root: Path, compile_database_path: Path
) -> dict[str, Any]:
    from .generated_build_facts import detect_generated_build_facts as detect

    return detect(repo_root, compile_database_path)


__all__ = [
    "detect_build_system_facts",
    "detect_generated_build_facts",
    "compiler_name",
    "file_binding",
    "is_source_argument",
    "is_linklike",
    "json_sha256",
    "normalize_response_files",
    "rejection",
    "repository_path",
    "resolve_repository_path",
    "summarize_path",
]
