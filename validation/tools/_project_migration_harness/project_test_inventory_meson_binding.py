from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .discovery_database import MAX_COMPILE_DATABASE_BYTES
from .meson_introspection import inspect_meson_introspection
from .meson_paths import (
    MAX_REFERENCED_BYTES, MAX_REFERENCED_FILE_BYTES, MAX_SNAPSHOT_BYTES,
    MesonPathError,
    hash_binding, read_bounded,
)
from .meson_schema_common import MAX_BUILDSYSTEM_FILES, strict_json


MESON_TEST_ADAPTER = "meson-introspect-tests-v1"
MAX_MESON_TEST_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_MESON_TEST_STDERR_BYTES = 1024 * 1024
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_BINDING_KEYS = {
    "adapter_version", "build_directory", "compile_database",
    "meson_snapshot_sha256", "snapshot_files", "buildsystem_files",
    "intro_tests", "binding_sha256",
}


def capture_meson_test_build_binding(
    repo_root: Path, compile_database_path: Path,
) -> tuple[dict[str, Any], list[Any]]:
    root = Path(repo_root).resolve(strict=True)
    database = Path(compile_database_path).resolve(strict=True)
    try:
        database.relative_to(root)
        report = inspect_meson_introspection(root, database)
        if report.get("status") != "ready":
            raise ValueError("project_test_meson_snapshot_unavailable")
        build_directory = str(report["build_root"])
        if database.parent != _repository_path(root, build_directory):
            raise ValueError("project_test_meson_build_directory_mismatch")
        _validate_tests_information(root, database.parent)
        intro_path = database.parent / "meson-info" / "intro-tests.json"
        intro_raw = read_bounded(root, intro_path, MAX_MESON_TEST_OUTPUT_BYTES)
        payload = strict_json(intro_raw, "tests")
        if not isinstance(payload, list):
            raise ValueError("project_test_meson_tests_schema_invalid")
        binding = {
            "adapter_version": MESON_TEST_ADAPTER,
            "build_directory": build_directory,
            "compile_database": hash_binding(
                root, database, MAX_COMPILE_DATABASE_BYTES,
            ),
            "meson_snapshot_sha256": report.get("snapshot_sha256"),
            "snapshot_files": report.get("snapshot_files"),
            "buildsystem_files": report.get("buildsystem_files"),
            "intro_tests": hash_binding(
                root, intro_path, MAX_MESON_TEST_OUTPUT_BYTES,
            ),
        }
        binding["binding_sha256"] = content_sha256(binding)
        validate_meson_test_build_binding(binding)
        return binding, payload
    except (KeyError, MesonPathError, OSError, TypeError, ValueError) as error:
        raise ValueError("project_test_meson_build_binding_invalid") from error


def validate_meson_test_build_binding(value: Any) -> None:
    if (
        not isinstance(value, Mapping) or set(value) != _BINDING_KEYS
        or value.get("adapter_version") != MESON_TEST_ADAPTER
        or value.get("binding_sha256") != content_sha256({
            key: item for key, item in value.items()
            if key != "binding_sha256"
        })
        or _SHA256.fullmatch(str(value.get("meson_snapshot_sha256"))) is None
    ):
        raise ValueError("project_test_meson_build_binding_invalid")
    build = _relative_directory(value.get("build_directory"))
    database = _file_binding(
        value.get("compile_database"), MAX_COMPILE_DATABASE_BYTES,
    )
    intro = _file_binding(
        value.get("intro_tests"), MAX_MESON_TEST_OUTPUT_BYTES,
    )
    if (
        PurePosixPath(str(database["path"])).parent != build
        or PurePosixPath(str(intro["path"]))
        != build / "meson-info" / "intro-tests.json"
    ):
        raise ValueError("project_test_meson_build_binding_invalid")
    snapshots = _binding_list(
        value.get("snapshot_files"), maximum=16,
        per_file_maximum=MAX_SNAPSHOT_BYTES, total_maximum=MAX_SNAPSHOT_BYTES,
    )
    build_files = _binding_list(
        value.get("buildsystem_files"), maximum=MAX_BUILDSYSTEM_FILES,
        per_file_maximum=MAX_REFERENCED_FILE_BYTES,
        total_maximum=MAX_REFERENCED_BYTES,
    )
    snapshot_paths = {str(item["path"]) for item in snapshots}
    required = {
        str(build / "build.ninja"),
        str(build / "meson-info" / "meson-info.json"),
        str(build / "meson-info" / "intro-targets.json"),
    }
    if not required <= snapshot_paths or "meson.build" not in {
        str(item["path"]) for item in build_files
    }:
        raise ValueError("project_test_meson_build_binding_invalid")


def _binding_list(
    value: Any, *, maximum: int, per_file_maximum: int, total_maximum: int,
) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise ValueError("project_test_meson_file_binding_invalid")
    result = [_file_binding(item, per_file_maximum) for item in value]
    paths = [str(item["path"]) for item in result]
    if paths != sorted(set(paths)):
        raise ValueError("project_test_meson_file_binding_invalid")
    if sum(int(item["size_bytes"]) for item in result) > total_maximum:
        raise ValueError("project_test_meson_file_binding_invalid")
    return result


def _validate_tests_information(root: Path, build: Path) -> None:
    info_path = build / "meson-info" / "meson-info.json"
    raw = read_bounded(root, info_path, 256 * 1024)
    payload = strict_json(raw, "info")
    introspection = payload.get("introspection") if isinstance(
        payload, Mapping,
    ) else None
    information = introspection.get("information") if isinstance(
        introspection, Mapping,
    ) else None
    tests = information.get("tests") if isinstance(information, Mapping) else None
    if (
        not isinstance(tests, Mapping)
        or set(tests) != {"file", "updated"}
        or tests.get("file") != "intro-tests.json"
        or not isinstance(tests.get("updated"), bool)
    ):
        raise ValueError("project_test_meson_tests_information_invalid")


def _file_binding(value: Any, maximum_bytes: int) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes", "kind",
    }:
        raise ValueError("project_test_meson_file_binding_invalid")
    path = _relative_path(value.get("path"))
    size = value.get("size_bytes")
    if (
        str(path) == "." or value.get("kind") != "file"
        or _SHA256.fullmatch(str(value.get("sha256"))) is None
        or isinstance(size, bool) or not isinstance(size, int)
        or not 0 <= size <= maximum_bytes
    ):
        raise ValueError("project_test_meson_file_binding_invalid")
    return value


def _relative_directory(value: Any) -> PurePosixPath:
    return _relative_path(value)


def _relative_path(value: Any) -> PurePosixPath:
    path = PurePosixPath(value) if isinstance(value, str) else None
    if (
        path is None or not value or path.as_posix() != value
        or path.is_absolute() or "\\" in str(value)
        or any(part in {"", ".."} for part in path.parts)
        or (path.parts and (path.parts[0].startswith("~") or ":" in path.parts[0]))
    ):
        raise ValueError("project_test_meson_path_invalid")
    return path


def _repository_path(root: Path, value: str) -> Path:
    return root / Path(*_relative_directory(value).parts)


__all__ = [
    "MAX_MESON_TEST_OUTPUT_BYTES", "MAX_MESON_TEST_STDERR_BYTES",
    "MESON_TEST_ADAPTER", "capture_meson_test_build_binding",
    "validate_meson_test_build_binding",
]
