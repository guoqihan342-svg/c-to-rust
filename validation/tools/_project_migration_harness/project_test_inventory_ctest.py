from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from .artifacts import content_sha256
from .sandbox_bubblewrap_argv import build_bubblewrap_argv


MAX_CTEST_OUTPUT_BYTES = 16 * 1024 * 1024
MAX_CTEST_STDERR_BYTES = 1024 * 1024


def collect_ctest_json(
    repo_root: Path, build_directory: Path, *, timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Collect CTest's stable JSON model without executing project tests."""
    if not 5 <= timeout_seconds <= 120:
        raise ValueError("project_test_ctest_timeout_invalid")
    ctest_value = shutil.which("ctest")
    bwrap_value = shutil.which("bwrap")
    if not ctest_value or not bwrap_value or os.name == "nt":
        return _blocked("project_test_ctest_sandbox_unavailable")
    try:
        root = repo_root.resolve(strict=True)
        build = build_directory.resolve(strict=True)
        build.relative_to(root)
        ctest = Path(ctest_value).resolve(strict=True)
        bwrap = Path(bwrap_value).resolve(strict=True)
        tool = _file_identity(ctest)
        launcher = _file_identity(bwrap)
    except (OSError, ValueError):
        return _blocked("project_test_ctest_input_invalid")
    runtime = Path(tempfile.mkdtemp(prefix="project-test-ctest-"))
    relative_build = build.relative_to(root).as_posix()
    guest_build = "/workspace" if relative_build == "." else f"/workspace/{relative_build}"
    command = ("/toolchain/bin/ctest", "--show-only=json-v1")
    argv = build_bubblewrap_argv(
        launcher=bwrap, workspace=root, runtime=runtime,
        tool_bindings=((ctest, "/toolchain/bin/ctest"),),
        environment=(("HOME", "/home/sandbox"), ("LANG", "C.UTF-8"),
                     ("LC_ALL", "C.UTF-8"), ("PATH", "/toolchain/bin:/usr/bin:/bin"),
                     ("TMPDIR", "/tmp")),
        guest_command=command,
    )
    boundary = argv.index("--chdir")
    argv[boundary + 1] = guest_build
    try:
        completed = subprocess.run(
            argv, cwd=runtime, env={"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            capture_output=True, timeout=timeout_seconds, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        shutil.rmtree(runtime, ignore_errors=True)
        return _blocked("project_test_ctest_execution_unavailable")
    finally:
        cleanup_target = runtime
    stdout, stderr = completed.stdout, completed.stderr
    shutil.rmtree(cleanup_target, ignore_errors=True)
    if runtime.exists():
        return _blocked("project_test_ctest_cleanup_failed")
    if (
        completed.returncode != 0
        or len(stdout) > MAX_CTEST_OUTPUT_BYTES
        or len(stderr) > MAX_CTEST_STDERR_BYTES
    ):
        return _blocked("project_test_ctest_execution_failed")
    try:
        payload = json.loads(stdout.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        return _blocked("project_test_ctest_json_invalid")
    if not isinstance(payload, dict):
        return _blocked("project_test_ctest_json_invalid")
    evidence = {
        "schema_version": 1,
        "artifact_kind": "ctest-json-v1-observation",
        "command": ["ctest", "--show-only=json-v1"],
        "build_directory": relative_build,
        "tool": tool,
        "sandbox_launcher": launcher,
        "returncode": completed.returncode,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stdout_size_bytes": len(stdout),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stderr_size_bytes": len(stderr),
        "payload": payload,
        "semantic_gate": False,
    }
    evidence["observation_sha256"] = content_sha256(evidence)
    return {"status": "collected", "observation": evidence}


def _file_identity(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "basename": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def _blocked(code: str) -> dict[str, Any]:
    return {"status": "blocked", "blocker": {"code": code}}


__all__ = ["collect_ctest_json"]
