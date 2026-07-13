from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from .integration_generation import (
    GenerationCommitError,
    generation_store_root,
    recover_current_generation,
)
from .integration_validation import existing_state
from .sandbox_contract import (
    SandboxBackend,
    SandboxContract,
    validate_contract,
    validate_run_result,
)
from .sandbox_diagnostics import cargo_diagnostics
from .sandbox_linux import discover_sandbox_backend


MAX_OUTPUT_BYTES = 1024 * 1024


def run_cargo_project_gates(
    project_root: Path, *, runtime_root: Path, cargo_command: str = "cargo",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if timeout_seconds < 30 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    project = _project_target(project_root)
    try:
        generation = recover_current_generation(project)
    except GenerationCommitError as error:
        return _blocked("generation_recovery_blocked", detail=error.code)
    source = generation or project.resolve(strict=True)
    return _run_managed_cargo(
        source, project, runtime_root, cargo_command, timeout_seconds,
    )


def run_cargo_generation_gates(
    generation_root: Path, *, runtime_root: Path, cargo_command: str = "cargo",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    if timeout_seconds < 30 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    source = _project_target(generation_root).resolve(strict=True)
    return _run_managed_cargo(
        source, source, runtime_root, cargo_command, timeout_seconds,
    )


def _run_managed_cargo(
    source: Path, project: Path, runtime_root: Path,
    cargo_command: str, timeout_seconds: int,
) -> dict[str, Any]:
    before, managed = existing_state(source)
    if not managed:
        raise ValueError("Cargo project must be a managed last-good reconstruction")
    runtime = _runtime_root(runtime_root, project, source)
    try:
        cargo = _cargo_binary(cargo_command)
    except (OSError, ValueError):
        return _blocked("cargo_tool_unavailable", project_state=before)
    discovery = discover_sandbox_backend(cargo, source)
    if discovery.backend is None:
        return _blocked(
            discovery.reason_code or "cargo_sandbox_unavailable",
            project_state=before,
        )
    backend = discovery.backend
    try:
        validate_contract(backend.contract)
    except ValueError:
        return _blocked("sandbox_contract_invalid", project_state=before)
    execution_root = Path(tempfile.mkdtemp(prefix="cargo-sandbox-", dir=runtime))
    for name in ("cargo-home", "target"):
        (execution_root / name).mkdir(mode=0o700)
    commands = [
        ["check", "--all-targets", "--offline", "--locked", "--message-format=json"],
        ["test", "--all-targets", "--offline", "--locked", "--message-format=json"],
    ]
    checks = []
    for cargo_args in commands:
        checks.append(_run(cargo, cargo_args, source, execution_root, timeout_seconds, backend))
        if checks[-1]["status"] != "passed":
            break
    try:
        after, still_managed = existing_state(source)
    except ValueError:
        after, still_managed = "unreadable", False
    unchanged = still_managed and after == before
    passed = unchanged and len(checks) == 2 and all(
        item["status"] == "passed" for item in checks
    )
    return {
        "schema_version": 1,
        "status": "passed" if passed else "failed",
        "cargo_executed": any(item["cargo_executed"] for item in checks),
        "project_state_before": before,
        "project_state_after": after,
        "project_state_unchanged": unchanged,
        "checks": checks,
        "sandbox": _sandbox_evidence(backend.contract, "executed"),
        "environment_policy": _environment_policy(),
        "diagnostics": [] if unchanged else [{
            "code": "managed_project_state_drift",
            "stage": "cargo-sandbox",
            "message": "Managed generation changed during sandboxed verification",
        }],
        "semantic_gate": False,
        "proof_boundary": "Sandboxed Cargo compile/test only; oracle and final verification remain separate",
    }


def _run(
    cargo: Path, cargo_args: list[str], project: Path, runtime: Path,
    timeout_seconds: int, backend: SandboxBackend,
) -> dict[str, Any]:
    command = ["cargo", *cargo_args]
    stage = f"cargo-{cargo_args[0]}"
    try:
        result = backend.execute(
            cargo, cargo_args, project_root=project, runtime_root=runtime,
            timeout_seconds=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _execution_failure(command, stage, "cargo_timeout", timed_out=True)
    except (OSError, ValueError, subprocess.SubprocessError):
        return _execution_failure(command, stage, "sandbox_execution_rejected")
    try:
        validate_run_result(result, backend.contract, command)
    except ValueError:
        code = "sandbox_command_not_started" if not result.command_started else "sandbox_contract_mismatch"
        return _execution_failure(command, stage, code)
    stdout = _text(result.completed.stdout)
    stderr = _text(result.completed.stderr)
    stdout_bytes = stdout.encode("utf-8")
    stderr_bytes = stderr.encode("utf-8")
    oversized = len(stdout_bytes) > MAX_OUTPUT_BYTES or len(stderr_bytes) > MAX_OUTPUT_BYTES
    returncode = int(result.completed.returncode)
    diagnostics = cargo_diagnostics(stdout, cargo_args[0])
    if returncode != 0 and not diagnostics:
        diagnostics = [{
            "code": "cargo_command_failed",
            "stage": stage,
            "message": f"cargo {cargo_args[0]} exited with code {returncode}",
        }]
    if oversized:
        diagnostics = [{
            "code": "cargo_output_too_large",
            "stage": stage,
            "message": "Cargo output exceeded the bounded capture size",
        }]
    return {
        "command": command,
        "status": "passed" if returncode == 0 and not oversized else "failed",
        "returncode": returncode,
        "timed_out": False,
        "cargo_executed": True,
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "sandbox_contract_sha256": result.contract_sha256,
        "sandbox_command_sha256": result.command_sha256,
        "sandbox_launcher_argv_sha256": result.launcher_argv_sha256,
        "diagnostics": diagnostics[:64],
    }


def _execution_failure(
    command: list[str], stage: str, code: str, *, timed_out: bool = False,
) -> dict[str, Any]:
    return {
        "command": command,
        "status": "failed",
        "returncode": 124 if timed_out else None,
        "timed_out": timed_out,
        "cargo_executed": False,
        "stdout_sha256": hashlib.sha256(b"").hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "diagnostics": [{
            "code": code,
            "stage": stage,
            "message": "Cargo execution was not proven inside the required sandbox",
        }],
    }


def _blocked(
    code: str, *, project_state: str = "unavailable", detail: str | None = None,
) -> dict[str, Any]:
    diagnostic = {
        "code": code,
        "stage": "cargo-sandbox",
        "message": "Required OS isolation is unavailable; candidate code was not executed",
    }
    if detail:
        diagnostic["detail_code"] = detail[:96]
    return {
        "schema_version": 1,
        "status": "blocked",
        "cargo_executed": False,
        "project_state_before": project_state,
        "project_state_after": project_state,
        "project_state_unchanged": True,
        "checks": [],
        "sandbox": {"status": "blocked", "reason_code": code},
        "environment_policy": _environment_policy(),
        "diagnostics": [diagnostic],
        "semantic_gate": False,
        "proof_boundary": "No Cargo claim without supported OS isolation",
    }


def _sandbox_evidence(contract: SandboxContract, status: str) -> dict[str, Any]:
    return {
        "status": status,
        "contract": contract.payload(),
        "contract_sha256": contract.sha256,
    }


def _environment_policy() -> dict[str, Any]:
    return {
        "network": "namespace-unshared",
        "locked": True,
        "cargo_offline_is_supplementary": True,
        "project_input_read_only": True,
        "isolated_cargo_home": True,
        "isolated_target_dir": True,
        "isolated_home": True,
        "isolated_tmp": True,
        "resource_limits": True,
    }


def _project_target(value: Path) -> Path:
    requested = Path(value).expanduser()
    if requested.name in {"", ".", ".."} or _is_linklike(requested):
        raise ValueError("project_root is invalid")
    parent = requested.parent.resolve(strict=True)
    return parent / requested.name


def _runtime_root(value: Path, project: Path, source: Path) -> Path:
    requested = Path(value).expanduser()
    if _is_linklike(requested):
        raise ValueError("runtime_root must not be a link")
    requested.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime = requested.resolve(strict=True)
    protected = (project, source, generation_store_root(project))
    if any(_overlaps(runtime, item.resolve()) for item in protected if item.exists()):
        raise ValueError("runtime_root must not overlap managed project state")
    return runtime


def _overlaps(left: Path, right: Path) -> bool:
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def _is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


def _cargo_binary(value: str) -> Path:
    if (
        not isinstance(value, str)
        or value.lower() not in {"cargo", "cargo.exe"}
        or Path(value).name != value
        or any(char in value for char in "\r\n\x00")
    ):
        raise ValueError("cargo_command is invalid")
    resolved = shutil.which(value)
    if not resolved:
        raise ValueError("cargo_command is unavailable")
    path = Path(resolved).resolve(strict=True)
    if path.name.lower() not in {"cargo", "cargo.exe", "rustup", "rustup.exe"} or not path.is_file():
        raise ValueError("cargo_command must resolve to Cargo")
    return path


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


__all__ = ["run_cargo_generation_gates", "run_cargo_project_gates"]
