from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .build_facts import is_linklike, resolve_repository_path
from .project_test_inventory_paths import referenced_repo_paths
from .project_test_oracle_snapshot import (
    MAX_SNAPSHOT_BYTES, MAX_SNAPSHOT_FILES, copy_stable_file,
)


def materialize_project_test_input_snapshot(
    repo_root: Path, destination: Path, inventory: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    target = Path(destination)
    tests = inventory.get("tests")
    if (
        not root.is_dir() or is_linklike(root) or target.exists()
        or not isinstance(tests, list) or not tests
    ):
        raise ValueError("project_test_input_snapshot_root_invalid")
    source_executables = _source_executables(tests)
    working_directories = _working_directories(tests)
    required_inputs = sorted({
        path for test in tests if isinstance(test, Mapping)
        for path in referenced_repo_paths(test)
    })
    _reject_oracle_overlap(required_inputs, source_executables)
    target.mkdir(parents=True, mode=0o700)
    directory_records: dict[str, dict[str, Any]] = {}
    file_records: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for relative in [".", *working_directories]:
        _ensure_directory(root, target, relative, directory_records)
    for relative in _minimal_roots(required_inputs):
        total_bytes = _copy_input(
            root, target, relative, directory_records, file_records, total_bytes,
        )
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-input-snapshot",
        "file_count": len(file_records),
        "directory_count": len(directory_records),
        "size_bytes": total_bytes,
        "files": [file_records[key] for key in sorted(file_records)],
        "directories": [directory_records[key] for key in sorted(directory_records)],
        "required_inputs": required_inputs,
        "working_directories": working_directories,
        "source_executables": source_executables,
        "policy": {
            "implicit_working_directory_inputs": "forbidden",
            "source_executables": "separate-sandbox-binding",
            "links": "forbidden", "special_files": "forbidden",
            "git_metadata": "forbidden",
        },
    }
    payload["snapshot_sha256"] = content_sha256(payload)
    _validate_snapshot_references(payload)
    return payload


def _copy_input(
    root: Path, target: Path, relative: str,
    directories: dict[str, dict[str, Any]], files: dict[str, dict[str, Any]],
    total_bytes: int,
) -> int:
    source = resolve_repository_path(root, relative)
    if not source.exists() or ".git" in PurePosixPath(relative).parts:
        raise ValueError("project_test_input_path_missing")
    if source.is_file():
        return _copy_file(root, target, source, directories, files, total_bytes)
    if not source.is_dir() or is_linklike(source):
        raise ValueError("project_test_input_type_forbidden")
    stack = [source]
    while stack:
        current = stack.pop()
        current_relative = current.relative_to(root).as_posix() or "."
        _ensure_directory(root, target, current_relative, directories)
        try:
            entries = sorted(os.scandir(current), key=lambda item: item.name)
        except OSError as error:
            raise ValueError("project_test_input_directory_unreadable") from error
        children = []
        for entry in entries:
            if entry.name == ".git":
                raise ValueError("project_test_input_git_metadata_forbidden")
            metadata = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or stat.S_ISLNK(metadata.st_mode):
                raise ValueError("project_test_input_link_forbidden")
            path = Path(entry.path)
            if stat.S_ISDIR(metadata.st_mode):
                children.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                total_bytes = _copy_file(
                    root, target, path, directories, files, total_bytes,
                )
            else:
                raise ValueError("project_test_input_special_file_forbidden")
        stack.extend(reversed(children))
    return total_bytes


def _copy_file(
    root: Path, target: Path, source: Path,
    directories: dict[str, dict[str, Any]], files: dict[str, dict[str, Any]],
    total_bytes: int,
) -> int:
    relative = source.relative_to(root).as_posix()
    if relative in files:
        return total_bytes
    metadata = source.stat(follow_symlinks=False)
    if len(files) >= MAX_SNAPSHOT_FILES:
        raise ValueError("project_test_input_file_limit_exceeded")
    total_bytes += metadata.st_size
    if total_bytes > MAX_SNAPSHOT_BYTES:
        raise ValueError("project_test_input_byte_limit_exceeded")
    parent = source.parent.relative_to(root).as_posix() or "."
    _ensure_directory(root, target, parent, directories)
    output = target / Path(*PurePosixPath(relative).parts)
    digest = copy_stable_file(source, output, metadata)
    files[relative] = {
        "path": relative, "sha256": digest, "size_bytes": metadata.st_size,
        "mode": metadata.st_mode & 0o777,
    }
    return total_bytes


def _ensure_directory(
    root: Path, target: Path, relative: str,
    records: dict[str, dict[str, Any]],
) -> None:
    parts = () if relative == "." else PurePosixPath(relative).parts
    for index in range(len(parts) + 1):
        item = "." if index == 0 else "/".join(parts[:index])
        if item in records:
            continue
        source = root if item == "." else resolve_repository_path(root, item)
        if not source.is_dir() or is_linklike(source):
            raise ValueError("project_test_input_working_directory_invalid")
        metadata = source.stat(follow_symlinks=False)
        output = target if item == "." else target / Path(*PurePosixPath(item).parts)
        output.mkdir(parents=True, exist_ok=True, mode=0o700)
        output.chmod(metadata.st_mode & 0o777)
        records[item] = {"path": item, "mode": metadata.st_mode & 0o777}


def _source_executables(tests: list[Any]) -> list[str]:
    result = set()
    for test in tests:
        binding = test.get("source_executable") if isinstance(test, Mapping) else None
        path = binding.get("path") if isinstance(binding, Mapping) else None
        if not isinstance(path, str) or not path:
            raise ValueError("project_test_source_executable_binding_invalid")
        result.add(path)
    return sorted(result)


def _working_directories(tests: list[Any]) -> list[str]:
    values = []
    for test in tests:
        value = test.get("working_directory") if isinstance(test, Mapping) else None
        if not isinstance(value, str) or not value:
            raise ValueError("project_test_working_directory_invalid")
        values.append(value)
    return sorted(set(values))


def _reject_oracle_overlap(inputs: list[str], executables: list[str]) -> None:
    for source in executables:
        source_parts = PurePosixPath(source).parts
        for value in inputs:
            input_parts = PurePosixPath(value).parts
            if source_parts[:len(input_parts)] == input_parts:
                raise ValueError("project_test_input_contains_source_executable")


def _minimal_roots(paths: list[str]) -> list[str]:
    result = []
    for value in sorted(paths, key=lambda item: (len(PurePosixPath(item).parts), item)):
        parts = PurePosixPath(value).parts
        if not any(parts[:len(PurePosixPath(item).parts)] == PurePosixPath(item).parts
                   for item in result):
            result.append(value)
    return result


def _validate_snapshot_references(payload: Mapping[str, Any]) -> None:
    indexed = {str(item["path"]) for item in payload["files"]}
    indexed.update(str(item["path"]) for item in payload["directories"])
    if any(path not in indexed for path in payload["required_inputs"]):
        raise ValueError("project_test_input_snapshot_reference_missing")
    if any(path not in indexed for path in payload["working_directories"]):
        raise ValueError("project_test_input_snapshot_working_directory_missing")


__all__ = ["materialize_project_test_input_snapshot"]
