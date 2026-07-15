from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from .build_ir import is_sha256, safe_posix_path
from .make_dry_run_binding import fixed_make_argv, validated_targets


class MakeDryRunContractError(ValueError):
    pass


def artifact_refs(value: Any, role: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        fail(f"make_dry_run_report_{role}_refs_invalid")
    result = [artifact_ref(item, role) for item in value]
    paths = [item["path"] for item in result]
    if paths != sorted(set(paths)):
        fail(f"make_dry_run_report_{role}_refs_not_canonical")
    return result


def artifact_ref(value: Any, role: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "path", "sha256", "size_bytes",
    }:
        fail(f"make_dry_run_{role}_ref_invalid")
    size = value.get("size_bytes")
    if (
        not safe_posix_path(value.get("path"))
        or not is_sha256(value.get("sha256"))
        or isinstance(size, bool) or not isinstance(size, int) or size < 0
    ):
        fail(f"make_dry_run_{role}_ref_invalid")
    return {"path": value["path"], "sha256": value["sha256"], "size_bytes": size}


def targets(value: Any) -> list[str]:
    if not isinstance(value, list):
        fail("make_dry_run_targets_invalid")
    try:
        return validated_targets(value)
    except ValueError as error:
        fail(str(error))


def fixed_argv(
    makefile: str, selected_targets: Sequence[str], working_directory: str,
) -> list[str]:
    try:
        return fixed_make_argv(
            makefile, selected_targets, working_directory=working_directory,
        )
    except ValueError as error:
        fail(str(error))


def require_raw_cas_ref(reference: Mapping[str, Any], role: str) -> None:
    path = PurePosixPath(str(reference["path"]))
    expected = ("cas", role, f"{reference['sha256']}.bin")
    if len(path.parts) <= len(expected) or tuple(path.parts[-3:]) != expected:
        fail(f"make_dry_run_{role.replace('-', '_')}_ref_not_cas")


def require_snapshot_cas_ref(reference: Mapping[str, Any]) -> None:
    path = PurePosixPath(str(reference["path"]))
    expected = (
        "cas", "repository-snapshot", f"{reference['sha256']}.json",
    )
    if len(path.parts) <= len(expected) or tuple(path.parts[-3:]) != expected:
        fail("make_dry_run_repository_snapshot_ref_not_cas")


def fail(code: str) -> None:
    raise MakeDryRunContractError(code)


__all__ = [
    "MakeDryRunContractError", "artifact_ref", "artifact_refs", "fail",
    "fixed_argv", "require_raw_cas_ref", "require_snapshot_cas_ref", "targets",
]
