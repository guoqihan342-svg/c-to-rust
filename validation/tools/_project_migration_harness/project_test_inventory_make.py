from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import content_sha256
from .build_facts import resolve_repository_path
from .project_test_inventory_make_parse import (
    MAKE_COMMAND, MAX_STDERR_BYTES, MAX_STDOUT_BYTES, derive_make_inventory,
)
from .sandbox_bubblewrap_argv import build_bubblewrap_argv, resource_limiter
from .sandbox_contract import SandboxContract
from .sandbox_requirements import strict_sandbox_requirements
from .project_test_inventory_sandbox import (
    canonical_project_tool_environment, restrict_project_tool_environment,
)


def collect_make_test_dry_run(
    repo_root: Path, build_directory: Path, timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Observe `make -n test` inside a read-only Linux bubblewrap sandbox."""
    if (
        isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int)
        or not 5 <= timeout_seconds <= 120
    ):
        raise ValueError("project_test_make_timeout_invalid")
    make_value, bwrap_value = shutil.which("make"), shutil.which("bwrap")
    if sys.platform != "linux" or not make_value or not bwrap_value:
        return _blocked("project_test_make_sandbox_unavailable")
    try:
        root = Path(repo_root).resolve(strict=True)
        build = resolve_repository_path(root, build_directory)
        if not root.is_dir() or not build.is_dir():
            raise ValueError("project test root is invalid")
        relative_build = build.relative_to(root).as_posix() or "."
        make = Path(make_value).resolve(strict=True)
        bwrap = Path(bwrap_value).resolve(strict=True)
        tool, launcher = _file_identity(make), _file_identity(bwrap)
        contract = _sandbox_contract(tool, launcher, timeout_seconds)
    except (OSError, TypeError, ValueError):
        return _blocked("project_test_make_input_invalid")
    temporary = Path(tempfile.mkdtemp(prefix="project-test-make-"))
    runtime = temporary / "runtime"
    guest_build = "/workspace" if relative_build == "." else f"/workspace/{relative_build}"
    try:
        runtime.mkdir(mode=0o700)
        argv = build_bubblewrap_argv(
            launcher=bwrap, workspace=root, runtime=runtime,
            tool_bindings=((make, "/toolchain/bin/make"),),
            environment=canonical_project_tool_environment(),
            guest_command=("/toolchain/bin/make", *MAKE_COMMAND[1:]),
            guest_working_directory=guest_build,
        )
        argv = restrict_project_tool_environment(argv)
    except (OSError, ValueError):
        shutil.rmtree(temporary, ignore_errors=True)
        return _blocked("project_test_make_execution_unavailable")
    completed: subprocess.CompletedProcess[bytes] | None = None
    failure: str | None = None
    stdout_path, stderr_path = temporary / "stdout", temporary / "stderr"
    stdout = stderr = b""
    try:
        with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
            completed = subprocess.run(
                argv, cwd=temporary, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                stdout=stdout_stream, stderr=stderr_stream,
                timeout=timeout_seconds, check=False, shell=False,
                preexec_fn=resource_limiter(contract),
            )
        stdout, stdout_flooded = _bounded_output(stdout_path, MAX_STDOUT_BYTES)
        stderr, stderr_flooded = _bounded_output(stderr_path, MAX_STDERR_BYTES)
        if stdout_flooded or stderr_flooded:
            failure = "project_test_make_output_limit_exceeded"
    except subprocess.TimeoutExpired:
        failure = "project_test_make_timeout"
    except (OSError, subprocess.SubprocessError):
        failure = "project_test_make_execution_unavailable"
    finally:
        shutil.rmtree(temporary, ignore_errors=True)
    if temporary.exists():
        return _blocked("project_test_make_cleanup_failed")
    if failure is not None or completed is None:
        return _blocked(failure or "project_test_make_execution_unavailable")
    if completed.returncode != 0:
        return _blocked("project_test_make_execution_failed")
    try:
        text = stdout.decode("utf-8", errors="strict")
    except UnicodeError:
        return _blocked("project_test_make_stdout_invalid")
    observation = {
        "schema_version": 1, "artifact_kind": "make-dry-run-v1-observation",
        "command": list(MAKE_COMMAND), "build_directory": relative_build,
        "tool": tool, "sandbox_launcher": launcher,
        "timeout_seconds": timeout_seconds, "returncode": 0, "stdout": text,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stdout_size_bytes": len(stdout),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_size_bytes": len(stderr), "semantic_gate": False,
    }
    observation["observation_sha256"] = content_sha256(observation)
    return {"status": "collected", "observation": observation}


def inventory_from_make_observation(
    repo_root: Path, build_ir: Mapping[str, Any], observation: Mapping[str, Any],
    *, source_observation: Mapping[str, Any],
) -> dict[str, Any]:
    return derive_make_inventory(
        repo_root, build_ir, observation, source_observation=source_observation,
    )


def _sandbox_contract(
    tool: Mapping[str, Any], launcher: Mapping[str, Any], timeout_seconds: int,
) -> SandboxContract:
    requirements = strict_sandbox_requirements(
        cpu_seconds=timeout_seconds,
        address_space_bytes=2 * 1024 * 1024 * 1024,
        file_size_bytes=MAX_STDOUT_BYTES,
        process_count=64,
        open_files=256,
    )
    return SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256=str(launcher["sha256"]),
        toolchain_sha256=str(tool["sha256"]),
        requirements=requirements,
    )


def _file_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "basename": path.name, "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _bounded_output(path: Path, limit: int) -> tuple[bytes, bool]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    return data, size > limit or len(data) > limit


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = ["collect_make_test_dry_run", "inventory_from_make_observation"]
