from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import content_sha256
from .build_facts import file_binding, is_linklike


MAKE_COMMAND_PREFIX = (
    "make", "-n", "--no-builtin-rules", "--no-builtin-variables",
)
MAKE_TEST_COMMAND = [*MAKE_COMMAND_PREFIX, "test"]
AUTOMAKE_CHECK_COMMAND = [*MAKE_COMMAND_PREFIX, "check"]
MAX_SCAN_DIRECTORIES = 4_096
MAX_MANIFESTS = 256
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MANIFEST_TOTAL_BYTES = 8 * 1024 * 1024
_ASSIGNMENT = re.compile(
    r"^\s*(TESTS|check_PROGRAMS)\s*(?:\+=|:=|\?=|=)", re.ASCII,
)
_KINDS = {"automake-content-v1": "check", "fixed-make-test-v1": "test"}
_VARIABLES = frozenset({"TESTS", "check_PROGRAMS"})


def select_make_test_command(repo_root: Path) -> dict[str, Any]:
    try:
        root = Path(repo_root)
        if is_linklike(root):
            raise ValueError("linked repository root")
        root = root.resolve(strict=True)
        if not root.is_dir():
            raise ValueError("repository root is not a directory")
        manifests = _scan_manifests(root)
    except (OSError, UnicodeError, ValueError):
        return _blocked("project_test_automake_manifest_scan_failed")
    declared = any(item["variables"] for item in manifests)
    root_manifest = any(item["path"] == "Makefile.am" for item in manifests)
    automake = declared and root_manifest
    kind = "automake-content-v1" if automake else "fixed-make-test-v1"
    binding = {
        "schema_version": 1,
        "kind": kind,
        "target": _KINDS[kind],
        "manifests": manifests,
        "manifest_set_sha256": content_sha256(manifests),
    }
    return {
        "status": "selected",
        "command": list(
            AUTOMAKE_CHECK_COMMAND if automake else MAKE_TEST_COMMAND
        ),
        "target_binding": binding,
    }


def command_for_target_binding(value: Any) -> list[str] | None:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "kind", "target", "manifests",
        "manifest_set_sha256",
    }:
        return None
    kind, manifests = value.get("kind"), value.get("manifests")
    if value.get("schema_version") != 1 or kind not in _KINDS:
        return None
    if value.get("target") != _KINDS[kind] or not isinstance(manifests, list):
        return None
    paths: list[str] = []
    total_bytes = 0
    declared = False
    for item in manifests:
        if not _valid_manifest(item):
            return None
        paths.append(str(item["path"]))
        total_bytes += int(item["size_bytes"])
        declared = declared or bool(item["variables"])
    if (
        paths != sorted(set(paths)) or len(paths) > MAX_MANIFESTS
        or total_bytes > MAX_MANIFEST_TOTAL_BYTES
    ):
        return None
    if value.get("manifest_set_sha256") != content_sha256(manifests):
        return None
    root_manifest = "Makefile.am" in paths
    automake = declared and root_manifest
    if (kind == "automake-content-v1") is not automake:
        return None
    return list(
        AUTOMAKE_CHECK_COMMAND if automake else MAKE_TEST_COMMAND
    )


def verify_make_target_binding(repo_root: Path, value: Any) -> bool:
    expected = select_make_test_command(repo_root)
    return (
        expected.get("status") == "selected"
        and expected.get("target_binding") == value
    )


def _scan_manifests(root: Path) -> list[dict[str, Any]]:
    manifests: list[dict[str, Any]] = []
    directories_seen = 0
    total_bytes = 0
    for current_text, directories, files in os.walk(
        root, topdown=True, followlinks=False,
    ):
        directories_seen += 1
        if directories_seen > MAX_SCAN_DIRECTORIES:
            raise ValueError("automake manifest directory limit exceeded")
        current = Path(current_text)
        directories[:] = sorted(
            name for name in directories
            if name != ".git" and not is_linklike(current / name)
        )
        if "Makefile.am" not in files:
            continue
        path = current / "Makefile.am"
        if is_linklike(path):
            raise ValueError("linked automake manifest")
        if len(manifests) >= MAX_MANIFESTS:
            raise ValueError("automake manifest count limit exceeded")
        binding = file_binding(root, path, max_bytes=MAX_MANIFEST_BYTES)
        total_bytes += int(binding["size_bytes"])
        if total_bytes > MAX_MANIFEST_TOTAL_BYTES:
            raise ValueError("automake manifest total size limit exceeded")
        data = path.read_bytes()
        if (
            len(data) != binding["size_bytes"]
            or hashlib.sha256(data).hexdigest() != binding["sha256"]
        ):
            raise ValueError("automake manifest changed during scan")
        text = data.decode("utf-8-sig", errors="strict")
        manifests.append({
            **binding,
            "variables": sorted({
                match.group(1)
                for line in text.splitlines()
                if (match := _ASSIGNMENT.match(_strip_comment(line)))
            }),
        })
    return sorted(manifests, key=lambda item: str(item["path"]))


def _strip_comment(line: str) -> str:
    escaped = False
    for index, character in enumerate(line):
        if character == "#" and not escaped:
            return line[:index]
        escaped = character == "\\" and not escaped
        if character != "\\":
            escaped = False
    return line


def _valid_manifest(value: Any) -> bool:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes", "variables",
    }:
        return False
    path = value.get("path")
    relative = PurePosixPath(path) if isinstance(path, str) else None
    size, variables = value.get("size_bytes"), value.get("variables")
    return (
        relative is not None and not relative.is_absolute()
        and ".." not in relative.parts and "\\" not in str(path)
        and relative.name == "Makefile.am"
        and isinstance(value.get("sha256"), str)
        and re.fullmatch(r"[0-9a-f]{64}", str(value["sha256"])) is not None
        and isinstance(size, int) and not isinstance(size, bool)
        and 0 <= size <= MAX_MANIFEST_BYTES
        and isinstance(variables, list)
        and variables == sorted(set(variables))
        and set(variables) <= _VARIABLES
    )


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = [
    "AUTOMAKE_CHECK_COMMAND", "MAKE_TEST_COMMAND",
    "command_for_target_binding", "select_make_test_command",
    "verify_make_target_binding",
]
