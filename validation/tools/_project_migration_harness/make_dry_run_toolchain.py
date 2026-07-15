from __future__ import annotations

from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .make_dry_run_host_evidence import MAKE_ENVIRONMENT, MAKE_RESOURCE_LIMITS


MAKE_TOOLCHAIN_KIND = "project-migration-make-dry-run-toolchain"
MAX_TOOL_BINARY_BYTES = 64 * 1024 * 1024
_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}\Z", re.ASCII)
_FIELDS = {
    "schema_version", "artifact_kind", "status", "backend", "backend_version",
    "launcher", "make", "environment", "resource_limits", "semantic_gate",
    "translation_coverage_numerator", "toolchain_sha256",
}


def create_make_toolchain_evidence(
    *, backend_version: str, launcher_sha256: str,
    launcher_size_bytes: int, make_version: str, make_sha256: str,
    make_size_bytes: int,
) -> dict[str, Any]:
    core = {
        "schema_version": 1,
        "artifact_kind": MAKE_TOOLCHAIN_KIND,
        "status": "ready",
        "backend": "bubblewrap-v1",
        "backend_version": backend_version,
        "launcher": {
            "name": "bwrap", "sha256": launcher_sha256,
            "size_bytes": launcher_size_bytes,
        },
        "make": {
            "name": "make", "implementation": "gnu-make",
            "version": make_version, "sha256": make_sha256,
            "size_bytes": make_size_bytes,
        },
        "environment": dict(MAKE_ENVIRONMENT),
        "resource_limits": dict(MAKE_RESOURCE_LIMITS),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return validate_make_toolchain_evidence({
        **core, "toolchain_sha256": content_sha256(core),
    })


def validate_make_toolchain_evidence(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _FIELDS:
        raise ValueError("make_dry_run_toolchain_fields_invalid")
    launcher = value.get("launcher")
    make = value.get("make")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != MAKE_TOOLCHAIN_KIND
        or value.get("status") != "ready"
        or value.get("backend") != "bubblewrap-v1"
        or not isinstance(value.get("backend_version"), str)
        or _VERSION.fullmatch(value["backend_version"]) is None
        or not _tool_record(launcher, {"name", "sha256", "size_bytes"})
        or not _tool_record(make, {
            "name", "implementation", "version", "sha256", "size_bytes",
        })
        or launcher.get("name") != "bwrap"
        or make.get("name") != "make"
        or make.get("implementation") != "gnu-make"
        or not isinstance(make.get("version"), str)
        or _VERSION.fullmatch(make["version"]) is None
        or value.get("environment") != dict(MAKE_ENVIRONMENT)
        or value.get("resource_limits") != dict(MAKE_RESOURCE_LIMITS)
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
    ):
        raise ValueError("make_dry_run_toolchain_policy_invalid")
    core = {key: value[key] for key in _FIELDS if key != "toolchain_sha256"}
    if value.get("toolchain_sha256") != content_sha256(core):
        raise ValueError("make_dry_run_toolchain_sha256_invalid")
    return dict(value)


def canonical_make_toolchain_evidence_bytes(value: Any) -> bytes:
    return canonical_json_bytes(validate_make_toolchain_evidence(value))


def trusted_executable(path: Path, expected_name: str) -> None:
    resolved = path.resolve(strict=True)
    metadata = resolved.stat()
    if (
        resolved.name != expected_name or not resolved.is_file()
        or not os.access(resolved, os.X_OK) or metadata.st_uid != 0
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or metadata.st_size > MAX_TOOL_BINARY_BYTES
    ):
        raise ValueError("make_dry_run_executable_untrusted")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_TOOL_BINARY_BYTES:
                raise ValueError("make_dry_run_tool_binary_too_large")
            digest.update(chunk)
    return digest.hexdigest()


def gnu_make_version(path: Path) -> str:
    completed = subprocess.run(
        [str(path), "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        timeout=5,
        check=False,
    )
    if (
        completed.returncode != 0 or completed.stderr
        or len(completed.stdout) > 64 * 1024
    ):
        raise ValueError("make_dry_run_make_version_untrusted")
    try:
        first = completed.stdout.decode("utf-8", errors="strict").splitlines()[0]
    except (IndexError, UnicodeError) as error:
        raise ValueError("make_dry_run_make_version_untrusted") from error
    matched = re.fullmatch(r"GNU Make ([0-9][0-9A-Za-z.+_-]{0,63})", first)
    if matched is None:
        raise ValueError("make_dry_run_make_version_untrusted")
    return matched.group(1)


def valid_backend_version(value: str) -> bool:
    return isinstance(value, str) and _VERSION.fullmatch(value) is not None


def _tool_record(value: Any, fields: set[str]) -> bool:
    if not isinstance(value, Mapping) or set(value) != fields:
        return False
    size = value.get("size_bytes")
    return (
        is_sha256(value.get("sha256"))
        and type(size) is int and 0 < size <= MAX_TOOL_BINARY_BYTES
    )


__all__ = [
    "MAKE_TOOLCHAIN_KIND", "MAX_TOOL_BINARY_BYTES",
    "canonical_make_toolchain_evidence_bytes", "create_make_toolchain_evidence",
    "file_sha256", "gnu_make_version", "trusted_executable",
    "valid_backend_version", "validate_make_toolchain_evidence",
]
