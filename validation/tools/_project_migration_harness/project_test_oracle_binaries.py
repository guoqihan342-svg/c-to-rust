from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .build_facts import is_linklike, resolve_repository_path
from .project_test_oracle_snapshot import copy_stable_file


def copy_oracle_binaries(
    repo_root: Path, destination: Path, tests: Mapping[str, Mapping[str, Any]],
) -> dict[str, Path]:
    destination.mkdir(mode=0o700)
    result = {}
    for test_id, test in tests.items():
        binding = test["source_executable"]
        source = resolve_repository_path(repo_root, str(binding["path"]))
        metadata = source.stat(follow_symlinks=False)
        if not source.is_file() or is_linklike(source):
            raise ValueError("project_test_source_executable_invalid")
        output = destination / test_id
        digest = copy_stable_file(source, output, metadata)
        if metadata.st_size != binding.get("size_bytes") or digest != binding.get("sha256"):
            raise ValueError("project_test_source_executable_binding_drifted")
        output.chmod((metadata.st_mode & 0o777) | 0o500)
        result[test_id] = output
    return result


def candidate_binaries(
    build_runtime: Path, mappings: Mapping[str, Mapping[str, Any]],
) -> dict[str, Path]:
    result = {}
    target_root = (build_runtime / "target" / "debug").resolve(strict=True)
    for source_target, mapping in mappings.items():
        path = target_root / str(mapping["rust_target_name"])
        resolved = path.resolve(strict=True)
        resolved.relative_to(target_root)
        if not resolved.is_file() or is_linklike(path) or not (resolved.stat().st_mode & 0o111):
            raise ValueError("project_test_candidate_executable_invalid")
        result[source_target] = resolved
    return result


def tests_by_id(inventory: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result = {}
    for test in inventory["tests"]:
        test_id = str(test["test_id"])
        if test_id in result or PurePosixPath(test_id).name != test_id:
            raise ValueError("project_test_id_invalid")
        result[test_id] = test
    return result


__all__ = ["candidate_binaries", "copy_oracle_binaries", "tests_by_id"]
