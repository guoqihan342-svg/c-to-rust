from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import canonical_json_bytes
from .build_facts import is_linklike
from .build_ir import is_sha256, safe_posix_path
from .make_dry_run_binding import make_input_sha256
from .make_dry_run_contract import (
    MAX_STDERR_BYTES, canonical_make_dry_run_report_bytes,
    validate_make_dry_run_report,
)
from .make_dry_run_host_evidence import (
    canonical_make_host_preflight_bytes, validate_make_host_preflight,
)
from .make_dry_run_parser import MAX_STDOUT_BYTES, parse_make_dry_run_stdout
from .make_dry_run_runner import (
    canonical_make_dry_run_plan_bytes, validate_make_dry_run_plan,
)
from .make_dry_run_snapshot import (
    canonical_repository_snapshot_bytes, verify_repository_snapshot,
)


MAX_REPORT_BYTES = 8 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024


class MakeDryRunReopenError(ValueError):
    pass


def reopen_make_dry_run_report(
    repo_root: str | Path, reference: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    data = _read_bound(root, reference, "report", MAX_REPORT_BYTES)
    report = _strict_object(data, "report")
    try:
        if canonical_make_dry_run_report_bytes(report) != data:
            raise MakeDryRunReopenError("make_report_not_canonical")
    except ValueError as error:
        raise MakeDryRunReopenError(str(error)) from error
    return verify_make_dry_run_report_inputs(root, report)


def verify_make_dry_run_report_inputs(
    repo_root: str | Path, value: Mapping[str, Any],
) -> dict[str, Any]:
    root = Path(repo_root).resolve(strict=True)
    try:
        report = validate_make_dry_run_report(value)
        opened = _reopen_refs(root, report)
        parsed = parse_make_dry_run_stdout(
            opened["raw_stdout_ref"],
            working_directory=report["working_directory"],
        )
        if (
            parsed["parser"] != report["parser"]
            or parsed["raw_stdout"] != report["raw_stdout"]
            or parsed["commands"] != report["commands"]
        ):
            raise MakeDryRunReopenError("make_report_raw_stdout_drift")
        plan = _strict_object(opened["execution_plan_ref"], "execution_plan")
        if canonical_make_dry_run_plan_bytes(plan) != opened["execution_plan_ref"]:
            raise MakeDryRunReopenError("make_report_plan_not_canonical")
        checked_plan = validate_make_dry_run_plan(
            plan,
            expected_command=report["make_argv"],
            expected_input_sha256=make_input_sha256(
                report["makefile_ref"], report["input_refs"],
                report["toolchain_ref"],
                working_directory=report["working_directory"],
                repository_snapshot_ref=report["repository_snapshot_ref"],
            ),
        )
        if (
            checked_plan["plan_sha256"] != report["execution_plan_sha256"]
            or checked_plan["working_directory"] != report["working_directory"]
            or checked_plan["repository_snapshot_ref"]
            != report["repository_snapshot_ref"]
        ):
            raise MakeDryRunReopenError("make_report_execution_plan_drift")
        sandbox = _strict_object(opened["sandbox_ref"], "sandbox")
        if canonical_make_host_preflight_bytes(sandbox) != opened["sandbox_ref"]:
            raise MakeDryRunReopenError("make_report_sandbox_not_canonical")
        validate_make_host_preflight(
            sandbox,
            expected_plan_sha256=checked_plan["plan_sha256"],
            expected_toolchain_sha256=report["toolchain_ref"]["sha256"],
        )
        if report["repository_snapshot_ref"] is not None:
            snapshot = _strict_object(
                opened["repository_snapshot_ref"], "repository_snapshot",
            )
            if (
                canonical_repository_snapshot_bytes(snapshot)
                != opened["repository_snapshot_ref"]
            ):
                raise MakeDryRunReopenError(
                    "make_report_repository_snapshot_not_canonical"
                )
            checked_snapshot = verify_repository_snapshot(root, snapshot)
            by_path = {
                item["path"]: item for item in checked_snapshot["files"]
            }
            bound_inputs = [
                report["makefile_ref"], *report["source_refs"],
                *report["input_refs"],
            ]
            if any(by_path.get(item["path"]) != item for item in bound_inputs):
                raise MakeDryRunReopenError(
                    "make_report_repository_snapshot_binding_drift"
                )
    except MakeDryRunReopenError:
        raise
    except (OSError, TypeError, UnicodeError, ValueError) as error:
        raise MakeDryRunReopenError(str(error) or "make_report_reopen_failed") from error
    return report


def _reopen_refs(root: Path, report: Mapping[str, Any]) -> dict[str, bytes]:
    roles: list[tuple[str, Mapping[str, Any], int]] = [
        ("makefile_ref", report["makefile_ref"], MAX_EVIDENCE_BYTES),
        ("toolchain_ref", report["toolchain_ref"], MAX_EVIDENCE_BYTES),
        ("sandbox_ref", report["sandbox_ref"], MAX_EVIDENCE_BYTES),
        ("execution_plan_ref", report["execution_plan_ref"], MAX_EVIDENCE_BYTES),
        ("raw_stdout_ref", report["raw_stdout_ref"], MAX_STDOUT_BYTES),
        ("raw_stderr_ref", report["raw_stderr_ref"], MAX_STDERR_BYTES),
    ]
    if report["repository_snapshot_ref"] is not None:
        roles.append((
            "repository_snapshot_ref", report["repository_snapshot_ref"],
            MAX_EVIDENCE_BYTES,
        ))
    roles.extend(
        (f"source_ref:{index}", reference, MAX_EVIDENCE_BYTES)
        for index, reference in enumerate(report["source_refs"])
    )
    roles.extend(
        (f"input_ref:{index}", reference, MAX_EVIDENCE_BYTES)
        for index, reference in enumerate(report["input_refs"])
    )
    by_binding: dict[tuple[str, str, int], bytes] = {}
    result: dict[str, bytes] = {}
    for role, reference, limit in roles:
        identity = (
            str(reference["path"]), str(reference["sha256"]),
            int(reference["size_bytes"]),
        )
        data = by_binding.get(identity)
        if data is None:
            data = _read_bound(root, reference, role, limit)
            by_binding[identity] = data
        result[role] = data
    return result


def _read_bound(
    root: Path, reference: Mapping[str, Any], label: str, limit: int,
) -> bytes:
    if not isinstance(reference, Mapping) or set(reference) != {
        "path", "sha256", "size_bytes",
    }:
        raise MakeDryRunReopenError(f"make_report_{label}_reference_invalid")
    relative = reference.get("path")
    size = reference.get("size_bytes")
    if (
        not safe_posix_path(relative) or not is_sha256(reference.get("sha256"))
        or isinstance(size, bool) or not isinstance(size, int)
        or not 0 <= size <= limit
    ):
        raise MakeDryRunReopenError(f"make_report_{label}_reference_invalid")
    current = root
    for part in PurePosixPath(relative).parts:
        current /= part
        if current.exists() and is_linklike(current):
            raise MakeDryRunReopenError(f"make_report_{label}_linked_path")
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise MakeDryRunReopenError(f"make_report_{label}_path_invalid") from error
    if not resolved.is_file() or resolved.stat().st_size != size:
        raise MakeDryRunReopenError(f"make_report_{label}_size_drift")
    data = resolved.read_bytes()
    if hashlib.sha256(data).hexdigest() != reference["sha256"]:
        raise MakeDryRunReopenError(f"make_report_{label}_sha256_drift")
    return data


def _strict_object(data: bytes, label: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise MakeDryRunReopenError(f"make_report_{label}_duplicate_key")
            result[key] = value
        return result
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MakeDryRunReopenError(f"make_report_{label}_invalid_json") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise MakeDryRunReopenError(f"make_report_{label}_not_canonical")
    return value


__all__ = [
    "MakeDryRunReopenError", "reopen_make_dry_run_report",
    "verify_make_dry_run_report_inputs",
]
