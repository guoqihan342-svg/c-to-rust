from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .artifacts import canonical_json_bytes, content_sha256
from .build_ir import is_sha256
from .make_dry_run_host_evidence import (
    MAKE_REQUIRED_CAPABILITIES, create_make_host_preflight,
    validate_make_host_preflight,
)
from .make_dry_run_binding import fixed_make_argv, make_input_sha256
from .make_dry_run_contract import MAX_STDERR_BYTES
from .make_dry_run_parser import MAX_STDOUT_BYTES
from .make_dry_run_result import MakeDryRunExecution, MakeDryRunOutcome


MAKE_PLAN_KIND = "project-migration-make-dry-run-plan"
MAKE_ENVIRONMENT_ALLOWLIST = ("LANG", "LC_ALL", "MAKEFLAGS", "PATH", "TMPDIR")
_PLAN_FIELDS = {
    "schema_version", "artifact_kind", "status", "command", "input_sha256",
    "timeout_seconds", "max_stdout_bytes", "max_stderr_bytes",
    "environment_allowlist", "required_capabilities", "semantic_gate",
    "translation_coverage_numerator", "plan_sha256",
}


@dataclass(frozen=True, slots=True)
class MakeDryRunPreflight:
    backend: str
    plan_sha256: str
    toolchain_sha256: str
    capability_results: tuple[tuple[str, bool], ...]
    cleanup_ready: bool

    def payload(self) -> dict[str, Any]:
        return create_make_host_preflight(
            backend=self.backend,
            plan_sha256=self.plan_sha256,
            toolchain_sha256=self.toolchain_sha256,
            capability_results=dict(self.capability_results),
            cleanup_ready=self.cleanup_ready,
        )


class MakeDryRunHostBackend(Protocol):
    def preflight(
        self, plan: Mapping[str, Any], *, project_root: Path, runtime_root: Path,
    ) -> MakeDryRunPreflight: ...

    def execute(
        self, make_binary: Path, make_args: Sequence[str], *,
        project_root: Path, runtime_root: Path, plan: Mapping[str, Any],
        preflight: MakeDryRunPreflight,
    ) -> MakeDryRunExecution: ...


