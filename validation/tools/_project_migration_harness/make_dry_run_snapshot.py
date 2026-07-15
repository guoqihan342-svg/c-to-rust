from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256, safe_posix_path
from .make_dry_run_cas import validated_make_output_root
from .make_dry_run_snapshot_io import (
    MAX_SNAPSHOT_FILES, MAX_SNAPSHOT_FILE_BYTES, MAX_SNAPSHOT_TOTAL_BYTES,
    snapshot_repository_files,
)


MAKE_SNAPSHOT_KIND = "project-migration-make-repository-snapshot"
MAX_SNAPSHOT_MANIFEST_BYTES = 64 * 1024 * 1024
_FIELDS = {
    "schema_version", "artifact_kind", "status", "collector_output_root",
    "excluded_paths", "files", "file_count", "total_bytes",
    "semantic_gate", "translation_coverage_numerator", "snapshot_sha256",
}


def capture_repository_snapshot(
    repo_root: Path, staging_workspace: Path, *, collector_output_root: str,
) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("make_snapshot_repository_invalid")
    destination = staging_workspace.resolve(strict=False)
    if destination.exists():
        raise ValueError("make_snapshot_staging_exists")
    if destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("make_snapshot_staging_not_independent")
    destination.mkdir(parents=True, mode=0o700)
    manifest = _snapshot(
        root, collector_output_root=collector_output_root,
        destination=destination,
    )
    if len(canonical_json_bytes(manifest)) > MAX_SNAPSHOT_MANIFEST_BYTES:
        raise ValueError("make_snapshot_manifest_limit_exceeded")
    return manifest


def validate_repository_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("make_snapshot_fields_invalid")
    out_root = validated_make_output_root(value.get("collector_output_root"))
    expected_exclusions = [".git", out_root]
    files = value.get("files")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != MAKE_SNAPSHOT_KIND
        or value.get("status") != "ready"
        or value.get("excluded_paths") != expected_exclusions
        or not isinstance(files, list) or not files
        or type(value.get("file_count")) is not int
        or value.get("file_count") != len(files)
        or not 0 < len(files) <= MAX_SNAPSHOT_FILES
        or type(value.get("total_bytes")) is not int
        or not 0 <= value.get("total_bytes") <= MAX_SNAPSHOT_TOTAL_BYTES
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("make_snapshot_policy_invalid")
    checked = [_file_reference(item) for item in files]
    paths = [item["path"] for item in checked]
    if paths != sorted(set(paths)):
        raise ValueError("make_snapshot_paths_not_canonical")
    if sum(item["size_bytes"] for item in checked) != value["total_bytes"]:
        raise ValueError("make_snapshot_total_bytes_invalid")
    if any(_is_excluded(PurePosixPath(path).parts, expected_exclusions) for path in paths):
        raise ValueError("make_snapshot_excluded_path_bound")
    core = {key: value[key] for key in _FIELDS if key != "snapshot_sha256"}
    if value.get("snapshot_sha256") != content_sha256(core):
        raise ValueError("make_snapshot_sha256_invalid")
    result = dict(value)
    result["files"] = checked
    return result


def canonical_repository_snapshot_bytes(value: Any) -> bytes:
    data = canonical_json_bytes(validate_repository_snapshot(value))
    if len(data) > MAX_SNAPSHOT_MANIFEST_BYTES:
        raise ValueError("make_snapshot_manifest_limit_exceeded")
    return data


def verify_repository_snapshot(repo_root: Path, value: Any) -> dict[str, Any]:
    expected = validate_repository_snapshot(value)
    actual = _snapshot(
        repo_root.resolve(strict=True),
        collector_output_root=expected["collector_output_root"],
        destination=None,
    )
    if actual != expected:
        raise ValueError("make_snapshot_repository_drift")
    return expected


def snapshot_file_map(value: Any) -> dict[str, dict[str, Any]]:
    checked = validate_repository_snapshot(value)
    return {item["path"]: dict(item) for item in checked["files"]}


def _snapshot(
    root: Path, *, collector_output_root: str, destination: Path | None,
) -> dict[str, Any]:
    out_root, exclusions, files, total = snapshot_repository_files(
        root,
        collector_output_root=collector_output_root,
        destination=destination,
    )
    core = {
        "schema_version": 1,
        "artifact_kind": MAKE_SNAPSHOT_KIND,
        "status": "ready",
        "collector_output_root": out_root,
        "excluded_paths": exclusions,
        "files": files,
        "file_count": len(files),
        "total_bytes": total,
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return validate_repository_snapshot({
        **core, "snapshot_sha256": content_sha256(core),
    })


def _file_reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        raise ValueError("make_snapshot_file_ref_invalid")
    size = value.get("size_bytes")
    if (
        not safe_posix_path(value.get("path"))
        or not is_sha256(value.get("sha256"))
        or type(size) is not int or not 0 <= size <= MAX_SNAPSHOT_FILE_BYTES
    ):
        raise ValueError("make_snapshot_file_ref_invalid")
    return {
        "path": value["path"], "sha256": value["sha256"], "size_bytes": size,
    }


def _is_excluded(parts: tuple[str, ...], exclusions: list[str]) -> bool:
    for value in exclusions:
        excluded = PurePosixPath(value).parts
        if tuple(parts[:len(excluded)]) == excluded:
            return True
    return False


__all__ = [
    "MAKE_SNAPSHOT_KIND", "MAX_SNAPSHOT_FILE_BYTES",
    "MAX_SNAPSHOT_MANIFEST_BYTES", "canonical_repository_snapshot_bytes",
    "capture_repository_snapshot", "snapshot_file_map",
    "validate_repository_snapshot", "verify_repository_snapshot",
]
