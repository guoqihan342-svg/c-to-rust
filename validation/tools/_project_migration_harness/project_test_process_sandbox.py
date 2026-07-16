from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .build_facts import is_linklike
from .sandbox_bubblewrap_argv import (
    build_bubblewrap_argv, redacted_bubblewrap_argv, resource_limiter,
)
from .sandbox_contract import SandboxContract, canonical_sha256
from .sandbox_environment import canonical_environment_items, cargo_guest_environment
from .sandbox_probe import SandboxProbeReceipt, validate_probe_receipt
from .sandbox_toolchain import file_sha256
from .project_test_stdin import MAX_PROJECT_TEST_STDIN_BYTES


MAX_CAPTURE_BYTES = 1024 * 1024 + 1
MAX_SUBJECT_BYTES = 1024 * 1024 * 1024
_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
Executor = Callable[..., subprocess.CompletedProcess[Any]]


def execute_isolated_project_test_process(
    *, launcher: Path, contract: SandboxContract, executor: Executor,
    executable: Path, workspace: Path, runtime: Path,
    arguments: Sequence[str], working_directory: str,
    environment: Mapping[str, str], timeout_seconds: int,
    input_sha256: str, standard_input: bytes,
    probe_receipt: SandboxProbeReceipt,
) -> dict[str, Any]:
    original_subject, original_project = Path(executable), Path(workspace)
    if is_linklike(original_subject) or is_linklike(original_project):
        raise ValueError("project_test_process_linked_input_forbidden")
    subject = original_subject.resolve(strict=True)
    project = original_project.resolve(strict=True)
    output = Path(runtime)
    _validate_inputs(
        subject, project, output, arguments, working_directory,
        environment, timeout_seconds, standard_input,
    )
    validate_probe_receipt(probe_receipt, contract, contract.requirements)
    executable_sha256 = file_sha256(subject)
    invocation = {
        "schema_version": 1, "purpose": "project-test-process",
        "executable_sha256": executable_sha256,
        "input_sha256": input_sha256,
        "arguments": list(arguments), "working_directory": working_directory,
        "environment": {key: environment[key] for key in sorted(environment)},
        "stdin_sha256": canonical_sha256_bytes(standard_input),
        "stdin_size_bytes": len(standard_input),
        "timeout_seconds": timeout_seconds,
        "sandbox_contract_sha256": contract.sha256,
        "sandbox_probe_receipt_sha256": probe_receipt.sha256,
    }
    invocation_sha256 = canonical_sha256(invocation)
    marker = output / "command.started"
    stdout_path, stderr_path = output / "stdout", output / "stderr"
    for name in ("home", "tmp"):
        (output / name).mkdir(mode=0o700)
    assignments = _environment_assignments(environment)
    guest_command = (
        "/bin/sh", "-c",
        "umask 077; printf '%s\\n%s\\n' \"$1\" \"$2\" > \"$3\" || exit 125; "
        "shift 3; exec /usr/bin/env -i \"$@\"",
        "sandbox-launch", contract.sha256, invocation_sha256,
        "/runtime/command.started", *assignments, "/subject", *arguments,
    )
    argv = build_bubblewrap_argv(
        launcher=launcher, workspace=project, runtime=output,
        tool_bindings=((subject, "/subject"),),
        environment=canonical_environment_items(cargo_guest_environment()),
        guest_command=guest_command,
        guest_working_directory=_guest_working_directory(working_directory),
    )
    timed_out = False
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            completed = executor(
                argv, cwd=output, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                input=standard_input, stdout=stdout, stderr=stderr,
                timeout=timeout_seconds, check=False,
                preexec_fn=resource_limiter(contract),
            )
        returncode = int(completed.returncode)
    except subprocess.TimeoutExpired:
        timed_out, returncode = True, None
    except (OSError, ValueError, subprocess.SubprocessError):
        return _blocked(invocation, invocation_sha256, "project_test_process_rejected")
    stdout = _read_capture(stdout_path)
    stderr = _read_capture(stderr_path)
    started = _marker_matches(marker, contract.sha256, invocation_sha256)
    executable_stable = file_sha256(subject) == executable_sha256
    oversized = len(stdout) >= MAX_CAPTURE_BYTES or len(stderr) >= MAX_CAPTURE_BYTES
    if timed_out or not started or not executable_stable or oversized:
        reason = (
            "project_test_process_timed_out" if timed_out
            else "project_test_process_not_started" if not started
            else "project_test_process_executable_drifted" if not executable_stable
            else "project_test_process_output_too_large"
        )
        return _blocked(
            invocation, invocation_sha256, reason, timed_out=timed_out,
            stdout=stdout, stderr=stderr,
        )
    signal = -returncode if returncode is not None and returncode < 0 else None
    exit_code = returncode if returncode is not None and returncode >= 0 else None
    return {
        "schema_version": 1, "artifact_kind": "project-test-process-result",
        "status": "completed", "reason_code": None,
        "invocation": invocation, "invocation_sha256": invocation_sha256,
        "exit_code": exit_code, "signal": signal,
        "timed_out": False, "oversized": False, "command_started": True,
        "stdout_sha256": canonical_sha256_bytes(stdout),
        "stderr_sha256": canonical_sha256_bytes(stderr),
        "stdout_size_bytes": len(stdout), "stderr_size_bytes": len(stderr),
        "launcher_argv_sha256": canonical_sha256(redacted_bubblewrap_argv(argv)),
        "_stdout": stdout, "_stderr": stderr,
    }


