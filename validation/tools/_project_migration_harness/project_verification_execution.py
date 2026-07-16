from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any

from .cargo_output_limits import MAX_CARGO_STREAM_BYTES
from .sandbox_contract import (
    SandboxBackend,
    SandboxContract,
    validate_run_result,
)
from .sandbox_diagnostics import cargo_check_diagnostics
from .sandbox_probe import SandboxProbeReceipt
from .sandbox_requirements import cargo_verification_plan


MAX_OUTPUT_BYTES = MAX_CARGO_STREAM_BYTES


def run_cargo_check(
    cargo: Path, cargo_args: list[str], project: Path, runtime: Path,
    timeout_seconds: int, backend: SandboxBackend, input_sha256: str,
    probe_receipt: SandboxProbeReceipt,
    *, capture_raw_output: bool = False, native_link_trace: bool = False,
) -> dict[str, Any]:
    command = ["cargo", *cargo_args]
    stage = f"cargo-{cargo_args[0]}"
    plan = cargo_verification_plan(
        stage, tuple(command), input_sha256,
        timeout_seconds=timeout_seconds,
        requirements=backend.contract.requirements,
        native_link_trace=native_link_trace,
    )
    try:
        result = backend.execute(
            cargo, cargo_args, project_root=project, runtime_root=runtime,
            verification_plan=plan, probe_receipt=probe_receipt,
        )
    except subprocess.TimeoutExpired:
        return _execution_failure(command, stage, "cargo_timeout", timed_out=True)
    except (OSError, ValueError, subprocess.SubprocessError):
        return _execution_failure(command, stage, "sandbox_execution_rejected")
    try:
        validate_run_result(result, backend.contract, plan, probe_receipt)
    except ValueError:
        code = (
            "sandbox_command_not_started"
            if not result.command_started
            else "sandbox_contract_mismatch"
        )
        return _execution_failure(command, stage, code)
    stdout_bytes = _raw_bytes(result.completed.stdout)
    stderr_bytes = _raw_bytes(result.completed.stderr)
    oversized = (
        len(stdout_bytes) > MAX_OUTPUT_BYTES
        or len(stderr_bytes) > MAX_OUTPUT_BYTES
    )
    returncode = int(result.completed.returncode)
    try:
        stdout = stdout_bytes.decode("utf-8", errors="strict")
        stderr_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        invalid_utf8 = True
        stdout = ""
    else:
        invalid_utf8 = False
    diagnostics = cargo_check_diagnostics(stdout, cargo_args[0], returncode)
    if oversized:
        diagnostics = [{
            "code": "cargo_output_too_large",
            "stage": stage,
            "message": "Cargo output exceeded the bounded capture size",
        }]
    elif invalid_utf8:
        diagnostics = [{
            "code": "cargo_output_invalid_utf8",
            "stage": stage,
            "message": "Cargo output was not valid UTF-8",
        }]
    output = {
        "command": command,
        "status": (
            "blocked" if oversized or invalid_utf8
            else "passed" if returncode == 0 else "failed"
        ),
        "returncode": returncode,
        "timed_out": False,
        "cargo_executed": True,
        "stdout_sha256": hashlib.sha256(stdout_bytes).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr_bytes).hexdigest(),
        "stdout_ref": None,
        "stderr_ref": None,
        "sandbox_contract_sha256": result.contract_sha256,
        "sandbox_command_sha256": result.command_sha256,
        "sandbox_command_started": bool(result.command_started),
        "sandbox_launcher_argv_sha256": result.launcher_argv_sha256,
        "sandbox_requirements_sha256": result.requirements_sha256,
        "sandbox_verification_plan": plan.payload(),
        "sandbox_verification_plan_sha256": result.verification_plan_sha256,
        "sandbox_probe_receipt_sha256": result.probe_receipt_sha256,
        "diagnostics": diagnostics[:64],
    }
    if capture_raw_output and not oversized:
        output["_captured_stdout"] = stdout_bytes
        output["_captured_stderr"] = stderr_bytes
    return output


def blocked_result(
    code: str, *, project_state: str = "unavailable",
    project_input_sha256: str | None = None, detail: str | None = None,
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
        "project_input_sha256": project_input_sha256,
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


def sandbox_evidence(
    contract: SandboxContract, status: str, *, cleanup_verified: bool,
    probe_receipt: SandboxProbeReceipt,
) -> dict[str, Any]:
    return {
        "status": status,
        "contract": contract.payload(),
        "contract_sha256": contract.sha256,
        "cleanup_verified": cleanup_verified,
        "probe_receipt": probe_receipt.payload(),
        "probe_receipt_sha256": probe_receipt.sha256,
    }


def environment_policy() -> dict[str, Any]:
    return _environment_policy()


def _execution_failure(
    command: list[str], stage: str, code: str, *, timed_out: bool = False,
) -> dict[str, Any]:
    return {
        "command": command,
        "status": "blocked",
        "returncode": 124 if timed_out else None,
        "timed_out": timed_out,
        "cargo_executed": False,
        "stdout_sha256": hashlib.sha256(b"").hexdigest(),
        "stderr_sha256": hashlib.sha256(b"").hexdigest(),
        "stdout_ref": None,
        "stderr_ref": None,
        "diagnostics": [{
            "code": code,
            "stage": stage,
            "message": "Cargo execution was not proven inside the required sandbox",
        }],
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
        "exit_cleanup_required": True,
    }


def _raw_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8") if isinstance(value, str) else b""


__all__ = [
    "MAX_OUTPUT_BYTES", "blocked_result", "environment_policy",
    "run_cargo_check", "sandbox_evidence",
]