def create_make_dry_run_plan(
    *, makefile_ref: Mapping[str, Any], input_refs: Sequence[Mapping[str, Any]],
    toolchain_ref: Mapping[str, Any],
    targets: Sequence[str], timeout_seconds: int = 300,
) -> dict[str, Any]:
    command = fixed_make_argv(str(makefile_ref.get("path")), targets)
    core = {
        "schema_version": 1,
        "artifact_kind": MAKE_PLAN_KIND,
        "status": "ready",
        "command": command,
        "input_sha256": make_input_sha256(makefile_ref, input_refs, toolchain_ref),
        "timeout_seconds": timeout_seconds,
        "max_stdout_bytes": MAX_STDOUT_BYTES,
        "max_stderr_bytes": MAX_STDERR_BYTES,
        "environment_allowlist": list(MAKE_ENVIRONMENT_ALLOWLIST),
        "required_capabilities": list(MAKE_REQUIRED_CAPABILITIES),
        "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    return validate_make_dry_run_plan({**core, "plan_sha256": content_sha256(core)})


def validate_make_dry_run_plan(
    value: Any, *, expected_command: Sequence[str] | None = None,
    expected_input_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _PLAN_FIELDS:
        raise ValueError("make_dry_run_plan_fields_invalid")
    timeout = value.get("timeout_seconds")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != MAKE_PLAN_KIND
        or value.get("status") != "ready"
        or type(timeout) is not int or not 30 <= timeout <= 3_600
        or value.get("max_stdout_bytes") != MAX_STDOUT_BYTES
        or value.get("max_stderr_bytes") != MAX_STDERR_BYTES
        or value.get("environment_allowlist") != list(MAKE_ENVIRONMENT_ALLOWLIST)
        or value.get("required_capabilities") != list(MAKE_REQUIRED_CAPABILITIES)
        or value.get("semantic_gate") is not False
        or value.get("translation_coverage_numerator") != 0
        or not is_sha256(value.get("input_sha256"))
    ):
        raise ValueError("make_dry_run_plan_policy_invalid")
    command = value.get("command")
    if not isinstance(command, list) or len(command) < 9:
        raise ValueError("make_dry_run_plan_command_invalid")
    try:
        expected_fixed = fixed_make_argv(command[6], command[8:])
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("make_dry_run_plan_command_invalid") from error
    if command != expected_fixed:
        raise ValueError("make_dry_run_plan_command_invalid")
    if expected_command is not None and command != list(expected_command):
        raise ValueError("make_dry_run_plan_command_drift")
    if expected_input_sha256 is not None and value["input_sha256"] != expected_input_sha256:
        raise ValueError("make_dry_run_plan_input_drift")
    core = {key: value[key] for key in _PLAN_FIELDS if key != "plan_sha256"}
    if value.get("plan_sha256") != content_sha256(core):
        raise ValueError("make_dry_run_plan_sha256_invalid")
    return dict(value)


def canonical_make_dry_run_plan_bytes(value: Any) -> bytes:
    return canonical_json_bytes(validate_make_dry_run_plan(value))


def run_make_dry_run(
    plan: Mapping[str, Any], *, project_root: Path, runtime_root: Path,
    make_binary: Path, toolchain_ref: Mapping[str, Any],
    sandbox_ref: Mapping[str, Any], backend: MakeDryRunHostBackend | None,
) -> MakeDryRunOutcome:
    try:
        checked = validate_make_dry_run_plan(plan)
    except ValueError:
        return _blocked("make_plan_invalid")
    plan_sha = str(checked["plan_sha256"])
    if backend is None:
        return _blocked("make_host_backend_unavailable", plan_sha=plan_sha)
    if make_binary.name.lower() not in {"make", "make.exe"}:
        return _blocked("make_binary_invalid", plan_sha=plan_sha)
    try:
        preflight = backend.preflight(
            checked, project_root=project_root, runtime_root=runtime_root,
        )
        _validate_preflight(preflight, checked, toolchain_ref, sandbox_ref)
    except (OSError, TypeError, ValueError):
        return _blocked("make_host_capability_unavailable", plan_sha=plan_sha)
    try:
        result = backend.execute(
            make_binary, checked["command"][1:], project_root=project_root,
            runtime_root=runtime_root, plan=checked, preflight=preflight,
        )
    except (OSError, TypeError, ValueError):
        return _blocked("make_host_execution_rejected", started=True, plan_sha=plan_sha)
    return _execution_outcome(result, checked, sandbox_ref)


def _validate_preflight(
    value: Any, plan: Mapping[str, Any], toolchain: Mapping[str, Any],
    sandbox: Mapping[str, Any],
) -> None:
    if not isinstance(value, MakeDryRunPreflight):
        raise ValueError("make preflight type is invalid")
    payload = value.payload()
    validate_make_host_preflight(
        payload, expected_plan_sha256=str(plan["plan_sha256"]),
        expected_toolchain_sha256=str(toolchain.get("sha256")),
    )
    if (
        content_sha256(payload) != sandbox.get("sha256")
        or value.cleanup_ready is not True
    ):
        raise ValueError("make preflight capability binding is invalid")


def _execution_outcome(
    result: Any, plan: Mapping[str, Any], sandbox: Mapping[str, Any],
) -> MakeDryRunOutcome:
    plan_sha = str(plan["plan_sha256"])
    if not isinstance(result, MakeDryRunExecution):
        return _blocked("make_execution_binding_invalid", started=True, plan_sha=plan_sha)
    command_sha = content_sha256(plan["command"])
    if (
        result.plan_sha256 != plan_sha or result.command_sha256 != command_sha
        or result.command_started is not True
    ):
        return _blocked("make_execution_binding_invalid", started=True, plan_sha=plan_sha)
    flooded = (
        len(result.stdout) > plan["max_stdout_bytes"]
        or len(result.stderr) > plan["max_stderr_bytes"]
    )
    blocker = None
    if result.timed_out:
        blocker = "make_timeout"
    elif flooded:
        blocker = "make_output_flood"
    elif result.cleanup_verified is not True:
        blocker = "make_exit_cleanup_unverified"
    elif type(result.returncode) is not int or result.returncode != 0:
        blocker = "make_exit_nonzero"
    if blocker:
        return MakeDryRunOutcome(
            "blocked", blocker, True, result.returncode, result.timed_out,
            flooded, result.cleanup_verified, plan_sha, None,
        )
    return MakeDryRunOutcome(
        "ready", None, True, 0, False, False, True, plan_sha,
        str(sandbox["sha256"]),
        result.stdout, result.stderr,
    )


def _blocked(
    blocker: str, *, started: bool = False, plan_sha: str | None = None,
) -> MakeDryRunOutcome:
    return MakeDryRunOutcome(
        "blocked", blocker, started, None, False, False, False, plan_sha, None,
    )


__all__ = [
    "MAKE_REQUIRED_CAPABILITIES", "MakeDryRunExecution", "MakeDryRunHostBackend",
    "MakeDryRunOutcome", "MakeDryRunPreflight", "canonical_make_dry_run_plan_bytes",
    "create_make_dry_run_plan", "run_make_dry_run", "validate_make_dry_run_plan",
]
