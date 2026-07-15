from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any

from .artifacts import content_sha256
from .build_ir import is_sha256, safe_posix_path


MAX_TARGETS = 64
MAX_TARGET_BYTES = 256


def fixed_make_argv(
    makefile: str, targets: Sequence[str], *, working_directory: str = ".",
) -> list[str]:
    normalized = validated_targets(targets)
    if not safe_posix_path(makefile):
        raise ValueError("make_dry_run_makefile_ref_invalid")
    workdir = validated_working_directory(working_directory)
    argument = makefile_argument(makefile, workdir)
    return [
        "make", "-B", "-n", "-j1", "--no-print-directory",
        "-f", argument, "--", *normalized,
    ]


def make_input_sha256(
    makefile_ref: Mapping[str, Any], input_refs: Sequence[Mapping[str, Any]],
    toolchain_ref: Mapping[str, Any],
    *, working_directory: str = ".",
    repository_snapshot_ref: Mapping[str, Any] | None = None,
) -> str:
    workdir = validated_working_directory(working_directory)
    snapshot = (
        validated_artifact_ref(repository_snapshot_ref)
        if repository_snapshot_ref is not None else None
    )
    payload = {
        "binding_mode": (
            "repository-snapshot" if snapshot is not None
            else "declared-input-refs"
        ),
        "makefile_ref": validated_artifact_ref(makefile_ref),
        "working_directory": workdir,
        "toolchain_ref": validated_artifact_ref(toolchain_ref),
        "repository_snapshot_ref": snapshot,
    }
    if snapshot is None:
        payload["input_refs"] = sorted(
            (validated_artifact_ref(item) for item in input_refs),
            key=lambda item: item["path"],
        )
    return content_sha256(payload)


def makefile_argument(makefile: str, working_directory: str = ".") -> str:
    if not safe_posix_path(makefile):
        raise ValueError("make_dry_run_makefile_ref_invalid")
    return repository_path_argument(makefile, working_directory)


def repository_path_argument(path: str, working_directory: str = ".") -> str:
    if not safe_posix_path(path):
        raise ValueError("make_dry_run_repository_path_invalid")
    workdir = validated_working_directory(working_directory)
    path_parts = list(PurePosixPath(path).parts)
    workdir_parts = [] if workdir == "." else list(PurePosixPath(workdir).parts)
    common = 0
    while (
        common < len(path_parts)
        and common < len(workdir_parts)
        and path_parts[common] == workdir_parts[common]
    ):
        common += 1
    parts = [".."] * (len(workdir_parts) - common) + path_parts[common:]
    if not parts:
        raise ValueError("make_dry_run_repository_path_invalid")
    return PurePosixPath(*parts).as_posix()


def normalize_repository_path(value: str, working_directory: str = ".") -> str:
    workdir = validated_working_directory(working_directory)
    if (
        not isinstance(value, str) or not value or len(value) > 4096
        or "\\" in value or "\x00" in value or "\r" in value or "\n" in value
    ):
        raise ValueError("make_dry_run_path_escape")
    posix = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        posix.is_absolute() or windows.is_absolute() or windows.drive
        or (posix.parts and posix.parts[0].startswith("~"))
    ):
        raise ValueError("make_dry_run_path_escape")
    parts = [] if workdir == "." else list(PurePosixPath(workdir).parts)
    for part in posix.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                raise ValueError("make_dry_run_path_escape")
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise ValueError("make_dry_run_path_escape")
    normalized = PurePosixPath(*parts).as_posix()
    if not safe_posix_path(normalized):
        raise ValueError("make_dry_run_path_escape")
    return normalized


def validated_working_directory(value: str) -> str:
    if value == ".":
        return value
    if not safe_posix_path(value):
        raise ValueError("make_dry_run_working_directory_invalid")
    return value


def validated_targets(value: Sequence[str]) -> list[str]:
    if (
        isinstance(value, (str, bytes)) or not isinstance(value, Sequence)
        or not 0 < len(value) <= MAX_TARGETS
    ):
        raise ValueError("make_dry_run_targets_invalid")
    result = list(value)
    for target in result:
        path = PurePosixPath(target) if isinstance(target, str) else None
        if (
            not isinstance(target, str) or not target
            or len(target.encode("utf-8")) > MAX_TARGET_BYTES
            or not re.fullmatch(r"[A-Za-z0-9_.+/@%=-]+", target)
            or target.startswith(("-", "~", "/")) or path is None
            or ".." in path.parts or path.as_posix() != target
        ):
            raise ValueError("make_dry_run_target_invalid")
    if len(result) != len(set(result)):
        raise ValueError("make_dry_run_targets_duplicate")
    return result


def validated_artifact_ref(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("make_dry_run_input_ref_invalid")
    size = value.get("size_bytes")
    if (
        not safe_posix_path(value.get("path"))
        or not is_sha256(value.get("sha256"))
        or isinstance(size, bool) or not isinstance(size, int) or size < 0
    ):
        raise ValueError("make_dry_run_input_ref_invalid")
    return {"path": value["path"], "sha256": value["sha256"], "size_bytes": size}


__all__ = [
    "fixed_make_argv", "make_input_sha256", "makefile_argument",
    "normalize_repository_path", "repository_path_argument", "validated_targets",
    "validated_artifact_ref", "validated_working_directory",
]
