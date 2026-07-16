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
from .meson_schema_common import MesonSchemaError, strict_json
from .project_test_inventory_meson_binding import (
    MAX_MESON_TEST_OUTPUT_BYTES, MAX_MESON_TEST_STDERR_BYTES,
    MESON_TEST_ADAPTER, capture_meson_test_build_binding,
)
from .project_test_inventory_sandbox import (
    canonical_project_tool_environment, restrict_project_tool_environment,
)
from .sandbox_bubblewrap_argv import build_bubblewrap_argv, resource_limiter
from .sandbox_contract import SandboxContract
from .sandbox_requirements import strict_sandbox_requirements


MAX_MESON_TOOL_BYTES = 64 * 1024 * 1024


def collect_meson_test_introspection(
    repo_root: Path, build_directory: Path, compile_database_path: Path,
    *, timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Read Meson's JSON test model without compiling or executing tests."""
    if (
        isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int)
        or not 5 <= timeout_seconds <= 120
    ):
        raise ValueError("project_test_meson_timeout_invalid")
    meson_value, bwrap_value = shutil.which("meson"), shutil.which("bwrap")
    if sys.platform != "linux" or not meson_value or not bwrap_value:
        return _blocked("project_test_meson_sandbox_unavailable")
    try:
        root = Path(repo_root).resolve(strict=True)
        build = Path(build_directory).resolve(strict=True)
        database = Path(compile_database_path).resolve(strict=True)
        build.relative_to(root)
        if database.parent != build:
            raise ValueError("compile database does not bind build directory")
        meson = Path(meson_value).resolve(strict=True)
        bwrap = Path(bwrap_value).resolve(strict=True)
        tool, launcher = _file_identity(meson), _file_identity(bwrap)
        contract = _sandbox_contract(tool, launcher, timeout_seconds)
        before, expected_payload = capture_meson_test_build_binding(root, database)
        relative_build = str(before["build_directory"])
    except (OSError, TypeError, ValueError):
        return _blocked("project_test_meson_input_invalid")
    temporary = Path(tempfile.mkdtemp(prefix="project-test-meson-"))
    runtime = temporary / "runtime"
    guest_build = (
        "/workspace" if relative_build == "."
        else "/workspace/" + relative_build
    )
    command = ["meson", "introspect", "--tests", relative_build]
    try:
        runtime.mkdir(mode=0o700)
        argv = build_bubblewrap_argv(
            launcher=bwrap, workspace=root, runtime=runtime,
            tool_bindings=((meson, "/toolchain/bin/meson"),),
            environment=canonical_project_tool_environment(),
            guest_command=(
                "/toolchain/bin/meson", "introspect", "--tests", guest_build,
            ),
            guest_working_directory="/workspace",
        )
        argv = restrict_project_tool_environment(argv)
    except (OSError, ValueError):
        shutil.rmtree(temporary, ignore_errors=True)
        return _blocked("project_test_meson_execution_unavailable")
    completed: subprocess.CompletedProcess[bytes] | None = None
    failure: str | None = None
    stdout_path, stderr_path = temporary / "stdout", temporary / "stderr"
    stdout = stderr = b""
    try:
        with stdout_path.open("wb") as stdout_stream, stderr_path.open("wb") as stderr_stream:
            completed = subprocess.run(
                argv, cwd=temporary, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                stdin=subprocess.DEVNULL, stdout=stdout_stream, stderr=stderr_stream,
                timeout=timeout_seconds, check=False, shell=False,
                preexec_fn=resource_limiter(contract),
            )
        stdout, stdout_flooded = _bounded_output(
            stdout_path, MAX_MESON_TEST_OUTPUT_BYTES,
        )
        stderr, stderr_flooded = _bounded_output(
            stderr_path, MAX_MESON_TEST_STDERR_BYTES,
        )
        if stdout_flooded or stderr_flooded:
            failure = "project_test_meson_output_limit_exceeded"
    except subprocess.TimeoutExpired:
        failure = "project_test_meson_timeout"
    except (OSError, subprocess.SubprocessError):
        failure = "project_test_meson_execution_unavailable"
    if failure is None and completed is not None and completed.returncode != 0:
        failure = "project_test_meson_execution_failed"
    payload: Any = None
    if failure is None:
        try:
            payload = strict_json(stdout, "tests")
            after, current_payload = capture_meson_test_build_binding(root, database)
            if (
                not isinstance(payload, list) or payload != expected_payload
                or current_payload != expected_payload or after != before
            ):
                raise ValueError("Meson introspection drifted")
        except (MesonSchemaError, OSError, TypeError, ValueError):
            failure = "project_test_meson_json_invalid"
    shutil.rmtree(temporary, ignore_errors=True)
    if temporary.exists():
        return _blocked("project_test_meson_cleanup_failed")
    if failure is not None or completed is None or not isinstance(payload, list):
        return _blocked(failure or "project_test_meson_execution_unavailable")
    observation = {
        "schema_version": 1,
        "artifact_kind": "meson-introspect-tests-v1-observation",
        "adapter_version": MESON_TEST_ADAPTER,
        "command": command,
        "build_directory": relative_build,
        "build_binding": before,
        "tool": tool,
        "sandbox_launcher": launcher,
        "sandbox_contract": contract.payload(),
        "sandbox_contract_sha256": contract.sha256,
        "timeout_seconds": timeout_seconds,
        "returncode": 0,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stdout_size_bytes": len(stdout),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_size_bytes": len(stderr),
        "payload": payload,
        "payload_sha256": content_sha256(payload),
        "tests_executed": False,
        "semantic_gate": False,
    }
    observation["observation_sha256"] = content_sha256(observation)
    return {"status": "collected", "observation": observation}


def _sandbox_contract(
    tool: Mapping[str, Any], launcher: Mapping[str, Any], timeout_seconds: int,
) -> SandboxContract:
    requirements = strict_sandbox_requirements(
        cpu_seconds=timeout_seconds,
        address_space_bytes=1024 * 1024 * 1024,
        file_size_bytes=MAX_MESON_TEST_OUTPUT_BYTES,
        process_count=32,
        open_files=128,
    )
    return SandboxContract(
        backend="bubblewrap-v1", launcher_sha256=str(launcher["sha256"]),
        toolchain_sha256=str(tool["sha256"]), requirements=requirements,
    )


def _file_identity(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    if not path.is_file() or not 0 < size <= MAX_MESON_TOOL_BYTES:
        raise ValueError("project_test_meson_tool_invalid")
    digest = hashlib.sha256()
    observed = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            observed += len(chunk)
            if observed > size:
                raise ValueError("project_test_meson_tool_drifted")
            digest.update(chunk)
    if observed != size or path.stat().st_size != size:
        raise ValueError("project_test_meson_tool_drifted")
    return {
        "basename": path.name, "sha256": digest.hexdigest(),
        "size_bytes": size,
    }


def _bounded_output(path: Path, limit: int) -> tuple[bytes, bool]:
    size = path.stat().st_size
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    return data, size > limit or len(data) > limit


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = ["collect_meson_test_introspection"]