def canonical_sha256_bytes(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()


def public_process_result(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: item for key, item in value.items() if not key.startswith("_")}
    invocation = result.get("invocation")
    if isinstance(invocation, Mapping):
        result["invocation"] = {
            "schema_version": invocation.get("schema_version"),
            "purpose": invocation.get("purpose"),
            "executable_sha256": invocation.get("executable_sha256"),
            "input_sha256": invocation.get("input_sha256"),
            "argument_count": len(invocation.get("arguments", [])),
            "environment_names": sorted(invocation.get("environment", {})),
            "stdin_sha256": invocation.get("stdin_sha256"),
            "stdin_size_bytes": invocation.get("stdin_size_bytes"),
            "working_directory": invocation.get("working_directory"),
            "timeout_seconds": invocation.get("timeout_seconds"),
            "sandbox_contract_sha256": invocation.get("sandbox_contract_sha256"),
            "sandbox_probe_receipt_sha256": invocation.get("sandbox_probe_receipt_sha256"),
        }
    return result


def _validate_inputs(
    subject: Path, project: Path, output: Path, arguments: Sequence[str],
    working_directory: str, environment: Mapping[str, str], timeout_seconds: int,
    standard_input: bytes,
) -> None:
    if (
        not subject.is_file() or is_linklike(subject)
        or not 0 < subject.stat().st_size <= MAX_SUBJECT_BYTES
        or not project.is_dir() or is_linklike(project)
        or output.exists() or not 1 <= timeout_seconds <= 3_600
    ):
        raise ValueError("project_test_process_input_invalid")
    if not isinstance(arguments, Sequence) or isinstance(arguments, (str, bytes)):
        raise ValueError("project_test_process_arguments_invalid")
    if len(arguments) > 128 or any(
        not isinstance(item, str) or "\x00" in item
        or len(item.encode("utf-8")) > 4096 for item in arguments
    ):
        raise ValueError("project_test_process_arguments_invalid")
    path = PurePosixPath(working_directory)
    host_working = project / Path(*path.parts)
    if (
        path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts)
        or not host_working.is_dir() or is_linklike(host_working)
    ):
        raise ValueError("project_test_process_working_directory_invalid")
    if len(environment) > 128 or any(
        not isinstance(key, str) or _ENVIRONMENT_NAME.fullmatch(key) is None
        or not isinstance(value, str) or "\x00" in value
        or len((key + value).encode("utf-8")) > 8192
        for key, value in environment.items()
    ):
        raise ValueError("project_test_process_environment_invalid")
    if not isinstance(standard_input, bytes) or len(standard_input) > MAX_PROJECT_TEST_STDIN_BYTES:
        raise ValueError("project_test_process_stdin_invalid")
    output.mkdir(parents=True, mode=0o700)


def _environment_assignments(environment: Mapping[str, str]) -> tuple[str, ...]:
    fixed = {
        "HOME": "/runtime/home", "TMPDIR": "/runtime/tmp",
        "TMP": "/runtime/tmp", "TEMP": "/runtime/tmp",
        "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PATH": "/usr/bin:/bin",
    }
    if set(fixed) & set(environment):
        raise ValueError("project_test_process_reserved_environment")
    combined = {**fixed, **environment}
    return tuple(f"{key}={combined[key]}" for key in sorted(combined))


def _guest_working_directory(relative: str) -> str:
    return "/workspace/" + "/".join(PurePosixPath(relative).parts)


def _marker_matches(path: Path, contract_sha256: str, invocation_sha256: str) -> bool:
    try:
        return path.read_text(encoding="ascii") == f"{contract_sha256}\n{invocation_sha256}\n"
    except (OSError, UnicodeError):
        return False


def _read_capture(path: Path) -> bytes:
    try:
        with path.open("rb") as stream:
            return stream.read(MAX_CAPTURE_BYTES)
    except OSError:
        return b""


def _blocked(
    invocation: Mapping[str, Any], invocation_sha256: str, reason: str,
    *, timed_out: bool = False, stdout: bytes = b"", stderr: bytes = b"",
) -> dict[str, Any]:
    return {
        "schema_version": 1, "artifact_kind": "project-test-process-result",
        "status": "blocked", "reason_code": reason,
        "invocation": dict(invocation), "invocation_sha256": invocation_sha256,
        "exit_code": None, "signal": None, "timed_out": timed_out,
        "oversized": len(stdout) >= MAX_CAPTURE_BYTES or len(stderr) >= MAX_CAPTURE_BYTES,
        "command_started": False,
        "stdout_sha256": canonical_sha256_bytes(stdout),
        "stderr_sha256": canonical_sha256_bytes(stderr),
        "stdout_size_bytes": len(stdout), "stderr_size_bytes": len(stderr),
        "_stdout": stdout, "_stderr": stderr,
    }


__all__ = [
    "execute_isolated_project_test_process", "public_process_result",
]
