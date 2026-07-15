from __future__ import annotations

from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .integration_generation import (
    GenerationCommitError,
    generation_store_root,
    recover_current_generation,
)
from .integration_validation import existing_state
from .sandbox_contract import (
    validate_contract,
)
from .sandbox_linux import discover_sandbox_backend
from .sandbox_probe import (
    SandboxProbeReceipt, validate_probe_receipt,
)
from .project_verification_execution import (
    MAX_OUTPUT_BYTES,
    blocked_result as _blocked,
    environment_policy as _environment_policy,
    run_cargo_check as _run,
    sandbox_evidence as _sandbox_evidence,
)


SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def run_cargo_project_gates(
    project_root: Path, *, runtime_root: Path, cargo_command: str = "cargo",
    timeout_seconds: int = 300, capture_raw_output: bool = False,
    capture_native_link_trace: bool = False,
) -> dict[str, Any]:
    if timeout_seconds < 30 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    if capture_native_link_trace and not capture_raw_output:
        raise ValueError("native linker trace requires raw Cargo output capture")
    project = _project_target(project_root)
    try:
        source = _current_managed_source(project)
    except GenerationCommitError as error:
        return _blocked(
            "generation_recovery_blocked",
            project_input_sha256=None,
            detail=error.code,
        )
    return _run_managed_cargo(
        source, project, runtime_root, cargo_command, timeout_seconds,
        capture_raw_output, capture_native_link_trace,
    )


def run_cargo_generation_gates(
    generation_root: Path, *, runtime_root: Path, cargo_command: str = "cargo",
    timeout_seconds: int = 300, capture_raw_output: bool = False,
) -> dict[str, Any]:
    if timeout_seconds < 30 or timeout_seconds > 3_600:
        raise ValueError("timeout_seconds must be between 30 and 3600")
    source = _project_target(generation_root).resolve(strict=True)
    return _run_managed_cargo(
        source, source, runtime_root, cargo_command, timeout_seconds,
        capture_raw_output, False,
    )


def managed_project_input_sha256(project_root: Path) -> str:
    project = _project_target(project_root)
    source = _current_managed_source(project)
    state, managed = existing_state(source)
    if not managed or not isinstance(state, str) or SHA256.fullmatch(state) is None:
        raise ValueError(
            "Cargo project must be a managed last-good reconstruction with a SHA-256 state"
        )
    return state


def _run_managed_cargo(
    source: Path, project: Path, runtime_root: Path,
    cargo_command: str, timeout_seconds: int, capture_raw_output: bool,
    capture_native_link_trace: bool,
) -> dict[str, Any]:
    before, managed = existing_state(source)
    if not managed:
        raise ValueError("Cargo project must be a managed last-good reconstruction")
    runtime = _runtime_root(runtime_root, project, source)
    try:
        cargo = _cargo_binary(cargo_command)
    except (OSError, ValueError):
        return _blocked(
            "cargo_tool_unavailable",
            project_state=before,
            project_input_sha256=before,
        )
    discovery = discover_sandbox_backend(cargo, source)
    if discovery.backend is None:
        return _blocked(
            discovery.reason_code or "cargo_sandbox_unavailable",
            project_state=before,
            project_input_sha256=before,
        )
    backend = discovery.backend
    try:
        validate_contract(backend.contract)
    except ValueError:
        return _blocked(
            "sandbox_contract_invalid",
            project_state=before,
            project_input_sha256=before,
        )
    try:
        probe_receipt = discovery.probe_receipt
        if not isinstance(probe_receipt, SandboxProbeReceipt):
            raise ValueError("sandbox probe receipt is missing")
        validate_probe_receipt(
            probe_receipt, backend.contract, backend.contract.requirements,
        )
    except ValueError:
        return _blocked(
            "sandbox_capability_probe_invalid",
            project_state=before,
            project_input_sha256=before,
        )
    execution_root = Path(tempfile.mkdtemp(prefix="cargo-sandbox-", dir=runtime))
    checks = []
    try:
        for name in ("cargo-home", "target"):
            (execution_root / name).mkdir(mode=0o700)
        commands = [
            (["check", "--all-targets", "--all-features", "--offline", "--locked",
              "--message-format=json"], False),
            (["test", "--all-targets", "--all-features", "--offline", "--locked",
              "--message-format=json", *(
                  ["--jobs", "1"] if capture_native_link_trace else []
              )], capture_native_link_trace),
        ]
        for cargo_args, native_link_trace in commands:
            checks.append(_run(
                cargo, cargo_args, source, execution_root,
                timeout_seconds, backend, before, probe_receipt,
                capture_raw_output=capture_raw_output,
                native_link_trace=native_link_trace,
            ))
            if checks[-1]["status"] != "passed":
                break
        try:
            after, still_managed = existing_state(source)
        except ValueError:
            after, still_managed = "unreadable", False
    finally:
        cleanup_verified = _cleanup_execution_root(execution_root)
    unchanged = still_managed and after == before
    passed = cleanup_verified and unchanged and len(checks) == 2 and all(
        item["status"] == "passed" for item in checks
    )
    blocked = (
        not cleanup_verified or not unchanged
        or any(item["status"] == "blocked" for item in checks)
    )
    diagnostics = [
        diagnostic
        for check in checks if check["status"] == "blocked"
        for diagnostic in check.get("diagnostics", [])
    ]
    if not unchanged:
        diagnostics.append({
            "code": "managed_project_state_drift",
            "stage": "cargo-sandbox",
            "message": "Managed generation changed during sandboxed verification",
        })
    if not cleanup_verified:
        diagnostics.append({
            "code": "sandbox_cleanup_failed",
            "stage": "cargo-sandbox",
            "message": "Sandbox execution root could not be proven removed",
        })
    return {
        "schema_version": 1,
        "status": "passed" if passed else "blocked" if blocked else "failed",
        "cargo_executed": any(item["cargo_executed"] for item in checks),
        "project_input_sha256": before,
        "project_state_before": before,
        "project_state_after": after,
        "project_state_unchanged": unchanged,
        "checks": checks,
        "sandbox": _sandbox_evidence(
            backend.contract, "executed", cleanup_verified=cleanup_verified,
            probe_receipt=probe_receipt,
        ),
        "environment_policy": _environment_policy(),
        "diagnostics": diagnostics,
        "semantic_gate": False,
        "proof_boundary": "Sandboxed Cargo compile/test only; oracle and final verification remain separate",
    }


def _cleanup_execution_root(root: Path) -> bool:
    try:
        if _is_linklike(root):
            return False
        shutil.rmtree(root)
        return not root.exists()
    except OSError:
        return False


def _current_managed_source(project: Path) -> Path:
    generation = recover_current_generation(project)
    return generation or project.resolve(strict=True)


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


__all__ = [
    "managed_project_input_sha256",
    "run_cargo_generation_gates",
    "run_cargo_project_gates",
]
